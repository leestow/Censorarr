"""Automation audio-source selection for Censorarr family-safe processing.

Keeps generated Censorarr tracks out of profanity transcription, lets Dialogue
Enhancement prefer CLEAN or Original audio, and records the actual source used in
the per-feature completion marker.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

PROFANITY_SOURCE_OPTIONS = {"best_original", "prefer_surround_original", "prefer_stereo_original"}
DIALOGUE_SOURCE_OPTIONS = {"auto_clean", "original", "clean_only"}
DIALOGUE_FALLBACK_OPTIONS = {"original", "skip"}

DEFAULT_PROFANITY_SOURCE = "best_original"
DEFAULT_DIALOGUE_SOURCE = "auto_clean"
DEFAULT_DIALOGUE_FALLBACK = "original"

_LAST_PROFANITY_SOURCE: dict[str, dict] = {}
_LAST_DIALOGUE_SOURCE: dict[str, dict] = {}


def install_defaults(pc) -> None:
    pc.DEFAULT_CONFIG.setdefault("profanity", {}).setdefault("source_preference", DEFAULT_PROFANITY_SOURCE)
    dcfg = pc.DEFAULT_CONFIG.setdefault("dialogue_enhancement", {})
    dcfg.setdefault("source_preference", DEFAULT_DIALOGUE_SOURCE)
    dcfg.setdefault("source_fallback", DEFAULT_DIALOGUE_FALLBACK)


def normalize_profanity_source(value: Any) -> str:
    value = str(value or DEFAULT_PROFANITY_SOURCE).strip().lower()
    return value if value in PROFANITY_SOURCE_OPTIONS else DEFAULT_PROFANITY_SOURCE


def normalize_dialogue_source(value: Any) -> str:
    value = str(value or DEFAULT_DIALOGUE_SOURCE).strip().lower()
    return value if value in DIALOGUE_SOURCE_OPTIONS else DEFAULT_DIALOGUE_SOURCE


def normalize_dialogue_fallback(value: Any) -> str:
    value = str(value or DEFAULT_DIALOGUE_FALLBACK).strip().lower()
    return value if value in DIALOGUE_FALLBACK_OPTIONS else DEFAULT_DIALOGUE_FALLBACK


def source_settings(cfg: dict) -> dict:
    pcfg = cfg.get("profanity", {}) or {}
    dcfg = cfg.get("dialogue_enhancement", {}) or {}
    return {
        "profanity_source": normalize_profanity_source(pcfg.get("source_preference")),
        "dialogue_source": normalize_dialogue_source(dcfg.get("source_preference")),
        "dialogue_fallback": normalize_dialogue_fallback(dcfg.get("source_fallback")),
    }


def _stream_title(stream: dict) -> str:
    tags = stream.get("tags") or {}
    return str(tags.get("title") or tags.get("handler_name") or "").strip()


def _language(stream: dict) -> str:
    return str((stream.get("tags") or {}).get("language") or "").strip().lower()


def _source_meta(stream: dict, rel: int, kind: str, *, requested: str, fallback_used: bool = False) -> dict:
    return {
        "kind": kind,
        "title": _stream_title(stream) or ("English - CLEAN" if kind == "clean" else "Original audio"),
        "language": _language(stream) or None,
        "codec": stream.get("codec_name"),
        "channels": stream.get("channels"),
        "channel_layout": stream.get("channel_layout"),
        "relative_index": int(rel),
        "requested": requested,
        "fallback_used": bool(fallback_used),
    }


def _generated_titles(cfg: dict) -> set[str]:
    clean = str((cfg.get("clean_track", {}) or {}).get("title", "English - CLEAN")).strip().lower()
    dialogue = str((cfg.get("dialogue_enhancement", {}) or {}).get("title", "English - DIALOGUE ENHANCED")).strip().lower()
    return {x for x in (clean, dialogue) if x}


def _original_candidates(probe: dict, cfg: dict) -> list[tuple[dict, int]]:
    generated = _generated_titles(cfg)
    out: list[tuple[dict, int]] = []
    rel = 0
    for stream in probe.get("streams", []) or []:
        if stream.get("codec_type") != "audio":
            continue
        names = {
            str((stream.get("tags") or {}).get("title") or "").strip().lower(),
            str((stream.get("tags") or {}).get("handler_name") or "").strip().lower(),
        }
        if not (names & generated):
            out.append((stream, rel))
        rel += 1
    return out


def choose_original(probe: dict, cfg: dict) -> tuple[dict, int]:
    candidates = _original_candidates(probe, cfg)
    if not candidates:
        # Last-resort compatibility for unusual files whose original track was manually
        # named exactly like a generated Censorarr track.
        audio = [(s, i) for i, s in enumerate(s for s in probe.get("streams", []) if s.get("codec_type") == "audio")]
        if not audio:
            raise RuntimeError("No audio streams found")
        candidates = audio

    pref = normalize_profanity_source((cfg.get("profanity", {}) or {}).get("source_preference"))
    codec_rank = {"truehd": 8, "dts": 7, "eac3": 6, "ac3": 5, "flac": 5, "aac": 4, "opus": 4, "mp3": 2}

    def score(item: tuple[dict, int]) -> tuple:
        stream, rel = item
        lang = _language(stream)
        channels = int(stream.get("channels") or 0)
        english = 1 if lang in {"eng", "en", "english"} else 0
        if pref == "prefer_surround_original":
            shape = 2 if channels > 2 else 0
        elif pref == "prefer_stereo_original":
            shape = 2 if 0 < channels <= 2 else 0
        else:
            shape = 1
        codec = codec_rank.get(str(stream.get("codec_name") or "").lower(), 0)
        try:
            bitrate = int(stream.get("bit_rate") or 0)
        except (TypeError, ValueError):
            bitrate = 0
        # Prefer English first, then requested channel shape, then richer source audio.
        return (english, shape, channels, codec, bitrate, -rel)

    return max(candidates, key=score)


def _dialogue_signature(cfg: dict) -> str:
    dcfg = dict(cfg.get("dialogue_enhancement", {}) or {})
    dcfg.pop("enabled", None)
    payload = {"dialogue_enhancement": dcfg, "audio_track": cfg.get("audio_track", "auto")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]


def _write_marker_source(pc, media: Path, cfg: dict, profanity_source: dict | None, dialogue_source: dict | None) -> None:
    try:
        mp = pc.marker_path(media, cfg)
        if not mp.exists():
            return
        data = pc.marker_load(media, cfg)
        entry = (data.get("files", {}) or {}).get(media.name)
        if not isinstance(entry, dict):
            return
        features = entry.setdefault("features", {})
        if profanity_source and isinstance(features.get("profanity_censoring"), dict):
            features["profanity_censoring"]["source"] = profanity_source
        if dialogue_source:
            rec = features.setdefault("dialogue_enhancement", {})
            rec["source"] = dialogue_source
            if dialogue_source.get("kind") == "skipped":
                rec.update({
                    "complete": True,
                    "signature": _dialogue_signature(cfg),
                    "status": "skipped-source",
                    "reason": dialogue_source.get("reason", "preferred-source-unavailable"),
                })
                rec.pop("track", None)
        tmp = mp.with_suffix(mp.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, mp)
    except Exception as exc:
        pc.logging.warning("Could not record automation audio source for %s: %s", media, exc)


def install(pc, dialogue) -> None:
    install_defaults(pc)

    original_add_dialogue = dialogue._add_dialogue_track
    original_process_file = pc.process_file
    original_marker_write = pc.marker_write

    def add_dialogue_with_source(pc_mod, src: Path, out: Path, audio_rel: int, cfg: dict, progress_callback=None):
        dcfg = cfg.get("dialogue_enhancement", {}) or {}
        requested = normalize_dialogue_source(dcfg.get("source_preference"))
        fallback = normalize_dialogue_fallback(dcfg.get("source_fallback"))
        out_probe = pc_mod.ffprobe(out)
        clean_title = str((cfg.get("clean_track", {}) or {}).get("title", "English - CLEAN"))
        clean = pc_mod.find_clean_audio_streams(out_probe, clean_title)

        source_path = src
        source_stream = None
        source_rel = audio_rel
        source_kind = "original"
        fallback_used = False

        if requested in {"auto_clean", "clean_only"} and clean:
            source_stream, source_rel = clean[0]
            source_path = out
            source_kind = "clean"
        elif requested == "clean_only" and fallback == "skip":
            _LAST_DIALOGUE_SOURCE[str(src)] = {
                "kind": "skipped",
                "requested": requested,
                "reason": "clean-track-unavailable",
                "fallback_used": False,
            }
            pc_mod.logging.info("Dialogue Enhancement skipped: CLEAN-only source requested but no CLEAN track exists")
            return None
        else:
            src_probe = pc_mod.ffprobe(src)
            source_stream, source_rel = choose_original(src_probe, cfg)
            source_path = src
            source_kind = "original"
            fallback_used = requested in {"auto_clean", "clean_only"}

        if source_stream is None:
            src_probe = pc_mod.ffprobe(source_path)
            audio = [s for s in src_probe.get("streams", []) if s.get("codec_type") == "audio"]
            source_stream = audio[source_rel]

        meta = _source_meta(source_stream, source_rel, source_kind, requested=requested, fallback_used=fallback_used)
        _LAST_DIALOGUE_SOURCE[str(src)] = meta
        pc_mod.logging.info(
            "Dialogue Enhancement source: %s (track=%s codec=%s channels=%s requested=%s%s)",
            source_kind,
            meta.get("title"),
            meta.get("codec"),
            meta.get("channels"),
            requested,
            " fallback=original" if fallback_used else "",
        )
        return original_add_dialogue(pc_mod, source_path, out, source_rel, cfg, progress_callback)

    dialogue._add_dialogue_track = add_dialogue_with_source

    def _has_clean(path: Path, cfg: dict) -> bool:
        try:
            title = str((cfg.get("clean_track", {}) or {}).get("title", "English - CLEAN"))
            return bool(pc.find_clean_audio_streams(pc.ffprobe(path), title))
        except Exception:
            return False

    def _apply_dialogue_after_clean(path: Path, cfg: dict) -> None:
        src_stat = path.stat()
        src_probe = pc.ffprobe(path)
        _original, original_rel = choose_original(src_probe, cfg)
        temp_out = path.with_name(path.name + ".censorarr.source.tmp" + path.suffix)
        if temp_out.exists():
            temp_out.unlink()
        try:
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
                "-i", str(path), "-map", "0", "-map_metadata", "0", "-map_chapters", "0", "-c", "copy", str(temp_out),
            ]
            pc.run_ffmpeg_progress(cmd, pc.duration_of(src_probe))
            dialogue._add_dialogue_track(pc, path, temp_out, original_rel, cfg)
            out_probe = pc.ffprobe(temp_out)
            title = str((cfg.get("dialogue_enhancement", {}) or {}).get("title") or dialogue.DEFAULTS["title"])
            found = dialogue._find_named_audio(out_probe, title)
            if len(found) != 1:
                raise RuntimeError(f"Dialogue Enhancement validation failed: expected one track titled {title!r}, found {len(found)}")
            if bool((cfg.get("safety", {}) or {}).get("validate_output", True)):
                src_v = [s for s in src_probe.get("streams", []) if s.get("codec_type") == "video"]
                out_v = [s for s in out_probe.get("streams", []) if s.get("codec_type") == "video"]
                if len(src_v) != len(out_v) or any(a.get("codec_name") != b.get("codec_name") for a, b in zip(src_v, out_v)):
                    raise RuntimeError("Dialogue Enhancement validation failed: video streams changed")
                tol = float((cfg.get("safety", {}) or {}).get("duration_tolerance_seconds", 2.0))
                if abs(pc.duration_of(src_probe) - pc.duration_of(out_probe)) > tol:
                    raise RuntimeError("Dialogue Enhancement validation failed: duration changed")
            pc.preserve_metadata(src_stat, temp_out, cfg)
            os.replace(temp_out, path)
        finally:
            try:
                if temp_out.exists():
                    temp_out.unlink()
            except OSError:
                pass

    def process_file_with_automation_sources(path: Path, cfg: dict, model, matcher) -> dict:
        work = copy.deepcopy(cfg)
        profanity_enabled = bool((work.get("profanity", {}) or {}).get("enabled", True))
        dialogue_enabled = bool((work.get("dialogue_enhancement", {}) or {}).get("enabled", False))

        # Resolve the actual original track once per job. This prevents CLEAN (which is
        # commonly audio stream 0) from ever becoming the profanity transcription source.
        if profanity_enabled:
            try:
                stream, rel = choose_original(pc.ffprobe(path), work)
                work["audio_track"] = rel
                _LAST_PROFANITY_SOURCE[str(path)] = _source_meta(
                    stream, rel, "original",
                    requested=normalize_profanity_source((work.get("profanity", {}) or {}).get("source_preference")),
                )
                pc.logging.info("Profanity source: original track %s (%s ch, %s)", rel, stream.get("channels"), stream.get("codec_name"))
            except Exception as exc:
                pc.logging.warning("Could not preselect original profanity source; using normal selector: %s", exc)

        dcfg = work.get("dialogue_enhancement", {}) or {}
        dsource = normalize_dialogue_source(dcfg.get("source_preference"))
        dfallback = normalize_dialogue_fallback(dcfg.get("source_fallback"))
        clean_before = _has_clean(path, work)

        # CLEAN-only + Skip needs orchestration around the family feature shim. If
        # profanity creates CLEAN during this job, add Dialogue immediately afterward;
        # if no CLEAN is produced, record a terminal per-feature skip for this signature.
        if dialogue_enabled and dsource == "clean_only" and dfallback == "skip" and not clean_before:
            if not profanity_enabled:
                _LAST_DIALOGUE_SOURCE[str(path)] = {
                    "kind": "skipped", "requested": dsource,
                    "reason": "clean-track-unavailable", "fallback_used": False,
                }
                try:
                    original_marker_write(
                        path, cfg, "dialogue-source-skipped",
                        completed_features={"dialogue_enhancement"},
                    )
                    _write_marker_source(pc, path, cfg, None, _LAST_DIALOGUE_SOURCE.get(str(path)))
                except TypeError:
                    pass
                pc.update_heartbeat("completed", str(path), progress=100, dialogue_skipped_source=True)
                return {"status": "dialogue-source-skipped", "detections": 0}

            work["dialogue_enhancement"]["enabled"] = False
            result = original_process_file(path, work, model, matcher)
            if str(result.get("status")) == "applied" and _has_clean(path, cfg):
                _apply_dialogue_after_clean(path, cfg)
                result = dict(result)
                result["dialogue_added"] = True
            else:
                _LAST_DIALOGUE_SOURCE[str(path)] = {
                    "kind": "skipped", "requested": dsource,
                    "reason": "clean-track-unavailable", "fallback_used": False,
                }
                result = dict(result)
                result["dialogue_skipped_source"] = True
            return result

        return original_process_file(path, work, model, matcher)

    pc.process_file = process_file_with_automation_sources

    def marker_write_with_sources(media: Path, cfg: dict, status: str, rating=None, report=None, **kwargs) -> None:
        psrc = _LAST_PROFANITY_SOURCE.get(str(media))
        dsrc = _LAST_DIALOGUE_SOURCE.get(str(media))
        completed = set(kwargs.pop("completed_features", set()) or set())
        if dsrc and dsrc.get("kind") == "skipped":
            completed.add("dialogue_enhancement")
        try:
            original_marker_write(
                media, cfg, status, rating=rating, report=report,
                completed_features=completed if completed else None,
                **kwargs,
            )
        except TypeError:
            original_marker_write(media, cfg, status, rating=rating, report=report)
        _write_marker_source(pc, media, cfg, psrc, dsrc)
        _LAST_PROFANITY_SOURCE.pop(str(media), None)
        _LAST_DIALOGUE_SOURCE.pop(str(media), None)

    pc.marker_write = marker_write_with_sources
