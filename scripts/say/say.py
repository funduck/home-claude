#!/usr/bin/env python3
#
# This script provides a simple command-line interface to speak text using the macOS `say` command or a cross-platform TTS engine. It detects whether the input text is in Russian and selects the appropriate voice for speech synthesis.

from pathlib import Path
import re
import subprocess
import sys

def is_russian(text):
    return bool(re.search('[А-Яа-яЁё]', text))

def say(text, timeout=None):
    """Speak text. Returns True if the TTS command ran to completion."""
    russian = is_russian(text)
    if sys.platform == 'darwin':
        voice = 'Milena' if russian else 'Samantha'
        argv = ['say', '-v', voice, '--', text]
    else:
        voice = 'ru_RU-irina-medium' if russian else 'en_US-lessac-medium'
        argv = ['python3', '-m', 'piper', '-m', voice, '--data-dir', str(Path.home() / '.piper'), '--', text]
    try:
        return subprocess.run(argv, timeout=timeout).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f'say: {e}', file=sys.stderr)
        return False

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: say.py <text>")
        sys.exit(1)
    text = ' '.join(sys.argv[1:])
    say(text)
