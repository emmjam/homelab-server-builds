import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Rufus'))
from app import Application, RequestError, handler
from rundeck import Client, IntegrationError

JOB = '6e0b2f6c-aaa0-4031-ba96-73c86164cb43'


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = Mock()
        self.client.start.return_value = 123
        self.client.execution.return_value = {'id': 123, 'job': {'id': JOB}, 'status': 'succeeded'}
        self.client.output.return_value = [{'message': 'healthy', 'level': 'INFO'}]
        self.config = {'jobs': {'health-check': {'id': JOB, 'name': 'Health', 'options': {}}},
                       'api_token': 'dummy-api', 'database': self.temp.name + '/db'}
        self.app = Application(self.config, self.client)

    def test_approved(self):
        result = self.app.start({'operation': 'health-check'})
        self.assertEqual(result['execution_id'], 123)
        self.client.start.assert_called_once_with(JOB, {})

    def test_unapproved(self):
        with self.assertRaises(RequestError):
            self.app.start({'operation': 'delete-vm'})
        self.client.start.assert_not_called()

    def test_parameters(self):
        with self.assertRaises(RequestError):
            self.app.start({'operation': 'health-check', 'options': {'shell': 'whoami'}})
        self.config['jobs']['health-check']['options'] = {'name': {'required': True, 'pattern': '[a-z]+'}}
        for options in ({}, {'name': 5}, {'name': 'a;rm'}, []):
            with self.assertRaises(RequestError):
                self.app.validate('health-check', options)
        self.app.validate('health-check', {'name': 'valid'})

    def test_success_and_persistence(self):
        self.app.start({'operation': 'health-check'})
        app = Application(self.config, self.client)
        result = app.result(123)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(result['output'][0]['message'], 'healthy')
        self.assertIsNone(result['failure'])

    def test_failure(self):
        self.app.start({'operation': 'health-check'})
        self.client.execution.return_value['status'] = 'failed'
        self.assertIn('failed', self.app.result(123)['failure'])

    def test_unknown_execution_and_job_mismatch(self):
        with self.assertRaises(RequestError):
            self.app.result(987)
        self.app.start({'operation': 'health-check'})
        self.client.execution.return_value['job']['id'] = 'other'
        with self.assertRaises(IntegrationError):
            self.app.result(123)

    def test_polling_timeout(self):
        self.app.start({'operation': 'health-check'})
        self.client.execution.return_value['status'] = 'running'
        result = self.app.result(123, .01)
        self.assertTrue(result['monitor_timeout'])
        self.assertEqual(result['status'], 'running')

    def test_http_auth_and_control_path(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}'
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(url + '/jobs')
            self.assertEqual(error.exception.code, 401)
            req = urllib.request.Request(url + '/executions', data=b'{"operation":"health-check"}',
                                         headers={'Authorization': 'Bearer dummy-api'})
            with urllib.request.urlopen(req) as response:
                self.assertEqual(response.status, 202)
                self.assertEqual(json.load(response)['execution_id'], 123)
            req = urllib.request.Request(url + '/executions/123', headers={'Authorization': 'Bearer dummy-api'})
            with urllib.request.urlopen(req) as response:
                self.assertEqual(json.load(response)['status'], 'succeeded')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.status, self.payload = 200, {'id': JOB, 'name': 'Health'}
        test = self
        class Remote(BaseHTTPRequestHandler):
            def do_GET(self):
                test.assertEqual(self.headers['X-Rundeck-Auth-Token'], 'dummy')
                body = test.payload if isinstance(test.payload, bytes) else json.dumps(test.payload).encode()
                self.send_response(test.status)
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Remote)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = Client(f'http://127.0.0.1:{self.server.server_port}', 'dummy', .2)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_connection(self):
        self.assertEqual(self.client.job(JOB)['name'], 'Health')

    def test_authentication(self):
        self.status = 403
        with self.assertRaisesRegex(IntegrationError, 'authentication'):
            self.client.job(JOB)

    def test_malformed_and_unexpected(self):
        for payload in (b'invalid JSON', [], {}, {'id': False}, {'id': 1, 'status': 'invented'}):
            self.payload = payload
            with self.assertRaises(IntegrationError):
                self.client.execution(1)

    def test_unreachable_and_timeout(self):
        self.client.opener.open = Mock(side_effect=TimeoutError)
        with self.assertRaises(IntegrationError) as error:
            self.client.job(JOB)
        self.assertEqual(error.exception.status, 504)
        self.client.opener.open = Mock(side_effect=urllib.error.URLError('offline'))
        with self.assertRaisesRegex(IntegrationError, 'unreachable'):
            self.client.job(JOB)

    def test_malformed_output(self):
        self.payload = {'entries': [{'log': 5}]}
        with self.assertRaises(IntegrationError):
            self.client.output(1)


if __name__ == '__main__':
    unittest.main()
