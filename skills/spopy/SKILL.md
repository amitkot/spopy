---
name: spopy
description: Control Spotify from the terminal — play, pause, search, queue, playlists
globs:
  - "spopy.py"
  - "spopy"
---

# spopy — Spotify CLI

```bash
# Playback
spopy status
spopy play "song name"
spopy pause
spopy resume
spopy next
spopy previous
spopy seek 1:30                  # +10s, -15s, ms
spopy volume 50
spopy shuffle on                 # on, off, toggle
spopy repeat track               # off, track, context

# Search
spopy search "query" --type track
spopy search "query" --type album,artist,playlist

# Queue
spopy queue list
spopy queue add "song"

# Playlists
spopy playlist list
spopy playlist create "Name"
spopy playlist items "Name"
spopy playlist add "Name" "song1" "song2"
spopy playlist remove "Name" "song1"
spopy playlist clear "Name"

# Library
spopy track save "song"
spopy track unsave "song"
spopy track check "song"
spopy library tracks
spopy library albums

# Devices
spopy devices list
spopy devices transfer "Device Name"

# Discovery
spopy recent
spopy top tracks
spopy top artists
spopy genre list
spopy genre search "rock"
spopy mood search "chill"

# Diagnostics
spopy doctor
spopy auth status
spopy auth setup-guide
```

Accepts: Spotify URI, URL, ID, or search query.

Exit codes: 0 ok, 2 bad input, 3 auth error, 4 API error, 5 rate limit.

Auth is zero-config. If exit code 3, run `spopy auth login`.
