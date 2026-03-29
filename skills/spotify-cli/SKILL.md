---
name: spotify-cli
description: Control Spotify from the terminal using spotify_cli.py — play, pause, search, queue, playlists, and more
globs:
  - "spotify_cli.py"
---

# Spotify CLI

`spotify_cli.py` is a single-file Spotify CLI. Run commands with `./spotify_cli.py` or `uv run spotify_cli.py`.

## Always use --json

Use `--json` for all commands to get machine-readable output:

```bash
./spotify_cli.py --json status
./spotify_cli.py auth --json status
./spotify_cli.py --json search "bohemian rhapsody"
```

JSON output shape: `{"ok": true, "command": "...", "data": {...}}`

For top-level commands (`status`, `doctor`, `search`, `play`, etc.), `--json` goes before the command.
For grouped commands (`auth`, `playlist`, `track`, etc.), `--json` goes after the group name.

## Quick reference

```bash
# Playback
./spotify_cli.py --json status              # what's playing
./spotify_cli.py play "song name"           # search and play
./spotify_cli.py play spotify:track:ID      # play by URI
./spotify_cli.py pause
./spotify_cli.py next
./spotify_cli.py seek 1:30                  # or +10s, -15s, 90000

# Search
./spotify_cli.py --json search "query" --type track
./spotify_cli.py --json search "query" --type album,artist

# Queue
./spotify_cli.py queue --json list
./spotify_cli.py queue add "song name"

# Playlists
./spotify_cli.py playlist --json list
./spotify_cli.py playlist create "Name"
./spotify_cli.py playlist add "Name" "song1" "song2"
./spotify_cli.py playlist remove "Name" "song1"
./spotify_cli.py playlist clear "Name" --yes

# Library
./spotify_cli.py track save "song name"
./spotify_cli.py library --json tracks

# Devices
./spotify_cli.py devices --json list
./spotify_cli.py devices transfer "Device Name"
```

## Auth

If commands fail with exit code 3, auth needs setup:

```bash
./spotify_cli.py auth setup-guide   # full instructions
./spotify_cli.py auth status        # check current state
./spotify_cli.py doctor             # diagnose all issues
```

Required env vars: `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`, `SPOTIPY_REDIRECT_URI`.

## Exit codes

- 0: success
- 2: invalid input (bad argument, no search results)
- 3: auth/config error (missing env vars, expired token)
- 4: Spotify API error (no device, Premium required, 403/404)
- 5: rate limit exhausted
- 10: internal error

## Unsupported operations

These have no Spotify API and the CLI reports them honestly:
- Queue clear / queue remove
- Recommendations (removed Nov 2024)
- Audio features (restricted to extended-access apps)
- Artist related (restricted to extended-access apps)
- Artist top tracks (removed Feb 2026 — uses search fallback)

## Resource inputs

Commands accept any of: Spotify URI (`spotify:track:ID`), URL (`https://open.spotify.com/track/ID`), raw ID, or a text search query. The CLI resolves automatically.
