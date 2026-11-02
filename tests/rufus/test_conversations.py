"""Approval safety and persistence without model calls or infrastructure changes."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Rufus'))
from conversations import Store, ConversationError


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000
        self.store = Store(self.temp.name + '/state.sqlite', clock=lambda: self.now)
        self.conversation = self.store.create()['id']

    def proposal(self):
        return self.store.propose(self.conversation, {'operation': 'test-only', 'options': {}})

    def decide(self, action, decision='approve'):
        return self.store.decide(action['id'], self.conversation, action['proposal_hash'], decision)

    def test_duplicate_message_and_changed_content(self):
        request = str(uuid.uuid4())
        first, created = self.store.message(self.conversation, request, 'diagnose')
        self.assertTrue(created)
        again, created = self.store.message(self.conversation, request, 'diagnose')
        self.assertFalse(created)
        self.assertEqual(first, again)
        with self.assertRaises(ConversationError):
            self.store.message(self.conversation, request, 'different')
        with self.assertRaises(ConversationError):
            self.store.message(self.conversation, str(uuid.uuid4()), 'parallel request')

    def test_no_submission_without_approval(self):
        with self.assertRaises(ConversationError):
            self.store.claim_submission(self.proposal()['id'])

    def test_rejection_and_replay(self):
        action = self.proposal()
        self.assertEqual(self.decide(action, 'reject')['status'], 'rejected')
        with self.assertRaises(ConversationError):
            self.decide(action)
        with self.assertRaises(ConversationError):
            self.store.claim_submission(action['id'])

    def test_expired_decision_is_persisted(self):
        action = self.proposal()
        self.now += 601
        with self.assertRaisesRegex(ConversationError, 'expired'):
            self.decide(action)
        self.assertEqual(self.store.action(action['id'])['status'], 'expired')

    def test_expiry_between_approval_and_submission(self):
        action = self.proposal()
        self.decide(action)
        self.now += 601
        with self.assertRaisesRegex(ConversationError, 'expired'):
            self.store.claim_submission(action['id'])
        self.assertEqual(self.store.action(action['id'])['status'], 'expired')

    def test_exact_hash_and_conversation_required(self):
        action = self.proposal()
        with self.assertRaises(ConversationError):
            self.store.decide(action['id'], self.conversation, 'different hash', 'approve')
        with self.assertRaises(ConversationError):
            self.store.decide(action['id'], self.store.create()['id'], action['proposal_hash'], 'approve')
        with self.store.db() as db:
            db.execute('UPDATE actions SET proposal=? WHERE id=?', ('{}', action['id']))
        with self.assertRaises(ConversationError):
            self.decide(action)

    def test_concurrent_approval_and_submission_consumed_once(self):
        action = self.proposal()
        def approve(_):
            try:
                self.decide(action)
                return True
            except ConversationError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(approve, range(2))), 1)
        self.assertEqual(self.store.claim_submission(action['id'])['status'], 'submitting')
        with self.assertRaises(ConversationError):
            self.store.claim_submission(action['id'])

    def test_restart_does_not_resubmit_and_preserves_history(self):
        message, _ = self.store.message(self.conversation, str(uuid.uuid4()), 'help')
        self.store.event(self.conversation, 'progress', {'status': 'diagnosing'})
        pending = self.proposal()
        action = self.proposal()
        self.decide(action)
        self.store.claim_submission(action['id'])
        store = Store(self.store.path)
        store.recover()
        self.assertEqual(store.action(action['id'])['status'], 'submission_unknown')
        self.assertEqual(store.action(pending['id'])['status'], 'pending')
        history = store.history(self.conversation)
        self.assertEqual(history['messages'][0]['id'], message['id'])
        self.assertEqual(history['messages'][0]['status'], 'interrupted')
        self.assertEqual(history['events'][0]['data']['status'], 'diagnosing')
        with self.assertRaises(ConversationError):
            store.claim_submission(action['id'])
