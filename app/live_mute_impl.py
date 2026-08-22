"""Experimental on-the-fly profanity muting for Plex playback.

Censorarr already stores final profanity mute ranges in analysis report JSON files.
This module reuses those timestamps and temporarily changes the active Plex client's
volume instead of requiring playback of the generated CLEAN audio track.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response

import censorarr as pc
import integrations as integ

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "users": [],
    "lead_ms": 220,
    "tail_ms": 140,
    "loop_ms": 50,
    "timeline_sync_ms": 350,
    "session_refresh_ms": 900,
    "require_volume_probe": True,
    "fallback_restore_volume": 100,
}

_CORE = None
_INSTALLED = False
_STOP = threading.Event()
_LOCK = threading.RLock()
_STATES: dict[str, dict[str, Any]] = {}
_RECENT_EVENTS: list[dict[str, Any]] = []
_LAST_ERROR = ""
_COMMAND_ID = 1


def _next_command_id() -> int:
    global _COMMAND_ID
    with _LOCK:
        _COMMAND_ID = 1 if _COMMAND_ID >= 2_000_000_000 else _COMMAND_ID + 1
        return _COMMAND_ID


def _live_cfg(cfg: dict) -> dict[str, Any]:
    out = {**DEFAULTS, **(cfg.get("live_mute", {}) or {})}
    users = out.get("users", [])
    if isinstance(users, str):
        users = [x.strip() for x in users.split(",") if x.strip()]
    out["users"] = [str(x).strip() for x in (users or []) if str(x).strip()]
    out["enabled"] = bool(out.get("enabled", False))
    out["lead_ms"] = max(0, min(1500, int(out.get("lead_ms", 220) or 0)))
    out["tail_ms"] = max(0, min(1500, int(out.get("tail_ms", 140) or 0)))
    out["loop_ms"] = max(25, min(500, int(out.get("loop_ms", 50) or 50)))
    out["timeline_sync_ms"] = max(100, min(2000, int(out.get("timeline_sync_ms", 350) or 350)))
    out["session_refresh_ms"] = max(300, min(5000, int(out.get("session_refresh_ms", 900) or 900)))
    out["require_volume_probe"] = bool(out.get("require_volume_probe", True))
    out["fallback_restore_volume"] = max(0, min(100, int(out.get("fallback_restore_volume", 100) or 100)))
    return out


def _eligible_user(user: str, settings: dict[str, Any]) -> bool:
    wanted = {x.casefold() for x in settings.get("users", [])}
    return not wanted or str(user or "").strip().casefold() in wanted


def _first(value: Any) -> dict:
    if isinstance(value, list):
        return value[0] if value and isinstance(value[0], dict) else {}
    return value if isinstance(value, dict) else {}


def _map_media_path(raw: str, media_type: str, cfg: dict) -> Path:
    raw = str(raw or "")
    if not raw:
        return Path("")
    rating = cfg.get("rating_filter", {}) or {}
    tv_rating = ((cfg.get("tv", {}) or {}).get("rating_filter", {}) or {})
    mappings: list[dict] = []
    if media_type == "episode":
        mappings.extend(tv_rating.get("plex_path_mappings", []) or [])
    mappings.extend(rating.get("plex_path_mappings", []) or [])
    arr = cfg.get("arr_integrations", {}) or {}
    mappings.extend(((arr.get("radarr", {}) or {}).get("path_mappings", []) or []))
    mappings.extend(((arr.get("sonarr", {}) or {}).get("path_mappings", []) or []))
    normalized = raw.replace("\\", "/")
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        src = str(mapping.get("from", "")).rstrip("/\\").replace("\\", "/")
        dst = str(mapping.get("to", "")).rstrip("/\\")
        if src and (normalized == src or normalized.startswith(src + "/")):
            return Path(dst + normalized[len(src):])
    return Path(normalized)


def _ranges_from_payload(payload: dict[str, Any]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for row in payload.get("mute_ranges", []) or []:
        try:
            start = int(round(float(row.get("start")) * 1000))
            end = int(round(float(row.get("end")) * 1000))
        except (TypeError, ValueError, AttributeError):
            continue
        if end > start:
            ranges.append((max(0, start), max(0, end)))
    ranges.sort()
    return ranges


def _read_report(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _report_for_media(media: Path, cfg: dict) -> tuple[str, list[tuple[int, int]]]:
    if str(media) in {"", "."}:
        return "", []
    report_dir = Path((cfg.get("reports", {}) or {}).get("directory", "/config/reports"))
    report = report_dir / (pc.report_name(media) + ".json")

    payload = _read_report(report)
    if payload is not None:
        return str(report), _ranges_from_payload(payload)

    wanted_name = media.name.casefold()
    if not wanted_name or not report_dir.is_dir():
        return str(report), []
    try:
        candidates = sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        candidates = list(report_dir.glob("*.json"))
    for candidate in candidates:
        if candidate == report:
            continue
        candidate_payload = _read_report(candidate)
        if candidate_payload is None:
            continue
        recorded_file = str(candidate_payload.get("file") or "").strip()
        if not recorded_file:
            continue
        try:
            recorded_name = Path(recorded_file).name.casefold()
        except Exception:
            continue
        if recorded_name != wanted_name:
            continue
        ranges = _ranges_from_payload(candidate_payload)
        logging.info(
            "Live Mute matched legacy-path report for %s: current=%s report_source=%s report=%s ranges=%d",
            media.name, media, recorded_file, candidate, len(ranges),
        )
        return str(candidate), ranges
    return str(report), []


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
        raw_file = str(part.get("file") or "")
        try:
            port = int(player.get("port") or 32500)
        except (TypeError, ValueError):
            port = 32500
        key = str(metadata.get("sessionKey") or session.get("id") or player.get("machineIdentifier") or metadata.get("ratingKey") or "")
        out.append({
            "key": key,
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
            "local_file": str(_map_media_path(raw_file, media_type, cfg)),
            "observed_mono": now,
        })
    return out


def _headers(token: str, session: dict, *, target: bool = False) -> dict[str, str]:
    h = {
        "Accept": "application/xml, text/xml, */*",
        "X-Plex-Token": token,
        "X-Plex-Client-Identifier": "censorarr-live-mute-controller",
        "X-Plex-Product": "Censorarr",
        "X-Plex-Device-Name": "Censorarr Live Mute",
    }
    if target and session.get("client_id"):
        h["X-Plex-Target-Client-Identifier"] = str(session["client_id"])
    return h


def _get(url: str, headers: dict[str, str], timeout: float = 1.2) -> bytes:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _client_bases(session: dict) -> list[str]:
    address = str(session.get("address") or "").strip()
    if not address:
        return []
    ports: list[int] = []
    for raw in (session.get("port"), 32500, 3005):
        try:
            port = int(raw)
        except (TypeError, ValueError):
            continue
        if port > 0 and port not in ports:
            ports.append(port)
    return [f"http://{address}:{p}" for p in ports]


def _timeline(session: dict, token: str) -> dict[str, Any] | None:
    path = f"/player/timeline/poll?wait=0&commandID={_next_command_id()}"
    for base in _client_bases(session):
        try:
            root = ET.fromstring(_get(base + path, _headers(token, session)))
            video = next((x for x in root.findall(".//Timeline") if str(x.attrib.get("type", "")).lower() == "video"), None)
            if video is None:
                continue
            attrs = video.attrib
            volume = attrs.get("volume")
            return {
                "time_ms": int(float(attrs.get("time") or 0)),
                "state": str(attrs.get("state") or "").lower(),
                "volume": None if volume in (None, "") else max(0, min(100, int(float(volume)))),
                "controllable": str(attrs.get("controllable") or ""),
                "base": base,
            }
        except Exception:
            continue
    return None


def _set_volume(session: dict, cfg: dict, volume: int, preferred_base: str = "") -> bool:
    server_base, token = integ._plex_cfg(cfg)
    if not token:
        return False
    volume = max(0, min(100, int(volume)))
    query = urllib.parse.urlencode({"volume": volume, "type": "video", "commandID": _next_command_id()})
    path = f"/player/playback/setParameters?{query}"
    bases: list[str] = []
    if preferred_base:
        bases.append(preferred_base)
    bases.extend(x for x in _client_bases(session) if x not in bases)
    for base in bases:
        try:
            _get(base + path, _headers(token, session))
            return True
        except Exception:
            pass
    if server_base and session.get("client_id"):
        try:
            _get(server_base.rstrip("/") + path, _headers(token, session, target=True), timeout=1.5)
            return True
        except Exception:
            pass
    return False


def _event(action: str, state: dict, **extra: Any) -> None:
    session = state.get("session", {}) or {}
    row = {"timestamp": time.time(), "action": action, "title": session.get("title"), "user": session.get("user"), "player": session.get("player"), **extra}
    with _LOCK:
        _RECENT_EVENTS.insert(0, row)
        del _RECENT_EVENTS[30:]


def _restore(state: dict, cfg: dict, reason: str) -> None:
    if not state.get("muted"):
        return
    volume = state.get("restore_volume")
    if volume is None:
        volume = _live_cfg(cfg)["fallback_restore_volume"]
    if _set_volume(state.get("session", {}), cfg, int(volume), str(state.get("preferred_base") or "")):
        _event("unmute", state, volume=int(volume), reason=reason)
        state.update({"muted": False, "restore_volume": None, "active_range": None, "last_error": ""})
    else:
        state["last_error"] = "Could not restore Plex player volume"


def _refresh_session(state: dict, session: dict, cfg: dict) -> None:
    old_file = str((state.get("session") or {}).get("local_file") or "")
    state["session"] = session
    if str(session.get("local_file") or "") != old_file or "ranges" not in state:
        report, ranges = _report_for_media(Path(session.get("local_file") or ""), cfg)
        report_found = bool(report and Path(report).is_file())
        if ranges:
            report_error = ""
        elif report_found:
            report_error = "Censorarr report found, but it contains no mute ranges"
        else:
            report_error = "No Censorarr mute-range report for this title"
        state.update({
            "report": report,
            "ranges": ranges,
            "active_range": None,
            "timeline_time_ms": int(session.get("view_offset_ms") or 0),
            "timeline_mono": float(session.get("observed_mono") or time.monotonic()),
            "last_timeline_sync_mono": 0.0,
            "last_error": report_error,
        })


def _position(state: dict) -> int:
    session = state.get("session", {}) or {}
    value = int(state.get("timeline_time_ms") or session.get("view_offset_ms") or 0)
    status = str(state.get("timeline_state") or session.get("state") or "")
    if status == "playing":
        value += int(max(0.0, time.monotonic() - float(state.get("timeline_mono") or time.monotonic())) * 1000)
    return value


def _active_range(ranges: list[tuple[int, int]], position: int, lead: int, tail: int) -> int | None:
    for idx, (start, end) in enumerate(ranges):
        if position < start - lead:
            return None
        if start - lead <= position <= end + tail:
            return idx
    return None


def _process(state: dict, cfg: dict, settings: dict[str, Any]) -> None:
    session = state.get("session", {}) or {}
    ranges = state.get("ranges", []) or []
    if session.get("state") in {"stopped", ""} or not ranges:
        _restore(state, cfg, "stopped-or-no-ranges")
        return
    server_base, token = integ._plex_cfg(cfg)
    if not server_base or not token:
        state["last_error"] = "Plex URL/token is not configured"
        _restore(state, cfg, "plex-not-configured")
        return

    now = time.monotonic()
    if (now - float(state.get("last_timeline_sync_mono") or 0)) * 1000 >= settings["timeline_sync_ms"]:
        timeline = _timeline(session, token)
        state["last_timeline_sync_mono"] = now
        if timeline:
            state.update({
                "timeline_time_ms": int(timeline.get("time_ms") or 0),
                "timeline_mono": now,
                "timeline_state": str(timeline.get("state") or session.get("state") or ""),
                "current_volume": timeline.get("volume"),
                "preferred_base": str(timeline.get("base") or ""),
                "controllable": str(timeline.get("controllable") or ""),
                "last_error": "",
            })
        elif settings["require_volume_probe"]:
            state["current_volume"] = None
            state["last_error"] = "Player timeline/volume is unavailable; Live Mute is staying hands-off"

    position = _position(state)
    state["position_ms"] = position
    if str(state.get("timeline_state") or session.get("state") or "") != "playing":
        return
    idx = _active_range(ranges, position, settings["lead_ms"], settings["tail_ms"])
    if idx is not None and not state.get("muted"):
        current_volume = state.get("current_volume")
        if current_volume is None and settings["require_volume_probe"]:
            return
        restore = settings["fallback_restore_volume"] if current_volume is None else int(current_volume)
        if restore <= 0:
            state["last_error"] = "Player volume is already 0; Live Mute did not take control"
            return
        if _set_volume(session, cfg, 0, str(state.get("preferred_base") or "")):
            start, end = ranges[idx]
            state.update({"muted": True, "restore_volume": restore, "active_range": idx, "current_volume": 0, "last_error": ""})
            _event("mute", state, range_index=idx, start_ms=start, end_ms=end, restore_volume=restore)
        else:
            state["last_error"] = "Plex player rejected the mute command"
        return
    if state.get("muted") and idx != state.get("active_range"):
        _restore(state, cfg, "range-ended-or-seeked")


def _loop() -> None:
    global _LAST_ERROR
    next_refresh = 0.0
    while not _STOP.is_set():
        started = time.monotonic()
        try:
            if _CORE is None:
                _STOP.wait(0.5)
                continue
            cfg = _CORE.pc.load_config(_CORE.CONFIG)
            settings = _live_cfg(cfg)
            if not settings["enabled"]:
                with _LOCK:
                    states = list(_STATES.values())
                for state in states:
                    _restore(state, cfg, "feature-disabled")
                _STOP.wait(0.6)
                continue

            now = time.monotonic()
            if now >= next_refresh:
                sessions = _parse_sessions(cfg)
                next_refresh = now + settings["session_refresh_ms"] / 1000.0
                seen: set[str] = set()
                with _LOCK:
                    for session in sessions:
                        key = str(session.get("key") or "")
                        if not key or not _eligible_user(session.get("user", ""), settings):
                            continue
                        seen.add(key)
                        state = _STATES.setdefault(key, {"muted": False, "restore_volume": None})
                        _refresh_session(state, session, cfg)
                    stale = [(k, v) for k, v in _STATES.items() if k not in seen]
                for key, state in stale:
                    _restore(state, cfg, "session-ended")
                    with _LOCK:
                        _STATES.pop(key, None)
            with _LOCK:
                states = list(_STATES.values())
            for state in states:
                _process(state, cfg, settings)
            _LAST_ERROR = ""
        except Exception as exc:
            _LAST_ERROR = str(exc)
            logging.warning("Experimental Live Mute loop error: %s", exc)

        sleep_s = 0.05
        try:
            if _CORE is not None:
                sleep_s = _live_cfg(_CORE.pc.load_config(_CORE.CONFIG))["loop_ms"] / 1000.0
        except Exception:
            pass
        _STOP.wait(max(0.01, sleep_s - (time.monotonic() - started)))


def _public_state(state: dict) -> dict[str, Any]:
    session = state.get("session", {}) or {}
    ranges = state.get("ranges", []) or []
    position = int(state.get("position_ms") or session.get("view_offset_ms") or 0)
    next_range = None
    for idx, (start, end) in enumerate(ranges):
        if end >= position:
            next_range = {"index": idx, "start_ms": start, "end_ms": end}
            break
    return {
        "key": session.get("key"), "title": session.get("title"), "item_title": session.get("item_title"),
        "user": session.get("user"), "player": session.get("player"),
        "state": state.get("timeline_state") or session.get("state"), "position_ms": position,
        "duration_ms": session.get("duration_ms"), "media_file": session.get("local_file"),
        "report": state.get("report"), "range_count": len(ranges), "muted": bool(state.get("muted")),
        "current_volume": state.get("current_volume"), "volume_probe_ok": state.get("current_volume") is not None,
        "active_range": state.get("active_range"), "next_range": next_range,
        "controllable": state.get("controllable", ""), "error": state.get("last_error", ""),
    }


def _save_settings(core, patch: dict[str, Any]) -> dict[str, Any]:
    raw = core.yaml.safe_load(core.CONFIG.read_text(encoding="utf-8")) or {}
    section = raw.setdefault("live_mute", {})
    allowed = {"enabled", "users", "lead_ms", "tail_ms", "loop_ms", "timeline_sync_ms", "session_refresh_ms", "require_volume_probe", "fallback_restore_volume"}
    for key, value in patch.items():
        if key not in allowed:
            continue
        if key == "users":
            if isinstance(value, str):
                value = [x.strip() for x in value.split(",") if x.strip()]
            value = [str(x).strip() for x in (value or []) if str(x).strip()]
        section[key] = value
    tmp = core.CONFIG.with_suffix(".tmp")
    tmp.write_text(core.yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    os.replace(tmp, core.CONFIG)
    return _live_cfg(core.pc.load_config(core.CONFIG))


def install(app, core) -> None:
    global _CORE, _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _CORE = core
    core.pc.DEFAULT_CONFIG.setdefault("live_mute", dict(DEFAULTS))

    @app.get("/api/live-mute/status")
    def live_mute_status(_: bool = Depends(core.auth)):
        cfg = core.pc.load_config(core.CONFIG)
        with _LOCK:
            sessions = [_public_state(x) for x in _STATES.values()]
            events = list(_RECENT_EVENTS[:20])
        return {"ok": True, "experimental": True, "settings": _live_cfg(cfg), "sessions": sessions, "recent_events": events, "last_error": _LAST_ERROR}

    @app.post("/api/live-mute/settings")
    async def live_mute_settings(request: Request, _: bool = Depends(core.auth)):
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            raise HTTPException(400, "Expected a JSON object")
        return {"ok": True, "settings": _save_settings(core, body)}

    @app.post("/api/live-mute/test")
    def live_mute_test(_: bool = Depends(core.auth)):
        cfg = core.pc.load_config(core.CONFIG)
        settings = _live_cfg(cfg)
        session = next((x for x in _parse_sessions(cfg) if x.get("state") == "playing" and _eligible_user(x.get("user", ""), settings)), None)
        if session is None:
            raise HTTPException(409, "No eligible Plex video is currently playing")
        _base, token = integ._plex_cfg(cfg)
        timeline = _timeline(session, token)
        if not timeline:
            raise HTTPException(409, f"Could not read the Plex player timeline for {session.get('player')}")
        volume = timeline.get("volume")
        restore_source = "reported"
        if volume is None:
            if settings["require_volume_probe"]:
                raise HTTPException(
                    409,
                    "This Plex client does not report its volume. For NVIDIA Shield/Android TV compatibility, uncheck "
                    "'Only mute when the current Plex volume can be read and safely restored', save Live Mute settings, "
                    "then run this test again. Censorarr will restore the Plex player to the configured fallback level."
                )
            volume = settings["fallback_restore_volume"]
            restore_source = "fallback"
        if int(volume) <= 0:
            raise HTTPException(409, "The Plex client restore volume is 0, so Censorarr refused to run the mute test")
        if not _set_volume(session, cfg, 0, str(timeline.get("base") or "")):
            raise HTTPException(409, "The Plex client rejected the test mute command")
        time.sleep(0.8)
        if not _set_volume(session, cfg, int(volume), str(timeline.get("base") or "")):
            raise HTTPException(500, f"Test mute worked, but Censorarr could not restore volume {volume}. Restore it manually before continuing.")
        return {
            "ok": True,
            "player": session.get("player"),
            "user": session.get("user"),
            "restored_volume": int(volume),
            "restore_source": restore_source,
        }

    @app.get("/live-mute.js", include_in_schema=False)
    def live_mute_script(_: bool = Depends(core.auth)):
        js = core.STATIC / "live-mute.js"
        if not js.is_file():
            raise HTTPException(404, "Live Mute script not found")
        return Response(js.read_text(encoding="utf-8"), media_type="application/javascript")

    threading.Thread(target=_loop, daemon=True, name="censorarr-live-mute").start()
    logging.info("Experimental Live Mute controller installed (disabled by default)")