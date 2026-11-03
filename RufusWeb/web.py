"""Separate trusted-LAN browser client. The Rufus bearer credential stays server-side."""
import argparse
from contextlib import contextmanager
import html
from auth import Auth, Throttled
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
    return ((path=='/jobs' and method=='GET') or
            (path=='/executions' and method=='POST') or
            (method=='GET' and re.fullmatch(r'/executions/[1-9][0-9]*',path)) or
            (path=='/conversations' and method in ('GET','POST')) or
            (method=='GET' and re.fullmatch(r'/conversations/'+ident,path)) or
            (method=='POST' and re.fullmatch(r'/conversations/'+ident+r'/messages',path)) or
            (method=='GET' and re.fullmatch(r'/actions/'+ident,path)) or
            (method=='POST' and re.fullmatch(r'/actions/'+ident+r'/decision',path)))


def handler(config,auth,client):
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
                'Referrer-Policy':'same-origin','Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
                **(headers or {})}.items():self.send_header(key,value)
            self.end_headers();self.wfile.write(payload)
        def cookie(self,name='rufus_web'):
            try:
                cookie=SimpleCookie(self.headers.get('Cookie',''))
                return cookie[name].value if name in cookie else ''
            except Exception:return ''
        def dispatch(self,method):
            try:
                host=self.headers.get('Host','')
                scheme='https' if config.get('cookie_secure',False) else 'http'
                origin=scheme+'://'+host
                if origin not in config['allowed_origins']:
                    return self.respond(403,{'error':'Unapproved web host'})
                # CSRF tokens are authoritative; browsers may omit or obscure Origin.
                if method=='POST' and self.headers.get('Origin') not in (None,'null',origin):
                    return self.respond(403,{'error':'Same-origin browser request required'})
                if self.headers.get('Transfer-Encoding'):return self.respond(400,{'error':'Unsupported request encoding'})
                raw=b''
                if method=='POST':
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=8192:return self.respond(400,{'error':'Invalid request size'})
                    raw=self.rfile.read(length)
                token=self.cookie();session=auth.session(token)
                secure='; Secure' if config.get('cookie_secure',False) else ''
                if method=='GET' and self.path in ('/','/app.js','/style.css'):
                    if self.path=='/':
                        if session:
                            filename='index.html';csrf=auth.csrf_rotate(token);headers={}
                        else:
                            filename='login.html';pre,csrf=auth.prelogin()
                            headers={'Set-Cookie':'rufus_pre='+pre+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=900'+secure}
                        page=(assets/filename).read_text().replace('{{CSRF}}',html.escape(csrf,quote=True))
                        return self.respond(200,page,'text/html; charset=utf-8',headers)
                    filename=self.path[1:];kind='text/javascript' if filename.endswith('.js') else 'text/css'
                    return self.respond(200,(assets/filename).read_text(),kind)
                if self.path=='/login' and method=='POST':
                    values=parse_qs(raw.decode(),max_num_fields=3)
                    csrf=values.get('csrf',[''])[0]
                    if not auth.pre_csrf(self.cookie('rufus_pre'),csrf):return self.respond(403,{'error':'Invalid login CSRF token'})
                    result=auth.login(values.get('username',[''])[0],values.get('password',[''])[0],self.client_address[0],self.cookie('rufus_pre'),csrf)
                    if not result:return self.respond(401,'Sign-in failed. Check your credentials or contact the administrator. Go back to try again.','text/plain')
                    return self.respond(303,'','text/plain',{'Location':'/','Set-Cookie':'rufus_web='+result[0]+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+secure})
                if not session:return self.respond(401,{'error':'Session expired or revoked. Sign in again.'})
                if method=='POST' and not auth.csrf(session,self.headers.get('X-CSRF-Token','')):
                    return self.respond(403,{'error':'Invalid CSRF token; refresh the page'})
                if self.path=='/logout' and method=='POST':
                    auth.logout(token)
                    return self.respond(200,{'status':'signed_out'},headers={'Set-Cookie':'rufus_web=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'+secure})
                path=self.path.removeprefix('/api')
                if not self.path.startswith('/api/') or not allowed(method,path):return self.respond(404,{'error':'Endpoint not available to browser client'})
                body=json.loads(raw) if method=='POST' else None
                status,result=client.request(method,path,body)
                # Defence in depth: never reflect the managed bearer credential.
                result=json.loads(json.dumps(result).replace(getattr(client,'token','\x00'), '[REDACTED]'))
                return self.respond(status,result)
            except Throttled as error:
                logging.info('Web authentication throttled')
                self.respond(429,{'error':'Too many sign-in attempts. Try again later.'},headers={'Retry-After':str(error.seconds)})
            except (ValueError,UnicodeError):self.respond(400,{'error':'Malformed request'})
            except Exception:
                logging.error('Web request could not complete')
                self.respond(500,{'error':'Web service could not complete the request'})
        def do_GET(self):self.dispatch('GET')
        def do_POST(self):self.dispatch('POST')
    return Handler


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',default='/opt/rufus-web/config/config.json');parser.add_argument('--admin-action',choices=['revoke']);parser.add_argument('--username');args=parser.parse_args()
    config=json.loads(Path(args.config).read_text());auth=Auth(config)
    if args.admin_action:
        import os
        if os.geteuid()!=0:raise SystemExit('Administrative action requires root')
        auth.admin(args.admin_action,args.username)
    else:
        import ipaddress
        address=ipaddress.ip_address(config['bind_address'])
        if address.version!=4 or address.is_unspecified or not address.is_private:raise SystemExit('Require a specific private IPv4 binding')
        logging.basicConfig(level=logging.INFO)
        server=ThreadingHTTPServer((str(address),config.get('port',8788)),handler(config,auth,Client(config)))
        server.daemon_threads=True;server.serve_forever()
