# spopy

A production-quality Spotify CLI in a single Python file. Runs anywhere with [uv](https://docs.astral.sh/uv/) — no install step, no virtualenv, no package manager.

Designed for both local use and self-hosting on a remote gateway (Dokku, VPS, etc.).

## Features

- **Single file** — one script, zero config files, inline dependencies via PEP 723
- **Two auth modes** — local browser login or headless gateway bootstrap (paste-back flow)
- **Persistent tokens** — authenticate once, use forever (auto-refresh)
- **Full playback control** — play, pause, seek, volume, shuffle, repeat, queue
- **Search and browse** — tracks, albums, artists, playlists
- **Playlist management** — create, add, remove, reorder, clear, replace
- **Library operations** — save, unsave, check, list saved tracks/albums
- **Discovery** — top tracks/artists, recently played, genre/mood search
- **Three output modes** — rich (human), plain (pipes), JSON (machines)
- **Honest API handling** — unsupported endpoints are reported clearly, never faked
- **Safe for servers** — never leaks tokens, no secrets in logs or output

## Install

**Requirements:** [uv](https://docs.astral.sh/uv/) (Python package runner)

### One-liner

```bash
curl -fsSL https://raw.githubusercontent.com/amitkot/spopy/main/install.sh | bash
```

This checks for uv (installs it if missing), downloads `spopy` to `~/.local/bin/spopy`, and prints next steps.

### Manual

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Download the CLI
curl -fsSL https://raw.githubusercontent.com/amitkot/spopy/main/spopy -o ~/.local/bin/spopy
chmod +x ~/.local/bin/spopy
```

Or clone the repo and run directly:

```bash
git clone https://github.com/amitkot/spopy.git
cd spopy
./spopy --help
```

## Spotify App Setup

Before using the CLI, you need a Spotify Developer app. This is a one-time setup.

### 1. Create the app

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Log in with your Spotify account
3. Click **Create App**
4. Fill in:
   - **App name:** anything (e.g. "My CLI")
   - **App description:** anything
   - **Redirect URI:** `http://127.0.0.1:8888/callback`
   - **Which API/SDKs:** select **Web API**
5. Click **Save**
6. Go to **Settings** and note your **Client ID** and **Client Secret**

> **Important:** The redirect URI must be exactly `http://127.0.0.1:8888/callback` — not `localhost`, not `https`.

### 2. Set environment variables

```bash
export SPOTIFY_CLIENT_ID='your_client_id'
export SPOTIFY_CLIENT_SECRET='your_client_secret'
export SPOTIFY_REDIRECT_URI='http://127.0.0.1:8888/callback'
```

Add these to your shell profile (`~/.bashrc`, `~/.zshrc`) to persist them.

For Dokku deployments:

```bash
dokku config:set myapp SPOTIFY_CLIENT_ID='...' SPOTIFY_CLIENT_SECRET='...' SPOTIFY_REDIRECT_URI='...'
```

### 3. Verify setup

```bash
spopy auth status
spopy doctor
```

The CLI also has a built-in guide: `spopy auth setup-guide`

## Quick Start

### Local machine (has a browser)

```bash
spopy auth login
# Browser opens → approve → copy the redirect URL → paste when prompted
spopy status
spopy play "bohemian rhapsody"
```

### Remote gateway (no browser)

```bash
spopy auth url
# Copy the printed URL → open in a browser on another machine
# Approve → browser shows "Unable to connect" → copy the URL from the address bar
spopy auth callback-url 'http://127.0.0.1:8888/callback?code=XXXXX&state=YYYYY'
spopy status
```

### Transfer token from local to remote

```bash
# On local machine
spopy auth login
spopy auth export-token-info --raw --yes > token.json

# Copy token.json to remote, then:
spopy auth import-token-info token.json
```

## Configuration

All configuration is via environment variables.

### Required

| Variable | Description |
|---|---|
| `SPOTIFY_CLIENT_ID` | Spotify app client ID |
| `SPOTIFY_CLIENT_SECRET` | Spotify app client secret |
| `SPOTIFY_REDIRECT_URI` | Redirect URI (must match app settings) |

### Optional

| Variable | Default | Description |
|---|---|---|
| `SPOTIFY_CACHE_PATH` | `.spopy_cache` | Token cache file path |
| `SPOTIFY_USERNAME` | | Spotify username (for multi-user) |
| `SPOTIFY_SCOPES` | (sensible defaults) | Override OAuth scopes |
| `SPOTIFY_DEFAULT_DEVICE_ID` | | Fallback device ID |
| `SPOTIFY_DEFAULT_DEVICE_NAME` | | Fallback device name |
| `SPOTIFY_MARKET` | | ISO country code for market |
| `SPOTIFY_OUTPUT` | `rich` | Default output: `rich`, `plain`, `json` |
| `SPOTIFY_TIMEOUT_SECONDS` | `15` | API request timeout |
| `SPOTIFY_RETRIES` | `3` | Max retry attempts |
| `SPOTIFY_BACKOFF_FACTOR` | `0.5` | Exponential backoff factor |
| `SPOTIFY_DEBUG` | `0` | Enable debug logging (`1`) |
| `SPOTIFY_OPEN_BROWSER` | `1` | Allow browser opening (`0` to disable) |
| `SPOTIFY_NO_COLOR` | `0` | Disable color output (`1`) |
| `SPOTIFY_STATE_FILE` | | Path to persist auth state |

## Commands

### Global flags

```
--json          JSON output
--plain         Plain text output (pipe-friendly)
--debug         Debug logging
--market CC     Spotify market (ISO country code)
--device-id ID  Target device ID
--device-name N Target device name
--limit N       Result limit
--offset N      Result offset
--yes           Skip confirmations
--exact         Prefer exact name matches
--interactive   Interactive selection from results
--version       Show version
```

### Auth

| Command | Description |
|---|---|
| `auth setup-guide` | First-time setup instructions |
| `auth status` | Show auth config and token status |
| `auth url` | Print authorization URL (for gateway flow) |
| `auth login` | Interactive login (local browser) |
| `auth callback-url <url>` | Exchange redirect URL for tokens |
| `auth code <code>` | Exchange raw auth code for tokens |
| `auth import-token-info <path>` | Import token JSON (`-` for stdin) |
| `auth export-token-info` | Export token JSON (`--raw` for real tokens) |
| `auth whoami` | Show current user |
| `auth logout` | Remove token cache |

### Playback

| Command | Description |
|---|---|
| `play [query]` | Play or resume. Search query, URI, URL, or ID |
| `pause` | Pause playback |
| `resume` | Resume playback |
| `stop` | Stop (alias for pause — no true stop API) |
| `next` | Skip to next track |
| `previous` | Skip to previous |
| `seek <pos>` | Seek: `1:30`, `+10s`, `-15s`, or milliseconds |
| `volume <0-100>` | Set volume |
| `repeat <off\|track\|context>` | Set repeat mode |
| `shuffle <on\|off\|toggle>` | Set shuffle |

### Search

| Command | Description |
|---|---|
| `search <query>` | Search (`--type track,album,artist,playlist`) |

### Devices

| Command | Description |
|---|---|
| `devices list` | List available devices |
| `devices transfer <device>` | Transfer playback (name or ID) |

### Track

| Command | Description |
|---|---|
| `track show <query>` | Track details |
| `track play <query>` | Play a track |
| `track queue <query>` | Add to queue |
| `track save <query>` | Save to library |
| `track unsave <query>` | Remove from library |
| `track check <query>` | Check if saved |
| `track open <query>` | Print Spotify URL |
| `track audio <query>` | Audio features (restricted API) |

### Album

| Command | Description |
|---|---|
| `album show <query>` | Album details |
| `album play <query>` | Play album |
| `album tracks <query>` | List album tracks |
| `album save <query>` | Save to library |
| `album unsave <query>` | Remove from library |
| `album check <query>` | Check if saved |

### Artist

| Command | Description |
|---|---|
| `artist show <query>` | Artist details |
| `artist top <query>` | Top tracks (search-based) |
| `artist albums <query>` | List albums |
| `artist follow <query>` | Follow artist |
| `artist unfollow <query>` | Unfollow artist |
| `artist related <query>` | Related artists (restricted API) |

### Playlist

| Command | Description |
|---|---|
| `playlist list` | Your playlists (`--all` for full list) |
| `playlist show <pl>` | Playlist details |
| `playlist create <name>` | Create (`--description`, `--public/--private`) |
| `playlist rename <pl> <name>` | Rename |
| `playlist describe <pl> <desc>` | Set description |
| `playlist set-public <pl>` | Make public |
| `playlist set-private <pl>` | Make private |
| `playlist follow <pl>` | Follow playlist |
| `playlist unfollow <pl>` | Unfollow playlist |
| `playlist items <pl>` | List items |
| `playlist add <pl> <tracks...>` | Add tracks |
| `playlist remove <pl> <tracks...>` | Remove tracks |
| `playlist clear <pl>` | Remove all items |
| `playlist reorder <pl>` | Reorder (`--from`, `--to`, `--length`) |
| `playlist replace <pl> <tracks...>` | Replace all items |

### Library

| Command | Description |
|---|---|
| `library tracks` | Saved tracks |
| `library albums` | Saved albums |
| `library save <query>` | Save item |
| `library unsave <query>` | Remove item |
| `library check <query>` | Check if saved |

### Queue

| Command | Description |
|---|---|
| `queue list` | Current queue |
| `queue add <query>` | Add to queue |
| `queue clear` | Not supported (no API) |
| `queue remove` | Not supported (no API) |

### Discovery

| Command | Description |
|---|---|
| `status` | Current playback summary |
| `current` | Detailed now-playing info |
| `recent` | Recently played tracks |
| `top tracks` | Your top tracks (`--time-range`) |
| `top artists` | Your top artists (`--time-range`) |
| `discover` | Discovery suggestions from your history |
| `radio <query>` | Build a queue from a seed (search heuristic) |
| `genre list` | Well-known genres |
| `genre search <genre>` | Search by genre |
| `mood search <mood>` | Search by mood (heuristic) |
| `doctor` | Diagnose auth, config, devices, connectivity |

## Output Modes

### Rich (default)

```
$ spopy status
╭─ Bohemian Rhapsody  —  Queen  (A Night at the Opera) ───╮
│ Playing  2:15 / 5:55                                     │
│ Device: MacBook Pro  |  Volume: 65%  |  Shuffle: off     │
╰──────────────────────────────────────────────────────────╯
```

### JSON

```
$ spopy --json status
{
  "ok": true,
  "command": "status",
  "data": {
    "name": "Bohemian Rhapsody",
    "artists": "Queen",
    "playing": true,
    "progress": "2:15",
    "duration": "5:55",
    "device": "MacBook Pro"
  }
}
```

### Plain

```
$ spopy --plain status
Bohemian Rhapsody	Queen	A Night at the Opera	playing	2:15/5:55	MacBook Pro
```

## AI Agent Skill

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill is included for AI agents.

To install it, copy the `skills/` directory into your project or Claude Code config:

```bash
# Project-level
cp -r skills/ /path/to/your/project/.claude/skills/

# Or user-level
cp -r skills/ ~/.claude/skills/
```

The skill teaches the agent how to invoke the CLI, parse JSON output, and handle errors.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 2 | Invalid user input |
| 3 | Auth/config error |
| 4 | Spotify API error (Premium required, no device, 403, 404) |
| 5 | Rate limit exhausted |
| 10 | Internal error |

## Device Selection

For playback commands, devices are selected in this order:

1. `--device-id` flag
2. `--device-name` flag
3. Currently active Spotify device
4. `SPOTIFY_DEFAULT_DEVICE_ID` env var
5. `SPOTIFY_DEFAULT_DEVICE_NAME` env var
6. Error with helpful message

## Known Limitations

These are Spotify API limitations, not CLI bugs:

- **Queue clear/remove** — no API endpoint exists
- **Recommendations** — removed from Spotify API (Nov 2024)
- **Audio features** — restricted to apps with extended API access
- **Related artists** — restricted to apps with extended API access
- **Artist top tracks** — removed from API (Feb 2026); CLI uses search fallback
- **Search limit** — max 10 results per type (Spotify API limit)
- **Volume control** — some devices (phones, smart speakers) don't support remote volume
- **Premium required** — all playback control requires Spotify Premium

## License

MIT License. See [LICENSE](LICENSE).
