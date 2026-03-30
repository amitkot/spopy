# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-30

### Added

- Zero-config auth: built-in Spotify app client ID using PKCE (no secret needed)
- GitHub Pages callback page at spopy.amitkot.com/callback (replaces "Unable to connect" error)
- Auto-detect non-interactive usage: JSON output and --yes enabled when stdin is not a TTY

### Changed

- Default auth flow is now PKCE — no Spotify app setup required for new users
- Set `SPOTIFY_CLIENT_SECRET` to opt in to the classic OAuth flow with your own app
- Simplified setup guide, README, and install script for zero-config experience
- Environment variables renamed from `SPOTIPY_*`/`SPOTIFY_CLI_*` to `SPOTIFY_*` (old names accepted as fallbacks)

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
