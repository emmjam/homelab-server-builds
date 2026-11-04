"""Validate inference boundaries and safe failures without loading a model."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Rufus'))
from inference import Client, InferenceError


class InferenceTests(unittest.TestCase):
    def setUp(self):
        self.client = Client({'url': 'http://ai-agent.lan:11434', 'model': 'qwen3:4b'})
        self.connection = Mock()
        self.response = self.connection.getresponse.return_value
        self.response.status = 200
        self.response.read.return_value = json.dumps(
            {'done': True, 'message': {'content': '{"status":"ready"}'}}).encode()
        self.factory = patch('inference.http.client.HTTPConnection', return_value=self.connection)
        self.factory.start()
        self.addCleanup(self.factory.stop)

    def test_structured_response_and_bounded_request(self):
        self.assertEqual(json.loads(self.client.chat([], {'type': 'object'})), {'status': 'ready'})
        body = json.loads(self.connection.request.call_args.kwargs['body'])
        self.assertEqual(body['model'], 'qwen3:4b')
        self.assertFalse(body['stream'])
        self.assertEqual(body['options']['num_ctx'], 8192)
        self.connection.sock.settimeout.assert_called_once_with(120)
        self.connection.close.assert_called_once()

    def test_unavailable_and_timeout_are_safe(self):
        for error, message in [(OSError('sensitive upstream text'), 'unavailable'),
                               (TimeoutError('sensitive upstream text'), 'timed out')]:
            with self.subTest(error=type(error).__name__):
                self.connection.connect.side_effect = error
                with self.assertRaisesRegex(InferenceError, message) as caught:
                    self.client.chat([])
                self.assertNotIn('sensitive', str(caught.exception))

    def test_http_error_does_not_disclose_body(self):
        self.response.status = 500
        with self.assertRaisesRegex(InferenceError, 'returned an error'):
            self.client.chat([])
        self.response.read.assert_not_called()

    def test_missing_model_is_understandable_and_does_not_disclose_body(self):
        self.response.status = 404
        with self.assertRaisesRegex(InferenceError, 'model or endpoint is unavailable'):
            self.client.chat([])
        self.response.read.assert_not_called()

    def test_inline_reasoning_is_not_returned_as_chat(self):
        for content in ('<think>private reasoning</think>Final answer',
                        'private reasoning</think>Final answer'):
            self.response.read.return_value=json.dumps({'done':True,'message':{'content':content}}).encode()
            self.assertEqual(self.client.chat([]),'Final answer')

    def test_incomplete_chat_has_no_successful_answer(self):
        for content,reason in [('<think>unfinished','stop'),('reasoning</think>','stop'),('unfinished answer','length')]:
            self.response.read.return_value=json.dumps({'done':True,'done_reason':reason,'message':{'content':content}}).encode()
            with self.assertRaises(InferenceError):self.client.chat([])

    def test_managed_prefill_only_applies_to_chat_and_does_not_mutate_history(self):
        self.client.config['chat_empty_thinking_prefill']=True
        messages=[{'role':'user','content':'Hello'}]
        self.client.chat(messages)
        body=json.loads(self.connection.request.call_args.kwargs['body'])
        self.assertEqual(body['messages'][-1],{'role':'assistant','content':'<think>\n\n</think>\n\n'})
        self.assertEqual(len(messages),1)
        self.assertEqual(body['options']['num_predict'],2048)
        self.client.chat(messages,{'type':'object'})
        body=json.loads(self.connection.request.call_args.kwargs['body'])
        self.assertEqual(body['messages'],messages)
        self.assertEqual(body['options']['num_predict'],256)

    def test_chat_budget_and_timeout_do_not_change_structured_calls(self):
        self.client.config['chat_num_ctx']=8192
        self.client.config['chat_num_predict']=2048
        self.client.chat_inference_timeout=360
        self.client.chat([])
        body=json.loads(self.connection.request.call_args.kwargs['body'])
        self.assertEqual(body['options']['num_predict'],2048)
        self.assertEqual(body['options']['num_ctx'],8192)
        self.connection.sock.settimeout.assert_called_with(360)
        self.client.chat([],{'type':'object'})
        body=json.loads(self.connection.request.call_args.kwargs['body'])
        self.assertEqual(body['options']['num_predict'],256)
        self.assertEqual(body['options']['num_ctx'],8192)
        self.connection.sock.settimeout.assert_called_with(120)
        self.response.read.return_value=json.dumps({'done':True,'done_reason':'length',
            'message':{'content':'partial answer'}}).encode()
        with self.assertRaisesRegex(InferenceError,'limit before completing'):self.client.chat([])

    def test_full_wire_budget_includes_schema_and_tool_fields(self):
        for messages,schema in [([{'role':'system','content':'x'*8000}],None),
            ([{'role':'user','content':'hello'}],{'description':'x'*8000}),
            ([{'role':'user','content':'hello','tool_calls':['x'*8000]}],None)]:
            with self.assertRaisesRegex(InferenceError,'context budget'):
                self.client.chat(messages,schema)
            self.connection.request.assert_not_called()

    def test_invalid_or_incomplete_responses(self):
        for body in (b'not JSON', b'{}', b'{"done":false,"message":{"content":"partial"}}',
                     b'{"done":true,"message":{"content":42}}'):
            with self.subTest(body=body):
                self.response.read.return_value = body
                with self.assertRaisesRegex(InferenceError, 'invalid response'):
                    self.client.chat([])

    def test_response_size_limit(self):
        self.response.read.return_value = b'x' * (1024 * 1024 + 1)
        with self.assertRaisesRegex(InferenceError, 'size limit'):
            self.client.chat([])

    def test_invalid_urls_and_timeouts(self):
        for url in ('file:///tmp/model', 'http://user:password@host', 'http://host?token=secret'):
            with self.assertRaises(ValueError):
                Client({'url': url, 'model': 'qwen3:4b'})
        with self.assertRaises(ValueError):
            Client({'url': 'http://host', 'model': 'qwen3:4b', 'inference_timeout': 0})
        self.assertEqual(Client({'url':'http://host','model':'qwen3:4b','chat_inference_timeout':600}).chat_inference_timeout,600)
        for timeout in (0,float('inf'),float('nan')):
            with self.assertRaises(ValueError):
                Client({'url':'http://host','model':'qwen3:4b','chat_inference_timeout':timeout})

    def test_structured_length_response_and_upstream_error_are_failures(self):
        for body in ({'done':True,'done_reason':'length','message':{'content':'{"status":"ready"}'}},
                     {'done':True,'error':'private upstream detail','message':{'content':'{"status":"ready"}'}},
                     [],None):
            self.response.read.return_value=json.dumps(body).encode()
            with self.assertRaises(InferenceError) as caught:self.client.chat([],{'type':'object'})
            self.assertNotIn('private upstream detail',str(caught.exception))

    def test_budget_rejection_is_structured_and_never_contacts_ollama(self):
        with self.assertRaises(InferenceError) as caught:
            self.client.chat([{'role':'user','content':'x'*9000}])
        self.assertEqual(caught.exception.details['code'],'inference_context_exceeded')
        self.connection.connect.assert_not_called()
