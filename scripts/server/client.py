#!/usr/bin/env python3
"""Client for the host command bridge (see server.py).

Usable as a module:

    from client import call
    call('say', text='hello')

or as a CLI:

    client.py say "hello there"
    client.py open https://example.com
    client.py notify "Title" "message body"
    client.py focus

Fail-soft: any transport error prints a warning to stderr and returns None
(exit 0 for the CLI) so a hook never blocks Claude.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

PORT = os.environ.get('SPEAK_SERVER_PORT', '8787')
TOKEN_FILE = Path(os.environ.get('SPEAK_SERVER_TOKEN_FILE', SCRIPT_DIR / 'secret'))
TIMEOUT = 5


def _default_host():
    if os.environ.get('SPEAK_SERVER_HOST'):
        return os.environ['SPEAK_SERVER_HOST']
    if Path('/.dockerenv').exists():
        return 'host.docker.internal'
    return '127.0.0.1'


def _token():
    try:
        return TOKEN_FILE.read_text().strip()
    except OSError:
        return ''


def call(action, **params):
    """POST an action to the host bridge. Returns the response dict or None."""
    host = _default_host()
    url = f'http://{host}:{PORT}/run'
    body = json.dumps({'action': action, **params}).encode()
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('X-Auth-Token', _token())
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')
        print(f'host-bridge: {action} -> HTTP {e.code} {detail}', file=sys.stderr)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        print(f'host-bridge: {action} unreachable ({e})', file=sys.stderr)
    return None


def _main(argv):
    if not argv:
        print(__doc__)
        return 0
    action = argv[0]
    if action == 'say':
        result = call('say', text=' '.join(argv[1:]))
    elif action == 'open':
        result = call('open', target=argv[1])
    elif action == 'notify':
        result = call('notify', title=argv[1], message=argv[2])
    elif action == 'focus':
        result = call('focus')
    else:
        result = call(action, **dict(a.split('=', 1) for a in argv[1:]))
    if result is None:
        return 0  # fail-soft
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
