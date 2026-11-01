"""Credential parsing and rejection checks using dummy values only."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('secret_reader',ROOT/'Rundeck/scripts/read-secret.py')
reader=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)

class SecretTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'secrets.txt'

    def write(self,text):
        self.path.write_text(text)
        self.path.chmod(0o600)

    def test_existing_store_format_and_key_blocks(self):
        self.write('# Local credentials\nRUNDECK_URL=http://example.invalid\nRUNDECK_TOKEN=dummy-api-token\n# Source: existing key\n-----BEGIN EXAMPLE KEY-----\nignored\n-----END EXAMPLE KEY-----\n')
        self.assertEqual(reader.read_secret('RUNDECK_TOKEN',self.path),'dummy-api-token')

    def test_password_hash_preserves_literal_dollar_signs(self):
        self.write("IAN_PASSWORD_HASH='$6$dummy-salt$dummy-hash'\n")
        self.assertEqual(reader.read_secret('IAN_PASSWORD_HASH', self.path),
                         '$6$dummy-salt$dummy-hash')

    def test_optional_github_entry(self):
        self.write('RUNDECK_TOKEN=dummy\n')
        self.assertEqual(reader.read_secret('GITHUB_TOKEN',self.path,optional=True),'')
        self.write('GITHUB_TOKEN="dummy-github-token"\n')
        self.assertEqual(reader.read_secret('GITHUB_TOKEN',self.path),'dummy-github-token')

    def test_missing_file_fails_even_for_optional_entry(self):
        with self.assertRaisesRegex(ValueError,'Cannot read'):
            reader.read_secret('RUNDECK_TOKEN',self.path,optional=True)

    def test_missing_required_entry(self):
        self.write('# no token\n')
        with self.assertRaisesRegex(ValueError,'Missing RUNDECK_TOKEN'):
            reader.read_secret('RUNDECK_TOKEN',self.path)

    def test_temporary_mode_777_is_accepted(self):
        self.write('RUNDECK_TOKEN=dummy\n');self.path.chmod(0o777)
        self.assertEqual(reader.read_secret('RUNDECK_TOKEN',self.path),'dummy')

    def test_symlink_is_rejected(self):
        actual=self.path.with_name('actual');actual.write_text('RUNDECK_TOKEN=dummy\n');actual.chmod(0o600)
        self.path.symlink_to(actual)
        with self.assertRaisesRegex(ValueError,'Cannot read'):
            reader.read_secret('RUNDECK_TOKEN',self.path)

    def test_duplicate_entry_is_rejected(self):
        self.write('RUNDECK_TOKEN=first\nRUNDECK_TOKEN=second\n')
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            reader.read_secret('RUNDECK_TOKEN',self.path)

    def test_shell_content_is_literal_and_never_executed(self):
        marker=Path(self.temp.name)/'must-not-exist'
        value=f'$(touch {marker})'
        self.write(f"RUNDECK_TOKEN='{value}'\n")
        self.assertEqual(reader.read_secret('RUNDECK_TOKEN',self.path),value)
        self.assertFalse(marker.exists())

    def test_errors_do_not_contain_values(self):
        self.write('RUNDECK_TOKEN="sensitive-dummy-without-closing-quote\n')
        try:reader.read_secret('RUNDECK_TOKEN',self.path)
        except ValueError as error:self.assertNotIn('sensitive-dummy',str(error))
        else:self.fail('Malformed entry accepted')


class CheckoutCredentialTests(unittest.TestCase):
    def run_checkout(self,file_github):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);repo=base/'repo';scripts=repo/'Rundeck/scripts'
            scripts.mkdir(parents=True);(repo/'Rundeck/jobs').mkdir();(repo/'Rundeck/pipelines').mkdir()
            secret=base/'secrets.txt'
            secret.write_text('RUNDECK_TOKEN=file-api-dummy\n'+('GITHUB_TOKEN=file-github-dummy\n' if file_github else ''))
            secret.chmod(0o600)
            (scripts/'read-secret.py').write_text((ROOT/'Rundeck/scripts/read-secret.py').read_text().replace("Path('/tmp/secrets.txt')",f'Path({str(secret)!r})'))
            updater=scripts/'update-github-checkout.sh'
            updater.write_text((ROOT/'Rundeck/scripts/update-github-checkout.sh').read_text().replace('REPO="/opt/homelab-server-builds"',f'REPO="{repo}"'))
            (repo/'Rundeck/jobs/test.yaml').write_text('- name: test\n  id: test-id\n  uuid: test-id\n  group: jobs\n')
            binaries=base/'bin';binaries.mkdir()
            git=binaries/'git';git.write_text('#!/usr/bin/env python3\nimport os\nassert os.environ["RD_OPTION_GITHUB_TOKEN"] == os.environ["EXPECTED_GITHUB"]\n');git.chmod(0o755)
            curl=binaries/'curl';curl.write_text('''#!/usr/bin/env python3
import sys,json
assert 'X-Rundeck-Auth-Token: file-api-dummy' in sys.argv
print(json.dumps({'failed':[]}) if any('/jobs/import' in x for x in sys.argv) else '[]')
''');curl.chmod(0o755)
            result=subprocess.run(['sh',str(updater)],env=dict(os.environ,PATH=f'{binaries}:'+os.environ['PATH'],RD_OPTION_GITHUB_TOKEN='storage-github-dummy',RD_OPTION_RUNDECK_API_TOKEN='old-api-must-not-be-used',EXPECTED_GITHUB='file-github-dummy' if file_github else 'storage-github-dummy'),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            for value in ['file-api-dummy','file-github-dummy','storage-github-dummy']:
                self.assertNotIn(value,result.stdout+result.stderr)

    def test_file_api_token_and_existing_github_storage(self):self.run_checkout(False)
    def test_file_github_token_takes_precedence(self):self.run_checkout(True)

if __name__=='__main__':unittest.main()
