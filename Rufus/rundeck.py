"""Bounded Rundeck JSON API client; credentials never enter errors or logs."""
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class IntegrationError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class Client:
    def __init__(self, url, token, timeout=10):
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('Invalid Rundeck URL')
        self.base = url.rstrip('/') + '/api/50/'
        self.token, self.timeout = token, timeout
        # Never forward authentication to redirects or environment-configured proxies.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, data=None):
        request = urllib.request.Request(self.base + path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'X-Rundeck-Auth-Token': self.token, 'Accept': 'application/json',
                     'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(1048577)
            if len(raw) > 1048576:
                raise IntegrationError('Rundeck response too large')
            result = json.loads(raw)
            if not isinstance(result, dict) or result.get('error'):
                raise IntegrationError('Unexpected Rundeck response')
            return result
        except urllib.error.HTTPError as error:
            error.close()
            if error.code in (401, 403):
                raise IntegrationError('Rundeck authentication or authorisation failed') from None
            raise IntegrationError('Rundeck HTTP request failed') from None
        except (TimeoutError, OSError, urllib.error.URLError):
            raise IntegrationError('Rundeck unreachable or request timed out', 504) from None
        except (ValueError, UnicodeError):
            raise IntegrationError('Malformed Rundeck response') from None

    def job(self, job):
        result = self.request('job/' + job + '/info')
        if result.get('id') != job or not isinstance(result.get('name'), str):
            raise IntegrationError('Unexpected Rundeck job response')
        return result

    def start(self, job, options):
        result = self.request('job/' + job + '/run', {'options': options})
        if type(result.get('id')) is not int or result['id'] <= 0:
            raise IntegrationError('Rundeck did not return a valid execution ID; check Rundeck before retrying')
        return result['id']

    def execution(self, execution):
        result = self.request('execution/' + str(execution))
        if result.get('id') != execution or result.get('status') not in {
            'queued', 'running', 'succeeded', 'failed', 'aborted', 'timedout',
            'failed-with-retry', 'scheduled', 'other'}:
            raise IntegrationError('Unexpected Rundeck execution response')
        return result

    def output(self, execution):
        result = self.request(f'execution/{execution}/output?format=json&lastlines=100')
        entries = result.get('entries')
        if not isinstance(entries, list) or any(not isinstance(e, dict) or not isinstance(e.get('log'), str) for e in entries):
            raise IntegrationError('Unexpected Rundeck output response')
        return [{'message': e['log'], 'level': e.get('level', 'INFO'),
                 'step': e.get('stepctx'), 'node': e.get('node')} for e in entries]
