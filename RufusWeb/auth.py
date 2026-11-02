"""Password authentication and revocable sessions; no infrastructure credentials."""
import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import logging
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

N,R,P=131072,8,1
PREFIX='scrypt-v1'

def password_hash(password):
    if not isinstance(password,str) or not 3<=len(password) or len(password.encode())>1024:
        raise ValueError('Use a passphrase of at least 3 characters and at most 1024 UTF-8 bytes')
    salt=secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode(),salt=salt,n=N,r=R,p=P,dklen=32,maxmem=256*1024*1024)
    return '$'.join([PREFIX,str(N),str(R),str(P),base64.b64encode(salt).decode(),base64.b64encode(digest).decode()])

def decode_hash(encoded):
    parts=encoded.split('$')
    if len(parts)!=6 or parts[:4]!=[PREFIX,str(N),str(R),str(P)]:raise ValueError('Unsupported password hash')
    salt,digest=(base64.b64decode(part,validate=True) for part in parts[4:])
    if len(salt)!=16 or len(digest)!=32:raise ValueError('Malformed password hash')
    return salt,digest

def password_valid(password,encoded):
    salt,expected=decode_hash(encoded)
    actual=hashlib.scrypt(password.encode(),salt=salt,n=N,r=R,p=P,dklen=32,maxmem=256*1024*1024)
    return hmac.compare_digest(actual,expected)

def username(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,64}',value):return ''
    return value.lower()

class Throttled(Exception):
    def __init__(self,seconds=900):self.seconds=max(1,int(seconds))

class Auth:
    def __init__(self,config,clock=time.time):
        self.config,self.clock=config,clock
        self.database=config['database'];self.lock=threading.BoundedSemaphore(1)
        self.dummy=PREFIX+'$131072$8$1$'+base64.b64encode(b'\0'*16).decode()+'$'+base64.b64encode(b'\0'*32).decode()
        self.accounts() # Fail closed before starting a listener.
        with self.db() as db:
            # Old code-issued sessions cannot authenticate against the v2 table.
            db.executescript('DROP TABLE IF EXISTS codes; DROP TABLE IF EXISTS sessions;'
                'CREATE TABLE IF NOT EXISTS web_sessions_v2(hash TEXT PRIMARY KEY,account TEXT,version TEXT,expires REAL,csrf_hash TEXT);'
                'CREATE TABLE IF NOT EXISTS preauth(hash TEXT PRIMARY KEY,expires REAL,csrf_hash TEXT);'
                'CREATE TABLE IF NOT EXISTS failures(kind TEXT,key TEXT,count INTEGER,start REAL,blocked REAL,PRIMARY KEY(kind,key));')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.database,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    @staticmethod
    def digest(value):return hashlib.sha256(value.encode()).hexdigest()
    def accounts(self):
        data=json.loads(Path(self.config['accounts_file']).read_text())
        if not isinstance(data,list):raise ValueError('Invalid accounts configuration')
        result={};ids=set()
        for account in data:
            if (not isinstance(account,dict) or set(account)!={'id','username','enabled','version','password_hash'}
                or username(account['username'])!=account['username'] or not account['username']
                or account['username'] in result or not isinstance(account['id'],str) or not account['id'] or account['id'] in ids
                or type(account['enabled']) is not bool or not isinstance(account['version'],str) or not account['version']):
                raise ValueError('Invalid accounts configuration')
            decode_hash(account['password_hash']);result[account['username']]=account;ids.add(account['id'])
        return result
    def cleanup(self,db):
        now=self.clock();window=self.config.get('failure_window',900)
        db.execute('DELETE FROM preauth WHERE expires<=?',(now,));db.execute('DELETE FROM web_sessions_v2 WHERE expires<=?',(now,))
        db.execute('DELETE FROM failures WHERE blocked<=? AND start<=?',(now,now-window))
    def prelogin(self):
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        with self.db() as db:
            self.cleanup(db)
            if db.execute('SELECT count(*) FROM preauth').fetchone()[0]>=1000:raise Throttled(60)
            db.execute('INSERT INTO preauth VALUES (?,?,?)',(self.digest(token),self.clock()+900,self.digest(csrf)))
        return token,csrf
    def pre_csrf(self,token,csrf):
        with self.db() as db:row=db.execute('SELECT * FROM preauth WHERE hash=?',(self.digest(token),)).fetchone()
        return bool(row and row['expires']>self.clock() and hmac.compare_digest(row['csrf_hash'],self.digest(csrf)))
    def check_limits(self,name,peer,db):
        now=self.clock()
        for kind,key in [('account',name),('ip',peer)]:
            row=db.execute('SELECT * FROM failures WHERE kind=? AND key=?',(kind,key)).fetchone()
            if row and row['blocked']>now:raise Throttled(row['blocked']-now)
    def failure(self,name,peer,db):
        now=self.clock();window=self.config.get('failure_window',900);block=self.config.get('lockout_seconds',900)
        for kind,key,limit in [('account',name,self.config.get('account_attempts',5)),('ip',peer,self.config.get('ip_attempts',20))]:
            row=db.execute('SELECT * FROM failures WHERE kind=? AND key=?',(kind,key)).fetchone()
            count=(row['count'] if row and row['start']>now-window else 0)+1
            start=row['start'] if row and row['start']>now-window else now
            db.execute('INSERT OR REPLACE INTO failures VALUES (?,?,?,?,?)',(kind,key,count,start,now+block if count>=limit else 0))
    def login(self,name,password,peer,pretoken,csrf):
        if not self.pre_csrf(pretoken,csrf):return None
        if not self.lock.acquire(blocking=False):raise Throttled(1)
        try:
            normal=username(name) or '<invalid>'
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE');self.cleanup(db);self.check_limits(normal,peer,db)
                if db.execute('SELECT count(*) FROM failures').fetchone()[0]>=10000:raise Throttled(60)
            account=self.accounts().get(normal)
            bounded=isinstance(password,str) and 0<len(password.encode())<=1024
            valid=bounded and password_valid(password,account['password_hash'] if account else self.dummy)
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE');self.check_limits(normal,peer,db)
                if not valid or not account or not account['enabled']:
                    self.failure(normal,peer,db);logging.info('Web authentication failed');return None
                if not self.pre_csrf(pretoken,csrf):return None
                token,new_csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
                db.execute('DELETE FROM preauth WHERE hash=?',(self.digest(pretoken),))
                db.execute('DELETE FROM failures WHERE kind=? AND key=?',('account',normal))
                db.execute('INSERT INTO web_sessions_v2 VALUES (?,?,?,?,?)',(self.digest(token),account['id'],account['version'],self.clock()+28800,self.digest(new_csrf)))
            logging.info('Web authentication succeeded');return token,new_csrf
        finally:self.lock.release()
    def session(self,token):
        with self.db() as db:row=db.execute('SELECT * FROM web_sessions_v2 WHERE hash=?',(self.digest(token),)).fetchone()
        if not row or row['expires']<=self.clock():return None
        accounts=self.accounts()
        account=next((a for a in accounts.values() if a['id']==row['account']),None)
        if not account or not account['enabled'] or account['version']!=row['version']:
            self.logout(token);return None
        return dict(row)
    def csrf(self,session,token):return bool(session and hmac.compare_digest(session['csrf_hash'],self.digest(token)))
    def logout(self,token):
        with self.db() as db:db.execute('DELETE FROM web_sessions_v2 WHERE hash=?',(self.digest(token),))
    def csrf_rotate(self,token):
        # Called once per authenticated page load. Other clients have distinct sessions.
        csrf=secrets.token_urlsafe(32)
        with self.db() as db:db.execute('UPDATE web_sessions_v2 SET csrf_hash=? WHERE hash=?',(self.digest(csrf),self.digest(token)))
        return csrf
    def admin(self,action,name):
        account=self.accounts().get(username(name))
        if not account:raise ValueError('Unknown account')
        with self.db() as db:
            if action=='revoke':db.execute('DELETE FROM web_sessions_v2 WHERE account=?',(account['id'],))
            elif action=='unlock':db.execute('DELETE FROM failures WHERE kind=? AND key=?',('account',account['username']))
            else:raise ValueError('Unknown administrative action')
