#!/bin/bash
# Reads staged files

# If not in a git repo, exit early
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  ECHO "Not a git repository. Exiting."
  exit 0
fi

set -euo pipefail

# Get staged files
STAGED=$(git diff --cached --name-only 2>/dev/null)
if [ -z "$STAGED" ]; then
  exit 0
fi

# Get the actual diff of staged changes
DIFF=$(git diff --cached 2>/dev/null | head -c 8000 || true)  # cap size

echo STAGED FILES:
echo "$STAGED"

echo 

echo STAGED DIFF:
echo "$DIFF"