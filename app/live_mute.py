"""Live Mute facade with Plex session enrichment.

Plex clients do not always include Media/Part/file in /status/sessions and some
clients (notably Plex Web/Chrome and some Android TV builds) do not expose a
Companion timeline endpoint.  Keep the controller implementation isolated in
live_mute_impl.py and enrich those two Plex compatibility paths here.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import integrations as integ
import live_mute_impl as _impl

# Cache media-file metadata by Plex rating key so the 900 ms session refresh does
# not turn into a full /library/metadata request on every pass.
_MEDIA_FILE_CACHE: dict[str, tuple[str, float]] = {}
_MEDIA_FILE_CACHE_SECONDS = 3600.0
_ORIGINAL_TIMELINE = _impl._timeline


def _first(value: Any) -> dict:
    return _impl._first(value)


def _metadata_media_file(metadata: dict, cfg: dict) -> str:
    rating_key = str(metadata.get("ratingKey") or "").strip()
    metadata_key = str(metadata.get("key") or "").strip()
    lookup = metadata_key if metadata_key.startswith("/library/metadata/") else (f"/library/metadata/{rating_key}" if rating_key else "")
    cache_key = rating_key or lookup
    if not lookup:
        return ""

    now = time.monotonic()
    cached = _MEDIA_FILE_CACHE.get(cache_key)
    if cached and now - cached[1] < _MEDIA_FILE_CACHE_SECONDS:
        return cached[0]

    try:
        data = integ.plex_request(cfg, lookup, timeout=5)
        rows = (data.get("MediaContainer", {}) or {}).get("Metadata", []) or []
        full = _first(rows)
        media = _first(full.get("Media"))
        part = _first(media.get("Part"))
        raw_file = str(part.get("file") or "").strip()
        if raw_file:
            _MEDIA_FILE_CACHE[cache_key] = (raw_file, now)
            return raw_file
    except Exception as exc:
        logging.debug("Live Mute Plex metadata lookup failed for %s: %s", lookup, exc)
    return ""


def _parse_sessions(cfg: dict) -> list[dict[str, Any]]:
    data = integ.plex_request(cfg, "/status/sessions", timeout=5)
    items = (data.get("MediaContainer", {}) or {}).get("Metadata", []) or []
    if isinstance(items, dict):
        items = [items]
    now = time.monotonic()
    out: list[dict[str, Any]] = []

    for metadata in items:
        media_type = str(metadata.get("type") or "").lower()
        if media_type not in {"movie", "episode", "clip"}:
            continue

        user = _first(metadata.get("User"))
        player = _first(metadata.get("Player"))
        session = _first(metadata.get("Session"))
        media = _first(metadata.get("Media"))
        part = _first(media.get("Part"))
        raw_file = str(part.get("file") or "").strip()

        # Many Plex clients omit Part.file from /status/sessions.  Resolve the
        # ratingKey once through /library/metadata/<id> and cache the result.
        if not raw_file:
            raw_file = _metadata_media_file(metadata, cfg)

        try:
            port = int(player.get("port") or 32500)
        except (TypeError, ValueError):
            port = 32500

        key = str(
            metadata.get("sessionKey")
            or session.get("id")
            or player.get("machineIdentifier")
            or metadata.get("ratingKey")
            or ""
        )
        mapped = _impl._map_media_path(raw_file, media_type, cfg)
        out.append({
            "key": key,
            "rating_key": str(metadata.get("ratingKey") or ""),
            "title": str(metadata.get("grandparentTitle") or metadata.get("title") or "Unknown"),
            "item_title": str(metadata.get("title") or "Unknown"),
            "user": str(user.get("title") or "Unknown"),
            "player": str(player.get("title") or "Unknown"),
            "client_id": str(player.get("machineIdentifier") or ""),
            "address": str(player.get("address") or ""),
            "port": port,
            "state": str(player.get("state") or "").lower(),
            "view_offset_ms": int(metadata.get("viewOffset") or 0),
            "duration_ms": int(metadata.get("duration") or 0),
            "plex_file": raw_file,
            "local_file": str(mapped),
            "observed_mono": now,
        })
    return out


def _timeline(session: dict, token: str) -> dict[str, Any] | None:
    timeline = _ORIGINAL_TIMELINE(session, token)
    if timeline:
        return timeline

    # Some clients do not expose the Plex Companion timeline endpoint at all.
    # /status/sessions still gives us a current viewOffset every session refresh,
    # so interpolate from that observation.  Volume remains unknown; the existing
    # require_volume_probe/fallback_restore_volume safety setting decides whether
    # Censorarr may act on such a client.
    state = str(session.get("state") or "").lower()
    position = int(session.get("view_offset_ms") or 0)
    observed = float(session.get("observed_mono") or time.monotonic())
    if state == "playing":
        position += int(max(0.0, time.monotonic() - observed) * 1000)
    return {
        "time_ms": max(0, position),
        "state": state,
        "volume": None,
        "controllable": "session-viewOffset-fallback",
        "base": "",
    }


# The implementation's controller loop and API routes resolve these names from
# its own module globals, so patch the compatibility functions before install().
_impl._parse_sessions = _parse_sessions
_impl._timeline = _timeline


def install(app, core) -> None:
    return _impl.install(app, core)


def __getattr__(name: str):
    return getattr(_impl, name)
