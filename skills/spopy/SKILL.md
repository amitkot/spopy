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
spopy pause | resume | next | previous
spopy seek 1:30                  # +10s, -15s, ms
spopy volume 50
spopy shuffle on | off | toggle
spopy repeat off | track | context

# Search
spopy search "query" --type track,album,artist,playlist

# Queue
spopy queue list | add "song"

# Playlists
spopy playlist list | create "Name" | items "Name"
spopy playlist add "Name" "song1" "song2"
spopy playlist remove "Name" "song1"
spopy playlist clear "Name"

# Library
spopy track save | unsave | check "song"
spopy library tracks | albums

# Devices
spopy devices list | transfer "Device Name"

# Discovery
spopy recent | top tracks | top artists
spopy genre list | genre search "rock"
spopy mood search "chill"

# Diagnostics
spopy doctor
spopy auth status | setup-guide
```

Accepts: Spotify URI, URL, ID, or search query.

Exit codes: 0 ok, 2 bad input, 3 auth error, 4 API error, 5 rate limit.

Auth is zero-config. If exit code 3, run `spopy auth login`.
