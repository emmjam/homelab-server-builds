#!/usr/bin/env python3
"""Read one literal credential from the manually supplied Rundeck secrets file."""
from pathlib import Path
import os
import re
import shlex
import stat
import sys

SECRETS_FILE = Path('/tmp/secrets.txt')


def read_secret(name, path=SECRETS_FILE, optional=False):
    if name not in {'RUNDECK_TOKEN', 'GITHUB_TOKEN', 'RUNDECK_URL', 'IAN_PASSWORD_HASH'}:
        raise ValueError('Unsupported credential name')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError('Cannot read /tmp/secrets.txt as the Rundeck service account') from None
    with os.fdopen(fd, 'r') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('/tmp/secrets.txt must be a regular file')
        if info.st_uid not in {0, os.geteuid()}:
            raise ValueError('/tmp/secrets.txt has an unexpected owner')
        matches = []
        for line in stream:
            match = re.fullmatch(r'([A-Z][A-Z0-9_]*)=(.*)', line.strip())
            if not match or match[1] != name:
                continue
            # Parse literal quoting only. Never source this file or evaluate shell code.
            try:
                parts = shlex.split(match[2], comments=False)
            except ValueError:
                raise ValueError(f'Malformed {name} entry in /tmp/secrets.txt') from None
            if len(parts) != 1 or not parts[0] or any(ord(c) < 32 for c in parts[0]):
                raise ValueError(f'Invalid {name} entry in /tmp/secrets.txt')
            matches.append(parts[0])
    if len(matches) > 1:
        raise ValueError(f'Duplicate {name} entries in /tmp/secrets.txt')
    if not matches:
        if optional:
            return ''
        raise ValueError(f'Missing {name} in /tmp/secrets.txt')
    return matches[0]


if __name__ == '__main__':
    try:
        if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != '--optional'):
            raise ValueError('Usage: read-secret.py NAME [--optional]')
        value = read_secret(sys.argv[1], optional=len(sys.argv) == 3)
    except UnicodeError:
        print('ERROR: Invalid secrets file encoding', file=sys.stderr)
        raise SystemExit(1)
    except ValueError as error:
        # All messages are controlled text; never include the value being read.
        print('ERROR: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
    if value:
        print(value)
