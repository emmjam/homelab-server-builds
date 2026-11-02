"""Durable conversations and one-use approvals. No model or infrastructure calls."""
from contextlib import contextmanager
import hashlib
import json
import sqlite3
import time
import uuid


class ConversationError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Store:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = path, clock
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, conversation TEXT NOT NULL,
                    request_id TEXT NOT NULL, content TEXT NOT NULL,
                    created REAL NOT NULL, status TEXT NOT NULL,
                    UNIQUE(conversation, request_id));
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, conversation TEXT NOT NULL,
                    created REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY, conversation TEXT NOT NULL,
                    proposal TEXT NOT NULL, proposal_hash TEXT NOT NULL,
                    expires REAL NOT NULL, status TEXT NOT NULL,
                    execution_id INTEGER, verification_id INTEGER,
                    updated REAL NOT NULL);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def require_conversation(self, db, conversation):
        if not db.execute('SELECT 1 FROM conversations WHERE id=?', (conversation,)).fetchone():
            raise ConversationError('Unknown conversation', 404)

    def create(self):
        result = {'id': str(uuid.uuid4()), 'created': self.clock()}
        with self.db() as db:
            db.execute('INSERT INTO conversations VALUES (?,?)', (result['id'], result['created']))
        return result

    def message(self, conversation, request_id, content):
        try:
            if str(uuid.UUID(request_id)) != request_id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ConversationError('Expected canonical UUID request_id', 400) from None
        if not isinstance(content, str) or not content.strip() or len(content) > 2048:
            raise ConversationError('Message must contain 1 to 2048 characters', 400)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.require_conversation(db, conversation)
            row = db.execute('SELECT * FROM messages WHERE conversation=? AND request_id=?',
                             (conversation, request_id)).fetchone()
            if row:
                if row['content'] != content:
                    raise ConversationError('Request ID already used with different content')
                return dict(row), False
            if db.execute("SELECT 1 FROM messages WHERE conversation=? AND status='processing'",
                          (conversation,)).fetchone():
                raise ConversationError('Conversation already has an active request')
            result = dict(id=str(uuid.uuid4()), conversation=conversation, request_id=request_id,
                          content=content, created=self.clock(), status='processing')
            db.execute('INSERT INTO messages VALUES (:id,:conversation,:request_id,:content,:created,:status)', result)
        return result, True

    def event(self, conversation, kind, data):
        # Caller must redact and bound evidence before passing it to storage.
        encoded = canonical(data)
        if len(encoded) > 16384:
            raise ConversationError('Event exceeds storage limit', 400)
        with self.db() as db:
            self.require_conversation(db, conversation)
            db.execute('INSERT INTO events(conversation,created,kind,data) VALUES (?,?,?,?)',
                       (conversation, self.clock(), kind, encoded))

    def finish_message(self, message, status='completed'):
        if status not in ('completed', 'failed', 'interrupted'):
            raise ValueError('Invalid message status')
        with self.db() as db:
            db.execute("UPDATE messages SET status=? WHERE id=? AND status='processing'", (status, message))

    def propose(self, conversation, proposal, ttl=600):
        if not 0 < ttl <= 3600:
            raise ValueError('Invalid approval lifetime')
        now = self.clock()
        action = str(uuid.uuid4())
        # Bind expiry and server identity as well as the exact execution proposal.
        specification = dict(action_id=action, conversation_id=conversation,
                             expires=now + ttl, proposal=proposal)
        encoded = canonical(specification)
        if len(encoded) > 16384:
            raise ConversationError('Proposal exceeds storage limit', 400)
        with self.db() as db:
            self.require_conversation(db, conversation)
            db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,NULL,NULL,?)',
                       (action, conversation, encoded, digest(specification), now + ttl, 'pending', now))
        return self.action(action)

    def action(self, action):
        with self.db() as db:
            row = db.execute('SELECT * FROM actions WHERE id=?', (action,)).fetchone()
        if not row:
            raise ConversationError('Unknown action', 404)
        result = dict(row)
        result['proposal'] = json.loads(result['proposal'])
        return result

    def decide(self, action, conversation, proposal_hash, decision):
        if decision not in ('approve', 'reject'):
            raise ConversationError('Decision must be approve or reject', 400)
        expired = False
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM actions WHERE id=?', (action,)).fetchone()
            if not row or row['conversation'] != conversation:
                raise ConversationError('Unknown action in this conversation', 404)
            if (row['proposal_hash'] != proposal_hash or
                    digest(json.loads(row['proposal'])) != row['proposal_hash']):
                raise ConversationError('Approval does not match the exact proposal')
            if row['status'] != 'pending':
                raise ConversationError('Action already decided or consumed')
            expired = self.clock() >= row['expires']
            status = 'expired' if expired else ('approved' if decision == 'approve' else 'rejected')
            db.execute('UPDATE actions SET status=?,updated=? WHERE id=?', (status, self.clock(), action))
        if expired:
            raise ConversationError('Approval expired')
        return self.action(action)

    def claim_submission(self, action):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM actions WHERE id=?', (action,)).fetchone()
            if not row or row['status'] != 'approved':
                raise ConversationError('Action is not available for submission')
            if digest(json.loads(row['proposal'])) != row['proposal_hash']:
                raise ConversationError('Action proposal changed')
            if self.clock() >= row['expires']:
                db.execute("UPDATE actions SET status='expired',updated=? WHERE id=?", (self.clock(), action))
                expired = True
            else:
                db.execute("UPDATE actions SET status='submitting',updated=? WHERE id=?", (self.clock(), action))
                expired = False
        if expired:
            raise ConversationError('Approval expired before submission')
        return self.action(action)

    def recover(self):
        # Reservations without an execution ID cannot safely be resubmitted.
        with self.db() as db:
            db.execute("UPDATE actions SET status='approval_interrupted',updated=? WHERE status='approved'", (self.clock(),))
            db.execute("UPDATE actions SET status='submission_unknown',updated=? WHERE status='submitting'",
                       (self.clock(),))
            db.execute("UPDATE actions SET status='unable_to_verify',updated=? WHERE status='verification_submitting'", (self.clock(),))
            db.execute("UPDATE messages SET status='interrupted' WHERE status='processing'")

    def history(self, conversation):
        with self.db() as db:
            self.require_conversation(db, conversation)
            messages = [dict(r) for r in db.execute('SELECT * FROM messages WHERE conversation=? ORDER BY created,id', (conversation,))]
            events = [dict(r) for r in db.execute('SELECT * FROM events WHERE conversation=? ORDER BY id', (conversation,))]
            actions = [r[0] for r in db.execute('SELECT id FROM actions WHERE conversation=? ORDER BY updated,id', (conversation,))]
        for event in events:
            event['data'] = json.loads(event['data'])
        return dict(id=conversation, messages=messages, events=events,
                    actions=[self.action(action) for action in actions])

    def update_action(self, action, expected, status, execution_id=None, verification_id=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM actions WHERE id=?', (action,)).fetchone()
            if not row or row['status'] not in expected:
                raise ConversationError('Action state changed')
            db.execute('UPDATE actions SET status=?,execution_id=COALESCE(?,execution_id),verification_id=COALESCE(?,verification_id),updated=? WHERE id=?',
                       (status, execution_id, verification_id, self.clock(), action))
        return self.action(action)

    def active_actions(self):
        with self.db() as db:
            return [r[0] for r in db.execute("SELECT id FROM actions WHERE status IN ('running','verifying')")]
