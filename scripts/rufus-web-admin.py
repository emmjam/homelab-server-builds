#!/usr/bin/env python3
"""Administrator-only hashed-account source management; no plaintext storage."""
import argparse
import getpass
import json
import os
from pathlib import Path
import shlex
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'RufusWeb'))
from auth import password_hash,username
parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['set-password','disable','enable','remove'])
parser.add_argument('username');parser.add_argument('--secrets-file',required=True)
args=parser.parse_args();name=username(args.username)
if not name:parser.error('Invalid username')
# Use the existing file and inode; never change its ownership or permissions.
fd=os.open(args.secrets_file,os.O_RDWR|os.O_NOFOLLOW)
with os.fdopen(fd,'r+') as f:
    lines=f.read().splitlines();key='RUFUS_WEB_ACCOUNTS';matches=[i for i,line in enumerate(lines) if line.startswith(key+'=')]
    if len(matches)>1:raise SystemExit('Duplicate account source entry')
    accounts=json.loads(shlex.split(lines[matches[0]].partition('=')[2])[0]) if matches else []
    account=next((a for a in accounts if a['username']==name),None)
    if args.action=='set-password':
        password=getpass.getpass('New Rufus password (3+ characters): ')
        if password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords differ')
        encoded=password_hash(password);del password
        if account is None:
            account={'id':str(uuid.uuid4()),'username':name};accounts.append(account)
        account.update(enabled=True,version=str(uuid.uuid4()),password_hash=encoded)
    else:
        if account is None:raise SystemExit('Unknown account')
        if args.action=='remove':accounts.remove(account)
        else:account.update(enabled=args.action=='enable',version=str(uuid.uuid4()))
    line=key+'='+shlex.quote(json.dumps(accounts,separators=(',',':')))
    if matches:lines[matches[0]]=line
    else:lines.append(line)
    f.seek(0);f.write('\n'.join(lines)+'\n');f.truncate();f.flush();os.fsync(f.fileno())
print('Account source updated. Transfer using the established secrets process, then run the managed Rufus Web deployment. No password or hash was printed.')
