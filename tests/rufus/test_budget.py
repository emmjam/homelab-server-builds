"""Conservative model-window accounting and additive context persistence."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Rufus'))
from budget import Budget, cost, limits, prompt, FRAMING_TOKENS
from conversations import Store, ConversationError

class BudgetTests(unittest.TestCase):
    def test_full_current_and_separate_repository_fit_configured_window(self):
        for config in ({},{'chat_num_ctx':4096,'chat_num_predict':1024}):
            for current in ('x'*(Budget(config).current_capacity//2),'🙂'*(Budget(config).current_capacity//8)):
                messages,usage=prompt(config,current,'source\n'*2000,[])
                self.assertEqual(messages[-1]['content'],current)
                self.assertTrue(usage['repository_shortened'])
                self.assertLessEqual(sum(cost(m['content'])+16 for m in messages)+FRAMING_TOKENS+limits(config)['generation_tokens'],limits(config)['context_tokens'])
                self.assertGreater(usage['repository_bytes_used'],0)
    def test_no_silent_current_truncation(self):
        maximum=limits({})['current_message_tokens']
        messages,_=prompt({},'x'*maximum,'repository',[])
        self.assertEqual(messages[-1]['content'],'x'*maximum)
        with self.assertRaisesRegex(ValueError,'not truncated'):prompt({},'x'*(maximum+1),'',[])
    def test_whole_recent_pairs_and_repository_priority(self):
        history=[{'role':'user','content':'old'*3000},{'role':'assistant','content':'old reply'},
                 {'role':'user','content':'new'},{'role':'assistant','content':'new reply'}]
        messages,usage=prompt({},'current','repo',history)
        self.assertEqual(usage['history_exchanges_used'],1)
        self.assertEqual(messages[-3:],history[-2:]+[{'role':'user','content':'current'}])
    def test_clip_boundaries_unicode_and_zero_tail(self):
        for size in range(300):
            selected=Budget({}).excerpt('🙂'*300,size)
            self.assertLessEqual(cost(selected),size)
            self.assertNotIn('�',selected)
    def test_existing_database_migration_and_idempotent_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path=directory+'/db';cid=str(uuid.uuid4());mid=str(uuid.uuid4());rid=str(uuid.uuid4())
            with sqlite3.connect(path) as db:
                db.executescript('CREATE TABLE messages (id TEXT PRIMARY KEY,conversation TEXT NOT NULL,request_id TEXT NOT NULL,content TEXT NOT NULL,created REAL NOT NULL,status TEXT NOT NULL,UNIQUE(conversation,request_id)); CREATE TABLE conversations(id TEXT PRIMARY KEY,created REAL NOT NULL);')
                db.execute('INSERT INTO conversations VALUES (?,0)',(cid,))
                db.execute('INSERT INTO messages VALUES (?,?,?,?,0,?)',(mid,cid,rid,'old','completed'))
            store=Store(path)
            self.assertEqual(store.history(cid)['messages'][0]['repository_context'],'')
            new_id=str(uuid.uuid4());row,new=store.message(cid,new_id,'new','repo')
            self.assertTrue(new)
            self.assertFalse(Store(path).message(cid,new_id,'new','repo')[1])
            with self.assertRaises(ConversationError):store.message(cid,new_id,'new','changed')
            self.assertEqual(Store(path).history(cid)['messages'][-1]['repository_context'],'repo')

    def test_repository_can_be_disabled_and_capabilities_are_backend_owned(self):
        budget=Budget({'repository_context_tokens':0})
        messages,usage=budget.prompt('Hello','repo',[])
        self.assertEqual(usage['repository_tokens_used'],0)
        self.assertTrue(usage['repository_shortened'])
        self.assertEqual(budget.capabilities()['repository_max_bytes'],32768)
        self.assertEqual(messages[-1]['content'],'Hello')

    def test_replaceable_estimator(self):
        class Estimator:
            name='test-estimator'
            def count(self,text): return len(text)
        budget=Budget({},estimator=Estimator())
        self.assertEqual(budget.count('🙂'),1)
        self.assertEqual(Budget({}).count('🙂'),4)
        self.assertEqual(budget.capabilities()['accounting'],'test-estimator')

    def test_independent_message_and_history_limits(self):
        budget=Budget({'incoming_message_tokens':64,'history_context_tokens':40})
        budget.validate_current('🙂'*16)
        with self.assertRaises(ValueError) as caught:budget.validate_current('🙂'*16+'x')
        self.assertEqual(caught.exception.details['code'],'message_too_large')
        self.assertEqual(caught.exception.details['limit'],64)
        history=[{'role':'user','content':'hello'},{'role':'assistant','content':'reply'}]
        messages,usage=budget.prompt('current','repository',history)
        self.assertEqual(usage['history_exchanges_used'],0)
        self.assertEqual(messages[-1]['content'],'current')
        self.assertGreater(usage['repository_tokens_used'],0)

    def test_exact_overall_boundary_and_schema(self):
        budget=Budget({})
        available=budget.window-budget.output-budget.framing-16
        budget.ensure_request([{'role':'user','content':'x'*available}])
        with self.assertRaises(ValueError) as caught:
            budget.ensure_request([{'role':'user','content':'x'*(available+1)}])
        self.assertEqual(caught.exception.details['budget'],'overall_request')
