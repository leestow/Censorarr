"""Live Mute compatibility facade and simulation support.

Plex clients do not always include Media/Part/file in /status/sessions and some
clients do not expose a Companion timeline endpoint. This facade enriches those
Plex paths and adds a simulation mode that runs the real scheduler without
sending player volume commands.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.responses import Response

import integrations as integ
import live_mute_impl as _impl

_MEDIA_FILE_CACHE: dict[str, tuple[str, float]] = {}
_MEDIA_FILE_CACHE_SECONDS = 3600.0
_ORIGINAL_TIMELINE = _impl._timeline
_ORIGINAL_LIVE_CFG = _impl._live_cfg
_ORIGINAL_SAVE_SETTINGS = _impl._save_settings
_ORIGINAL_SET_VOLUME = _impl._set_volume
_ORIGINAL_EVENT = _impl._event
_SIMULATED_ACTIVE_KEYS: set[str] = set()
_SIMULATED_RESTORE_EVENT_KEYS: set[str] = set()
_SESSION_CLOCKS: dict[str, dict[str, Any]] = {}
_EXTRA_ROUTES_INSTALLED = False
_SIMULATION_RUNTIME = False

# Plex Web often advances /status/sessions viewOffset in coarse heartbeats.  Treat
# small discrepancies as heartbeat quantization, not as real seeks.  Rewinds are
# always honored immediately; large forward discontinuities are treated as seeks.
_CLOCK_SEEK_ERROR_MS = 4000
_CLOCK_FORWARD_SEEK_EXTRA_MS = 3000
_CLOCK_BACKWARD_JITTER_MS = 250
_CLOCK_MAX_HEARTBEAT_CORRECTION_MS = 120


def _first(value: Any) -> dict:
    return _impl._first(value)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _simulation_enabled(cfg: dict) -> bool:
    return _truthy((cfg.get("live_mute", {}) or {}).get("simulation_mode", False))


def _live_cfg(cfg: dict) -> dict[str, Any]:
    global _SIMULATION_RUNTIME
    out = _ORIGINAL_LIVE_CFG(cfg)
    out["simulation_mode"] = _simulation_enabled(cfg)
    _SIMULATION_RUNTIME = bool(out["simulation_mode"])
    if out["simulation_mode"]:
        out["require_volume_probe"] = False
    return out


def _save_settings(core, patch: dict[str, Any]) -> dict[str, Any]:
    if "simulation_mode" in patch:
        raw = core.yaml.safe_load(core.CONFIG.read_text(encoding="utf-8")) or {}
        raw.setdefault("live_mute", {})["simulation_mode"] = _truthy(patch.get("simulation_mode"))
        tmp = core.CONFIG.with_suffix(".tmp")
        tmp.write_text(core.yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        os.replace(tmp, core.CONFIG)
    return _ORIGINAL_SAVE_SETTINGS(core, patch)


def _session_key(session: dict) -> str:
    return str(session.get("key") or session.get("client_id") or session.get("rating_key") or "")


def _set_volume(session: dict, cfg: dict, volume: int, preferred_base: str = "") -> bool:
    key = _session_key(session)
    if _simulation_enabled(cfg):
        if int(volume) == 0 and key:
            _SIMULATED_ACTIVE_KEYS.add(key)
        elif int(volume) > 0 and key:
            _SIMULATED_ACTIVE_KEYS.discard(key)
        return True

    if key and key in _SIMULATED_ACTIVE_KEYS and int(volume) > 0:
        _SIMULATED_ACTIVE_KEYS.discard(key)
        _SIMULATED_RESTORE_EVENT_KEYS.add(key)
        return True
    return _ORIGINAL_SET_VOLUME(session, cfg, volume, preferred_base)


def _event(action: str, state: dict, **extra: Any) -> None:
    session = state.get("session", {}) or {}
    key = _session_key(session)
    simulated = key in _SIMULATED_RESTORE_EVENT_KEYS
    if not simulated and _impl._CORE is not None:
        try:
            cfg = _impl._CORE.pc.load_config(_impl._CORE.CONFIG)
            simulated = _simulation_enabled(cfg)
        except Exception:
            simulated = False
    if simulated:
        extra["simulated"] = True
        action = f"simulated-{action}"
    _ORIGINAL_EVENT(action, state, **extra)
    if key and action.endswith("unmute"):
        _SIMULATED_RESTORE_EVENT_KEYS.discard(key)


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
        raw_file = str(part.get("file") or "").strip() or _metadata_media_file(metadata, cfg)
        try:
            port = int(player.get("port") or 32500)
        except (TypeError, ValueError):
            port = 32500
        key = str(metadata.get("sessionKey") or session.get("id") or player.get("machineIdentifier") or metadata.get("ratingKey") or "")
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


def _predicted_at(clock: dict[str, Any], when_mono: float) -> int:
    position = int(clock.get("anchor_position") or 0)
    if str(clock.get("anchor_state") or "") == "playing":
        position += int(max(0.0, when_mono - float(clock.get("anchor_mono") or when_mono)) * 1000)
    return max(0, position)


def _session_timeline(session: dict) -> dict[str, Any]:
    """Seek-aware smooth clock for coarse Plex /status/sessions samples.

    Plex Web can repeat one viewOffset for several seconds and then jump forward.
    The local monotonic clock therefore remains authoritative during ordinary
    playback. New server samples are used to detect real seeks/state changes and
    to make only a tiny bounded correction for normal heartbeat quantization.
    """
    now = time.monotonic()
    observed = float(session.get("observed_mono") or now)
    state = str(session.get("state") or "").lower()
    server_position = max(0, int(session.get("view_offset_ms") or 0))
    media_file = str(session.get("local_file") or "")
    key = _session_key(session) or f"{session.get('player')}|{media_file}"

    clock = _SESSION_CLOCKS.get(key)
    if clock is None or str(clock.get("media_file") or "") != media_file:
        clock = {
            "media_file": media_file,
            "server_position": server_position,
            "server_state": state,
            "server_observed_mono": observed,
            "anchor_position": server_position,
            "anchor_mono": observed,
            "anchor_state": state,
            "last_seen_mono": now,
            "last_sync_reason": "initial",
        }
        _SESSION_CLOCKS[key] = clock
    else:
        old_server_position = int(clock.get("server_position") or 0)
        old_server_state = str(clock.get("server_state") or "")
        old_server_observed = float(clock.get("server_observed_mono") or observed)
        sample_changed = server_position != old_server_position or state != old_server_state

        if sample_changed:
            predicted = _predicted_at(clock, observed)
            error_ms = server_position - predicted
            observed_elapsed_ms = max(0, int((observed - old_server_observed) * 1000))
            server_advance_ms = server_position - old_server_position

            state_changed = state != old_server_state
            backward_seek = server_position < old_server_position - _CLOCK_BACKWARD_JITTER_MS
            paused_position_change = state != "playing" and server_position != old_server_position
            forward_seek = (
                state == "playing"
                and server_advance_ms - observed_elapsed_ms > _CLOCK_FORWARD_SEEK_EXTRA_MS
            )
            large_discontinuity = abs(error_ms) >= _CLOCK_SEEK_ERROR_MS

            if state_changed or backward_seek or paused_position_change or forward_seek or large_discontinuity:
                # Real transport change: honor Plex immediately.
                clock.update({
                    "anchor_position": server_position,
                    "anchor_mono": observed,
                    "anchor_state": state,
                    "last_sync_reason": "seek/state",
                })
            else:
                # Ordinary coarse heartbeat. Preserve continuous local playback and
                # only nudge a tiny amount so the UI/scheduler never jumps seconds.
                correction = max(
                    -_CLOCK_MAX_HEARTBEAT_CORRECTION_MS,
                    min(_CLOCK_MAX_HEARTBEAT_CORRECTION_MS, error_ms),
                )
                clock.update({
                    "anchor_position": max(0, predicted + correction),
                    "anchor_mono": observed,
                    "anchor_state": state,
                    "last_sync_reason": "heartbeat",
                })

            clock.update({
                "server_position": server_position,
                "server_state": state,
                "server_observed_mono": observed,
            })

        clock["last_seen_mono"] = now

    position = _predicted_at(clock, now)

    if len(_SESSION_CLOCKS) > 64:
        cutoff = now - 3600.0
        for stale_key in [k for k, v in _SESSION_CLOCKS.items() if float(v.get("last_seen_mono") or 0) < cutoff]:
            _SESSION_CLOCKS.pop(stale_key, None)

    return {
        "time_ms": max(0, position),
        "state": state,
        "volume": None,
        "controllable": "simulation-viewOffset-seek-aware" if _SIMULATION_RUNTIME else "session-viewOffset-seek-aware",
        "base": "",
    }


def _timeline(session: dict, token: str) -> dict[str, Any] | None:
    if _SIMULATION_RUNTIME:
        return _session_timeline(session)

    timeline = _ORIGINAL_TIMELINE(session, token)
    if timeline:
        return timeline
    return _session_timeline(session)


_impl.DEFAULTS.setdefault("simulation_mode", False)
_impl._live_cfg = _live_cfg
_impl._save_settings = _save_settings
_impl._set_volume = _set_volume
_impl._event = _event
_impl._parse_sessions = _parse_sessions
_impl._timeline = _timeline


def _script_response(core, filename: str) -> Response:
    path = core.STATIC / filename
    if not path.is_file():
        raise HTTPException(404, f"{filename} not found")
    return Response(path.read_text(encoding="utf-8"), media_type="application/javascript")


def install(app, core) -> None:
    global _EXTRA_ROUTES_INSTALLED
    result = _impl.install(app, core)
    if not _EXTRA_ROUTES_INSTALLED:
        _EXTRA_ROUTES_INSTALLED = True

        @app.get("/live-mute-base.js", include_in_schema=False)
        def live_mute_base_script(_: bool = Depends(core.auth)):
            return _script_response(core, "live-mute-base.js")

        @app.get("/live-mute-sim.js", include_in_schema=False)
        def live_mute_sim_script(_: bool = Depends(core.auth)):
            return _script_response(core, "live-mute-sim.js")
    return result


def __getattr__(name: str):
    return getattr(_impl, name)
