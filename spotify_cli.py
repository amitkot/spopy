#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "spotipy==2.26.0",
#   "typer==0.24.1",
#   "rich==14.3.3",
# ]
# ///
"""
Spotify CLI — a production-quality command-line interface for Spotify.

Supports local and gateway (headless) authentication bootstrap, persistent
token caching, rich/plain/JSON output, and a comprehensive set of Spotify
operations with honest handling of unsupported endpoints.

See: spotify_cli.py --help
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import parse_qs, urlparse

import spotipy
import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from spotipy.oauth2 import SpotifyOAuth

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "spotify-cli"

DEFAULT_SCOPES = " ".join([
    "user-read-playback-state",
    "user-read-currently-playing",
    "user-modify-playback-state",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "playlist-modify-public",
    "user-library-read",
    "user-library-modify",
    "user-top-read",
    "user-read-recently-played",
    "user-follow-read",
    "user-follow-modify",
    "user-read-private",
])

DEFAULT_CACHE_PATH = ".spotify_cli_cache"
DEFAULT_MARKET = ""
DEFAULT_TIMEOUT = 15
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 0.5

WELL_KNOWN_GENRES = [
    "acoustic", "afrobeat", "alt-rock", "alternative", "ambient", "anime",
    "black-metal", "bluegrass", "blues", "bossanova", "brazil", "breakbeat",
    "british", "cantopop", "chicago-house", "children", "chill", "classical",
    "club", "comedy", "country", "dance", "dancehall", "death-metal",
    "deep-house", "detroit-techno", "disco", "disney", "drum-and-bass", "dub",
    "dubstep", "edm", "electro", "electronic", "emo", "folk", "forro", "french",
    "funk", "garage", "german", "gospel", "goth", "grindcore", "groove",
    "grunge", "guitar", "happy", "hard-rock", "hardcore", "hardstyle",
    "heavy-metal", "hip-hop", "holidays", "honky-tonk", "house", "idm",
    "indian", "indie", "indie-pop", "industrial", "iranian", "j-dance",
    "j-idol", "j-pop", "j-rock", "jazz", "k-pop", "kids", "latin", "latino",
    "malay", "mandopop", "metal", "metal-misc", "metalcore", "minimal-techno",
    "movies", "mpb", "new-age", "new-release", "opera", "pagode", "party",
    "philippines-opm", "piano", "pop", "pop-film", "post-dubstep", "power-pop",
    "progressive-house", "psych-rock", "punk", "punk-rock", "r-n-b", "rainy-day",
    "reggae", "reggaeton", "road-trip", "rock", "rock-n-roll", "rockabilly",
    "romance", "sad", "salsa", "samba", "sertanejo", "show-tunes",
    "singer-songwriter", "ska", "sleep", "songwriter", "soul", "soundtracks",
    "spanish", "study", "summer", "swedish", "synth-pop", "tango", "techno",
    "trance", "trip-hop", "turkish", "work-out", "world-music",
]

MOOD_MAP: dict[str, list[str]] = {
    "chill": ["chill vibes", "chill out", "relaxing"],
    "focus": ["focus music", "concentration", "deep focus"],
    "happy": ["happy hits", "feel good", "good vibes"],
    "sad": ["sad songs", "melancholy", "heartbreak"],
    "workout": ["workout motivation", "gym music", "high energy"],
    "sleep": ["sleep music", "ambient sleep", "calm"],
    "party": ["party hits", "dance party", "party mix"],
    "study": ["study music", "lo-fi study", "study beats"],
}


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

class ExitCode(IntEnum):
    SUCCESS = 0
    INVALID_INPUT = 2
    AUTH_CONFIG_ERROR = 3
    API_ERROR = 4
    RATE_LIMIT = 5
    INTERNAL_ERROR = 10


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(APP_NAME)


def _setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.WARNING
    handler = RichHandler(
        show_time=False,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
    )
    logging.basicConfig(level=level, handlers=[handler], format="%(message)s")
    logger.setLevel(level)


# ---------------------------------------------------------------------------
# CLI error helper
# ---------------------------------------------------------------------------

_console = Console(stderr=True)
_out = Console()


def _die(msg: str, code: ExitCode = ExitCode.INTERNAL_ERROR, hint: str | None = None) -> NoReturn:
    """Print an error and exit with the given code."""
    _console.print(f"[bold red]Error:[/] {msg}")
    if hint:
        _console.print(f"[dim]Hint:[/] {hint}")
    raise typer.Exit(code=int(code))


# ---------------------------------------------------------------------------
# Output mode
# ---------------------------------------------------------------------------

class OutputMode:
    RICH = "rich"
    PLAIN = "plain"
    JSON = "json"


# ---------------------------------------------------------------------------
# Global state (populated from callback/env before commands run)
# ---------------------------------------------------------------------------

@dataclass
class CLIState:
    """Runtime configuration loaded from env vars and CLI flags."""
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    cache_path: str = DEFAULT_CACHE_PATH
    username: str = ""
    scopes: str = DEFAULT_SCOPES
    default_device_id: str = ""
    default_device_name: str = ""
    market: str = DEFAULT_MARKET
    output: str = OutputMode.RICH
    timeout: int = DEFAULT_TIMEOUT
    retries: int = DEFAULT_RETRIES
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR
    debug: bool = False
    open_browser: bool = True
    no_color: bool = False
    token_import_json: str = ""
    state_file: str = ""
    # CLI-flag overrides (populated per invocation)
    flag_json: bool = False
    flag_plain: bool = False
    flag_debug: bool = False
    flag_market: str = ""
    flag_device_id: str = ""
    flag_device_name: str = ""
    flag_limit: int = 0
    flag_offset: int = 0
    flag_yes: bool = False
    flag_exact: bool = False
    flag_interactive: bool = False
    flag_no_color: bool = False

    @property
    def effective_output(self) -> str:
        if self.flag_json:
            return OutputMode.JSON
        if self.flag_plain:
            return OutputMode.PLAIN
        return self.output

    @property
    def effective_market(self) -> str | None:
        m = self.flag_market or self.market
        return m if m else None

    @property
    def effective_device_id(self) -> str:
        return self.flag_device_id or self.default_device_id

    @property
    def effective_device_name(self) -> str:
        return self.flag_device_name or self.default_device_name

    @property
    def effective_limit(self) -> int:
        return self.flag_limit if self.flag_limit > 0 else 10

    @property
    def effective_offset(self) -> int:
        return self.flag_offset

    @property
    def is_debug(self) -> bool:
        return self.flag_debug or self.debug

    @property
    def auto_yes(self) -> bool:
        return self.flag_yes

    def auth_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)


_state = CLIState()


def _load_env() -> None:
    """Populate state from environment variables."""
    _state.client_id = os.environ.get("SPOTIPY_CLIENT_ID", "")
    _state.client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET", "")
    _state.redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "")
    _state.cache_path = os.environ.get("SPOTIPY_CACHE_PATH", DEFAULT_CACHE_PATH)
    _state.username = os.environ.get("SPOTIPY_USERNAME", "")
    _state.scopes = os.environ.get("SPOTIFY_CLI_SCOPES", DEFAULT_SCOPES)
    _state.default_device_id = os.environ.get("SPOTIFY_CLI_DEFAULT_DEVICE_ID", "")
    _state.default_device_name = os.environ.get("SPOTIFY_CLI_DEFAULT_DEVICE_NAME", "")
    _state.market = os.environ.get("SPOTIFY_CLI_MARKET", "")
    _state.output = os.environ.get("SPOTIFY_CLI_OUTPUT", OutputMode.RICH)
    _state.timeout = int(os.environ.get("SPOTIFY_CLI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT)))
    _state.retries = int(os.environ.get("SPOTIFY_CLI_RETRIES", str(DEFAULT_RETRIES)))
    _state.backoff_factor = float(os.environ.get("SPOTIFY_CLI_BACKOFF_FACTOR", str(DEFAULT_BACKOFF_FACTOR)))
    _state.debug = os.environ.get("SPOTIFY_CLI_DEBUG", "0") == "1"
    _state.open_browser = os.environ.get("SPOTIFY_CLI_OPEN_BROWSER", "1") == "1"
    _state.no_color = os.environ.get("SPOTIFY_CLI_NO_COLOR", "0") == "1"
    _state.token_import_json = os.environ.get("SPOTIFY_CLI_TOKEN_IMPORT_JSON", "")
    _state.state_file = os.environ.get("SPOTIFY_CLI_STATE_FILE", "")


# ---------------------------------------------------------------------------
# Auth manager helpers
# ---------------------------------------------------------------------------

def _build_oauth(open_browser: bool = False) -> SpotifyOAuth:
    """Build a SpotifyOAuth instance from the current state."""
    if not _state.auth_configured():
        missing = []
        if not _state.client_id:
            missing.append("SPOTIPY_CLIENT_ID")
        if not _state.client_secret:
            missing.append("SPOTIPY_CLIENT_SECRET")
        if not _state.redirect_uri:
            missing.append("SPOTIPY_REDIRECT_URI")
        _die(
            f"Missing required auth env var(s): {', '.join(missing)}",
            ExitCode.AUTH_CONFIG_ERROR,
            hint="Export the variables or add them to your Dokku config.",
        )
    return SpotifyOAuth(
        client_id=_state.client_id,
        client_secret=_state.client_secret,
        redirect_uri=_state.redirect_uri,
        scope=_state.scopes,
        cache_path=_state.cache_path,
        open_browser=open_browser,
        username=_state.username or None,
    )


def _get_spotify(require_auth: bool = True) -> spotipy.Spotify:
    """Return an authenticated Spotify client, refreshing tokens as needed."""
    oauth = _build_oauth(open_browser=False)
    token_info = oauth.get_cached_token()
    if token_info is None and require_auth:
        _die(
            "No cached token found. Run 'auth login' or 'auth callback-url' first.",
            ExitCode.AUTH_CONFIG_ERROR,
        )
    if token_info and oauth.is_token_expired(token_info):
        logger.debug("Token expired, refreshing…")
        try:
            token_info = oauth.refresh_access_token(token_info["refresh_token"])
        except Exception as exc:
            _die(f"Token refresh failed: {exc}", ExitCode.AUTH_CONFIG_ERROR)
    return spotipy.Spotify(
        auth=token_info["access_token"] if token_info else None,
        requests_timeout=_state.timeout,
    )


def _mask_token(tok: str | None, show: int = 4) -> str:
    """Return a masked version of a token string."""
    if not tok:
        return "(none)"
    if len(tok) <= show * 2:
        return "***"
    return f"{tok[:show]}…{tok[-show:]}"


# ---------------------------------------------------------------------------
# Token cache helpers
# ---------------------------------------------------------------------------

def _read_cache() -> dict[str, Any] | None:
    """Read and return the cached token info, or None."""
    p = Path(_state.cache_path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())  # type: ignore[no-any-return]
    except Exception:
        return None


def _write_cache(token_info: dict[str, Any]) -> None:
    """Write token info to the cache file."""
    p = Path(_state.cache_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(token_info, indent=2))
    try:
        p.chmod(0o600)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

def _api_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call a Spotify API function with retries and error handling."""
    last_exc: Exception | None = None
    for attempt in range(_state.retries):
        try:
            return fn(*args, **kwargs)
        except spotipy.exceptions.SpotifyException as exc:
            last_exc = exc
            status = exc.http_status
            if status == 401:
                _die("Unauthorized (401). Token may be invalid — try 'auth login'.", ExitCode.AUTH_CONFIG_ERROR)
            if status == 403:
                msg = str(exc.msg) if exc.msg else "Forbidden"
                if "PREMIUM" in msg.upper() or "premium" in msg.lower():
                    _die("Spotify Premium is required for this action.", ExitCode.API_ERROR)
                _die(f"Forbidden (403): {msg}", ExitCode.API_ERROR)
            if status == 404:
                _die(f"Not found (404): {exc.msg}", ExitCode.API_ERROR)
            if status == 429:
                retry_after = int(exc.headers.get("Retry-After", "2")) if exc.headers else 2
                logger.debug("Rate limited (429), retrying after %ds (attempt %d/%d)", retry_after, attempt + 1, _state.retries)
                time.sleep(retry_after)
                continue
            if status >= 500:
                wait = _state.backoff_factor * (2 ** attempt)
                logger.debug("Server error %d, retrying in %.1fs (attempt %d/%d)", status, wait, attempt + 1, _state.retries)
                time.sleep(wait)
                continue
            _die(f"Spotify API error ({status}): {exc.msg}", ExitCode.API_ERROR)
        except Exception as exc:
            last_exc = exc
            wait = _state.backoff_factor * (2 ** attempt)
            logger.debug("Unexpected error: %s — retrying in %.1fs", exc, wait)
            time.sleep(wait)
    if last_exc:
        if isinstance(last_exc, spotipy.exceptions.SpotifyException) and last_exc.http_status == 429:
            _die("Rate limit exceeded after retries.", ExitCode.RATE_LIMIT)
        _die(f"API call failed after {_state.retries} retries: {last_exc}", ExitCode.API_ERROR)


# ---------------------------------------------------------------------------
# Resource parsing / resolution
# ---------------------------------------------------------------------------

_URI_RE = re.compile(r"^spotify:(?P<type>track|album|artist|playlist|episode|show):(?P<id>[a-zA-Z0-9]+)$")
_URL_RE = re.compile(r"https?://open\.spotify\.com/(?:intl-\w+/)?(?P<type>track|album|artist|playlist|episode|show)/(?P<id>[a-zA-Z0-9]+)")
_ID_RE = re.compile(r"^[a-zA-Z0-9]{22}$")


@dataclass
class SpotifyResource:
    """A resolved Spotify resource."""
    resource_type: str
    resource_id: str
    uri: str = ""
    name: str = ""
    raw_input: str = ""

    def __post_init__(self) -> None:
        if not self.uri:
            self.uri = f"spotify:{self.resource_type}:{self.resource_id}"


def _parse_resource(value: str, preferred_type: str = "track") -> SpotifyResource | None:
    """Try to parse a URI, URL, or bare ID into a SpotifyResource."""
    m = _URI_RE.match(value)
    if m:
        return SpotifyResource(resource_type=m.group("type"), resource_id=m.group("id"), raw_input=value)
    m = _URL_RE.match(value)
    if m:
        return SpotifyResource(resource_type=m.group("type"), resource_id=m.group("id"), raw_input=value)
    if _ID_RE.match(value):
        return SpotifyResource(resource_type=preferred_type, resource_id=value, raw_input=value)
    return None


def _resolve_resource(
    query: str,
    preferred_type: str = "track",
    sp: spotipy.Spotify | None = None,
) -> SpotifyResource:
    """Resolve a query (URI, URL, ID, or search text) to a SpotifyResource."""
    parsed = _parse_resource(query, preferred_type)
    if parsed:
        return parsed

    # Search
    if sp is None:
        sp = _get_spotify()
    search_type = preferred_type if preferred_type in ("track", "album", "artist", "playlist") else "track"
    results = _api_call(sp.search, q=query, type=search_type, limit=_state.effective_limit, market=_state.effective_market)
    key = f"{search_type}s"
    items = results.get(key, {}).get("items", []) if results else []
    if not items:
        _die(f"No {search_type} results for: {query}", ExitCode.INVALID_INPUT)

    if _state.flag_exact:
        ql = query.lower()
        exact = [i for i in items if i.get("name", "").lower() == ql]
        if exact:
            items = exact

    if _state.flag_interactive and len(items) > 1:
        _console.print(f"\n[bold]Select a {search_type}:[/]")
        for idx, item in enumerate(items, 1):
            extra = _artist_names(item) if search_type == "track" else ""
            label = f"  {idx}. {item['name']}"
            if extra:
                label += f" — {extra}"
            _console.print(label)
        choice = typer.prompt("Number", type=int, default=1)
        if 1 <= choice <= len(items):
            items = [items[choice - 1]]

    item = items[0]
    return SpotifyResource(
        resource_type=search_type,
        resource_id=item["id"],
        uri=item["uri"],
        name=item.get("name", ""),
        raw_input=query,
    )


def _resolve_resources(
    queries: list[str],
    preferred_type: str = "track",
    sp: spotipy.Spotify | None = None,
) -> list[SpotifyResource]:
    """Resolve multiple queries."""
    if sp is None:
        sp = _get_spotify()
    return [_resolve_resource(q, preferred_type, sp) for q in queries]


# ---------------------------------------------------------------------------
# Artist name helper
# ---------------------------------------------------------------------------

def _artist_names(item: dict[str, Any]) -> str:
    """Return comma-joined artist names from a track/album item."""
    artists = item.get("artists", [])
    return ", ".join(a.get("name", "?") for a in artists)


# ---------------------------------------------------------------------------
# Device selection
# ---------------------------------------------------------------------------

def _select_device(sp: spotipy.Spotify) -> str | None:
    """Select a device ID following the priority chain. Returns None if none found."""
    if _state.flag_device_id:
        logger.debug("Using --device-id: %s", _state.flag_device_id)
        return _state.flag_device_id

    if _state.flag_device_name:
        return _resolve_device_by_name(sp, _state.flag_device_name)

    # Check active device
    playback = _api_call(sp.current_playback)
    if playback and playback.get("device"):
        dev_id = playback["device"]["id"]
        logger.debug("Using active device: %s (%s)", playback["device"].get("name"), dev_id)
        return dev_id

    # Env defaults
    if _state.default_device_id:
        logger.debug("Using default device id from env: %s", _state.default_device_id)
        return _state.default_device_id
    if _state.default_device_name:
        return _resolve_device_by_name(sp, _state.default_device_name)

    return None


def _resolve_device_by_name(sp: spotipy.Spotify, name: str) -> str:
    """Find a device by name (case-insensitive)."""
    devs = _api_call(sp.devices)
    devices = devs.get("devices", []) if devs else []
    nl = name.lower()
    for d in devices:
        if d.get("name", "").lower() == nl:
            logger.debug("Resolved device name '%s' → %s", name, d["id"])
            return d["id"]
    _die(f"Device not found: '{name}'", ExitCode.API_ERROR, hint="Run 'devices list' to see available devices.")
    # unreachable, but satisfies type checker
    return ""  # pragma: no cover


def _require_device(sp: spotipy.Spotify) -> str:
    """Select a device or die with a helpful message."""
    dev = _select_device(sp)
    if not dev:
        _die(
            "No active device and no default configured.",
            ExitCode.API_ERROR,
            hint="Open Spotify on a device, or set SPOTIFY_CLI_DEFAULT_DEVICE_ID / SPOTIFY_CLI_DEFAULT_DEVICE_NAME.",
        )
    return dev


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _json_out(command: str, data: Any, ok: bool = True) -> None:
    """Print JSON envelope to stdout."""
    _out.print_json(json.dumps({"ok": ok, "command": command, "data": data}, default=str))


def _print_output(command: str, *, rich_fn: Any, plain_fn: Any, data_fn: Any) -> None:
    """Dispatch output to the appropriate mode handler."""
    mode = _state.effective_output
    if mode == OutputMode.JSON:
        _json_out(command, data_fn())
    elif mode == OutputMode.PLAIN:
        plain_fn()
    else:
        rich_fn()


# ---------------------------------------------------------------------------
# Seek position parser
# ---------------------------------------------------------------------------

_SEEK_RELATIVE_RE = re.compile(r"^([+-])(\d+)([sm]?)$")
_SEEK_MMSS_RE = re.compile(r"^(\d+):(\d{1,2})$")


def _parse_seek(pos_str: str, current_ms: int = 0, duration_ms: int = 0) -> int:
    """Parse a seek position string to milliseconds."""
    # Relative: +10s, -15s, +30, -5m
    m = _SEEK_RELATIVE_RE.match(pos_str)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        val = int(m.group(2))
        unit = m.group(3) or "s"
        ms = val * 1000 if unit == "s" else val * 60_000
        result = current_ms + sign * ms
        result = max(0, result)
        if duration_ms > 0:
            result = min(result, duration_ms)
        return result

    # mm:ss
    m = _SEEK_MMSS_RE.match(pos_str)
    if m:
        result = int(m.group(1)) * 60_000 + int(m.group(2)) * 1000
        if duration_ms > 0:
            result = min(result, duration_ms)
        return max(0, result)

    # Raw milliseconds
    try:
        result = int(pos_str)
        if duration_ms > 0:
            result = min(result, duration_ms)
        return max(0, result)
    except ValueError:
        _die(f"Invalid seek position: {pos_str}", ExitCode.INVALID_INPUT, hint="Use ms, mm:ss, +10s, -15s")
    return 0  # unreachable


def _format_ms(ms: int | None) -> str:
    """Format milliseconds as mm:ss."""
    if ms is None:
        return "--:--"
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


def _spotify_url(resource_type: str, resource_id: str) -> str:
    return f"https://open.spotify.com/{resource_type}/{resource_id}"


# ---------------------------------------------------------------------------
# Confirmation helper
# ---------------------------------------------------------------------------

def _confirm(message: str) -> bool:
    """Ask for confirmation unless --yes is set."""
    if _state.auto_yes:
        return True
    return typer.confirm(message)


# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="spotify-cli",
    help="Production-quality Spotify CLI. Supports local and gateway auth bootstrap.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    # Note: allow_interspersed_args is left as default (False) so that
    # sub-app --help works correctly.  Top-level commands that produce output
    # accept --json/--plain as their own options instead.
)

auth_app = typer.Typer(name="auth", help="Authentication and token management.", no_args_is_help=True)
devices_app = typer.Typer(name="devices", help="Device listing and control.", no_args_is_help=True)
track_app = typer.Typer(name="track", help="Track operations.", no_args_is_help=True)
album_app = typer.Typer(name="album", help="Album operations.", no_args_is_help=True)
artist_app = typer.Typer(name="artist", help="Artist operations.", no_args_is_help=True)
playlist_app = typer.Typer(name="playlist", help="Playlist management.", no_args_is_help=True)
library_app = typer.Typer(name="library", help="Library (saved items) operations.", no_args_is_help=True)
queue_app = typer.Typer(name="queue", help="Queue operations.", no_args_is_help=True)
top_app = typer.Typer(name="top", help="Top tracks and artists.", no_args_is_help=True)
genre_app = typer.Typer(name="genre", help="Genre browsing and search.", no_args_is_help=True)
mood_app = typer.Typer(name="mood", help="Mood-based search (heuristic).", no_args_is_help=True)

app.add_typer(auth_app)
app.add_typer(devices_app)
app.add_typer(track_app)
app.add_typer(album_app)
app.add_typer(artist_app)
app.add_typer(playlist_app)
app.add_typer(library_app)
app.add_typer(queue_app)
app.add_typer(top_app)
app.add_typer(genre_app)
app.add_typer(mood_app)


# ---------------------------------------------------------------------------
# Shared output/debug options — applied at root and on every sub-app callback
# so that --json/--plain/--debug work in any position and appear in --help.
# ---------------------------------------------------------------------------

def _apply_output_flags(
    json_out: bool = False,
    plain: bool = False,
    debug: bool = False,
    no_color: bool = False,
) -> None:
    """Merge output flags into global state (idempotent, last-write-wins)."""
    if json_out:
        _state.flag_json = True
    if plain:
        _state.flag_plain = True
    if debug:
        _state.flag_debug = True
        _setup_logging(True)
    if no_color:
        _state.flag_no_color = True
        _out.no_color = True
        _console.no_color = True


@auth_app.callback()
def _auth_cb(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    """Authentication and token management."""
    _apply_output_flags(json_out, plain, debug, no_color)


@devices_app.callback()
def _devices_cb(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    """Device listing and control."""
    _apply_output_flags(json_out, plain, debug, no_color)


@track_app.callback()
def _track_cb(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    """Track operations."""
    _apply_output_flags(json_out, plain, debug, no_color)


@album_app.callback()
def _album_cb(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    """Album operations."""
    _apply_output_flags(json_out, plain, debug, no_color)


@artist_app.callback()
def _artist_cb(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    """Artist operations."""
    _apply_output_flags(json_out, plain, debug, no_color)


@playlist_app.callback()
def _playlist_cb(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    """Playlist management."""
    _apply_output_flags(json_out, plain, debug, no_color)


@library_app.callback()
def _library_cb(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    """Library (saved items) operations."""
    _apply_output_flags(json_out, plain, debug, no_color)


@queue_app.callback()
def _queue_cb(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    """Queue operations."""
    _apply_output_flags(json_out, plain, debug, no_color)


@top_app.callback()
def _top_cb(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    """Top tracks and artists."""
    _apply_output_flags(json_out, plain, debug, no_color)


@genre_app.callback()
def _genre_cb(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    """Genre browsing and search."""
    _apply_output_flags(json_out, plain, debug, no_color)


@mood_app.callback()
def _mood_cb(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
) -> None:
    """Mood-based search (heuristic)."""
    _apply_output_flags(json_out, plain, debug, no_color)


# ---------------------------------------------------------------------------
# Global callback (options applied to every command)
# ---------------------------------------------------------------------------

@app.callback()
def _global_options(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
    plain: bool = typer.Option(False, "--plain", help="Output as plain text."),
    debug: bool = typer.Option(False, "--debug", "--verbose", help="Enable debug logging."),
    market: str = typer.Option("", "--market", help="Spotify market (ISO country code)."),
    device_id: str = typer.Option("", "--device-id", help="Target device ID."),
    device_name: str = typer.Option("", "--device-name", help="Target device name."),
    limit: int = typer.Option(0, "--limit", help="Result limit."),
    offset: int = typer.Option(0, "--offset", help="Result offset."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmations."),
    exact: bool = typer.Option(False, "--exact", help="Prefer exact name matches."),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive selection."),
) -> None:
    """Spotify CLI — rich, production-quality Spotify control from your terminal."""
    _load_env()
    _apply_output_flags(json_out, plain, debug, no_color)
    _state.flag_market = market
    _state.flag_device_id = device_id
    _state.flag_device_name = device_name
    _state.flag_limit = limit
    _state.flag_offset = offset
    _state.flag_yes = yes
    _state.flag_exact = exact
    _state.flag_interactive = interactive
    _setup_logging(_state.is_debug)
    if no_color or _state.no_color:
        _out.no_color = True
        _console.no_color = True


# ===========================================================================
# AUTH COMMANDS
# ===========================================================================

@auth_app.command("status")
def auth_status() -> None:
    """Show auth configuration and token status."""
    cache_path = Path(_state.cache_path)
    cache_exists = cache_path.exists()
    token_info = _read_cache()
    expired = False
    has_refresh = False
    user_display = ""
    if token_info:
        expires_at = token_info.get("expires_at", 0)
        expired = time.time() > expires_at
        has_refresh = bool(token_info.get("refresh_token"))
        if not expired or has_refresh:
            try:
                sp = _get_spotify(require_auth=True)
                me = _api_call(sp.current_user)
                user_display = me.get("display_name") or me.get("id", "?") if me else ""
            except (SystemExit, Exception):
                user_display = "(unable to fetch)"

    def _rich() -> None:
        table = Table(title="Auth Status", show_lines=True)
        table.add_column("Property", style="bold")
        table.add_column("Value")
        table.add_row("Client ID", _mask_token(_state.client_id, 4) if _state.client_id else "[red]NOT SET[/]")
        table.add_row("Client Secret", "[green]set[/]" if _state.client_secret else "[red]NOT SET[/]")
        table.add_row("Redirect URI", _state.redirect_uri or "[red]NOT SET[/]")
        table.add_row("Cache Path", str(cache_path))
        table.add_row("Cache Exists", "[green]yes[/]" if cache_exists else "[yellow]no[/]")
        if token_info:
            table.add_row("Token Expired", "[red]yes[/]" if expired else "[green]no[/]")
            table.add_row("Refresh Token", "[green]present[/]" if has_refresh else "[yellow]missing[/]")
            table.add_row("Access Token", _mask_token(token_info.get("access_token")))
        if user_display:
            table.add_row("Current User", user_display)
        _out.print(table)

    def _plain() -> None:
        print(f"client_id\t{_mask_token(_state.client_id, 4) if _state.client_id else 'NOT SET'}")
        print(f"client_secret\t{'set' if _state.client_secret else 'NOT SET'}")
        print(f"redirect_uri\t{_state.redirect_uri or 'NOT SET'}")
        print(f"cache_path\t{cache_path}")
        print(f"cache_exists\t{cache_exists}")
        if token_info:
            print(f"token_expired\t{expired}")
            print(f"refresh_token\t{'present' if has_refresh else 'missing'}")
        if user_display:
            print(f"user\t{user_display}")

    def _data() -> dict[str, Any]:
        d: dict[str, Any] = {
            "client_id_set": bool(_state.client_id),
            "client_secret_set": bool(_state.client_secret),
            "redirect_uri": _state.redirect_uri,
            "cache_path": str(cache_path),
            "cache_exists": cache_exists,
        }
        if token_info:
            d["token_expired"] = expired
            d["has_refresh_token"] = has_refresh
        if user_display:
            d["user"] = user_display
        return d

    _print_output("auth status", rich_fn=_rich, plain_fn=_plain, data_fn=_data)


@auth_app.command("url")
def auth_url(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Generate and print the authorization URL."""
    import secrets
    oauth = _build_oauth(open_browser=False)
    state_val = secrets.token_urlsafe(16)
    url = oauth.get_authorize_url(state=state_val)

    if _state.state_file:
        Path(_state.state_file).write_text(json.dumps({"state": state_val}))
        logger.debug("State saved to %s", _state.state_file)

    if json_out or _state.flag_json:
        _json_out("auth url", {
            "url": url,
            "scopes": _state.scopes,
            "redirect_uri": _state.redirect_uri,
            "state": state_val,
        })
    else:
        _out.print(Panel(url, title="Authorization URL", subtitle="Open this in a browser"))
        _out.print(f"\n[dim]Redirect URI:[/] {_state.redirect_uri}")
        _out.print(f"[dim]State:[/] {state_val}")
        _out.print("\n[bold]Next steps:[/]")
        _out.print("  1. Open the URL above in a browser.")
        _out.print("  2. Authorize the app.")
        _out.print("  3. Copy the redirect URL from the browser address bar.")
        _out.print("  4. Run: [green]spotify_cli.py auth callback-url '<redirected_url>'[/]")


@auth_app.command("login")
def auth_login(
    open_browser: bool = typer.Option(True, "--open-browser/--no-open-browser", help="Open browser for auth."),
) -> None:
    """Log in interactively (local bootstrap). Prints URL for gateway use."""
    should_open = open_browser and _state.open_browser
    oauth = _build_oauth(open_browser=False)
    url = oauth.get_authorize_url()

    if should_open:
        _out.print(f"[bold]Opening browser for authorization…[/]")
        _out.print(f"[dim]URL: {url}[/]")
        try:
            webbrowser.open(url)
        except Exception:
            _out.print("[yellow]Could not open browser.[/]")
            should_open = False

    if not should_open:
        _out.print(Panel(url, title="Authorization URL"))
        _out.print("\n[bold]No browser mode.[/] After authorizing, use one of:")
        _out.print("  [green]spotify_cli.py auth callback-url '<full_redirect_url>'[/]")
        _out.print("  [green]spotify_cli.py auth code '<authorization_code>'[/]")
        return

    _out.print("\nAfter authorizing, paste the [bold]full redirect URL[/] below.")
    redirect_response = typer.prompt("Redirect URL")
    try:
        code = oauth.parse_response_code(redirect_response)
        if not code or code == redirect_response:
            _die("Could not parse authorization code from URL.", ExitCode.INVALID_INPUT)
        token_info = oauth.get_access_token(code, check_cache=False)
        if isinstance(token_info, str):
            _die("Unexpected token format.", ExitCode.INTERNAL_ERROR)
        _write_cache(token_info)
        sp = spotipy.Spotify(auth=token_info["access_token"])
        me = _api_call(sp.current_user)
        name = me.get("display_name") or me.get("id", "?") if me else "unknown"
        _out.print(f"\n[bold green]Login successful![/] Authenticated as: [bold]{name}[/]")
        _out.print(f"[dim]Token cached at: {_state.cache_path}[/]")
    except SystemExit:
        raise
    except Exception as exc:
        _die(f"Login failed: {exc}", ExitCode.AUTH_CONFIG_ERROR)


@auth_app.command("callback-url")
def auth_callback_url(
    url: str = typer.Argument(..., help="Full redirected callback URL."),
) -> None:
    """Exchange a callback URL (pasted from the browser) for tokens."""
    oauth = _build_oauth(open_browser=False)
    try:
        code = oauth.parse_response_code(url)
        if not code or code == url:
            # Try manual parse
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            codes = qs.get("code", [])
            if not codes:
                _die("No 'code' parameter found in the URL.", ExitCode.INVALID_INPUT)
            code = codes[0]
    except Exception as exc:
        _die(f"Failed to parse callback URL: {exc}", ExitCode.INVALID_INPUT)

    # Validate state if state file exists
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    url_state = qs.get("state", [None])[0]
    if _state.state_file and Path(_state.state_file).exists():
        saved = json.loads(Path(_state.state_file).read_text())
        expected_state = saved.get("state")
        if expected_state and url_state and url_state != expected_state:
            _console.print("[yellow]Warning: state mismatch. Proceeding anyway.[/]")

    try:
        token_info = oauth.get_access_token(code, check_cache=False)
        if isinstance(token_info, str):
            _die("Unexpected token format.", ExitCode.INTERNAL_ERROR)
        _write_cache(token_info)
        sp = spotipy.Spotify(auth=token_info["access_token"])
        me = _api_call(sp.current_user)
        name = me.get("display_name") or me.get("id", "?") if me else "unknown"
        _out.print(f"[bold green]Success![/] Authenticated as: [bold]{name}[/]")
        _out.print(f"[dim]Token cached at: {_state.cache_path}[/]")
    except SystemExit:
        raise
    except Exception as exc:
        _die(f"Token exchange failed: {exc}", ExitCode.AUTH_CONFIG_ERROR)


@auth_app.command("code")
def auth_code_cmd(
    code: str = typer.Argument(..., help="Raw authorization code."),
    state: str = typer.Option("", "--state", help="State value for validation."),
) -> None:
    """Exchange a raw authorization code for tokens."""
    if _state.state_file and Path(_state.state_file).exists() and state:
        saved = json.loads(Path(_state.state_file).read_text())
        expected = saved.get("state")
        if expected and state != expected:
            _console.print("[yellow]Warning: state mismatch.[/]")

    oauth = _build_oauth(open_browser=False)
    try:
        token_info = oauth.get_access_token(code, check_cache=False)
        if isinstance(token_info, str):
            _die("Unexpected token format.", ExitCode.INTERNAL_ERROR)
        _write_cache(token_info)
        sp = spotipy.Spotify(auth=token_info["access_token"])
        me = _api_call(sp.current_user)
        name = me.get("display_name") or me.get("id", "?") if me else "unknown"
        _out.print(f"[bold green]Success![/] Authenticated as: [bold]{name}[/]")
        _out.print(f"[dim]Token cached at: {_state.cache_path}[/]")
    except SystemExit:
        raise
    except Exception as exc:
        _die(f"Token exchange failed: {exc}", ExitCode.AUTH_CONFIG_ERROR)


@auth_app.command("import-token-info")
def auth_import_token_info(
    path: str = typer.Argument(..., help="Path to token-info JSON, or '-' for stdin."),
) -> None:
    """Import token-info JSON (e.g. exported from a local bootstrap)."""
    if path == "-":
        raw = sys.stdin.read()
    else:
        p = Path(path)
        if not p.exists():
            _die(f"File not found: {path}", ExitCode.INVALID_INPUT)
        raw = p.read_text()

    try:
        token_info = json.loads(raw)
    except json.JSONDecodeError as exc:
        _die(f"Invalid JSON: {exc}", ExitCode.INVALID_INPUT)

    required = ["access_token", "refresh_token", "token_type"]
    missing = [k for k in required if k not in token_info]
    if missing:
        _die(f"Missing required fields: {', '.join(missing)}", ExitCode.INVALID_INPUT)

    _write_cache(token_info)
    _out.print(f"[bold green]Token info imported.[/]")
    _out.print(f"  Access token:  {_mask_token(token_info.get('access_token'))}")
    _out.print(f"  Refresh token: {_mask_token(token_info.get('refresh_token'))}")
    _out.print(f"  Saved to:      {_state.cache_path}")


@auth_app.command("export-token-info")
def auth_export_token_info(
    out: str = typer.Option("", "--out", help="Write to file instead of stdout."),
    masked: bool = typer.Option(False, "--masked", help="Mask sensitive fields."),
    raw: bool = typer.Option(False, "--raw", help="Export actual tokens (requires --yes for safety)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety warning for --raw."),
) -> None:
    """Export token-info JSON. Safe (masked) by default."""
    token_info = _read_cache()
    if not token_info:
        _die("No cached token to export.", ExitCode.AUTH_CONFIG_ERROR)

    if raw:
        if not (yes or _state.auto_yes):
            _console.print("[bold yellow]Warning:[/] --raw exports real tokens. Use --yes to confirm.")
            if not typer.confirm("Export raw tokens?"):
                raise typer.Abort()
        data = token_info
    elif masked:
        data = {
            **token_info,
            "access_token": _mask_token(token_info.get("access_token")),
            "refresh_token": _mask_token(token_info.get("refresh_token")),
        }
    else:
        # Default: safe/masked
        data = {
            **token_info,
            "access_token": _mask_token(token_info.get("access_token")),
            "refresh_token": _mask_token(token_info.get("refresh_token")),
        }

    text = json.dumps(data, indent=2)
    if out:
        Path(out).write_text(text)
        _out.print(f"[green]Exported to {out}[/]")
    else:
        print(text)


@auth_app.command("whoami")
def auth_whoami() -> None:
    """Show current authenticated user."""
    sp = _get_spotify()
    me = _api_call(sp.current_user)
    if not me:
        _die("Could not fetch user profile.", ExitCode.API_ERROR)

    def _rich() -> None:
        table = Table(title="Current User", show_lines=True)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        table.add_row("Display Name", me.get("display_name", "—"))
        table.add_row("ID", me.get("id", "—"))
        table.add_row("URI", me.get("uri", "—"))
        table.add_row("Profile URL", (me.get("external_urls") or {}).get("spotify", "—"))
        _out.print(table)

    def _plain() -> None:
        print(f"display_name\t{me.get('display_name', '')}")
        print(f"id\t{me.get('id', '')}")
        print(f"uri\t{me.get('uri', '')}")

    _print_output("auth whoami", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: me)


@auth_app.command("logout")
def auth_logout(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Remove local token cache."""
    p = Path(_state.cache_path)
    if not p.exists():
        _out.print("[yellow]No token cache found.[/]")
        return
    if not (yes or _state.auto_yes):
        if not typer.confirm(f"Remove token cache at {p}?"):
            raise typer.Abort()
    p.unlink()
    _out.print("[green]Token cache removed.[/]")


# ===========================================================================
# DOCTOR
# ===========================================================================

@app.command("doctor")
def doctor() -> None:
    """Diagnose auth, config, connectivity, and playback readiness."""
    checks: list[tuple[str, str, str]] = []  # (label, status_icon, detail)

    # 1. Env vars
    for var in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"):
        val = os.environ.get(var, "")
        if val:
            checks.append((var, "[green]OK[/]", "Set"))
        else:
            checks.append((var, "[red]MISSING[/]", f"Export {var}"))

    # 2. Cache path
    cp = Path(_state.cache_path)
    if cp.exists():
        checks.append(("Cache file", "[green]OK[/]", str(cp)))
    else:
        checks.append(("Cache file", "[yellow]WARN[/]", f"Not found at {cp} — run 'auth login'"))

    # 3. Cache dir writable
    cache_dir = cp.parent
    if cache_dir.exists() and os.access(str(cache_dir), os.W_OK):
        checks.append(("Cache dir writable", "[green]OK[/]", str(cache_dir)))
    else:
        checks.append(("Cache dir writable", "[red]FAIL[/]", f"Directory {cache_dir} is not writable"))

    # 4. Token
    token_info = _read_cache()
    if token_info:
        expired = time.time() > token_info.get("expires_at", 0)
        has_refresh = bool(token_info.get("refresh_token"))
        if not expired:
            checks.append(("Token valid", "[green]OK[/]", "Not expired"))
        elif has_refresh:
            checks.append(("Token valid", "[yellow]WARN[/]", "Expired but refresh token available"))
        else:
            checks.append(("Token valid", "[red]FAIL[/]", "Expired and no refresh token"))
    else:
        checks.append(("Token valid", "[red]FAIL[/]", "No token cached"))

    # 5. User lookup
    user_ok = False
    if _state.auth_configured() and token_info:
        try:
            sp = _get_spotify()
            me = _api_call(sp.current_user)
            if me:
                checks.append(("User lookup", "[green]OK[/]", me.get("display_name") or me.get("id", "?")))
                user_ok = True
            else:
                checks.append(("User lookup", "[red]FAIL[/]", "Empty response"))
        except SystemExit:
            checks.append(("User lookup", "[red]FAIL[/]", "Auth error"))
        except Exception as exc:
            checks.append(("User lookup", "[red]FAIL[/]", str(exc)))
    else:
        checks.append(("User lookup", "[dim]SKIP[/]", "No auth configured or no token"))

    # 6. Devices
    if user_ok:
        try:
            sp = _get_spotify()
            devs = _api_call(sp.devices)
            device_list = devs.get("devices", []) if devs else []
            if device_list:
                names = ", ".join(d.get("name", "?") for d in device_list)
                checks.append(("Devices", "[green]OK[/]", f"{len(device_list)} found: {names}"))
            else:
                checks.append(("Devices", "[yellow]WARN[/]", "No devices online — open Spotify somewhere"))
        except (SystemExit, Exception):
            checks.append(("Devices", "[red]FAIL[/]", "Could not list devices"))
    else:
        checks.append(("Devices", "[dim]SKIP[/]", "Requires successful user lookup"))

    # 7. Playback readiness summary
    playback_ready = user_ok and token_info is not None
    if playback_ready:
        checks.append(("Playback ready", "[green]OK[/]", "Auth is healthy for playback commands"))
    else:
        checks.append(("Playback ready", "[red]NO[/]", "Fix auth issues above before using playback commands"))

    # Output
    def _rich() -> None:
        table = Table(title="Doctor", show_lines=True)
        table.add_column("Check", style="bold")
        table.add_column("Status")
        table.add_column("Detail")
        for label, icon, detail in checks:
            table.add_row(label, icon, detail)
        _out.print(table)

    def _plain() -> None:
        for label, _, detail in checks:
            print(f"{label}\t{detail}")

    def _data() -> list[dict[str, str]]:
        return [{"check": l, "detail": d} for l, _, d in checks]

    _print_output("doctor", rich_fn=_rich, plain_fn=_plain, data_fn=_data)


# ===========================================================================
# STATUS / CURRENT
# ===========================================================================

@app.command("status")
def status_cmd() -> None:
    """Show combined playback summary."""
    sp = _get_spotify()
    pb = _api_call(sp.current_playback, market=_state.effective_market)

    if not pb or not pb.get("item"):
        if _state.effective_output == OutputMode.JSON:
            _json_out("status", {"playing": False})
        else:
            _out.print("[dim]Nothing is currently playing.[/]")
        return

    item = pb["item"]
    device = pb.get("device", {})
    is_playing = pb.get("is_playing", False)
    progress = pb.get("progress_ms", 0)
    duration = item.get("duration_ms", 0)

    info = {
        "name": item.get("name", "?"),
        "artists": _artist_names(item),
        "album": item.get("album", {}).get("name", "") if item.get("album") else "",
        "type": item.get("type", "track"),
        "playing": is_playing,
        "progress": _format_ms(progress),
        "duration": _format_ms(duration),
        "progress_ms": progress,
        "duration_ms": duration,
        "device": device.get("name", "?"),
        "device_id": device.get("id", ""),
        "volume": device.get("volume_percent"),
        "shuffle": pb.get("shuffle_state", False),
        "repeat": pb.get("repeat_state", "off"),
        "uri": item.get("uri", ""),
    }

    def _rich() -> None:
        state_icon = "[green]Playing[/]" if is_playing else "[yellow]Paused[/]"
        title = f"{info['name']}  —  {info['artists']}"
        if info["album"]:
            title += f"  ({info['album']})"
        bar = f"{info['progress']} / {info['duration']}"
        body = f"{state_icon}  {bar}\n"
        body += f"Device: {info['device']}  |  Volume: {info['volume']}%  |  Shuffle: {'on' if info['shuffle'] else 'off'}  |  Repeat: {info['repeat']}"
        _out.print(Panel(body, title=title, border_style="green" if is_playing else "yellow"))

    def _plain() -> None:
        status_str = "playing" if is_playing else "paused"
        print(f"{info['name']}\t{info['artists']}\t{info['album']}\t{status_str}\t{info['progress']}/{info['duration']}\t{info['device']}")

    _print_output("status", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: info)


@app.command("current")
def current_cmd() -> None:
    """Show detailed currently playing item."""
    sp = _get_spotify()
    pb = _api_call(sp.current_playback, market=_state.effective_market)

    if not pb or not pb.get("item"):
        if _state.effective_output == OutputMode.JSON:
            _json_out("current", {"playing": False})
        else:
            _out.print("[dim]Nothing is currently playing.[/]")
        return

    item = pb["item"]
    device = pb.get("device", {})
    progress = pb.get("progress_ms", 0)
    duration = item.get("duration_ms", 0)
    is_playing = pb.get("is_playing", False)
    url = (item.get("external_urls") or {}).get("spotify", "")

    info: dict[str, Any] = {
        "name": item.get("name", "?"),
        "type": item.get("type", "track"),
        "artists": _artist_names(item),
        "album": item.get("album", {}).get("name", "") if item.get("album") else "",
        "progress": _format_ms(progress),
        "duration": _format_ms(duration),
        "progress_ms": progress,
        "duration_ms": duration,
        "playing": is_playing,
        "uri": item.get("uri", ""),
        "url": url,
        "device": device.get("name", "?"),
        "device_id": device.get("id", ""),
    }

    def _rich() -> None:
        table = Table(show_lines=True)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        for k, v in info.items():
            table.add_row(k, str(v))
        _out.print(table)

    def _plain() -> None:
        for k, v in info.items():
            print(f"{k}\t{v}")

    _print_output("current", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: info)


# Alias: now -> current
app.command("now", hidden=True)(current_cmd)


# ===========================================================================
# DEVICES
# ===========================================================================

@devices_app.command("list")
def devices_list() -> None:
    """List available Spotify Connect devices."""
    sp = _get_spotify()
    result = _api_call(sp.devices)
    devices = result.get("devices", []) if result else []

    if not devices:
        if _state.effective_output == OutputMode.JSON:
            _json_out("devices list", [])
        else:
            _out.print("[yellow]No devices found. Open Spotify on a device.[/]")
        return

    def _rich() -> None:
        table = Table(title="Devices")
        table.add_column("Name", style="bold")
        table.add_column("ID", style="dim")
        table.add_column("Type")
        table.add_column("Active")
        table.add_column("Volume")
        table.add_column("Restricted")
        for d in devices:
            active = "[green]yes[/]" if d.get("is_active") else "no"
            table.add_row(
                d.get("name", "?"),
                d.get("id", "?"),
                d.get("type", "?"),
                active,
                str(d.get("volume_percent", "?")),
                "yes" if d.get("is_restricted") else "no",
            )
        _out.print(table)

    def _plain() -> None:
        for d in devices:
            active = "*" if d.get("is_active") else ""
            print(f"{d.get('name', '?')}\t{d.get('id', '?')}\t{d.get('type', '?')}\t{active}\t{d.get('volume_percent', '?')}")

    _print_output("devices list", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: devices)


# Alias
devices_app.command("ls", hidden=True)(devices_list)


@devices_app.command("transfer")
def devices_transfer(
    device: str = typer.Argument(..., help="Device ID or name."),
    play: bool = typer.Option(True, "--play/--no-play", help="Start playing on transfer."),
) -> None:
    """Transfer playback to another device."""
    sp = _get_spotify()
    # Try as name first if it doesn't look like an ID
    target_id = device
    if not _ID_RE.match(device):
        target_id = _resolve_device_by_name(sp, device)
    _api_call(sp.transfer_playback, device_id=target_id, force_play=play)
    _out.print(f"[green]Playback transferred to {device}.[/]")


# ===========================================================================
# PLAYBACK CONTROL
# ===========================================================================

@app.command("play")
def play_cmd(
    query: str = typer.Argument("", help="Track/album/playlist URI, URL, ID, or search query. Empty = resume."),
    position_ms: int = typer.Option(0, "--position-ms", help="Start position in ms."),
    from_track: int = typer.Option(0, "--from-track-number", help="1-based track number for album/playlist contexts."),
    type_hint: str = typer.Option("", "--type", help="Resource type hint (track, album, playlist)."),
) -> None:
    """Play or resume. With a query, searches and plays the result."""
    sp = _get_spotify()
    device = _select_device(sp)

    if not query:
        # Resume
        _api_call(sp.start_playback, device_id=device)
        _out.print("[green]Playback resumed.[/]")
        return

    ptype = type_hint or "track"
    # Try to detect context types
    resource = _resolve_resource(query, preferred_type=ptype, sp=sp)
    logger.debug("Resolved: %s (%s)", resource.uri, resource.resource_type)

    kwargs: dict[str, Any] = {"device_id": device}
    if position_ms > 0:
        kwargs["position_ms"] = position_ms

    if resource.resource_type in ("album", "playlist"):
        kwargs["context_uri"] = resource.uri
        if from_track > 0:
            kwargs["offset"] = {"position": from_track - 1}
        _api_call(sp.start_playback, **kwargs)
    elif resource.resource_type in ("artist",):
        kwargs["context_uri"] = resource.uri
        _api_call(sp.start_playback, **kwargs)
    else:
        kwargs["uris"] = [resource.uri]
        _api_call(sp.start_playback, **kwargs)

    name = resource.name or resource.uri
    _out.print(f"[green]Playing:[/] {name}")


@app.command("pause")
def pause_cmd() -> None:
    """Pause playback."""
    sp = _get_spotify()
    device = _select_device(sp)
    _api_call(sp.pause_playback, device_id=device)
    _out.print("[yellow]Playback paused.[/]")


@app.command("resume")
def resume_cmd() -> None:
    """Resume playback (alias for play without args)."""
    sp = _get_spotify()
    device = _select_device(sp)
    _api_call(sp.start_playback, device_id=device)
    _out.print("[green]Playback resumed.[/]")


@app.command("stop")
def stop_cmd() -> None:
    """Stop playback. (Implemented as pause — Spotify has no separate stop endpoint.)"""
    sp = _get_spotify()
    device = _select_device(sp)
    _api_call(sp.pause_playback, device_id=device)
    _out.print("[yellow]Playback stopped (paused). Note: Spotify has no true stop endpoint.[/]")


@app.command("next")
def next_cmd() -> None:
    """Skip to next track."""
    sp = _get_spotify()
    device = _select_device(sp)
    _api_call(sp.next_track, device_id=device)
    _out.print("[green]Skipped to next.[/]")


@app.command("previous")
def previous_cmd() -> None:
    """Skip to previous track."""
    sp = _get_spotify()
    device = _select_device(sp)
    _api_call(sp.previous_track, device_id=device)
    _out.print("[green]Skipped to previous.[/]")


# Alias
app.command("prev", hidden=True)(previous_cmd)


@app.command("seek")
def seek_cmd(
    position: str = typer.Argument(..., help="Position: ms, mm:ss, +10s, -15s."),
) -> None:
    """Seek to a position in the current track."""
    sp = _get_spotify()
    pb = _api_call(sp.current_playback)
    current_ms = pb.get("progress_ms", 0) if pb else 0
    duration_ms = pb.get("item", {}).get("duration_ms", 0) if pb and pb.get("item") else 0
    target = _parse_seek(position, current_ms, duration_ms)
    device = _select_device(sp)
    _api_call(sp.seek_track, position_ms=target, device_id=device)
    _out.print(f"[green]Seeked to {_format_ms(target)}[/]")


@app.command("volume")
def volume_cmd(
    percent: int = typer.Argument(..., help="Volume percent 0-100."),
) -> None:
    """Set playback volume."""
    if not 0 <= percent <= 100:
        _die("Volume must be 0-100.", ExitCode.INVALID_INPUT)
    sp = _get_spotify()
    device = _select_device(sp)
    _api_call(sp.volume, volume_percent=percent, device_id=device)
    _out.print(f"[green]Volume set to {percent}%[/]")


# Alias
app.command("vol", hidden=True)(volume_cmd)


@app.command("repeat")
def repeat_cmd(
    mode: str = typer.Argument(..., help="Repeat mode: off, track, context."),
) -> None:
    """Set repeat mode."""
    if mode not in ("off", "track", "context"):
        _die("Repeat mode must be: off, track, context.", ExitCode.INVALID_INPUT)
    sp = _get_spotify()
    device = _select_device(sp)
    _api_call(sp.repeat, state=mode, device_id=device)
    _out.print(f"[green]Repeat: {mode}[/]")


@app.command("shuffle")
def shuffle_cmd(
    mode: str = typer.Argument(..., help="Shuffle: on, off, toggle."),
) -> None:
    """Set shuffle mode."""
    sp = _get_spotify()
    if mode == "toggle":
        pb = _api_call(sp.current_playback)
        current = pb.get("shuffle_state", False) if pb else False
        mode = "off" if current else "on"
    if mode not in ("on", "off"):
        _die("Shuffle mode must be: on, off, toggle.", ExitCode.INVALID_INPUT)
    device = _select_device(sp)
    _api_call(sp.shuffle, state=(mode == "on"), device_id=device)
    _out.print(f"[green]Shuffle: {mode}[/]")


# ===========================================================================
# QUEUE
# ===========================================================================

@queue_app.command("list")
def queue_list() -> None:
    """Show the current playback queue."""
    sp = _get_spotify()
    result = _api_call(sp.queue)
    if not result:
        _out.print("[dim]Queue is empty or unavailable.[/]")
        return

    currently = result.get("currently_playing")
    items = result.get("queue", [])

    def _rich() -> None:
        if currently:
            _out.print(f"[bold]Now playing:[/] {currently.get('name', '?')} — {_artist_names(currently)}")
        if not items:
            _out.print("[dim]Queue is empty.[/]")
            return
        table = Table(title="Queue")
        table.add_column("#", style="dim")
        table.add_column("Track", style="bold")
        table.add_column("Artist")
        table.add_column("URI", style="dim")
        for i, t in enumerate(items, 1):
            table.add_row(str(i), t.get("name", "?"), _artist_names(t), t.get("uri", ""))
        _out.print(table)

    def _plain() -> None:
        if currently:
            print(f"NOW\t{currently.get('name', '?')}\t{_artist_names(currently)}")
        for i, t in enumerate(items, 1):
            print(f"{i}\t{t.get('name', '?')}\t{_artist_names(t)}\t{t.get('uri', '')}")

    def _data() -> dict[str, Any]:
        return {"currently_playing": currently, "queue": items}

    _print_output("queue list", rich_fn=_rich, plain_fn=_plain, data_fn=_data)


queue_app.command("ls", hidden=True)(queue_list)


@queue_app.command("add")
def queue_add(
    query: str = typer.Argument(..., help="Track URI, URL, ID, or search query."),
) -> None:
    """Add a track to the queue."""
    sp = _get_spotify()
    resource = _resolve_resource(query, preferred_type="track", sp=sp)
    device = _select_device(sp)
    _api_call(sp.add_to_queue, uri=resource.uri, device_id=device)
    _out.print(f"[green]Queued:[/] {resource.name or resource.uri}")


@queue_app.command("clear")
def queue_clear() -> None:
    """Clear the playback queue. (Not supported by Spotify API.)"""
    _out.print("[yellow]Queue clear is not supported by the Spotify Web API.[/]")
    _out.print("[dim]There is no endpoint to remove items from or clear the queue.")
    _out.print("This is a long-standing limitation of the Spotify platform.[/]")
    raise typer.Exit(code=int(ExitCode.API_ERROR))


@queue_app.command("remove")
def queue_remove(
    query: str = typer.Argument("", help="Track to remove."),
) -> None:
    """Remove an item from the queue. (Not supported by Spotify API.)"""
    _out.print("[yellow]Queue item removal is not supported by the Spotify Web API.[/]")
    _out.print("[dim]Playlist item removal is supported via 'playlist remove', but the")
    _out.print("playback queue does not expose a remove or reorder endpoint.[/]")
    raise typer.Exit(code=int(ExitCode.API_ERROR))


queue_app.command("rm", hidden=True)(queue_remove)


# ===========================================================================
# SEARCH
# ===========================================================================

@app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Search query."),
    type_filter: str = typer.Option("track", "--type", "-t", help="Result types: track, album, artist, playlist (comma-separated)."),
) -> None:
    """Search Spotify."""
    sp = _get_spotify()
    types = type_filter.replace(" ", "").strip()
    limit = min(_state.effective_limit, 10)
    results = _api_call(sp.search, q=query, type=types, limit=limit, market=_state.effective_market)

    all_items: dict[str, list[dict[str, Any]]] = {}
    for t in types.split(","):
        t = t.strip()
        key = f"{t}s"
        items = results.get(key, {}).get("items", []) if results else []
        if items:
            all_items[t] = items

    if not all_items:
        _out.print(f"[yellow]No results for: {query}[/]")
        return

    def _rich() -> None:
        for rtype, items in all_items.items():
            table = Table(title=f"{rtype.capitalize()}s")
            table.add_column("Name", style="bold")
            if rtype == "track":
                table.add_column("Artist")
                table.add_column("Album")
            elif rtype == "album":
                table.add_column("Artist")
                table.add_column("Year")
            elif rtype == "artist":
                table.add_column("Genres")
            table.add_column("URI", style="dim")
            for item in items:
                if rtype == "track":
                    table.add_row(item.get("name"), _artist_names(item), item.get("album", {}).get("name", ""), item.get("uri"))
                elif rtype == "album":
                    year = (item.get("release_date") or "")[:4]
                    table.add_row(item.get("name"), _artist_names(item), year, item.get("uri"))
                elif rtype == "artist":
                    genres = ", ".join(item.get("genres", [])[:3])
                    table.add_row(item.get("name"), genres, item.get("uri"))
                elif rtype == "playlist":
                    table.add_row(item.get("name"), item.get("uri"))
            _out.print(table)

    def _plain() -> None:
        for rtype, items in all_items.items():
            for item in items:
                name = item.get("name", "?")
                uri = item.get("uri", "")
                extra = _artist_names(item) if rtype in ("track", "album") else ""
                print(f"{rtype}\t{name}\t{extra}\t{uri}")

    _print_output("search", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: all_items)


# ===========================================================================
# TRACK COMMANDS
# ===========================================================================

@track_app.command("show")
def track_show(query: str = typer.Argument(..., help="Track URI, URL, ID, or search.")) -> None:
    """Show track details."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)
    track = _api_call(sp.track, resource.resource_id, market=_state.effective_market)
    if not track:
        _die("Track not found.", ExitCode.API_ERROR)

    info = {
        "name": track.get("name"),
        "artists": _artist_names(track),
        "album": track.get("album", {}).get("name", ""),
        "duration": _format_ms(track.get("duration_ms")),
        "uri": track.get("uri"),
        "url": (track.get("external_urls") or {}).get("spotify", ""),
        "track_number": track.get("track_number"),
        "disc_number": track.get("disc_number"),
        "explicit": track.get("explicit", False),
    }

    def _rich() -> None:
        table = Table(title="Track", show_lines=True)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        for k, v in info.items():
            table.add_row(k, str(v))
        _out.print(table)

    def _plain() -> None:
        for k, v in info.items():
            print(f"{k}\t{v}")

    _print_output("track show", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: info)


@track_app.command("play")
def track_play(query: str = typer.Argument(..., help="Track to play.")) -> None:
    """Play a specific track."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)
    device = _select_device(sp)
    _api_call(sp.start_playback, device_id=device, uris=[resource.uri])
    _out.print(f"[green]Playing track:[/] {resource.name or resource.uri}")


@track_app.command("queue")
def track_queue(query: str = typer.Argument(..., help="Track to queue.")) -> None:
    """Add a track to the queue."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)
    device = _select_device(sp)
    _api_call(sp.add_to_queue, uri=resource.uri, device_id=device)
    _out.print(f"[green]Queued:[/] {resource.name or resource.uri}")


@track_app.command("save")
def track_save(query: str = typer.Argument(..., help="Track to save.")) -> None:
    """Save a track to your library."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)
    _api_call(sp.current_user_saved_tracks_add, tracks=[resource.resource_id])
    _out.print(f"[green]Saved:[/] {resource.name or resource.uri}")


@track_app.command("unsave")
def track_unsave(query: str = typer.Argument(..., help="Track to unsave.")) -> None:
    """Remove a track from your library."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)
    _api_call(sp.current_user_saved_tracks_delete, tracks=[resource.resource_id])
    _out.print(f"[yellow]Unsaved:[/] {resource.name or resource.uri}")


@track_app.command("check")
def track_check(query: str = typer.Argument(..., help="Track to check.")) -> None:
    """Check if a track is saved in your library."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)
    result = _api_call(sp.current_user_saved_tracks_contains, tracks=[resource.resource_id])
    saved = result[0] if result else False
    if _state.effective_output == OutputMode.JSON:
        _json_out("track check", {"uri": resource.uri, "saved": saved})
    else:
        icon = "[green]Saved[/]" if saved else "[dim]Not saved[/]"
        _out.print(f"{resource.name or resource.uri}: {icon}")


@track_app.command("open")
def track_open(query: str = typer.Argument(..., help="Track to open.")) -> None:
    """Print the Spotify URL for a track."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)
    url = _spotify_url("track", resource.resource_id)
    print(url)


@track_app.command("audio")
def track_audio(query: str = typer.Argument(..., help="Track for audio features.")) -> None:
    """Show audio features for a track (requires extended API access)."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)
    try:
        features = _api_call(sp.audio_features, tracks=[resource.resource_id])
        if features and features[0]:
            feat = features[0]
            if _state.effective_output == OutputMode.JSON:
                _json_out("track audio", feat)
            else:
                table = Table(title="Audio Features", show_lines=True)
                table.add_column("Feature", style="bold")
                table.add_column("Value")
                for k in ("danceability", "energy", "key", "loudness", "mode", "speechiness",
                           "acousticness", "instrumentalness", "liveness", "valence", "tempo",
                           "duration_ms", "time_signature"):
                    table.add_row(k, str(feat.get(k, "—")))
                _out.print(table)
        else:
            _out.print("[yellow]No audio features available.[/]")
    except SystemExit:
        raise
    except Exception:
        _out.print("[yellow]Audio features are restricted to apps with extended API access (since Nov 2024).[/]")
        _out.print("[dim]This endpoint is not available to new applications.[/]")


# ===========================================================================
# ALBUM COMMANDS
# ===========================================================================

@album_app.command("show")
def album_show(query: str = typer.Argument(..., help="Album URI, URL, ID, or search.")) -> None:
    """Show album details."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "album", sp)
    album = _api_call(sp.album, resource.resource_id, market=_state.effective_market)
    if not album:
        _die("Album not found.", ExitCode.API_ERROR)

    info = {
        "name": album.get("name"),
        "artists": _artist_names(album),
        "release_date": album.get("release_date", ""),
        "total_tracks": album.get("total_tracks", 0),
        "album_type": album.get("album_type", ""),
        "uri": album.get("uri"),
        "url": (album.get("external_urls") or {}).get("spotify", ""),
        "label": album.get("label", ""),
    }

    def _rich() -> None:
        table = Table(title="Album", show_lines=True)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        for k, v in info.items():
            table.add_row(k, str(v))
        _out.print(table)

    def _plain() -> None:
        for k, v in info.items():
            print(f"{k}\t{v}")

    _print_output("album show", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: info)


@album_app.command("play")
def album_play(
    query: str = typer.Argument(..., help="Album to play."),
    from_track: int = typer.Option(0, "--from-track-number", help="1-based track number."),
) -> None:
    """Play an album."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "album", sp)
    device = _select_device(sp)
    kwargs: dict[str, Any] = {"device_id": device, "context_uri": resource.uri}
    if from_track > 0:
        kwargs["offset"] = {"position": from_track - 1}
    _api_call(sp.start_playback, **kwargs)
    _out.print(f"[green]Playing album:[/] {resource.name or resource.uri}")


@album_app.command("tracks")
def album_tracks(query: str = typer.Argument(..., help="Album to list tracks from.")) -> None:
    """List tracks in an album."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "album", sp)
    result = _api_call(sp.album_tracks, resource.resource_id, limit=50, market=_state.effective_market)
    tracks = result.get("items", []) if result else []

    def _rich() -> None:
        table = Table(title="Album Tracks")
        table.add_column("#", style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Artist")
        table.add_column("Duration")
        table.add_column("URI", style="dim")
        for t in tracks:
            table.add_row(
                str(t.get("track_number", "")),
                t.get("name", "?"),
                _artist_names(t),
                _format_ms(t.get("duration_ms")),
                t.get("uri", ""),
            )
        _out.print(table)

    def _plain() -> None:
        for t in tracks:
            print(f"{t.get('track_number', '')}\t{t.get('name', '?')}\t{_artist_names(t)}\t{t.get('uri', '')}")

    _print_output("album tracks", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: tracks)


@album_app.command("save")
def album_save(query: str = typer.Argument(..., help="Album to save.")) -> None:
    """Save an album to your library."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "album", sp)
    _api_call(sp.current_user_saved_albums_add, albums=[resource.resource_id])
    _out.print(f"[green]Saved album:[/] {resource.name or resource.uri}")


@album_app.command("unsave")
def album_unsave(query: str = typer.Argument(..., help="Album to unsave.")) -> None:
    """Remove an album from your library."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "album", sp)
    _api_call(sp.current_user_saved_albums_delete, albums=[resource.resource_id])
    _out.print(f"[yellow]Unsaved album:[/] {resource.name or resource.uri}")


@album_app.command("check")
def album_check(query: str = typer.Argument(..., help="Album to check.")) -> None:
    """Check if an album is saved in your library."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "album", sp)
    result = _api_call(sp.current_user_saved_albums_contains, albums=[resource.resource_id])
    saved = result[0] if result else False
    if _state.effective_output == OutputMode.JSON:
        _json_out("album check", {"uri": resource.uri, "saved": saved})
    else:
        icon = "[green]Saved[/]" if saved else "[dim]Not saved[/]"
        _out.print(f"{resource.name or resource.uri}: {icon}")


# ===========================================================================
# ARTIST COMMANDS
# ===========================================================================

@artist_app.command("show")
def artist_show(query: str = typer.Argument(..., help="Artist URI, URL, ID, or search.")) -> None:
    """Show artist details."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "artist", sp)
    art = _api_call(sp.artist, resource.resource_id)
    if not art:
        _die("Artist not found.", ExitCode.API_ERROR)

    info = {
        "name": art.get("name"),
        "genres": ", ".join(art.get("genres", [])),
        "uri": art.get("uri"),
        "url": (art.get("external_urls") or {}).get("spotify", ""),
    }

    def _rich() -> None:
        table = Table(title="Artist", show_lines=True)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        for k, v in info.items():
            table.add_row(k, str(v))
        _out.print(table)

    def _plain() -> None:
        for k, v in info.items():
            print(f"{k}\t{v}")

    _print_output("artist show", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: info)


@artist_app.command("top")
def artist_top(query: str = typer.Argument(..., help="Artist name or URI.")) -> None:
    """Show top tracks for an artist (search-based fallback — endpoint removed Feb 2026)."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "artist", sp)
    art = _api_call(sp.artist, resource.resource_id)
    artist_name = art.get("name", query) if art else query

    # Fallback: search for tracks by this artist
    results = _api_call(sp.search, q=f"artist:{artist_name}", type="track", limit=10, market=_state.effective_market)
    tracks = results.get("tracks", {}).get("items", []) if results else []

    if not tracks:
        _out.print(f"[yellow]No tracks found for artist: {artist_name}[/]")
        return

    _out.print("[dim]Note: artist top-tracks endpoint was removed Feb 2026. Results are search-based.[/]")

    def _rich() -> None:
        table = Table(title=f"Top Tracks — {artist_name}")
        table.add_column("#", style="dim")
        table.add_column("Track", style="bold")
        table.add_column("Album")
        table.add_column("URI", style="dim")
        for i, t in enumerate(tracks, 1):
            table.add_row(str(i), t.get("name", "?"), t.get("album", {}).get("name", ""), t.get("uri", ""))
        _out.print(table)

    def _plain() -> None:
        for i, t in enumerate(tracks, 1):
            print(f"{i}\t{t.get('name', '?')}\t{t.get('album', {}).get('name', '')}\t{t.get('uri', '')}")

    _print_output("artist top", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: tracks)


@artist_app.command("albums")
def artist_albums(query: str = typer.Argument(..., help="Artist name or URI.")) -> None:
    """List albums by an artist."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "artist", sp)
    result = _api_call(sp.artist_albums, resource.resource_id, album_type="album,single", limit=_state.effective_limit)
    albums = result.get("items", []) if result else []

    if not albums:
        _out.print("[yellow]No albums found.[/]")
        return

    def _rich() -> None:
        table = Table(title="Artist Albums")
        table.add_column("Name", style="bold")
        table.add_column("Type")
        table.add_column("Year")
        table.add_column("Tracks")
        table.add_column("URI", style="dim")
        for a in albums:
            table.add_row(
                a.get("name", "?"),
                a.get("album_type", ""),
                (a.get("release_date") or "")[:4],
                str(a.get("total_tracks", "")),
                a.get("uri", ""),
            )
        _out.print(table)

    def _plain() -> None:
        for a in albums:
            print(f"{a.get('name', '?')}\t{a.get('album_type', '')}\t{(a.get('release_date') or '')[:4]}\t{a.get('uri', '')}")

    _print_output("artist albums", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: albums)


@artist_app.command("follow")
def artist_follow(query: str = typer.Argument(..., help="Artist to follow.")) -> None:
    """Follow an artist."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "artist", sp)
    _api_call(sp.user_follow_artists, ids=[resource.resource_id])
    _out.print(f"[green]Following:[/] {resource.name or resource.uri}")


@artist_app.command("unfollow")
def artist_unfollow(query: str = typer.Argument(..., help="Artist to unfollow.")) -> None:
    """Unfollow an artist."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "artist", sp)
    _api_call(sp.user_unfollow_artists, ids=[resource.resource_id])
    _out.print(f"[yellow]Unfollowed:[/] {resource.name or resource.uri}")


@artist_app.command("related")
def artist_related(query: str = typer.Argument(..., help="Artist name or URI.")) -> None:
    """Show related artists (requires extended API access)."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "artist", sp)
    try:
        result = _api_call(sp.artist_related_artists, resource.resource_id)
        artists = result.get("artists", []) if result else []
        if not artists:
            _out.print("[yellow]No related artists found.[/]")
            return

        def _rich() -> None:
            table = Table(title="Related Artists")
            table.add_column("Name", style="bold")
            table.add_column("Genres")
            table.add_column("URI", style="dim")
            for a in artists:
                table.add_row(a.get("name", "?"), ", ".join(a.get("genres", [])[:3]), a.get("uri", ""))
            _out.print(table)

        def _plain() -> None:
            for a in artists:
                print(f"{a.get('name', '?')}\t{', '.join(a.get('genres', [])[:3])}\t{a.get('uri', '')}")

        _print_output("artist related", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: artists)
    except SystemExit:
        raise
    except Exception:
        _out.print("[yellow]Related artists endpoint is restricted to apps with extended API access (since Nov 2024).[/]")
        _out.print("[dim]This endpoint is not available to new applications.[/]")


# ===========================================================================
# PLAYLIST COMMANDS
# ===========================================================================

@playlist_app.command("list")
def playlist_list(
    all_pages: bool = typer.Option(False, "--all", help="Fetch all playlists."),
) -> None:
    """List your playlists."""
    sp = _get_spotify()
    limit = _state.effective_limit
    offset = _state.effective_offset

    if all_pages:
        playlists: list[dict[str, Any]] = []
        while True:
            result = _api_call(sp.current_user_playlists, limit=50, offset=offset)
            items = result.get("items", []) if result else []
            if not items:
                break
            playlists.extend(items)
            if not result.get("next"):
                break
            offset += 50
    else:
        result = _api_call(sp.current_user_playlists, limit=limit, offset=offset)
        playlists = result.get("items", []) if result else []

    if not playlists:
        _out.print("[dim]No playlists found.[/]")
        return

    def _rich() -> None:
        table = Table(title="Your Playlists")
        table.add_column("Name", style="bold")
        table.add_column("Tracks")
        table.add_column("Owner")
        table.add_column("Public")
        table.add_column("URI", style="dim")
        for p in playlists:
            table.add_row(
                p.get("name", "?"),
                str(p.get("tracks", {}).get("total", "")),
                p.get("owner", {}).get("display_name", "?"),
                "yes" if p.get("public") else "no",
                p.get("uri", ""),
            )
        _out.print(table)

    def _plain() -> None:
        for p in playlists:
            print(f"{p.get('name', '?')}\t{p.get('tracks', {}).get('total', '')}\t{p.get('uri', '')}")

    _print_output("playlist list", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: playlists)


playlist_app.command("ls", hidden=True)(playlist_list)


@playlist_app.command("show")
def playlist_show(query: str = typer.Argument(..., help="Playlist URI, URL, ID, or search.")) -> None:
    """Show playlist details."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "playlist", sp)
    pl = _api_call(sp.playlist, resource.resource_id, market=_state.effective_market)
    if not pl:
        _die("Playlist not found.", ExitCode.API_ERROR)

    info = {
        "name": pl.get("name"),
        "description": pl.get("description", ""),
        "owner": pl.get("owner", {}).get("display_name", "?"),
        "total_tracks": pl.get("tracks", {}).get("total", 0),
        "public": pl.get("public"),
        "collaborative": pl.get("collaborative"),
        "uri": pl.get("uri"),
        "url": (pl.get("external_urls") or {}).get("spotify", ""),
    }

    def _rich() -> None:
        table = Table(title="Playlist", show_lines=True)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        for k, v in info.items():
            table.add_row(k, str(v))
        _out.print(table)

    def _plain() -> None:
        for k, v in info.items():
            print(f"{k}\t{v}")

    _print_output("playlist show", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: info)


@playlist_app.command("create")
def playlist_create(
    name: str = typer.Argument(..., help="Playlist name."),
    description: str = typer.Option("", "--description", "-d", help="Playlist description."),
    public: bool = typer.Option(True, "--public/--private", help="Public or private."),
    collaborative: bool = typer.Option(False, "--collaborative", help="Collaborative playlist."),
) -> None:
    """Create a new playlist."""
    sp = _get_spotify()
    me = _api_call(sp.current_user)
    user_id = me.get("id") if me else None
    if not user_id:
        _die("Could not determine user ID.", ExitCode.AUTH_CONFIG_ERROR)
    result = _api_call(sp.user_playlist_create, user_id, name, public=public, collaborative=collaborative, description=description)
    if _state.effective_output == OutputMode.JSON:
        _json_out("playlist create", result)
    else:
        _out.print(f"[green]Created playlist:[/] {name}")
        if result:
            _out.print(f"[dim]URI: {result.get('uri', '')}[/]")


@playlist_app.command("rename")
def playlist_rename(
    playlist: str = typer.Argument(..., help="Playlist URI, URL, ID, or search."),
    new_name: str = typer.Argument(..., help="New playlist name."),
) -> None:
    """Rename a playlist."""
    sp = _get_spotify()
    resource = _resolve_resource(playlist, "playlist", sp)
    _api_call(sp.playlist_change_details, resource.resource_id, name=new_name)
    _out.print(f"[green]Renamed to:[/] {new_name}")


@playlist_app.command("describe")
def playlist_describe(
    playlist: str = typer.Argument(..., help="Playlist."),
    description: str = typer.Argument(..., help="New description."),
) -> None:
    """Set the description of a playlist."""
    sp = _get_spotify()
    resource = _resolve_resource(playlist, "playlist", sp)
    _api_call(sp.playlist_change_details, resource.resource_id, description=description)
    _out.print("[green]Description updated.[/]")


@playlist_app.command("set-public")
def playlist_set_public(playlist: str = typer.Argument(..., help="Playlist.")) -> None:
    """Make a playlist public."""
    sp = _get_spotify()
    resource = _resolve_resource(playlist, "playlist", sp)
    _api_call(sp.playlist_change_details, resource.resource_id, public=True)
    _out.print("[green]Playlist is now public.[/]")


@playlist_app.command("set-private")
def playlist_set_private(playlist: str = typer.Argument(..., help="Playlist.")) -> None:
    """Make a playlist private."""
    sp = _get_spotify()
    resource = _resolve_resource(playlist, "playlist", sp)
    _api_call(sp.playlist_change_details, resource.resource_id, public=False)
    _out.print("[green]Playlist is now private.[/]")


@playlist_app.command("follow")
def playlist_follow(playlist: str = typer.Argument(..., help="Playlist.")) -> None:
    """Follow a playlist."""
    sp = _get_spotify()
    resource = _resolve_resource(playlist, "playlist", sp)
    _api_call(sp.current_user_follow_playlist, resource.resource_id)
    _out.print(f"[green]Following playlist:[/] {resource.name or resource.uri}")


@playlist_app.command("unfollow")
def playlist_unfollow(playlist: str = typer.Argument(..., help="Playlist.")) -> None:
    """Unfollow a playlist."""
    sp = _get_spotify()
    resource = _resolve_resource(playlist, "playlist", sp)
    _api_call(sp.current_user_unfollow_playlist, resource.resource_id)
    _out.print(f"[yellow]Unfollowed playlist:[/] {resource.name or resource.uri}")


@playlist_app.command("items")
def playlist_items(
    playlist: str = typer.Argument(..., help="Playlist."),
) -> None:
    """List items in a playlist."""
    sp = _get_spotify()
    resource = _resolve_resource(playlist, "playlist", sp)
    result = _api_call(sp.playlist_items, resource.resource_id, limit=_state.effective_limit, offset=_state.effective_offset, market=_state.effective_market)
    items = result.get("items", []) if result else []

    def _rich() -> None:
        table = Table(title="Playlist Items")
        table.add_column("#", style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Artist")
        table.add_column("Duration")
        table.add_column("URI", style="dim")
        for i, it in enumerate(items, _state.effective_offset + 1):
            track = it.get("track") or {}
            table.add_row(
                str(i),
                track.get("name", "?"),
                _artist_names(track),
                _format_ms(track.get("duration_ms")),
                track.get("uri", ""),
            )
        _out.print(table)

    def _plain() -> None:
        for i, it in enumerate(items, _state.effective_offset + 1):
            track = it.get("track") or {}
            print(f"{i}\t{track.get('name', '?')}\t{_artist_names(track)}\t{track.get('uri', '')}")

    _print_output("playlist items", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: items)


@playlist_app.command("add")
def playlist_add(
    playlist: str = typer.Argument(..., help="Playlist."),
    tracks: list[str] = typer.Argument(..., help="One or more track URIs or search queries."),
) -> None:
    """Add tracks to a playlist."""
    sp = _get_spotify()
    pl_resource = _resolve_resource(playlist, "playlist", sp)
    track_resources = _resolve_resources(tracks, "track", sp)
    uris = [r.uri for r in track_resources]
    _api_call(sp.playlist_add_items, pl_resource.resource_id, uris)
    _out.print(f"[green]Added {len(uris)} track(s) to playlist.[/]")


@playlist_app.command("remove")
def playlist_remove(
    playlist: str = typer.Argument(..., help="Playlist."),
    tracks: list[str] = typer.Argument(..., help="One or more track URIs or search queries."),
    all_matches: bool = typer.Option(True, "--all-matches/--first-match", help="Remove all or first match."),
) -> None:
    """Remove tracks from a playlist."""
    sp = _get_spotify()
    pl_resource = _resolve_resource(playlist, "playlist", sp)
    track_resources = _resolve_resources(tracks, "track", sp)
    uris = [r.uri for r in track_resources]
    _api_call(sp.playlist_remove_all_occurrences_of_items, pl_resource.resource_id, uris)
    _out.print(f"[yellow]Removed {len(uris)} track(s) from playlist.[/]")


playlist_app.command("rm", hidden=True)(playlist_remove)


@playlist_app.command("clear")
def playlist_clear(
    playlist: str = typer.Argument(..., help="Playlist."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Remove all items from a playlist."""
    if not (yes or _state.auto_yes):
        if not _confirm("Clear all items from this playlist?"):
            raise typer.Abort()
    sp = _get_spotify()
    pl_resource = _resolve_resource(playlist, "playlist", sp)
    _api_call(sp.playlist_replace_items, pl_resource.resource_id, [])
    _out.print("[yellow]Playlist cleared.[/]")


@playlist_app.command("reorder")
def playlist_reorder(
    playlist: str = typer.Argument(..., help="Playlist."),
    range_start: int = typer.Option(..., "--from", help="0-based start index."),
    insert_before: int = typer.Option(..., "--to", help="0-based insert-before index."),
    length: int = typer.Option(1, "--length", help="Number of items to move."),
) -> None:
    """Reorder items in a playlist."""
    sp = _get_spotify()
    pl_resource = _resolve_resource(playlist, "playlist", sp)
    _api_call(sp.playlist_reorder_items, pl_resource.resource_id, range_start=range_start, insert_before=insert_before, range_length=length)
    _out.print("[green]Playlist reordered.[/]")


@playlist_app.command("replace")
def playlist_replace(
    playlist: str = typer.Argument(..., help="Playlist."),
    tracks: list[str] = typer.Argument(..., help="Replacement track URIs or search queries."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Replace all items in a playlist."""
    if not (yes or _state.auto_yes):
        if not _confirm("Replace ALL items in this playlist?"):
            raise typer.Abort()
    sp = _get_spotify()
    pl_resource = _resolve_resource(playlist, "playlist", sp)
    track_resources = _resolve_resources(tracks, "track", sp)
    uris = [r.uri for r in track_resources]
    _api_call(sp.playlist_replace_items, pl_resource.resource_id, uris)
    _out.print(f"[green]Playlist replaced with {len(uris)} track(s).[/]")


# ===========================================================================
# LIBRARY COMMANDS
# ===========================================================================

@library_app.command("tracks")
def library_tracks() -> None:
    """List saved tracks."""
    sp = _get_spotify()
    result = _api_call(sp.current_user_saved_tracks, limit=_state.effective_limit, offset=_state.effective_offset, market=_state.effective_market)
    items = result.get("items", []) if result else []

    def _rich() -> None:
        table = Table(title="Saved Tracks")
        table.add_column("#", style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Artist")
        table.add_column("Album")
        table.add_column("URI", style="dim")
        for i, it in enumerate(items, _state.effective_offset + 1):
            t = it.get("track") or {}
            table.add_row(str(i), t.get("name", "?"), _artist_names(t), t.get("album", {}).get("name", ""), t.get("uri", ""))
        _out.print(table)

    def _plain() -> None:
        for i, it in enumerate(items, _state.effective_offset + 1):
            t = it.get("track") or {}
            print(f"{i}\t{t.get('name', '?')}\t{_artist_names(t)}\t{t.get('uri', '')}")

    _print_output("library tracks", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: items)


@library_app.command("albums")
def library_albums() -> None:
    """List saved albums."""
    sp = _get_spotify()
    result = _api_call(sp.current_user_saved_albums, limit=_state.effective_limit, offset=_state.effective_offset, market=_state.effective_market)
    items = result.get("items", []) if result else []

    def _rich() -> None:
        table = Table(title="Saved Albums")
        table.add_column("#", style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Artist")
        table.add_column("Year")
        table.add_column("URI", style="dim")
        for i, it in enumerate(items, _state.effective_offset + 1):
            a = it.get("album") or {}
            table.add_row(str(i), a.get("name", "?"), _artist_names(a), (a.get("release_date") or "")[:4], a.get("uri", ""))
        _out.print(table)

    def _plain() -> None:
        for i, it in enumerate(items, _state.effective_offset + 1):
            a = it.get("album") or {}
            print(f"{i}\t{a.get('name', '?')}\t{_artist_names(a)}\t{a.get('uri', '')}")

    _print_output("library albums", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: items)


@library_app.command("check")
def library_check(query: str = typer.Argument(..., help="Track or album to check.")) -> None:
    """Check if an item is saved."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)
    if resource.resource_type == "album":
        result = _api_call(sp.current_user_saved_albums_contains, albums=[resource.resource_id])
    else:
        result = _api_call(sp.current_user_saved_tracks_contains, tracks=[resource.resource_id])
    saved = result[0] if result else False
    if _state.effective_output == OutputMode.JSON:
        _json_out("library check", {"uri": resource.uri, "saved": saved})
    else:
        icon = "[green]Saved[/]" if saved else "[dim]Not saved[/]"
        _out.print(f"{resource.name or resource.uri}: {icon}")


@library_app.command("save")
def library_save(query: str = typer.Argument(..., help="Track or album to save.")) -> None:
    """Save an item to your library."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)
    if resource.resource_type == "album":
        _api_call(sp.current_user_saved_albums_add, albums=[resource.resource_id])
    else:
        _api_call(sp.current_user_saved_tracks_add, tracks=[resource.resource_id])
    _out.print(f"[green]Saved:[/] {resource.name or resource.uri}")


@library_app.command("unsave")
def library_unsave(query: str = typer.Argument(..., help="Track or album to unsave.")) -> None:
    """Remove an item from your library."""
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)
    if resource.resource_type == "album":
        _api_call(sp.current_user_saved_albums_delete, albums=[resource.resource_id])
    else:
        _api_call(sp.current_user_saved_tracks_delete, tracks=[resource.resource_id])
    _out.print(f"[yellow]Unsaved:[/] {resource.name or resource.uri}")


# ===========================================================================
# RECENT / TOP
# ===========================================================================

@app.command("recent")
def recent_cmd() -> None:
    """Show recently played tracks."""
    sp = _get_spotify()
    result = _api_call(sp.current_user_recently_played, limit=_state.effective_limit)
    items = result.get("items", []) if result else []

    def _rich() -> None:
        table = Table(title="Recently Played")
        table.add_column("#", style="dim")
        table.add_column("Track", style="bold")
        table.add_column("Artist")
        table.add_column("Played At", style="dim")
        for i, it in enumerate(items, 1):
            t = it.get("track") or {}
            table.add_row(str(i), t.get("name", "?"), _artist_names(t), it.get("played_at", ""))
        _out.print(table)

    def _plain() -> None:
        for it in items:
            t = it.get("track") or {}
            print(f"{t.get('name', '?')}\t{_artist_names(t)}\t{it.get('played_at', '')}\t{t.get('uri', '')}")

    _print_output("recent", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: items)


@top_app.command("tracks")
def top_tracks(
    time_range: str = typer.Option("medium_term", "--time-range", help="short_term, medium_term, long_term."),
) -> None:
    """Show your top tracks."""
    sp = _get_spotify()
    result = _api_call(sp.current_user_top_tracks, limit=_state.effective_limit, offset=_state.effective_offset, time_range=time_range)
    items = result.get("items", []) if result else []

    def _rich() -> None:
        table = Table(title=f"Top Tracks ({time_range})")
        table.add_column("#", style="dim")
        table.add_column("Track", style="bold")
        table.add_column("Artist")
        table.add_column("URI", style="dim")
        for i, t in enumerate(items, _state.effective_offset + 1):
            table.add_row(str(i), t.get("name", "?"), _artist_names(t), t.get("uri", ""))
        _out.print(table)

    def _plain() -> None:
        for t in items:
            print(f"{t.get('name', '?')}\t{_artist_names(t)}\t{t.get('uri', '')}")

    _print_output("top tracks", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: items)


@top_app.command("artists")
def top_artists(
    time_range: str = typer.Option("medium_term", "--time-range", help="short_term, medium_term, long_term."),
) -> None:
    """Show your top artists."""
    sp = _get_spotify()
    result = _api_call(sp.current_user_top_artists, limit=_state.effective_limit, offset=_state.effective_offset, time_range=time_range)
    items = result.get("items", []) if result else []

    def _rich() -> None:
        table = Table(title=f"Top Artists ({time_range})")
        table.add_column("#", style="dim")
        table.add_column("Artist", style="bold")
        table.add_column("Genres")
        table.add_column("URI", style="dim")
        for i, a in enumerate(items, _state.effective_offset + 1):
            table.add_row(str(i), a.get("name", "?"), ", ".join(a.get("genres", [])[:3]), a.get("uri", ""))
        _out.print(table)

    def _plain() -> None:
        for a in items:
            print(f"{a.get('name', '?')}\t{', '.join(a.get('genres', [])[:3])}\t{a.get('uri', '')}")

    _print_output("top artists", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: items)


# ===========================================================================
# GENRE / MOOD / DISCOVER / RADIO
# ===========================================================================

@genre_app.command("list")
def genre_list() -> None:
    """List well-known Spotify genres. (Genre seeds endpoint removed Nov 2024.)"""
    _out.print("[dim]Note: Genre seeds endpoint was removed Nov 2024. Showing well-known genre list.[/]")

    def _rich() -> None:
        table = Table(title="Genres")
        table.add_column("Genre")
        for g in WELL_KNOWN_GENRES:
            table.add_row(g)
        _out.print(table)

    def _plain() -> None:
        for g in WELL_KNOWN_GENRES:
            print(g)

    _print_output("genre list", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: WELL_KNOWN_GENRES)


genre_app.command("ls", hidden=True)(genre_list)


@genre_app.command("search")
def genre_search(genre: str = typer.Argument(..., help="Genre to search for.")) -> None:
    """Search for playlists, tracks, and artists in a genre."""
    sp = _get_spotify()
    results: dict[str, Any] = {}
    for stype in ("playlist", "artist", "track"):
        r = _api_call(sp.search, q=f"genre:{genre}" if stype != "playlist" else genre, type=stype, limit=5, market=_state.effective_market)
        items = r.get(f"{stype}s", {}).get("items", []) if r else []
        if items:
            results[stype] = items

    if not results:
        _out.print(f"[yellow]No results for genre: {genre}[/]")
        return

    def _rich() -> None:
        for rtype, items in results.items():
            table = Table(title=f"{rtype.capitalize()}s — {genre}")
            table.add_column("Name", style="bold")
            table.add_column("URI", style="dim")
            for item in items:
                table.add_row(item.get("name", "?"), item.get("uri", ""))
            _out.print(table)

    def _plain() -> None:
        for rtype, items in results.items():
            for item in items:
                print(f"{rtype}\t{item.get('name', '?')}\t{item.get('uri', '')}")

    _print_output("genre search", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: results)


@mood_app.command("search")
def mood_search(mood: str = typer.Argument(..., help="Mood: chill, focus, happy, sad, workout, sleep, party, study.")) -> None:
    """Search by mood (heuristic — maps mood to playlist/track search queries)."""
    queries = MOOD_MAP.get(mood.lower(), [mood])
    sp = _get_spotify()
    all_playlists: list[dict[str, Any]] = []
    for q in queries:
        r = _api_call(sp.search, q=q, type="playlist", limit=3, market=_state.effective_market)
        items = r.get("playlists", {}).get("items", []) if r else []
        all_playlists.extend(items)

    if not all_playlists:
        _out.print(f"[yellow]No results for mood: {mood}[/]")
        return

    _out.print(f"[dim]Note: Mood matching is heuristic. Results are search-based, not guaranteed Spotify metadata.[/]")

    def _rich() -> None:
        table = Table(title=f"Mood: {mood}")
        table.add_column("Playlist", style="bold")
        table.add_column("Owner")
        table.add_column("URI", style="dim")
        for p in all_playlists:
            table.add_row(p.get("name", "?"), p.get("owner", {}).get("display_name", "?"), p.get("uri", ""))
        _out.print(table)

    def _plain() -> None:
        for p in all_playlists:
            print(f"{p.get('name', '?')}\t{p.get('owner', {}).get('display_name', '?')}\t{p.get('uri', '')}")

    _print_output("mood search", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: all_playlists)


@app.command("discover")
def discover_cmd() -> None:
    """Discovery helper: shows a mix of your top tracks and artists for exploration.

    Note: The recommendations endpoint was removed Nov 2024. This uses your
    top tracks and artists as a discovery starting point instead.
    """
    sp = _get_spotify()
    top_t = _api_call(sp.current_user_top_tracks, limit=5, time_range="short_term")
    top_a = _api_call(sp.current_user_top_artists, limit=5, time_range="short_term")
    tracks = top_t.get("items", []) if top_t else []
    artists = top_a.get("items", []) if top_a else []

    if not tracks and not artists:
        _out.print("[yellow]Not enough listening history for discovery.[/]")
        return

    # Search for fresh tracks based on top artists
    fresh: list[dict[str, Any]] = []
    for a in artists[:3]:
        r = _api_call(sp.search, q=f"artist:{a.get('name', '')}", type="track", limit=3, market=_state.effective_market)
        fresh.extend(r.get("tracks", {}).get("items", []) if r else [])

    def _rich() -> None:
        if tracks:
            _out.print("[bold]Your current top tracks:[/]")
            for t in tracks:
                _out.print(f"  {t.get('name', '?')} — {_artist_names(t)}")
        if fresh:
            _out.print("\n[bold]Discover based on your top artists:[/]")
            for t in fresh:
                _out.print(f"  {t.get('name', '?')} — {_artist_names(t)}  [dim]{t.get('uri', '')}[/]")

    def _plain() -> None:
        for t in tracks:
            print(f"top\t{t.get('name', '?')}\t{_artist_names(t)}\t{t.get('uri', '')}")
        for t in fresh:
            print(f"discover\t{t.get('name', '?')}\t{_artist_names(t)}\t{t.get('uri', '')}")

    _print_output("discover", rich_fn=_rich, plain_fn=_plain, data_fn=lambda: {"top_tracks": tracks, "discovered": fresh})


@app.command("radio")
def radio_cmd(
    query: str = typer.Argument(..., help="Track or artist to build radio from."),
) -> None:
    """Build a radio-like queue from a seed track or artist (search + queue heuristic).

    Note: There is no dedicated radio API. This searches for similar tracks
    by the same or related artists and adds them to your queue.
    """
    sp = _get_spotify()
    resource = _resolve_resource(query, "track", sp)

    # Get the seed artist
    if resource.resource_type == "track":
        track = _api_call(sp.track, resource.resource_id, market=_state.effective_market)
        artists = track.get("artists", []) if track else []
        artist_name = artists[0].get("name", query) if artists else query
    else:
        art = _api_call(sp.artist, resource.resource_id)
        artist_name = art.get("name", query) if art else query

    # Search for more tracks by the same artist
    results = _api_call(sp.search, q=f"artist:{artist_name}", type="track", limit=10, market=_state.effective_market)
    tracks = results.get("tracks", {}).get("items", []) if results else []

    if not tracks:
        _out.print(f"[yellow]No tracks found for radio seed: {query}[/]")
        return

    device = _select_device(sp)
    added = 0
    for t in tracks:
        try:
            _api_call(sp.add_to_queue, uri=t["uri"], device_id=device)
            added += 1
        except (SystemExit, Exception):
            pass

    _out.print(f"[green]Radio:[/] Added {added} tracks from {artist_name} to your queue.")
    _out.print("[dim]Note: This is a search-based heuristic. There is no dedicated radio API.[/]")


# ===========================================================================
# MAIN
# ===========================================================================

if __name__ == "__main__":
    app()


# ---------------------------------------------------------------------------
# SMOKE TESTS
# ---------------------------------------------------------------------------
# Run these manually after setup:
#
#   uv run spotify_cli.py --help
#   uv run spotify_cli.py auth --help
#   uv run spotify_cli.py auth status
#   uv run spotify_cli.py auth url
#   uv run spotify_cli.py auth login --no-open-browser
#   uv run spotify_cli.py auth callback-url 'http://127.0.0.1:8888/callback?code=XXXXX&state=YYYYY'
#   uv run spotify_cli.py auth export-token-info --masked
#   uv run spotify_cli.py auth export-token-info --raw --yes > token.json
#   uv run spotify_cli.py auth import-token-info token.json
#   uv run spotify_cli.py auth whoami
#   uv run spotify_cli.py doctor
#   uv run spotify_cli.py devices list
#   uv run spotify_cli.py search "bohemian rhapsody" --type track
#   uv run spotify_cli.py status
#   uv run spotify_cli.py current
#   uv run spotify_cli.py play "bohemian rhapsody"
#   uv run spotify_cli.py pause
#   uv run spotify_cli.py next
#   uv run spotify_cli.py previous
#   uv run spotify_cli.py seek 1:30
#   uv run spotify_cli.py volume 50
#   uv run spotify_cli.py shuffle toggle
#   uv run spotify_cli.py repeat track
#   uv run spotify_cli.py queue list
#   uv run spotify_cli.py queue add "hotel california"
#   uv run spotify_cli.py track show "stairway to heaven"
#   uv run spotify_cli.py album show "dark side of the moon"
#   uv run spotify_cli.py artist top "pink floyd"
#   uv run spotify_cli.py artist albums "pink floyd"
#   uv run spotify_cli.py playlist list
#   uv run spotify_cli.py playlist create "My Test Playlist"
#   uv run spotify_cli.py playlist add "My Test Playlist" "bohemian rhapsody" "hotel california"
#   uv run spotify_cli.py playlist items "My Test Playlist"
#   uv run spotify_cli.py playlist remove "My Test Playlist" "bohemian rhapsody"
#   uv run spotify_cli.py playlist clear "My Test Playlist" --yes
#   uv run spotify_cli.py library tracks
#   uv run spotify_cli.py recent
#   uv run spotify_cli.py top tracks
#   uv run spotify_cli.py top artists
#   uv run spotify_cli.py genre list
#   uv run spotify_cli.py mood search chill
#   uv run spotify_cli.py discover
#   uv run spotify_cli.py radio "pink floyd"
#   uv run spotify_cli.py auth logout --yes
