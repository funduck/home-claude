#!/usr/bin/env python3
"""Host command bridge for Claude hooks.

A tiny HTTP server that runs on the macOS host and executes a fixed set of
named actions (say, open, ...) on behalf of Claude hooks running either on the
host or inside a devcontainer.

Safe by construction:
  - only named actions, each mapped to a hard-coded argv template
  - subprocess is always run with shell=False
  - every request must carry the shared secret from ./secret
"""
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / 'say'))
sys.path.insert(0, str(SCRIPT_DIR.parent / 'notification'))
from say import say  # noqa: E402 - scripts/say/say.py
from notification import notify, host_idle_seconds, frontmost_app  # noqa: E402 - scripts/notification/notification.py

PORT = int(os.environ.get('SPEAK_SERVER_PORT', '8787'))
BIND = os.environ.get('SPEAK_SERVER_BIND', '127.0.0.1')
TOKEN_FILE = Path(os.environ.get('SPEAK_SERVER_TOKEN_FILE', SCRIPT_DIR / 'secret'))

MAX_BODY = 64 * 1024
EXEC_TIMEOUT = 30
OUTPUT_CAP = 4 * 1024

_DEFAULT_TERMINAL_APPS = 'iTerm,Terminal,WezTerm,Alacritty,kitty,Ghostty,Hyper,tmux'
TERMINAL_APPS = [
    a.strip().lower()
    for a in os.environ.get('SPEAK_SERVER_TERMINAL_APPS', _DEFAULT_TERMINAL_APPS).split(',')
    if a.strip()
]

OPEN_ROOTS = [Path.home(), Path('/tmp'), Path('/private/tmp')]
_extra_root = os.environ.get('SPEAK_SERVER_OPEN_ROOTS', '')
if _extra_root:
    OPEN_ROOTS += [Path(p).expanduser() for p in _extra_root.split(':') if p]


class BadRequest(Exception):
    pass


def log(msg):
    print(msg, flush=True)


def load_token():
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text().strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(32)
    fd = os.open(str(TOKEN_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(tok + '\n')
    log(f'generated new secret at {TOKEN_FILE}')
    return tok


TOKEN = load_token()


# --- actions -----------------------------------------------------------------

_CONTROL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')


def _require_str(params, key, maxlen):
    val = params.get(key)
    if not isinstance(val, str) or not val:
        raise BadRequest(f'missing or invalid {key!r}')
    if len(val) > maxlen:
        raise BadRequest(f'{key!r} too long')
    if _CONTROL.search(val):
        raise BadRequest(f'{key!r} contains control characters')
    return val


def action_say(params):
    text = _require_str(params, 'text', 2000)
    ok = say(text, timeout=EXEC_TIMEOUT)
    return {'ok': bool(ok), 'code': 0 if ok else 1}


def action_open(params):
    target = _require_str(params, 'target', 2000)
    if target.startswith('-'):
        raise BadRequest('invalid target')
    parsed = urlparse(target)
    if parsed.scheme in ('http', 'https'):
        return ['open', '--', target]
    if parsed.scheme in ('', 'file'):
        raw = parsed.path if parsed.scheme == 'file' else target
        real = Path(os.path.realpath(os.path.expanduser(raw)))
        if not real.exists():
            raise BadRequest('target does not exist')
        if not any(_is_within(real, root) for root in OPEN_ROOTS):
            raise BadRequest('target outside allowed roots')
        return ['open', '--', str(real)]
    raise BadRequest(f'scheme {parsed.scheme!r} not allowed')


def action_notify(params):
    title = _require_str(params, 'title', 200)
    message = _require_str(params, 'message', 500)
    ok = notify(title, message, timeout=EXEC_TIMEOUT)
    return {'ok': bool(ok), 'code': 0 if ok else 1}


def _is_terminal(name, bundle):
    hay = f'{name} {bundle}'.lower()
    return any(app in hay for app in TERMINAL_APPS)


def action_focus(params):
    name, bundle = frontmost_app()
    return {
        'ok': True,
        'app': name,
        'bundle_id': bundle,
        'idle_seconds': host_idle_seconds(),
        'terminal_frontmost': _is_terminal(name, bundle),
    }


def _is_within(path, root):
    try:
        path.relative_to(os.path.realpath(root))
        return True
    except ValueError:
        return False


ACTIONS = {
    'say': action_say,
    'open': action_open,
    'notify': action_notify,
    'focus': action_focus,
}


# --- http ------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = 'hostbridge/1.0'

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # we do our own logging

    def do_GET(self):
        if self.path == '/health':
            self._send(200, {'ok': True})
        else:
            self._send(404, {'error': 'not found'})

    def do_POST(self):
        client = self.client_address[0]
        if self.path != '/run':
            self._send(404, {'error': 'not found'})
            return

        supplied = self.headers.get('X-Auth-Token', '')
        if not hmac.compare_digest(supplied, TOKEN):
            log(f'{client} POST /run -> 401 (bad token)')
            self._send(401, {'error': 'unauthorized'})
            return

        length = int(self.headers.get('Content-Length', '0') or '0')
        if length > MAX_BODY:
            self._send(413, {'error': 'body too large'})
            return
        try:
            data = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            self._send(400, {'error': 'invalid json'})
            return

        action = str(data.get('action'))
        handler = ACTIONS.get(action)
        if handler is None:
            log(f'{client} action={action!r} -> 400 (unknown action)')
            self._send(400, {'error': 'unknown action'})
            return

        try:
            result = handler(data)
        except BadRequest as e:
            log(f'{client} action={action!r} -> 400 ({e})')
            self._send(400, {'error': str(e)})
            return

        if isinstance(result, dict):
            log(f'{client} action={action!r} -> 200 (in-process, ok={result.get("ok")})')
            self._send(200, result)
            return

        argv = result
        try:
            proc = subprocess.run(
                argv, shell=False, capture_output=True, text=True,
                timeout=EXEC_TIMEOUT,
                check=False
            )
        except subprocess.TimeoutExpired:
            log(f'{client} action={action!r} -> 504 (timeout)')
            self._send(504, {'error': 'command timed out'})
            return
        except FileNotFoundError:
            log(f'{client} action={action!r} -> 500 ({argv[0]} not found)')
            self._send(500, {'error': f'{argv[0]} not found'})
            return

        log(f'{client} action={action!r} -> 200 (exit {proc.returncode})')
        self._send(200, {
            'ok': proc.returncode == 0,
            'code': proc.returncode,
            'stdout': proc.stdout[:OUTPUT_CAP],
            'stderr': proc.stderr[:OUTPUT_CAP],
        })

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except Exception as e:  # noqa: BLE001 - never leak a stack trace
            log(f'handler error: {e!r}')


def main():
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    httpd.timeout = 10
    log(f'listening on {BIND}:{PORT}; actions: {", ".join(sorted(ACTIONS))}')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log('shutting down')
        httpd.shutdown()


if __name__ == '__main__':
    sys.exit(main())
