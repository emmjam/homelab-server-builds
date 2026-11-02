#!/usr/bin/env python3
"""Run routine repository checks, retaining verbose output outside the summary."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    logs = Path(tempfile.mkdtemp(prefix='homelab-validation-'))
    results = []

    def record(name, action):
        path = logs / (name + '.log')
        with path.open('w') as output:
            try:
                success = action(output)
            except Exception as error:
                output.write(str(error) + '\n')
                success = False
        result = dict(check=name, status='PASS' if success else 'FAIL', log=str(path))
        results.append(result)
        print(json.dumps(result), flush=True)

    def command(args, output):
        return subprocess.run(args, cwd=ROOT, stdout=output,
                              stderr=subprocess.STDOUT, timeout=300).returncode == 0

    def shell_syntax(output):
        files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
        success = True
        for name in filter(None, files):
            path = ROOT / name
            if path.is_file() and (path.suffix == '.sh' or
                    path.read_bytes()[:100].split(b'\n')[0] in
                    (b'#!/bin/bash', b'#!/usr/bin/env bash')):
                output.write(name + '\n')
                output.flush()
                if not command(['bash', '-n', str(path)], output):
                    success = False
        return success

    record('shell-syntax', shell_syntax)
    suites = sorted({p.parent for p in (ROOT / 'tests').rglob('test_*.py')})
    for suite in suites:
        record('tests-' + '-'.join(suite.relative_to(ROOT / 'tests').parts),
               lambda output, suite=suite: command(
                   [sys.executable, '-m', 'unittest', 'discover', '-s', str(suite), '-v'], output))
    if not suites:
        record('test-discovery', lambda output: False)
    failed = sum(r['status'] == 'FAIL' for r in results)
    summary = dict(status='FAIL' if failed else 'PASS', checks=len(results),
                   failed=failed, logs=str(logs))
    (logs / 'summary.json').write_text(json.dumps(dict(summary=summary, results=results), indent=2) + '\n')
    print(json.dumps(summary))
    return int(bool(failed))


if __name__ == '__main__':
    sys.exit(main())
