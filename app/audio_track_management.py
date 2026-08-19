"""Safe audio-track management helpers for Censorarr movie details."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Query, Request

FEATURE_PROFANITY = "profanity_censoring"
FEATURE_DIALOGUE = "dialogue_enhancement"
_LOCK = threading.RLock()


def _stream_title(stream: dict) -> str:
    tags = stream.get("tags") or {}
    return str(tags.get("title") or tags.get("handler_name") or "").strip()


def _audio(probe: dict) -> list[tuple[dict, int]]:
    rows = []
    rel = 0
    for stream in probe.get("streams", []) or []:
        if stream.get("codec_type") != "audio":
            continue
        rows.append((stream, rel))
        rel += 1
    return rows


def _marker_entry(core, media: Path, cfg: dict) -> tuple[dict, dict]:
    try:
        data = core.pc.marker_load(media, cfg)
    except Exception:
        data = {"files": {}}
    if not isinstance(data, dict):
        data = {"files": {}}
    files = data.setdefault("files", {})
    entry = files.get(media.name)
    return data, entry if isinstance(entry, dict) else {}


def _known_generated(core, media: Path, cfg: dict) -> dict[str, str]:
    _data, entry = _marker_entry(core, media, cfg)
    features = entry.get("features") or {}
    known: dict[str, str] = {}
    for feature in (FEATURE_PROFANITY, FEATURE_DIALOGUE):
        rec = features.get(feature)
        if not isinstance(rec, dict):
            continue
        status = str(rec.get("status") or "").lower()
        title = str(rec.get("track") or "").strip()
        if title and status in {"applied", "dialogue-applied"} and not rec.get("suppressed"):
            known[title.lower()] = feature

    top_status = str(entry.get("status") or "").lower()
    try:
        state_status = str(core.state_row_for(media).get("status") or "").lower()
    except Exception:
        state_status = ""
    statuses = {top_status, state_status}
    if "applied" in statuses:
        clean_title = str((cfg.get("clean_track", {}) or {}).get("title", "English - CLEAN")).strip()
        if clean_title:
            known.setdefault(clean_title.lower(), FEATURE_PROFANITY)
        drec = features.get(FEATURE_DIALOGUE)
        dialogue_title = str((cfg.get("dialogue_enhancement", {}) or {}).get("title", "English - DIALOGUE ENHANCED")).strip()
        if dialogue_title and isinstance(drec, dict) and str(drec.get("status") or "").lower() == "applied":
            known.setdefault(dialogue_title.lower(), FEATURE_DIALOGUE)
    if "dialogue-applied" in statuses:
        title = str((cfg.get("dialogue_enhancement", {}) or {}).get("title", "English - DIALOGUE ENHANCED")).strip()
        if title:
            known.setdefault(title.lower(), FEATURE_DIALOGUE)
    return known


def _track_rows(core, media: Path, cfg: dict, probe: dict | None = None) -> list[dict]:
    probe = probe or core.pc.ffprobe(media)
    generated = _known_generated(core, media, cfg)
    rows = []
    for stream, rel in _audio(probe):
        title = _stream_title(stream)
        feature = generated.get(title.lower()) if title else None
        tags = stream.get("tags") or {}
        rows.append({
            "stream_index": int(stream.get("index", -1)),
            "relative_index": rel,
            "codec": stream.get("codec_name"),
            "channels": stream.get("channels"),
            "channel_layout": stream.get("channel_layout"),
            "sample_rate": stream.get("sample_rate"),
            "language": tags.get("language"),
            "title": title,
            "default": bool((stream.get("disposition") or {}).get("default")),
            "removable": bool(feature),
            "protected": not bool(feature),
            "feature": feature,
            "kind": "censorarr-generated" if feature else "original-or-preexisting",
        })
    return rows


def _signature(stream: dict) -> tuple[Any, ...]:
    tags = stream.get("tags") or {}
    return (
        str(stream.get("codec_name") or ""),
        int(stream.get("channels") or 0),
        str(stream.get("channel_layout") or ""),
        str(stream.get("sample_rate") or ""),
        str(tags.get("language") or "").lower(),
        _stream_title(stream).lower(),
    )
