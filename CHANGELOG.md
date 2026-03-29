# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-29

### Added

- Initial release
- Full auth: local login, gateway bootstrap (url + callback-url + code), token import/export
- `auth setup-guide` command with first-time setup instructions
- Playback: play, pause, resume, stop, next, previous, seek, volume, repeat, shuffle
- Search with type filtering (track, album, artist, playlist)
- Track/album/artist/playlist show commands
- Queue: list, add (clear/remove honestly reported as unsupported by Spotify API)
- Playlist CRUD: create, rename, describe, add, remove, clear, reorder, replace
- Library: saved tracks/albums, save/unsave/check
- Discovery: top tracks/artists, recent, genre list/search, mood search, discover, radio
- Doctor diagnostics with actionable fixes
- Rich/plain/JSON output modes (`--json`, `--plain`)
- Retry with exponential backoff and Retry-After support
- Device selection chain (flag > active > env default)
- Honest degradation for removed API endpoints (recommendations, audio features, artist top tracks, related artists, queue clear/remove)
