"""Loopback API with deterministic validation and supervised model proposals."""
from contextlib import contextmanager
import argparse
import hmac
import json
import logging
import re
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from config import load
from rundeck import Client, IntegrationError
from conversations import ConversationError
from workflow import Workflow


class RequestError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Application:
    def __init__(self, config, client=None):
        self.config = config
        self.client = client or Client(config['rundeck_url'], config['token'], config.get('request_timeout', 10))
        self.jobs = config['jobs']
        self.lock = threading.Lock()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS executions (id INTEGER PRIMARY KEY, operation TEXT, options TEXT)')
        self.workflow = None
        self.workflow = Workflow(self, config['conversation_catalogue']) if config.get('conversation_catalogue') else None

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.config['database'], timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def validate(self, operation, options):
        if operation not in self.jobs:
            raise RequestError('Operation is not approved', 403)
        rules = self.jobs[operation]['options']
        if not isinstance(options, dict) or set(options) - set(rules):
            raise RequestError('Unknown or invalid options')
        for name, rule in rules.items():
            value = options.get(name)
            if value is None:
                if rule.get('required'):
                    raise RequestError('Missing required option: ' + name)
                continue
            if not isinstance(value, str) or len(value) > 256 or not re.fullmatch(rule['pattern'], value):
                raise RequestError('Invalid option: ' + name)
        return self.jobs[operation]

    def start(self, body):
        if isinstance(body, dict) and isinstance(body.get('operation'), str):
            if self.jobs.get(body['operation'], {}).get('requires_approval'):
                raise RequestError('This operation requires an exact conversational approval', 403)
        return self._submit(body)

    def _submit(self, body):
        if not isinstance(body, dict) or set(body) - {'operation', 'options'} or not isinstance(body.get('operation'), str):
            raise RequestError('Expected operation and options')
        operation, options = body['operation'], body.get('options', {})
        job = self.validate(operation, options)
        # Serialize submissions. Never automatically retry an ambiguous POST.
        with self.lock:
            execution = self.client.start(job['id'], options)
            try:
                with self.db() as db:
                    db.execute('INSERT INTO executions VALUES (?, ?, ?)', (execution, operation, json.dumps(options)))
            except sqlite3.Error:
                raise IntegrationError('Execution started but could not be recorded; check Rundeck before retrying') from None
        return {'status': 'queued', 'execution_id': execution,
                'operation': operation, 'job': {'id': job['id'], 'name': job['name']},
                'parameters': options, 'failure': None}

    def result(self, execution, wait=0):
        with self.db() as db:
            row = db.execute('SELECT operation, options FROM executions WHERE id=?', (execution,)).fetchone()
        if not row or row[0] not in self.jobs:
            raise RequestError('Unknown Rufus execution', 404)
        job = self.jobs[row[0]]
        deadline = time.monotonic() + wait
        while True:
            state = self.client.execution(execution)
            if not isinstance(state.get('job'), dict) or state['job'].get('id') != job['id']:
                raise IntegrationError('Rundeck execution job mismatch')
            raw = state['status']
            status = {'scheduled': 'queued', 'aborted': 'failed', 'timedout': 'failed',
                      'failed-with-retry': 'failed', 'other': 'failed'}.get(raw, raw)
            if status not in ('queued', 'running') or time.monotonic() >= deadline:
                break
            time.sleep(min(1, max(0, deadline - time.monotonic())))
        logs = self.client.output(execution)
        if self.workflow:
            logs = json.loads(self.workflow.clean_json(logs))
        return {'status': status, 'rundeck_status': raw, 'execution_id': execution,
                'operation': row[0], 'job': {'id': job['id'], 'name': job['name']},
                'parameters': json.loads(row[1]), 'output': logs,
                'failure': ('Rundeck execution ended with status ' + raw) if status == 'failed' else None,
                'monitor_timeout': status in ('queued', 'running') and bool(wait)}


def handler(app):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, fmt, *args):
            # Do not log request paths, headers, parameters or credentials.
            logging.info('HTTP request completed')

        def respond(self, code, data):
            payload = json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def dispatch(self, method):
            if not hmac.compare_digest(self.headers.get('Authorization', '').encode(), ('Bearer ' + app.config['api_token']).encode()):
                return self.respond(401, {'error': 'Unauthorised'})
            try:
                if method == 'GET' and self.path == '/health':
                    return self.respond(200, {'status': 'ok'})
                if method == 'GET' and self.path == '/jobs':
                    jobs = []
                    for operation, policy in app.jobs.items():
                        remote = app.client.job(policy['id'])
                        jobs.append({'operation': operation, 'id': policy['id'],
                                     'name': remote['name'], 'options': policy['options']})
                    return self.respond(200, {'jobs': jobs})
                body = None
                if method == 'POST':
                    if self.headers.get('Transfer-Encoding'):
                        raise RequestError('Transfer encoding unsupported')
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 8192:
                        raise RequestError('Invalid request size')
                    body = json.loads(self.rfile.read(length))
                if method == 'POST' and self.path == '/executions':
                    return self.respond(202, app.start(body))
                if app.workflow:
                    workflow = app.workflow
                    if method == 'GET' and self.path == '/conversations':
                        return self.respond(200, workflow.store.list_conversations())
                    if method == 'POST' and self.path == '/conversations':
                        if body != {}: raise RequestError('Expected empty object')
                        return self.respond(201, workflow.store.create())
                    conversation = re.fullmatch(r'/conversations/([0-9a-f-]{36})(/messages)?', self.path)
                    if conversation:
                        if method == 'GET' and not conversation[2]:
                            return self.respond(200, workflow.store.history(conversation[1]))
                        if method == 'POST' and conversation[2]:
                            return self.respond(202, workflow.message(conversation[1], body))
                    action = re.fullmatch(r'/actions/([0-9a-f-]{36})(/decision)?', self.path)
                    if action:
                        if method == 'GET' and not action[2]:
                            return self.respond(200, workflow.action(action[1]))
                        if method == 'POST' and action[2]:
                            return self.respond(202, workflow.decision(action[1], body))
                match = re.fullmatch(r'/executions/([1-9][0-9]*)(?:\?wait=([0-9]+))?', self.path)
                if method == 'GET' and match:
                    wait = int(match[2] or 0)
                    if wait > 30:
                        raise RequestError('Maximum wait is 30 seconds')
                    return self.respond(200, app.result(int(match[1]), wait))
                raise RequestError('Endpoint not found', 404)
            except (RequestError, IntegrationError, ConversationError) as error:
                self.respond(error.status, {'error': str(error)})
            except (ValueError, UnicodeError):
                self.respond(400, {'error': 'Malformed request'})
            except Exception:
                logging.error('Internal request failure')
                self.respond(500, {'error': 'Internal service failure'})

        def do_GET(self):
            self.dispatch('GET')

        def do_POST(self):
            self.dispatch('POST')
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    config = load(args.config)
    app = Application(config)
    # Loopback only for the initial milestone; future client exposure is separate.
    server = ThreadingHTTPServer(('127.0.0.1', config.get('port', 8787)), handler(app))
    server.daemon_threads = True
    server.serve_forever()
