#!/usr/bin/env python3
#
# Desktop notifications on the macOS host, plus helpers to tell whether the user
# is actually looking at the terminal running Claude (frontmost app + input
# idle time). Mirrors scripts/say/say.py: plain functions usable in-process and
# a small CLI.

import json
import re
import subprocess
import sys


def notify(title, message, timeout=None):
    """Show a macOS notification banner. Returns True if osascript exited 0."""
    script = f'display notification {json.dumps(message)} with title {json.dumps(title)}'
    argv = ['osascript', '-e', script]
    try:
        return subprocess.run(argv, timeout=timeout).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f'notify: {e}', file=sys.stderr)
        return False


def _run(argv, timeout=5):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f'notify: {e}', file=sys.stderr)
        return ''


def host_idle_seconds():
    """Seconds since the last HID (keyboard/mouse) event on the host.

    Returns 0.0 on non-darwin platforms or if the value can't be read.
    """
    if sys.platform != 'darwin':
        return 0.0
    m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', _run(['ioreg', '-c', 'IOHIDSystem']))
    return int(m.group(1)) / 1_000_000_000 if m else 0.0


def frontmost_app():
    """(display_name, bundle_id) of the frontmost macOS app; ('', '') on failure.

    Uses `lsappinfo`, which needs no Automation/Accessibility permission. Falls
    back to System Events via osascript if `lsappinfo` is unavailable.
    """
    if sys.platform != 'darwin':
        return ('', '')
    front = _run(['lsappinfo', 'front']).strip()
    if front:
        info = _run(['lsappinfo', 'info', '-only', 'name', '-only', 'bundleID', front])
        name = re.search(r'"LSDisplayName"\s*=\s*"([^"]*)"', info)
        bundle = re.search(r'"CFBundleIdentifier"\s*=\s*"([^"]*)"', info)
        if name or bundle:
            return (name.group(1) if name else '', bundle.group(1) if bundle else '')
    name = _run([
        'osascript', '-e',
        'tell application "System Events" to get name of first application process whose frontmost is true',
    ]).strip()
    return (name, '')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: notification.py <title> <message>')
        sys.exit(1)
    notify(sys.argv[1], ' '.join(sys.argv[2:]))
