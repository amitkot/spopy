---
name: spopy
description: Control Spotify from the terminal using spopy — play, pause, search, queue, playlists, and more
globs:
  - "spopy"
---

# spopy

`spopy` is a single-file Spotify CLI. Run commands with `spopy` or `./spopy`.

## Always use --json

Use `--json` for all commands to get machine-readable output:

```bash
spopy --json status
spopy auth --json status
spopy --json search "bohemian rhapsody"
```

JSON output shape: `{"ok": true, "command": "...", "data": {...}}`

For top-level commands (`status`, `doctor`, `search`, `play`, etc.), `--json` goes before the command.
For grouped commands (`auth`, `playlist`, `track`, etc.), `--json` goes after the group name.

## Quick reference

```bash
# Playback
spopy --json status              # what's playing
spopy play "song name"           # search and play
spopy play spotify:track:ID      # play by URI
spopy pause
spopy next
spopy seek 1:30                  # or +10s, -15s, 90000

# Search
spopy --json search "query" --type track
spopy --json search "query" --type album,artist

# Queue
spopy queue --json list
spopy queue add "song name"

# Playlists
spopy playlist --json list
spopy playlist create "Name"
spopy playlist add "Name" "song1" "song2"
spopy playlist remove "Name" "song1"
spopy playlist clear "Name" --yes

# Library
spopy track save "song name"
spopy library --json tracks

# Devices
spopy devices --json list
spopy devices transfer "Device Name"
```

## Auth

If commands fail with exit code 3, auth needs setup:

```bash
spopy auth setup-guide   # full instructions
spopy auth status        # check current state
spopy doctor             # diagnose all issues
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
