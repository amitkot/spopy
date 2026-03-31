---
name: spopy
description: Control Spotify from the terminal — play, pause, search, queue, playlists
globs:
  - "spopy.py"
  - "spopy"
---

# spopy — Spotify CLI

```bash
spopy play "song name"
spopy pause
spopy resume
spopy next
spopy previous
spopy status
spopy search "query"
spopy queue add "song"
```

Accepts: Spotify URI, URL, ID, or search query.
Auto-selects device when only one is available.
Run `spopy --help` for full command list.

If auth fails (exit 3), run `spopy auth login`.
