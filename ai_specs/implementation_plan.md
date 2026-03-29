# Implementation Plan: spotify_cli.py

**Spec:** [`spotify_cli_spec.md`](spotify_cli_spec.md)
**API Research:** [`../ai_docs/spotify_api_research.md`](../ai_docs/spotify_api_research.md)

---

## Key Findings from API Research

See full details in [`ai_docs/spotify_api_research.md`](../ai_docs/spotify_api_research.md). Summary of what affects the implementation:

### Removed / Restricted Endpoints

| Feature | Status | CLI Behavior |
|---|---|---|
| `recommendations()` | REMOVED Nov 2024 | `discover`, `radio` — search-based heuristic, clearly documented |
| `recommendation_genre_seeds()` | REMOVED Nov 2024 | `genre list` — hardcoded well-known genre list |
| `artist_related_artists()` | Restricted (extended access only) | `artist related` — try, catch 403, degrade gracefully |
| `artist_top_tracks()` | REMOVED Feb 2026 | `artist top` — search fallback with `artist:<name>` query |
| `audio_features()` | Restricted (extended access only) | `track audio` — try, catch 403, explain clearly |
| Queue remove / clear | No API endpoint exists | Honest explanation, no faking |

### Auth Notes
- Use `http://127.0.0.1` not `http://localhost` in redirect URIs (localhost deprecated)
- Spotipy `SpotifyOAuth.parse_auth_response_url(url)` → extracts code + state
- `sp_oauth.get_access_token(code)` → exchanges code for token_info dict
- `sp_oauth.cache_handler.save_token_to_cache(token_info)` → manual save
- Token info shape: `{access_token, token_type, expires_in, refresh_token, scope, expires_at}`
- Token cache file should be mode 600 (spotipy 2.25.1+ handles this)

### Search Limit
- Max 10 results per type as of Feb 2026 (reduced from 50) — cap `--limit` at 10

---

## File Structure

Single file: `spotify_cli.py`

### Header (exact)
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

### Code Sections (in order)

1. **Imports** — stdlib + spotipy + typer + rich
2. **Constants** — default scopes, exit codes, API limits, mood/genre maps
3. **Config dataclass** — loaded from env vars with validation
4. **Auth manager** — SpotifyOAuth wrapper, cache helpers, token import/export
5. **Retry wrapper** — exponential backoff, Retry-After header respect
6. **Resource resolver** — URI/URL/ID/query → typed resource (track/album/artist/playlist)
7. **Device selector** — priority: --device-id > --device-name > active device > env default > fail
8. **Spotify service layer** — thin wrappers over spotipy, honest about removed endpoints
9. **Output formatters** — rich tables/panels, plain text, JSON envelope
10. **Typer app + command groups** (see below)
11. **Smoke test comment block**

---

## Command Groups

### `auth` group
- `auth status` — env vars, cache, token summary (no secrets)
- `auth url` — print auth URL, optionally save state file
- `auth login` — local flow with/without browser; gateway: print URL + instructions
- `auth callback-url <url>` — parse redirect URL, exchange code, save cache
- `auth code <code>` — exchange raw code, save cache
- `auth import-token-info <path|->` — import token JSON, validate, save cache
- `auth export-token-info` — safe by default (`--masked`), raw requires `--raw --yes`
- `auth whoami` — current user profile
- `auth logout` — remove cache, confirm unless `--yes`

### `devices` group
- `devices list` — table with id, name, type, active, restricted, volume
- `devices transfer <device>` — by id or name, `--play/--no-play`

### Playback commands (top-level)
- `play [query_or_uri]` — resume or play target
- `pause` / `resume` / `stop` (alias for pause, documented)
- `next` / `previous` (alias: `prev`)
- `seek <position>` — ms, mm:ss, +10s, -15s
- `volume <0-100>` (alias: `vol`)
- `repeat <off|track|context>`
- `shuffle <on|off|toggle>`

### `status` / `current` (alias: `now`)

### `queue` group
- `queue list`
- `queue add <query_or_uri>`
- `queue clear` — honest: no API, explain
- `queue remove` — honest: no API, explain

### `search`
- `--type track|album|artist|playlist` (multiple), `--limit`, `--market`, `--exact`

### `track` group
- `show`, `play`, `queue`, `save`, `unsave`, `check`, `open`, `audio`

### `album` group
- `show`, `play`, `tracks`, `save`, `unsave`, `check`

### `artist` group
- `show`, `top` (search fallback), `albums`, `follow`, `unfollow`, `related` (graceful)

### `playlist` group
- `list` (alias: `ls`), `create`, `rename`, `describe`, `set-public`, `set-private`
- `follow`, `unfollow`, `show`, `items`
- `add`, `remove` (alias: `rm`), `clear`, `reorder`, `replace`

### `library` group
- `tracks`, `albums`, `check`, `save`, `unsave`

### `recent` / `top tracks` / `top artists`

### Discovery (honest degradation)
- `genre list` — hardcoded genres (no API)
- `genre search <genre>` — playlist search heuristic
- `mood search <mood>` — playlist/track search heuristic, documented as heuristic
- `discover` — built from top tracks + top artists + search
- `radio <query_or_uri>` — search + queue heuristic, honest about implementation

### `doctor` — env, cache, token, user, devices, playback readiness

---

## Output Modes

- **rich** (default): Rich tables, panels, progress text
- **plain**: line-based, tab-separated, no markup
- **json**: `{"ok": true, "command": "...", "data": {...}}`

Global flags: `--json`, `--plain`, `--debug`, `--no-color`, `--market`, `--device-id`, `--device-name`, `--limit`, `--offset`, `--yes`, `--exact`, `--interactive`

---

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 2 | Invalid user input |
| 3 | Auth / config error |
| 4 | API / playback error (Premium required, device not found, 403, 404) |
| 5 | Rate limit exhausted |
| 10 | Internal error |

---

## Verification

```bash
uv run spotify_cli.py --help
uv run spotify_cli.py auth --help
uv run spotify_cli.py auth status
uv run spotify_cli.py auth url
uv run spotify_cli.py doctor
```
