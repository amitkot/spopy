# Spotify Web API Research Report

## 1. Authentication & Authorization

### OAuth 2.0 Authorization Code Flow

**Authorization URL:** `https://accounts.spotify.com/authorize`

Parameters:
- `client_id`, `response_type=code`, `redirect_uri`, `scope`, `state`, `show_dialog`

**Token Exchange:** `POST https://accounts.spotify.com/api/token`
- Headers: `Authorization: Basic <base64(client_id:client_secret)>`, `Content-Type: application/x-www-form-urlencoded`
- Body: `grant_type=authorization_code`, `code=<code>`, `redirect_uri=<uri>`

Response shape:
```json
{
  "access_token": "BQD...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "AQC...",
  "scope": "user-read-private ...",
  "expires_at": 1704067200
}
```

**Token Refresh:** `POST https://accounts.spotify.com/api/token`
- Body: `grant_type=refresh_token`, `refresh_token=<token>`
- Response may NOT include new refresh_token — keep existing one

### Spotipy SpotifyOAuth

```python
SpotifyOAuth(
    client_id, client_secret, redirect_uri,
    scope, cache_path, state, show_dialog, username,
    requests_timeout
)
```

Key methods:
- `get_authorization_url(state, show_dialog)` → auth URL string
- `parse_auth_response_url(url)` → code string
- `get_access_token(code, check_cache=True, as_dict=True)` → token_info dict
- `get_cached_token()` → token_info or None
- `is_token_expired(token_info)` → bool
- `refresh_access_token(refresh_token)` → new token_info
- `cache_handler.save_token_to_cache(token_info)` → save manually

Token cache: JSON file at `cache_path`. CVE-2025-27154: use spotipy>=2.25.1 for 600 file permissions.

### 2025 OAuth Changes
- Implicit Grant Flow deprecated
- HTTP redirect URIs must be HTTPS (localhost: use `http://127.0.0.1`)
- Localhost aliases no longer work; use `http://127.0.0.1`

---

## 2. Available Endpoints (Status as of 2025/2026)

### Player (all require Premium + `user-modify-playback-state`)

| Spotipy method | Purpose |
|---|---|
| `current_playback()` | Get playback state |
| `current_user_playing_track()` | Currently playing |
| `devices()` | List devices |
| `start_playback(device_id, context_uri, uris, position_ms)` | Start/resume |
| `pause_playback(device_id)` | Pause |
| `next_track(device_id)` | Skip next |
| `previous_track(device_id)` | Skip previous |
| `seek_track(position_ms, device_id)` | Seek |
| `volume(volume_percent, device_id)` | Set volume |
| `repeat(state, device_id)` | Set repeat (off/context/track) |
| `shuffle(state, device_id)` | Set shuffle |
| `transfer_playback(device_id, force_play)` | Transfer to device |

### Queue

| Spotipy method | Status |
|---|---|
| `queue()` | ✓ Available — returns `currently_playing` + `queue` list |
| `add_to_queue(uri, device_id)` | ✓ Available |
| Remove from queue | ❌ NO API ENDPOINT |
| Clear queue | ❌ NO API ENDPOINT |

### Playlists

| Spotipy method | Status | Notes |
|---|---|---|
| `playlist(playlist_id)` | ✓ | Get playlist details |
| `playlist_items(playlist_id, limit, offset)` | ✓ | New Feb 2026 endpoint |
| `playlist_add_items(playlist_id, items, position)` | ✓ | Up to 100 items |
| `playlist_remove_all_occurrences_of_items(playlist_id, items)` | ✓ | Remove by URI |
| `playlist_reorder_items(playlist_id, range_start, insert_before, range_length)` | ✓ | |
| `playlist_change_details(playlist_id, name, public, collaborative, description)` | ✓ | |
| `user_playlist_create(user, name, public, collaborative, description)` | ✓ | Still works |
| `current_user_playlists(limit, offset)` | ✓ | Still works in spotipy 2.26 |
| `current_user_follow_playlist(playlist_id)` | ✓ | |
| `current_user_unfollow_playlist(playlist_id)` | ✓ | |

### Library / Saved Items

| Spotipy method | Status |
|---|---|
| `current_user_saved_tracks(limit, offset, market)` | ✓ |
| `current_user_saved_tracks_contains(tracks)` | ✓ |
| `current_user_saved_albums(limit, offset, market)` | ✓ |
| `current_user_saved_albums_contains(albums)` | ✓ |
| `current_user_saved_tracks_add(tracks)` | ✓ |
| `current_user_saved_tracks_delete(tracks)` | ✓ |
| `current_user_saved_albums_add(albums)` | ✓ |
| `current_user_saved_albums_delete(albums)` | ✓ |

### Artists / Follow

| Spotipy method | Status |
|---|---|
| `artist(artist_id)` | ✓ |
| `artist_albums(artist_id, album_type, limit, offset)` | ✓ |
| `artist_top_tracks(artist_id, country)` | ❌ REMOVED Feb 2026 |
| `artist_related_artists(artist_id)` | ❌ Restricted — extended access only |
| `current_user_following_artists(limit)` | ✓ |
| `user_follow_artists(ids)` | ✓ |
| `user_unfollow_artists(ids)` | ✓ |
| `current_user_is_following_artists(ids)` | ✓ |

### Search

| Parameter | Notes |
|---|---|
| `q` | Query string |
| `type` | track, album, artist, playlist, show, episode, audiobook |
| `limit` | Max 10 per type (reduced from 50 in Feb 2026) |
| `offset` | Pagination |
| `market` | ISO country code |

### Top / History

| Spotipy method | Status |
|---|---|
| `current_user_top_tracks(limit, offset, time_range)` | ✓ `user-top-read` |
| `current_user_top_artists(limit, offset, time_range)` | ✓ `user-top-read` |
| `current_user_recently_played(limit, after, before)` | ✓ `user-read-recently-played` — tracks only |

### Deprecated / Unavailable

| Endpoint | Status |
|---|---|
| `audio_features(track_id)` | ❌ Extended access only (Nov 2024) |
| `recommendations(seed_tracks, seed_artists, seed_genres, ...)` | ❌ REMOVED Nov 2024 |
| `recommendation_genre_seeds()` | ❌ REMOVED Nov 2024 |
| `artist_related_artists()` | ❌ Extended access only |
| `artist_top_tracks()` | ❌ REMOVED Feb 2026 |

### Current User

| Spotipy method | Status |
|---|---|
| `current_user()` | ✓ (some fields removed: country, email, product, followers) |

---

## 3. Important Caveats

- **Premium required** for all playback control
- **No queue clear/remove** — be honest in the CLI
- **No recommendations** for new apps since Nov 2024
- **No related artists** for new apps since Nov 2024
- **artist_top_tracks removed** Feb 2026
- **Search limit** is now 10 per type (was 50)
- `http://127.0.0.1` for local redirect (not `localhost`)
- Token cache file should be mode 600 (spotipy 2.25.1+)
