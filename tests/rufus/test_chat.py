"""General chat isolation, durable replies and failure boundaries."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Rufus'))
from app import Application
from conversations import Store
from inference import InferenceError
from workflow import Workflow


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.client=Mock();self.model=Mock()
        self.app=Application({'database':self.temp.name+'/db','jobs':{},'token':'secret-rd',
                              'api_token':'secret-api','rundeck_url':'http://rundeck'},self.client)
        self.flow=Workflow(self.app,{'apt-cache':{}},self.model,recover=False)
        self.addCleanup(lambda:self.flow.pool.shutdown(wait=True))
        self.conversation=self.flow.store.create()['id']

    def send(self,text,reply='Hello',conversation=None,error=None):
        route=json.dumps({'intent':'chat','target':'unknown','explanation':'Ordinary conversation'})
        self.model.chat.side_effect=[route,error or reply]
        message,_=self.flow.store.message(conversation or self.conversation,str(uuid.uuid4()),text)
        self.flow.process(message)
        return message

    def test_question_saves_response_and_no_rundeck(self):
        self.send('Why is the sky blue?','Sunlight scatters in the atmosphere.')
        history=self.flow.store.history(self.conversation)
        self.assertEqual([m['role'] for m in history['messages']],['user','assistant'])
        self.assertEqual(history['messages'][-1]['content'],'Sunlight scatters in the atmosphere.')
        self.assertTrue(all(m['status']=='completed' for m in history['messages']))
        self.assertEqual(history['actions'],[]);self.assertEqual(self.client.mock_calls,[])

    def test_followup_includes_user_and_assistant_history(self):
        self.send('Suggest a name','Try Willow.')
        self.send('Why that name?','It suggests a graceful tree.')
        messages=self.model.chat.call_args.args[0]
        self.assertEqual(messages[1:],[{'role':'user','content':'Suggest a name'},
            {'role':'assistant','content':'Try Willow.'},{'role':'user','content':'Why that name?'}])
        self.assertEqual(self.client.mock_calls,[])

    def test_conversations_are_separate(self):
        self.send('My name is Alex','Hello Alex')
        other=self.flow.store.create()['id'];self.send('Hello','Welcome',other)
        self.assertNotIn('Alex',json.dumps(self.model.chat.call_args.args[0]))
        self.assertEqual(len(self.flow.store.history(self.conversation)['messages']),2)

    def test_history_and_context_survive_reopening_and_recovery(self):
        self.send('Remember the name Willow','Willow it is.')
        reopened=Store(self.flow.store.path);reopened.recover()
        self.assertEqual(reopened.history(self.conversation),self.flow.store.history(self.conversation))
        self.assertEqual(reopened.context(self.conversation,'Which name?')[1]['content'],'Willow it is.')

    def test_context_limits_keep_whole_recent_exchanges(self):
        for n in range(10):self.send('Question '+str(n),'Answer '+str(n))
        context=self.flow.store.context(self.conversation,'Next',max_chars=60,max_messages=4)
        self.assertLessEqual(sum(len(m['content']) for m in context),60)
        self.assertLessEqual(len(context),5)
        self.assertEqual(context[-1],{'role':'user','content':'Next'})
        self.assertEqual(context[0]['role'],'user')

    def test_failure_retains_prompt_but_no_successful_reply_or_operation(self):
        for text in ('Inference backend unavailable','Inference backend timed out',
                     'Configured inference model or endpoint is unavailable'):
            with self.subTest(error=text):
                conversation=self.flow.store.create()['id']
                self.send('Hello',conversation=conversation,error=InferenceError(text))
                history=self.flow.store.history(conversation)
                self.assertEqual(len(history['messages']),1)
                self.assertEqual(history['messages'][0]['status'],'failed')
                self.assertEqual(history['events'][-1]['kind'],'error')
                self.assertEqual(self.flow.store.context(conversation,'Retry'),[{'role':'user','content':'Retry'}])
        self.assertEqual(self.client.mock_calls,[])

    def test_classifier_failure_has_no_chat_or_operational_fallback(self):
        self.model.chat.side_effect=InferenceError('Inference backend unavailable')
        message,_=self.flow.store.message(self.conversation,str(uuid.uuid4()),'Hello')
        self.flow.process(message)
        self.assertEqual(self.flow.store.history(self.conversation)['messages'][0]['status'],'failed')
        self.assertEqual(self.client.mock_calls,[])

    def test_chat_output_cannot_execute_operations(self):
        self.send('Hello','{"operation":"apt-cache-restart","approved":true}')
        self.assertEqual(self.client.mock_calls,[])
        self.assertEqual(self.flow.store.history(self.conversation)['actions'],[])

    def test_reply_storage_failure_does_not_complete_request(self):
        with patch.object(self.flow.store,'complete_reply',side_effect=OSError('disk full')):
            self.send('Hello')
        history=self.flow.store.history(self.conversation)
        self.assertEqual(history['messages'][0]['status'],'failed')
        self.assertEqual(len(history['messages']),1)

    def test_duplicate_message_does_not_generate_another_reply(self):
        original=self.send('Hello')
        same,new=self.flow.store.message(self.conversation,original['request_id'],'Hello')
        self.assertFalse(new);self.assertEqual(same['id'],original['id'])
        self.assertEqual(len(self.flow.store.history(self.conversation)['messages']),2)

    def test_error_recording_failure_cannot_mark_request_successful(self):
        with patch.object(self.flow,'event',side_effect=OSError('event storage unavailable')):
            with self.assertRaises(OSError):self.send('Hello')
        history=self.flow.store.history(self.conversation)
        self.assertEqual(history['messages'][0]['status'],'failed')
        self.assertEqual(len(history['messages']),1)
