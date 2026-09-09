#!/bin/bash
# Install the host command bridge as a launchd LaunchAgent (run on the macOS host).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.user.hostserver"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
BIND="${SPEAK_SERVER_BIND:-127.0.0.1}"

mkdir -p "$HOME/Library/LaunchAgents"

sed -e "s#__SERVER_PY__#$DIR/server.py#" \
    -e "s#__LOG__#$DIR/server.log#" \
    -e "s#__BIND__#$BIND#" \
    "$DIR/com.user.hostserver.plist" > "$PLIST_DST"

launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load -w "$PLIST_DST"

echo "loaded $LABEL (bind $BIND:8787)"
sleep 1
curl -fsS "http://127.0.0.1:8787/health" && echo " <- health OK"
echo "secret: $DIR/secret"
