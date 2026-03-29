# Spotify CLI — Full Specification

## Overview

A production-quality, single-file Spotify CLI in Python using Spotipy.

Output only one complete file named `spotify_cli.py`. Single file, directly runnable with uv using PEP 723 inline metadata header.

## File Header (exact shape)

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "spotipy==2.26.0",
#   "typer==0.24.1",
#   "rich==14.3.3",
# ]
# ///
```

## Core Product Goals

1. CLI, not MCP server.
2. Designed for self-hosting on a remote Linux gateway (Dokku app), also works locally.
3. Authentication: two first-class bootstrap modes:
   - local bootstrap
   - gateway bootstrap by printing a URL, having the user open it elsewhere, then calling the CLI again with the returned callback URL or auth code
4. Persist token state in a configurable cache file (usually one-time setup).
5. Read auth and runtime config from environment variables (injectable via Dokku config).
6. Rich set of Spotify CLI operations with honest handling of unsupported endpoints.
7. Safe for server use — never leak secrets or full tokens.

## High-Level Implementation Style

1. `typer` for CLI
2. `rich` for output (tables, panels, errors, status summaries)
3. `spotipy` for Spotify API integration and auth
4. Only standard library beyond pinned deps
5. Single file, clearly structured with:
   - constants
   - dataclasses or typed models
   - env/config loading
   - auth manager construction
   - token cache helpers
   - resource parsing and resolution helpers
   - Spotify service layer
   - command handlers
   - output formatting helpers
   - main app entrypoint
6. Type hints throughout
7. Docstrings on all non-trivial functions
8. Modern Python 3.12+ style
9. Robust error handling and precise exit codes

## Exit Codes

- 0 success
- 2 invalid user input
- 3 auth/config error
- 4 Spotify API error, permission error, premium/device/playback error
- 5 rate limit or retryable transient failure exhausted
- 10 unexpected internal failure

## Environment Variables

Required auth variables:
- SPOTIPY_CLIENT_ID
- SPOTIPY_CLIENT_SECRET
- SPOTIPY_REDIRECT_URI

Optional auth/runtime variables:
- SPOTIPY_CACHE_PATH
- SPOTIPY_USERNAME
- SPOTIFY_CLI_SCOPES
- SPOTIFY_CLI_DEFAULT_DEVICE_ID
- SPOTIFY_CLI_DEFAULT_DEVICE_NAME
- SPOTIFY_CLI_MARKET
- SPOTIFY_CLI_OUTPUT              allowed: rich, plain, json
- SPOTIFY_CLI_TIMEOUT_SECONDS
- SPOTIFY_CLI_RETRIES
- SPOTIFY_CLI_BACKOFF_FACTOR
- SPOTIFY_CLI_DEBUG               allowed: 0, 1
- SPOTIFY_CLI_OPEN_BROWSER        allowed: 0, 1
- SPOTIFY_CLI_NO_COLOR            allowed: 0, 1
- SPOTIFY_CLI_TOKEN_IMPORT_JSON   optional path to token-info JSON used for bootstrap/import
- SPOTIFY_CLI_STATE_FILE          optional path used to persist auth state for manual callback handling

## Default Scopes

If SPOTIFY_CLI_SCOPES is not set, use:
- user-read-playback-state
- user-read-currently-playing
- user-modify-playback-state
- playlist-read-private
- playlist-read-collaborative
- playlist-modify-private
- playlist-modify-public
- user-library-read
- user-library-modify
- user-top-read
- user-read-recently-played
- user-follow-read
- user-follow-modify
- user-read-private

## Authentication Design Requirements

### Bootstrap Mode A — Local Bootstrap
- User runs CLI locally with a browser
- CLI can open browser or print URL
- Callback lands on registered redirect URI
- CLI exchanges code, stores token data, can optionally export token-info

### Bootstrap Mode B — Gateway Bootstrap
- User runs CLI on gateway
- CLI generates and prints authorization URL
- User opens URL from separate machine with a browser
- User copies either the full redirected callback URL, or the raw code
- CLI exchanges code and stores token data on gateway
- Do NOT assume gateway can/should open a browser
- Do NOT assume gateway must run a listener on a network port during auth
- Do NOT require inbound connectivity to gateway
- Manual paste-back flow is a first-class happy path

## Required Auth Commands

### `auth status`
- validate auth env vars
- show configured redirect URI
- show cache path
- show whether token cache exists
- show whether token appears expired
- show whether refresh token is present
- show current authenticated user if possible
- never print full access token or full refresh token
- show only safe summaries (masked suffixes)

### `auth url`
- generate and print authorization URL
- support `--json`
- include URL, scope summary, redirect URI, state in JSON output
- optionally save auth state to SPOTIFY_CLI_STATE_FILE if configured

### `auth login`
- default login flow for local use
- support `--open-browser/--no-open-browser`
- respect SPOTIFY_CLI_OPEN_BROWSER
- if browser not opened, print auth URL and explain next step
- if local callback flow possible, use it
- otherwise tell user to use `auth callback-url` or `auth code`

### `auth callback-url <full_redirected_url>`
- parse full redirected URL pasted by user
- validate `code` and optional `state`
- exchange code for token data
- store token cache to configured path
- print success summary and authenticated user

### `auth code <authorization_code>`
- accept raw authorization code
- support optional `--state`
- exchange for tokens
- store token cache
- print success summary

### `auth import-token-info <path-or-dash>`
- import token-info JSON produced by local bootstrap or export command
- support `-` for stdin
- validate required fields
- save to configured cache path
- print safe success summary

### `auth export-token-info`
- export token-info JSON to stdout or `--out <path>`
- support `--masked` for safe display
- support `--raw` for actual export
- default must be safe (not secret-leaking)
- if `--raw` used, warn clearly unless `--yes` also given

### `auth whoami`
- show current user profile summary

### `auth logout`
- remove local token cache after confirmation
- support `--yes`

### `doctor`
- validate env vars
- validate cache path and directory permissions
- validate token load/refresh
- validate current user lookup
- validate device list lookup
- print actionable diagnoses and fixes
- section explaining whether current auth state is healthy enough for playback commands

## Auth Implementation Requirements

1. Use `SpotifyOAuth` or compatible Spotipy auth helpers
2. Make cache path explicit and configurable
3. Support manual auth code handling without forcing a live callback listener
4. Support token refresh automatically
5. Support importing token-info JSON created elsewhere
6. Support exporting token-info for transfer between local machine and gateway
7. Validate missing env vars and show exactly which are missing
8. Validate redirect URI mismatch and explain it clearly
9. Never log secrets in debug output
10. Common operational flow:
    - local login once → export token-info → import on gateway → continue normally
11. Gateway bootstrap:
    - auth url → open in browser elsewhere → auth callback-url or auth code → continue normally

## Global CLI Options

- `--json`
- `--plain`
- `--debug`
- `--market <market>`
- `--device-id <device-id>`
- `--device-name <device-name>`
- `--limit <n>`
- `--offset <n>`
- `--no-color`
- `--yes`
- `--exact`
- `--interactive`
- `--type <resource-type>`

## Output Modes

- rich: default human mode with Rich tables/panels
- plain: pipe-friendly plain text, line-based or tab-separated
- json: stable machine-friendly JSON envelope

### JSON Output Shape
```json
{
  "ok": true,
  "command": "play",
  "data": { ... }
}
```

## Resource Normalization and Resolution

Helpers that accept and normalize:
- Spotify URI (spotify:track:...)
- Spotify URL (open.spotify.com/...)
- raw Spotify ID
- plain text search query

Resolvers infer resource type from:
- URI prefix
- URL path
- explicit `--type`
- command context

Resolution behavior:
- `track play` prefers track resolution
- `album play` prefers album resolution
- generic `play` resolves track first, then album, then playlist unless overridden
- `queue add` prefers track resolution
- `playlist add` accepts mixed track URIs and track queries

Plain text query resolution:
- resolve by search
- pick top result by default
- `--interactive`: let user choose from numbered list
- `--exact`: prefer exact-ish matches

## Device Selection Behavior

For playback-changing commands:
1. If `--device-id` given, use it
2. Else if `--device-name` given, resolve it
3. Else if there is an active device, use that
4. Else if default device env vars configured, use those
5. Else fail with clear message

## Required Command Groups

### A. General and State

#### `status`
- combined playback summary: current item, device, progress, playing/paused state, repeat, shuffle, volume

#### `current` (alias: `now`)
- detailed currently playing item
- item name, type, artists, album/show, progress, duration, URI, URL, device

#### `devices list`
- list all available devices
- mark active device
- include id, name, type, active, restricted, volume

#### `devices transfer <device>`
- accept device id or name
- support `--play/--no-play`

### B. Playback Control

#### `play [query_or_uri]`
- no argument: resume playback
- track URI/ID/query: play that track
- album/playlist URI/ID/query: play that context
- support `--device-id`, `--device-name`, `--position-ms`, `--from-track-number`

#### `pause`
#### `resume` (explicit alias of play without target)
#### `stop` (honest alias for pause, documented as no true stop endpoint)
#### `next`
#### `previous` (alias: `prev`)

#### `seek <position>`
- accept milliseconds
- accept mm:ss
- accept relative forms: +10s, -15s
- validate bounds when duration is known

#### `volume <percent>` (alias: `vol`)
- integers 0..100

#### `repeat <off|track|context>`
#### `shuffle <on|off|toggle>`

### C. Queue Commands

#### `queue list`
#### `queue add <query_or_uri>`
- resolve to track or episode
#### `queue clear`
- honest explanation if first-class clear not available
#### `queue remove <query_or_uri>`
- honest explanation if queue-item removal not available
- clarify that playlist item removal is supported but queue item removal may not be

### D. Search and Browse

#### `search <query>`
- `--type track|album|artist|playlist` (multiple types)
- `--limit`, `--market`, `--exact`
- concise results tables with URI and URL

#### `track show <query_or_uri>`
#### `album show <query_or_uri>`
#### `artist show <query_or_uri>`
#### `playlist show <query_or_uri>`

Each show command: resolve target, fetch metadata, print human summary, support JSON output

### E. Track Commands

#### `track play <query_or_uri>`
#### `track queue <query_or_uri>`
#### `track save <query_or_uri>`
#### `track unsave <query_or_uri>`
#### `track check <query_or_uri>`
#### `track open <query_or_uri>` (print Spotify URL only)
#### `track audio <query_or_uri>` (audio metadata if available, else graceful failure)

### F. Album Commands

#### `album play <query_or_uri>`
#### `album tracks <query_or_uri>`
#### `album save <query_or_uri>`
#### `album unsave <query_or_uri>`
#### `album check <query_or_uri>`

### G. Artist Commands

#### `artist top <query_or_uri>`
#### `artist albums <query_or_uri>`
#### `artist follow <query_or_uri>`
#### `artist unfollow <query_or_uri>`
#### `artist related <query_or_uri>` (degrade gracefully if unsupported)

### H. Playlist Commands

#### `playlist list` (alias: `ls`)
- `--limit`, `--offset`, `--all`

#### `playlist create <name>`
- `--description`, `--public/--private`, `--collaborative`

#### `playlist rename <playlist> <new_name>`
#### `playlist describe <playlist> <description>`
#### `playlist set-public <playlist>`
#### `playlist set-private <playlist>`
#### `playlist follow <playlist>`
#### `playlist unfollow <playlist>`

#### `playlist items <playlist>`
- list items with paging support

#### `playlist add <playlist> <one_or_more_queries_or_uris>`
- support multiple inputs, resolve text queries to tracks

#### `playlist remove <playlist> <one_or_more_queries_or_uris>` (alias: `rm`)
- support duplicates, `--all-matches`, `--first-match`

#### `playlist clear <playlist>`
- require confirmation unless `--yes`

#### `playlist reorder <playlist> --from <i> --to <j> [--length <n>]`

#### `playlist replace <playlist> <one_or_more_queries_or_uris>`
- replace playlist items entirely
- require confirmation unless `--yes`

### I. Library Commands

#### `library tracks`
#### `library albums`
#### `library check <query_or_uri>`
#### `library save <query_or_uri>`
#### `library unsave <query_or_uri>`
#### `recent`
#### `top tracks`
#### `top artists`

### J. Discovery Helpers

#### `genre list`
- use genre seeds if available, degrade gracefully otherwise

#### `genre search <genre>`
- search across tracks, artists, playlists

#### `mood search <mood>`
- heuristic, not guaranteed first-class Spotify metadata
- moods: chill, focus, happy, sad, workout, sleep, party, study
- clearly documented as heuristic

#### `discover`
- optional helper from top tracks, saved library, genres, artists, or search fallbacks
- degrade gracefully if recommendation endpoint unavailable

#### `radio <query_or_uri>`
- optional helper
- use supported APIs if available, otherwise create search+queue heuristic
- honest about implementation path

## Command Aliases

- `now` → `current`
- `prev` → `previous`
- `vol` → `volume`
- `ls` → `list` where appropriate
- `rm` → `remove` where appropriate
- `add` → `queue add` or `playlist add` in context

## Output Requirements

Rich mode: Rich tables and panels, compact progress text for current item
Plain mode: predictable, pipe-friendly, line-based or tab-separated, no Rich formatting
JSON mode: stable keys, machine-friendly, consistent envelope

## Error Handling

Handle explicitly:
- missing env vars
- missing or unreadable cache path
- redirect URI mismatch
- no browser available
- no active device
- device not found
- no Premium or playback failure
- query resolves to zero results
- query resolves ambiguously
- 401 unauthorized
- 403 forbidden
- 404 not found
- 429 rate limited
- unsupported operation
- token refresh failure

## Rate Limiting and Retries

Retry wrapper:
- respect Retry-After when present
- exponential backoff
- do not retry permanent failures
- useful debug info without leaking secrets

## Logging and Debug

Debug logger controlled by flag or env var. Never log:
- client secret
- access token
- refresh token
- authorization code

OK to log: command path, resolver decisions, selected device id/name, token expiry timestamp, retry behavior, endpoint category

## Security and Operational Requirements

1. Never print secrets in normal output
2. Never require writing secrets to shell history
3. Avoid destructive actions without confirmation unless `--yes`
4. Make token cache path configurable and easy to persist on Dokku storage
5. Exported token-info safe by default
6. Raw token export requires explicit intent
7. Non-interactive by default except for optional selection or destructive confirmations
8. Safe to run on remote gateway

## Code Quality Requirements

1. Script must run as-is
2. Modern typing throughout
3. Polished, practical help text with examples
4. Separate user-facing error messages from debug details
5. Clean entrypoint structure with `main()`
6. End with `if __name__ == "__main__":` invoking the Typer app

## Smoke Tests Comment Block

At bottom of file:
```
# SMOKE TESTS:
# auth status
# auth url
# auth callback-url <url>
# auth export-token-info
# auth import-token-info <path>
# devices list
# search "bohemian rhapsody"
# status
# play / pause / next
# playlist create "My List" / playlist add "My List" "bohemian rhapsody" / playlist remove / playlist clear
```

## Final Acceptance Criteria

1. Single-file executable Python script
2. uv inline dependency header with pinned versions
3. Reads auth and runtime config from environment variables
4. Both auth bootstrap modes supported
5. Persistent cached token state
6. Human and JSON output
7. Major Spotify CLI operations
8. Unsupported operations handled honestly, not faked
9. Safe for remote server use
10. Production-ready and maintainable
