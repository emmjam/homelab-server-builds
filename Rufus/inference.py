"""Bounded, client-independent access to the configured HP inference backend."""
import http.client
import json
import math
import socket
from urllib.parse import urlsplit

from config import secret


class InferenceError(Exception):
    """Safe upstream error; never includes request content or credentials."""


class Client:
    def __init__(self, config):
        self.config = config
        self.url = urlsplit(config['url'])
        if (self.url.scheme not in ('http', 'https') or not self.url.hostname
                or self.url.username or self.url.password or self.url.query or self.url.fragment):
            raise ValueError('Invalid inference URL')
        self.connect_timeout = float(config.get('connect_timeout', 5))
        self.inference_timeout = float(config.get('inference_timeout', 120))
        self.chat_inference_timeout = float(config.get('chat_inference_timeout', self.inference_timeout))
        if not (0 < self.connect_timeout <= 30 and 0 < self.inference_timeout <= 300
                and math.isfinite(self.chat_inference_timeout) and 0 < self.chat_inference_timeout):
            raise ValueError('Invalid inference timeouts')

    def chat(self, messages, schema=None):
        data = {'model': self.config['model'], 'messages': messages, 'stream': False,
                'think': False, 'keep_alive': 0,
                'options': {'num_ctx': 4096 if schema is not None else int(self.config.get('chat_num_ctx',8192)),
                            'num_predict': 256 if schema is not None else int(self.config.get('chat_num_predict',2048)), 'temperature': 0}}
        if schema is None and self.config.get('chat_empty_thinking_prefill',False):
            # This retained template unconditionally opens <think>; complete the
            # empty block on the wire without changing stored conversation history.
            data['messages']=list(messages)+[{'role':'assistant','content':'<think>\n\n</think>\n\n'}]
        if schema is not None:
            data['format'] = schema
        headers = {'Content-Type': 'application/json'}
        if self.config.get('auth_secret_name'):
            headers['Authorization'] = 'Bearer ' + secret(
                self.config['auth_secret_file'], self.config['auth_secret_name'])
        connection_type = (http.client.HTTPSConnection if self.url.scheme == 'https'
                           else http.client.HTTPConnection)
        connection = connection_type(self.url.hostname, self.url.port, timeout=self.connect_timeout)
        try:
            connection.connect()
            connection.sock.settimeout(self.inference_timeout if schema is not None else self.chat_inference_timeout)
            connection.request('POST', self.url.path.rstrip('/') + '/api/chat',
                               body=json.dumps(data).encode(), headers=headers)
            response = connection.getresponse()
            if response.status == 404:
                raise InferenceError('Configured inference model or endpoint is unavailable')
            if response.status != 200:
                raise InferenceError('Inference backend returned an error')
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise InferenceError('Inference response exceeded the size limit')
            result = json.loads(raw)
            content = result['message']['content']
            if result.get('done') is not True or not isinstance(content, str) or not content.strip():
                raise ValueError()
            if schema is None:
                # Retained Qwen/Ollama can inline reasoning despite think=false,
                # sometimes omitting the opening tag. Never persist it as a reply.
                if result.get('done_reason') == 'length':
                    raise InferenceError('Inference response reached its limit before completing; try a shorter question')
                if '</think>' in content:
                    content = content.split('</think>', 1)[1].strip()
                if '<think>' in content or not content.strip():
                    raise InferenceError('Inference backend did not provide a final answer')
            if schema is not None:
                # Parsing is not schema validation; callers must validate their schema.
                json.loads(content)
            return content
        except (TimeoutError, socket.timeout):
            raise InferenceError('Inference backend timed out') from None
        except (OSError, http.client.HTTPException):
            raise InferenceError('Inference backend unavailable') from None
        except (ValueError, KeyError, TypeError):
            raise InferenceError('Inference backend returned an invalid response') from None
        finally:
            connection.close()
