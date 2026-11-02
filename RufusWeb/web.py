"""Separate loopback browser client. The Rufus bearer credential stays server-side."""
import argparse
from contextlib import contextmanager
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit
import urllib.error
import urllib.request


class Sessions:
    def __init__(self, database, clock=time.time):
        self.database,self.clock=database,clock
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS codes(hash TEXT PRIMARY KEY,expires REAL);'
                             'CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,expires REAL);')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.database,timeout=10)
        try:
            with db:yield db
        finally:db.close()
    @staticmethod
    def digest(value):return hashlib.sha256(value.encode()).hexdigest()
    def code(self):
        code=secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('DELETE FROM codes WHERE expires<=?',(self.clock(),))
            db.execute('DELETE FROM sessions WHERE expires<=?',(self.clock(),))
            db.execute('INSERT INTO codes VALUES (?,?)',(self.digest(code),self.clock()+180))
        return code
    def login(self,code):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT expires FROM codes WHERE hash=?',(self.digest(code),)).fetchone()
            if not row or row[0]<=self.clock():return None
            db.execute('DELETE FROM codes WHERE hash=?',(self.digest(code),))
            token=secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES (?,?)',(self.digest(token),self.clock()+28800))
        return token
    def valid(self,token):
        with self.db() as db:
            row=db.execute('SELECT expires FROM sessions WHERE hash=?',(self.digest(token),)).fetchone()
        return bool(row and row[0]>self.clock())
    def logout(self,token):
        with self.db() as db:db.execute('DELETE FROM sessions WHERE hash=?',(self.digest(token),))


class Client:
    def __init__(self,config):
        self.url=config['api_url'].rstrip('/')
        parsed=urlsplit(self.url)
        if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('Rufus API must use the configured loopback HTTP endpoint')
        self.token=Path(config['api_token_file']).read_text().strip()
        if not self.token:raise ValueError('Missing Rufus API credential')
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(self,method,path,body):
        request=urllib.request.Request(self.url+path,method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            with self.opener.open(request,timeout=20) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:
            # Do not reflect upstream authentication errors or arbitrary response bodies.
            if error.code in (400,403,404,409):
                try:return error.code,json.loads(error.read(16384))
                except ValueError:pass
            return 502,{'error':'Rufus API request failed; check its service and the managed web credential.'}
        except (OSError,ValueError):return 502,{'error':'Rufus API is unavailable. Your conversation remains saved.'}


def allowed(method,path):
    ident=r'[0-9a-f-]{36}'
    return ((path=='/conversations' and method in ('GET','POST')) or
            (method=='GET' and re.fullmatch(r'/conversations/'+ident,path)) or
            (method=='POST' and re.fullmatch(r'/conversations/'+ident+r'/messages',path)) or
            (method=='GET' and re.fullmatch(r'/actions/'+ident,path)) or
            (method=='POST' and re.fullmatch(r'/actions/'+ident+r'/decision',path)))


def handler(config,sessions,client):
    assets=Path(config.get('static_directory',Path(__file__).parent/'static'))
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup();self.connection.settimeout(15)
        def log_message(self,*args):logging.info('Web request completed')
        def respond(self,status,data,kind='application/json',headers=None):
            payload=json.dumps(data).encode() if kind=='application/json' else data.encode()
            self.send_response(status)
            for key,value in {'Content-Type':kind,'Content-Length':str(len(payload)),
                'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY',
                'Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
                **(headers or {})}.items():self.send_header(key,value)
            self.end_headers();self.wfile.write(payload)
        def cookie(self):
            try:
                cookie=SimpleCookie(self.headers.get('Cookie',''))
                return cookie['rufus_web'].value if 'rufus_web' in cookie else ''
            except Exception:return ''
        def dispatch(self,method):
            try:
                host=self.headers.get('Host','')
                parsed=urlsplit('http://'+host)
                if parsed.hostname not in config.get('allowed_hosts',['127.0.0.1','localhost']) or parsed.username or parsed.path or parsed.query or parsed.fragment or parsed.port is None:
                    return self.respond(403,{'error':'Unapproved web host'})
                if method=='POST' and self.headers.get('Origin')!='http://'+host:
                    return self.respond(403,{'error':'Same-origin browser request required'})
                if self.headers.get('Transfer-Encoding'):return self.respond(400,{'error':'Unsupported request encoding'})
                raw=b''
                if method=='POST':
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=8192:return self.respond(400,{'error':'Invalid request size'})
                    raw=self.rfile.read(length)
                if method=='GET' and self.path in ('/','/app.js','/style.css'):
                    if self.path=='/':
                        filename='index.html' if sessions.valid(self.cookie()) else 'login.html';kind='text/html; charset=utf-8'
                    else:filename=self.path[1:];kind='text/javascript' if filename.endswith('.js') else 'text/css'
                    return self.respond(200,(assets/filename).read_text(),kind)
                if self.path=='/login' and method=='POST':
                    values=parse_qs(raw.decode(),max_num_fields=2)
                    token=sessions.login(values.get('code',[''])[0])
                    if not token:return self.respond(401,'Login code invalid, expired or already used. Go back and request a fresh code through SSH.','text/plain')
                    return self.respond(303,'','text/plain',{'Location':'/','Set-Cookie':'rufus_web='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})
                token=self.cookie()
                if not sessions.valid(token):return self.respond(401,{'error':'Session expired. Sign in again using a fresh SSH-issued code.'})
                if self.path=='/logout' and method=='POST':
                    sessions.logout(token)
                    return self.respond(200,{'status':'signed_out'},headers={'Set-Cookie':'rufus_web=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
                path=self.path.removeprefix('/api')
                if not self.path.startswith('/api/') or not allowed(method,path):return self.respond(404,{'error':'Endpoint not available to browser client'})
                body=json.loads(raw) if method=='POST' else None
                status,result=client.request(method,path,body)
                # Defence in depth: never reflect the managed bearer credential.
                result=json.loads(json.dumps(result).replace(getattr(client,'token','\x00'), '[REDACTED]'))
                return self.respond(status,result)
            except (ValueError,UnicodeError):self.respond(400,{'error':'Malformed request'})
            except Exception:
                logging.error('Web request could not complete')
                self.respond(500,{'error':'Web service could not complete the request'})
        def do_GET(self):self.dispatch('GET')
        def do_POST(self):self.dispatch('POST')
    return Handler


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',default='/opt/rufus-web/config/config.json');parser.add_argument('--login-code',action='store_true');args=parser.parse_args()
    config=json.loads(Path(args.config).read_text());sessions=Sessions(config['database'])
    if args.login_code:print(sessions.code())
    else:
        logging.basicConfig(level=logging.INFO)
        server=ThreadingHTTPServer(('127.0.0.1',config.get('port',8788)),handler(config,sessions,Client(config)))
        server.daemon_threads=True;server.serve_forever()
