# Host command bridge

A tiny stdlib HTTP server that runs on the **macOS host** and executes a fixed
set of named actions for Claude hooks — whether the hook runs on the host or
inside the Linux devcontainer.

## Design

- **Only named actions.** The client sends `{"action": "say", "text": "..."}`.
  The server maps each action to a hard-coded `argv` and runs it with
  `shell=False`. No client-supplied binary, flags, or shell string.
- **Shared secret.** `./secret` (auto-generated on first run, mode `0600`,
  git-ignored). Every `POST /run` must send it as `X-Auth-Token`.
- **Plain HTTP.** Host reaches it at `127.0.0.1:8787`; the devcontainer reaches
  it at `host.docker.internal:8787` (the container already bind-mounts
  `~/.claude`, so it reads the same `secret` file).

## Actions

| action   | params                          | runs                                   |
|----------|---------------------------------|----------------------------------------|
| `say`    | `text`                          | `scripts/say/say.py`'s `say()` in-process (macOS `say -v <voice>`, else `piper`); voice picked by language |
| `open`   | `target` (http/https URL, or existing path under `$HOME` / `/tmp`) | `open -- TARGET` |
| `notify` | `title`, `message`              | `osascript -e 'display notification …'` |

Add more in the `ACTIONS` dict in `server.py`. A handler returns an `argv` list
(run via `subprocess`, `shell=False`) or a result `dict` (work already done).

## Install (on the Mac)

```sh
.claude/scripts/server/install.sh          # loads a launchd LaunchAgent
# or, if the container can't reach 127.0.0.1:
SPEAK_SERVER_BIND=0.0.0.0 .claude/scripts/server/install.sh
```

Run manually instead:

```sh
python3 .claude/scripts/server/server.py
```

## Use

```sh
python3 .claude/scripts/server/client.py say "hello"
python3 .claude/scripts/server/client.py open https://example.com
```

Environment overrides: `SPEAK_SERVER_HOST`, `SPEAK_SERVER_PORT`,
`SPEAK_SERVER_BIND`, `SPEAK_SERVER_TOKEN_FILE`, `SPEAK_SERVER_OPEN_ROOTS`.
