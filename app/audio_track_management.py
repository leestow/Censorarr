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
    try:
        if not entry or str(entry.get("fingerprint") or "") != str(core.pc.fingerprint(media)):
            return {}
    except Exception:
        return {}

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
    if top_status == "applied":
        prec = features.get(FEATURE_PROFANITY)
        clean_title = str((cfg.get("clean_track", {}) or {}).get("title", "English - CLEAN")).strip()
        if clean_title and not (isinstance(prec, dict) and prec.get("suppressed")):
            known.setdefault(clean_title.lower(), FEATURE_PROFANITY)
        drec = features.get(FEATURE_DIALOGUE)
        dialogue_title = str((cfg.get("dialogue_enhancement", {}) or {}).get("title", "English - DIALOGUE ENHANCED")).strip()
        if dialogue_title and isinstance(drec, dict) and str(drec.get("status") or "").lower() == "applied" and not drec.get("suppressed"):
            known.setdefault(dialogue_title.lower(), FEATURE_DIALOGUE)
    if top_status == "dialogue-applied":
        drec = features.get(FEATURE_DIALOGUE)
        title = str((cfg.get("dialogue_enhancement", {}) or {}).get("title", "English - DIALOGUE ENHANCED")).strip()
        if title and not (isinstance(drec, dict) and drec.get("suppressed")):
            known.setdefault(title.lower(), FEATURE_DIALOGUE)
    return known


def _track_rows(core, media: Path, cfg: dict, probe: dict | None = None) -> list[dict]:
    probe = probe or core.pc.ffprobe(media)
    generated = _known_generated(core, media, cfg)
    audio_rows = _audio(probe)
    title_counts: dict[str, int] = {}
    for stream, _rel in audio_rows:
        title = _stream_title(stream).lower()
        if title:
            title_counts[title] = title_counts.get(title, 0) + 1

    rows = []
    for stream, rel in audio_rows:
        title = _stream_title(stream)
        key = title.lower() if title else ""
        # Never guess between duplicate titles. Ambiguous streams are all protected.
        feature = generated.get(key) if key and title_counts.get(key, 0) == 1 else None
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


def _validate_remux(core, src_probe: dict, out_probe: dict, removed_global_index: int, cfg: dict) -> None:
    src_streams = list(src_probe.get("streams", []) or [])
    out_streams = list(out_probe.get("streams", []) or [])
    if len(out_streams) != len(src_streams) - 1:
        raise RuntimeError(
            f"Audio removal validation failed: expected {len(src_streams)-1} total streams, found {len(out_streams)}"
        )

    src_v = [s for s in src_streams if s.get("codec_type") == "video"]
    out_v = [s for s in out_streams if s.get("codec_type") == "video"]
    if [s.get("codec_name") for s in src_v] != [s.get("codec_name") for s in out_v]:
        raise RuntimeError("Audio removal validation failed: video streams changed")

    src_sub = [s for s in src_streams if s.get("codec_type") == "subtitle"]
    out_sub = [s for s in out_streams if s.get("codec_type") == "subtitle"]
    if [s.get("codec_name") for s in src_sub] != [s.get("codec_name") for s in out_sub]:
        raise RuntimeError("Audio removal validation failed: subtitle streams changed")

    expected_audio = [
        _signature(s) for s in src_streams
        if s.get("codec_type") == "audio" and int(s.get("index", -1)) != removed_global_index
    ]
    actual_audio = [_signature(s) for s in out_streams if s.get("codec_type") == "audio"]
    if expected_audio != actual_audio:
        raise RuntimeError("Audio removal validation failed: a protected audio stream changed")
    if not actual_audio:
        raise RuntimeError("Audio removal validation failed: no protected/original audio remains")

    before = core.pc.duration_of(src_probe)
    after = core.pc.duration_of(out_probe)
    tol = float((cfg.get("safety", {}) or {}).get("duration_tolerance_seconds", 2.0))
    if before and after and abs(before - after) > tol:
        raise RuntimeError(f"Audio removal validation failed: duration changed by {abs(before-after):.2f}s")


def _record_suppression(core, media: Path, cfg: dict, feature: str, title: str, stream_index: int) -> None:
    data, entry = _marker_entry(core, media, cfg)
    files = data.setdefault("files", {})
    features = entry.setdefault("features", {})
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    rec = features.get(feature)
    if not isinstance(rec, dict):
        rec = {}
    rec.update({
        "complete": True,
        "signature": "",
        "suppressed": True,
        "status": "manually-removed",
        "removed_at": now,
        "track": title,
        "removed_stream_index": int(stream_index),
    })
    features[feature] = rec
    entry.update({
        "done": True,
        "fingerprint": core.pc.fingerprint(media),
        "media_type": core.pc.media_type_for(media, cfg),
        "version": core.pc.VERSION,
        "features": features,
    })
    files[media.name] = entry
    core.write_json(core.pc.marker_path(media, cfg), data)

    try:
        state = core.read_json(core.STATE, {"files": {}})
        row = state.setdefault("files", {}).setdefault(str(media), {})
        suppressions = row.setdefault("feature_suppressions", {})
        suppressions[feature] = {"track": title, "removed_at": now}
        core.write_json(core.STATE, state)
    except Exception:
        pass


def _clear_suppression(core, media: Path, cfg: dict, feature: str | None = None) -> list[str]:
    data, entry = _marker_entry(core, media, cfg)
    features = entry.get("features") or {}
    targets = [feature] if feature in {FEATURE_PROFANITY, FEATURE_DIALOGUE} else [FEATURE_PROFANITY, FEATURE_DIALOGUE]
    changed: list[str] = []
    for name in targets:
        rec = features.get(name)
        if not isinstance(rec, dict) or not rec.get("suppressed"):
            continue
        rec["suppressed"] = False
        rec["complete"] = False
        rec["status"] = "manual-reprocess-requested"
        rec.pop("removed_at", None)
        rec.pop("removed_stream_index", None)
        changed.append(name)
    if changed:
        entry["fingerprint"] = core.pc.fingerprint(media)
        data.setdefault("files", {})[media.name] = entry
        core.write_json(core.pc.marker_path(media, cfg), data)
        try:
            state = core.read_json(core.STATE, {"files": {}})
            row = state.setdefault("files", {}).setdefault(str(media), {})
            suppressions = row.get("feature_suppressions") or {}
            for name in changed:
                suppressions.pop(name, None)
            if suppressions:
                row["feature_suppressions"] = suppressions
            else:
                row.pop("feature_suppressions", None)
            core.write_json(core.STATE, state)
        except Exception:
            pass
    return changed


def install(app, core) -> None:
    @app.get("/api/audio-tracks")
    def audio_tracks(path: str = Query(...), _: bool = Depends(core.auth)):
        media = core.safe_media_path(path)
        if not media.is_file():
            raise HTTPException(400, "Choose a media file")
        cfg = core.pc.load_config(core.CONFIG)
        try:
            probe = core.pc.ffprobe(media)
            rows = _track_rows(core, media, cfg, probe)
        except Exception as exc:
            raise HTTPException(500, f"Could not inspect audio tracks: {exc}")
        return {
            "ok": True,
            "path": str(media),
            "fingerprint": core.pc.fingerprint(media),
            "audio": rows,
            "protected_count": sum(1 for x in rows if x["protected"]),
            "removable_count": sum(1 for x in rows if x["removable"]),
        }

    @app.post("/api/audio-tracks/remove")
    async def remove_audio_track(request: Request, _: bool = Depends(core.auth)):
        body = await request.json()
        media = core.safe_media_path(str(body.get("path") or ""))
        try:
            requested_index = int(body.get("stream_index"))
        except (TypeError, ValueError):
            raise HTTPException(400, "A valid audio stream index is required")

        with _LOCK:
            hb = core.read_json(core.HEARTBEAT, {})
            current = str(hb.get("current") or "").strip()
            if current:
                try:
                    if Path(current).resolve() == media.resolve():
                        raise HTTPException(409, "This file is currently processing. Finish or stop that job before removing a track.")
                except FileNotFoundError:
                    pass

            cfg = core.pc.load_config(core.CONFIG)
            src_probe = core.pc.ffprobe(media)
            rows = _track_rows(core, media, cfg, src_probe)
            selected = next((x for x in rows if int(x["stream_index"]) == requested_index), None)
            if not selected:
                raise HTTPException(404, "Audio track was not found")
            if not selected.get("removable") or not selected.get("feature"):
                raise HTTPException(403, "Original and pre-existing audio tracks are protected and cannot be removed")
            if sum(1 for x in rows if x.get("protected")) < 1:
                raise HTTPException(409, "Removal refused because no protected original audio track could be verified")

            global_stream = next(
                (s for s in src_probe.get("streams", []) or [] if int(s.get("index", -1)) == requested_index),
                None,
            )
            if not global_stream or global_stream.get("codec_type") != "audio":
                raise HTTPException(409, "Selected stream is no longer the same audio track")
            if _stream_title(global_stream) != str(selected.get("title") or ""):
                raise HTTPException(409, "Selected audio track changed; reload movie details and try again")

            src_stat = media.stat()
            temp = media.with_name(media.stem + ".censorarr-remove.tmp" + media.suffix)
            if temp.exists():
                try:
                    temp.unlink()
                except OSError:
                    pass
            try:
                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
                    "-i", str(media),
                    "-map", "0", "-map", f"-0:{requested_index}",
                    "-map_metadata", "0", "-map_chapters", "0", "-c", "copy",
                    str(temp),
                ]
                core.pc.logging.info(
                    "Removing Censorarr-generated audio track: %s stream=%s feature=%s",
                    selected.get("title") or "(untitled)", requested_index, selected.get("feature"),
                )
                core.pc.run(cmd)
                out_probe = core.pc.ffprobe(temp)
                _validate_remux(core, src_probe, out_probe, requested_index, cfg)
                if hasattr(core.pc, "preserve_metadata"):
                    core.pc.preserve_metadata(src_stat, temp, cfg)
                os.replace(temp, media)
                _record_suppression(
                    core, media, cfg, str(selected["feature"]), str(selected.get("title") or ""), requested_index
                )
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(500, f"Could not safely remove audio track: {exc}")
            finally:
                try:
                    if temp.exists():
                        temp.unlink()
                except OSError:
                    pass

        return {
            "ok": True,
            "path": str(media),
            "removed": selected,
            "message": f"Removed {selected.get('title') or 'Censorarr audio track'}. Automation will not recreate it unless you manually Process/Reprocess this media.",
        }

    @app.post("/api/audio-tracks/unsuppress")
    async def unsuppress_audio_feature(request: Request, _: bool = Depends(core.auth)):
        body = await request.json()
        media = core.safe_media_path(str(body.get("path") or ""))
        cfg = core.pc.load_config(core.CONFIG)
        feature = str(body.get("feature") or "").strip() or None
        if feature is not None and feature not in {FEATURE_PROFANITY, FEATURE_DIALOGUE}:
            raise HTTPException(400, "Unknown audio feature")
        changed = _clear_suppression(core, media, cfg, feature)
        return {"ok": True, "path": str(media), "cleared": changed}
