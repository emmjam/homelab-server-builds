"""Administrative source updates preserve metadata and transfer only hashes."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'RufusWeb'))
from auth import password_valid

class AdminSourceTests(unittest.TestCase):
    def invoke(self,path,action='set-password',transfer=False):
        argv=['rufus-web-admin.py',action,'ian','--secrets-file',str(path)]+(['--transfer'] if transfer else [])
        output=io.StringIO()
        with patch('sys.argv',argv),patch('getpass.getpass',side_effect=['abc','abc']),patch('subprocess.run') as run,contextlib.redirect_stdout(output):
            runpy.run_path(str(ROOT/'scripts/rufus-web-admin.py'),run_name='__main__')
        return run,output.getvalue()
    def records(self,path):
        line=next(line for line in path.read_text().splitlines() if line.startswith('RUFUS_WEB_ACCOUNTS='))
        return json.loads(shlex.split(line.partition('=')[2])[0])
    def test_three_character_password_hash_only_transfer_and_preserved_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'secrets.txt';path.write_text('UNRELATED=dummy-existing-value\n');path.chmod(0o600)
            before=path.stat();run,output=self.invoke(path,transfer=True);after=path.stat()
            account=self.records(path)[0]
            self.assertTrue(password_valid('abc',account['password_hash']))
            self.assertEqual(account['username'],'ian')
            self.assertEqual((before.st_ino,before.st_uid,before.st_gid,before.st_mode),(after.st_ino,after.st_uid,after.st_gid,after.st_mode))
            self.assertIn('UNRELATED=dummy-existing-value',path.read_text())
            sent=json.loads(run.call_args.kwargs['input'])
            self.assertEqual(sent,[account]);self.assertNotIn('dummy-existing-value',run.call_args.kwargs['input'])
            self.assertNotIn(account['password_hash'],output);self.assertNotIn('abc',output)
            self.assertNotIn(account['password_hash'],' '.join(run.call_args.args[0]))
    def test_disable_enable_remove_preserve_hash_and_change_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'secrets.txt';path.write_text('')
            self.invoke(path);original=self.records(path)[0]
            self.invoke(path,'disable');disabled=self.records(path)[0]
            self.assertFalse(disabled['enabled']);self.assertNotEqual(original['version'],disabled['version'])
            self.assertEqual(original['password_hash'],disabled['password_hash'])
            self.invoke(path,'enable');self.assertTrue(self.records(path)[0]['enabled'])
            self.invoke(path,'remove');self.assertEqual(self.records(path),[])
