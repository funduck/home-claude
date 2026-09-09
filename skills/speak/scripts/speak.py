#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

# The spoken line is considered "seen" only if the terminal running Claude was
# frontmost AND the machine was active within this many seconds. Otherwise we
# also raise a desktop notification so the message isn't missed.
IDLE_GRACE = float(os.environ.get('NOTIFY_IDLE_SECONDS', '60'))


def _call():
    sys.path.insert(0, str(Path.home() / '.claude' / 'scripts' / 'server'))
    from client import call
    return call


# Spoken lines matching any of these never raise a desktop notification (the
# audio cue is enough; a banner for "waiting for input" is just noise).
NOTIFY_SUPPRESS = ('waiting for your input',)


def announce(title, text):
    """Speak `text`; unless the user was looking at the terminal, also notify."""
    call = _call()
    call('say', text=text)
    if any(s in text.lower() for s in NOTIFY_SUPPRESS):
        return
    focus = call('focus') or {}
    seen = focus.get('terminal_frontmost') and focus.get('idle_seconds', 1e9) < IDLE_GRACE
    if not seen:
        call('notify', title=title, message=text)


def has_running_subagents(session_id):
    f = Path(f'/tmp/claude-subagents-{session_id}')
    if not f.exists():
        return False
    events = f.read_text().strip().splitlines()
    return events.count('start') > events.count('stop')


def project_name():
    cwd = Path.cwd()

    # 1. Explicit one-liner override: .claude/project-name
    override = cwd / '.claude' / 'project-name'
    if override.exists():
        name = override.read_text().strip().splitlines()[0]
        if name:
            return name

    # 2. First H1 heading in CLAUDE.md
    claude_md = cwd / 'CLAUDE.md'
    if claude_md.exists():
        for line in claude_md.read_text().splitlines():
            if line.startswith('# '):
                return line[2:].strip()

    # 3. Git remote repo name
    try:
        result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            name = url.rstrip('/').split('/')[-1].removesuffix('.git')
            if name:
                return name
    except Exception:
        pass

    # 4. Directory basename
    return cwd.name


def format_path(path_str):
    p = Path(path_str).expanduser()
    name = p.name or path_str
    parent = p.parent.name
    if parent and parent not in ('', '.', '/'):
        return f"{name} in {parent}"
    return name


def format_url(url):
    parsed = urlparse(url)
    host = re.sub(r'^www\.', '', parsed.netloc)
    parts = [p for p in parsed.path.split('/') if p]
    if parts:
        return f"{host}, {parts[-1]}"
    return host


def format_command(cmd):
    first_line = cmd.split('\n')[0].strip()
    if len(first_line) > 50:
        return first_line[:47] + '...'
    return first_line


def make_message(data):
    tool_name = data.get('tool_name')

    if tool_name is None and 'message' not in data:
        session_id = data.get('session_id', '')
        if session_id and has_running_subagents(session_id):
            return None
        return f"{project_name()}: Done"

    if tool_name is None:
        msg = data.get('message', 'Attention needed')
        return msg.split('.')[0][:80]

    inp = data.get('tool_input', {})

    if tool_name == 'Bash':
        action = 'Run: ' + format_command(inp.get('command', ''))
    elif tool_name == 'Write':
        action = 'Write ' + format_path(inp.get('file_path', ''))
    elif tool_name in ('Edit', 'MultiEdit'):
        action = 'Edit ' + format_path(inp.get('file_path', ''))
    elif tool_name == 'Read':
        action = 'Read ' + format_path(inp.get('file_path', ''))
    elif tool_name == 'WebFetch':
        action = 'Fetch ' + format_url(inp.get('url', ''))
    elif tool_name == 'WebSearch':
        action = 'Search: ' + inp.get('query', '')[:30]
    else:
        action = tool_name or 'Permission needed'

    return f"{project_name()}: {action}"


if __name__ == '__main__':
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        announce('Claude', 'Claude needs attention')
        sys.exit(0)

    text = make_message(data)
    if text:
        announce(project_name(), text)
