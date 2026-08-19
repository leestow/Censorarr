"""Experimental dialogue-enhancement support for Censorarr.

Censorarr supports two dialogue engines: AI Dialogue Isolation on the optional GPU
worker, and the original lightweight center/EQ/compression path as a fast fallback.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import ai_dialogue

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "title": "English - DIALOGUE ENHANCED",
    "language": "eng",
    "strength": "medium",
    "method": "ai",
    "ai_model": "mdx_q",
    "ai_fallback_classic": True,
    "ai_worker_cpu_fallback": True,
    "ai_segment_seconds": 4,
    "ai_timeout_seconds": 7200,
    "codec": "aac",
    "bitrate": "192k",
    "make_default": False,
    "replace_existing": True,
}


def _stream_title(stream: dict) -> str:
    tags = stream.get("tags") or {}
    return str(tags.get("title") or tags.get("handler_name") or "").strip()


def _find_named_audio(probe: dict, title: str) -> list[tuple[dict, int]]:
    wanted = title.strip().lower()
    found: list[tuple[dict, int]] = []
    rel = 0
    for stream in probe.get("streams", []) or []:
        if stream.get("codec_type") != "audio":
            continue
        if _stream_title(stream).lower() == wanted:
            found.append((stream, rel))
        rel += 1
    return found


def _strength_values(name: str) -> tuple[float, float, float, float, float, float]:
    level = str(name or "medium").lower().strip()
    if level == "light":
        return 1.25, 0.72, 0.12, 1.5, 0.18, 2.0
    if level == "strong":
        return 1.90, 0.52, 0.08, 3.5, 0.10, 4.0
    return 1.55, 0.62, 0.10, 2.5, 0.14, 3.0


def _dialogue_filter(audio_stream: dict, strength: str) -> str:
    center, front, surround, presence_db, threshold, ratio = _strength_values(strength)
    layout = str(audio_stream.get("channel_layout") or "").lower().strip()
    channels = int(audio_stream.get("channels") or 2)

    filters: list[str] = []
    if channels >= 3 and layout == "3.0":
        filters.append(
            f"pan=stereo|FL={front:.3f}*FL+{center:.3f}*FC|"
            f"FR={front:.3f}*FR+{center:.3f}*FC"
        )
    elif channels >= 3 and "5.1(side)" in layout:
        filters.append(
            f"pan=stereo|FL={front:.3f}*FL+{center:.3f}*FC+{surround:.3f}*SL|"
            f"FR={front:.3f}*FR+{center:.3f}*FC+{surround:.3f}*SR"
        )
    elif channels >= 3 and layout.startswith("5.1"):
        filters.append(
            f"pan=stereo|FL={front:.3f}*FL+{center:.3f}*FC+{surround:.3f}*BL|"
            f"FR={front:.3f}*FR+{center:.3f}*FC+{surround:.3f}*BR"
        )
    elif channels >= 3 and layout.startswith("7.1"):
        filters.append(
            f"pan=stereo|FL={front:.3f}*FL+{center:.3f}*FC+{surround:.3f}*BL+{surround:.3f}*SL|"
            f"FR={front:.3f}*FR+{center:.3f}*FC+{surround:.3f}*BR+{surround:.3f}*SR"
        )

    filters.extend([
        "highpass=f=80",
        "lowpass=f=12000",
        f"equalizer=f=2500:t=q:w=1:g={presence_db:.1f}",
        f"acompressor=threshold={threshold:.3f}:ratio={ratio:.1f}:attack=8:release=140:makeup=1.35",
        "alimiter=limit=0.95",
    ])
    return ",".join(filters)


def _add_dialogue_track(pc, src: Path, out: Path, audio_rel: int, cfg: dict, progress_callback=None) -> None:
    dcfg = cfg.get("dialogue_enhancement", {}) or {}
    if not bool(dcfg.get("enabled", False)):
        return

    title = str(dcfg.get("title") or DEFAULTS["title"]).strip()
    if not title:
        raise RuntimeError("Dialogue enhancement title cannot be blank")

    method = str(dcfg.get("method") or "ai").strip().lower()
    if method == "ai":
        try:
            meta = ai_dialogue.add_ai_dialogue_track(
                pc,
                src,
                out,
                audio_rel,
                cfg,
                _find_named_audio,
                progress_callback,
            )
            pc.logging.info(
                "AI Dialogue Enhanced track added: %s (model=%s device=%s)",
                title,
                meta.get("model", dcfg.get("ai_model", "mdx_q")),
                meta.get("device", "remote"),
            )
            return
        except Exception as exc:
            if not bool(dcfg.get("ai_fallback_classic", True)):
                raise
            pc.logging.warning(
                "AI Dialogue Isolation unavailable/failed (%s); falling back to Classic enhancement",
                exc,
            )

    current_probe = pc.ffprobe(out)
    existing = _find_named_audio(current_probe, title)
    replace = bool(dcfg.get("replace_existing", True))
    if existing and not replace:
        pc.logging.info("Dialogue-enhanced track already exists; leaving it unchanged: %s", title)
        return

    excluded = {int(stream.get("index", -1)) for stream, _rel in existing} if replace else set()
    retained_audio_count = sum(
        1
        for stream in current_probe.get("streams", []) or []
        if stream.get("codec_type") == "audio" and int(stream.get("index", -1)) not in excluded
    )
    source_audio = [s for s in (pc.ffprobe(src).get("streams", []) or []) if s.get("codec_type") == "audio"]
    if audio_rel < 0 or audio_rel >= len(source_audio):
        raise RuntimeError(f"Dialogue enhancement source audio index is invalid: {audio_rel}")

    filt = _dialogue_filter(source_audio[audio_rel], str(dcfg.get("strength", "medium")))
    temp = out.with_name(out.stem + ".dialogue.tmp" + out.suffix)
    if temp.exists():
        temp.unlink()

    pc.logging.info(
        "Building Classic dialogue-enhanced track: title=%s strength=%s source_audio=%s",
        title,
        dcfg.get("strength", "medium"),
        audio_rel,
    )
    try:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
            "-i", str(out),
            "-i", str(src),
            "-filter_complex", f"[1:a:{audio_rel}]{filt}[dialogue]",
        ]
        for stream in sorted(current_probe.get("streams", []) or [], key=lambda x: int(x.get("index", 0))):
            gi = int(stream.get("index", 0))
            if gi in excluded:
                continue
            cmd += ["-map", f"0:{gi}"]
        cmd += ["-map", "[dialogue]", "-map_metadata", "0", "-map_chapters", "0", "-c", "copy"]

        new_rel = retained_audio_count
        codec = str(dcfg.get("codec") or "aac").strip().lower()
        bitrate = str(dcfg.get("bitrate") or "192k").strip()
        cmd += [f"-c:a:{new_rel}", codec, f"-ac:a:{new_rel}", "2"]
        if bitrate:
            cmd += [f"-b:a:{new_rel}", bitrate]
        cmd += [
            f"-metadata:s:a:{new_rel}", f"title={title}",
            f"-metadata:s:a:{new_rel}", f"language={dcfg.get('language', 'eng')}",
        ]
        if src.suffix.lower() in {".mp4", ".m4v"}:
            cmd += [f"-metadata:s:a:{new_rel}", f"handler_name={title}"]

        if bool(dcfg.get("make_default", False)):
            for i in range(retained_audio_count + 1):
                cmd += [f"-disposition:a:{i}", "0"]
            cmd += [f"-disposition:a:{new_rel}", "default"]
        else:
            cmd += [f"-disposition:a:{new_rel}", "0"]

        cmd += [str(temp)]
        pc.run_ffmpeg_progress(cmd, pc.duration_of(current_probe), progress_callback)
        check = pc.ffprobe(temp)
        found = _find_named_audio(check, title)
        if len(found) != 1:
            raise RuntimeError(
                f"Dialogue enhancement validation failed: expected one track titled {title!r}, found {len(found)}"
            )
        os.replace(temp, out)
        pc.logging.info("Classic dialogue-enhanced track added: %s", title)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def install(pc) -> None:
    defaults = pc.DEFAULT_CONFIG.setdefault("dialogue_enhancement", {})
    for key, value in DEFAULTS.items():
        defaults.setdefault(key, value)

    original_remux = pc.remux_with_clean_track
    original_validate = pc.validate_output

    def remux_with_dialogue(
        src: Path,
        out: Path,
        audio_rel: int,
        probe: dict,
        ranges: list[tuple[float, float]],
        cfg: dict,
        progress_callback=None,
    ) -> None:
        original_remux(src, out, audio_rel, probe, ranges, cfg, progress_callback)
        _add_dialogue_track(pc, src, out, audio_rel, cfg, progress_callback)

    def validate_with_dialogue(src_probe: dict, out_probe: dict, cfg: dict) -> None:
        dcfg = cfg.get("dialogue_enhancement", {}) or {}
        if not bool(dcfg.get("enabled", False)):
            original_validate(src_probe, out_probe, cfg)
            return

        clean_title = str(cfg["clean_track"].get("title", "English - CLEAN"))
        clean = pc.find_clean_audio_streams(out_probe, clean_title)
        if len(clean) != 1:
            raise RuntimeError(
                f"Validation failed: expected exactly one clean track titled {clean_title!r}, found {len(clean)}"
            )
        clean_stream, clean_rel = clean[0]
        clean_cfg = cfg.get("clean_track", {})
        if bool(clean_cfg.get("place_clean_first", True)) and clean_rel != 0:
            raise RuntimeError(f"Validation failed: CLEAN audio was expected first but is audio stream {clean_rel}")
        if (
            bool(clean_cfg.get("make_default", False))
            and not bool(dcfg.get("make_default", False))
            and not bool((clean_stream.get("disposition") or {}).get("default"))
        ):
            raise RuntimeError("Validation failed: CLEAN audio was expected to be marked default")

        src_v = [s for s in src_probe.get("streams", []) if s.get("codec_type") == "video"]
        out_v = [s for s in out_probe.get("streams", []) if s.get("codec_type") == "video"]
        if len(src_v) != len(out_v):
            raise RuntimeError("Validation failed: video stream count changed")
        for before, after in zip(src_v, out_v):
            if before.get("codec_name") != after.get("codec_name"):
                raise RuntimeError("Validation failed: video codec changed")

        dur_a, dur_b = pc.duration_of(src_probe), pc.duration_of(out_probe)
        tol = float(cfg["safety"].get("duration_tolerance_seconds", 2.0))
        if dur_a and dur_b and abs(dur_a - dur_b) > tol:
            raise RuntimeError(f"Validation failed: duration changed by {abs(dur_a-dur_b):.2f}s")

        title = str(dcfg.get("title") or DEFAULTS["title"])
        dialogue = _find_named_audio(out_probe, title)
        if len(dialogue) != 1:
            raise RuntimeError(
                f"Validation failed: expected exactly one dialogue-enhanced track titled {title!r}, found {len(dialogue)}"
            )

        src_audio = [s for s in src_probe.get("streams", []) if s.get("codec_type") == "audio"]
        src_clean = pc.find_clean_audio_streams(src_probe, clean_title)
        src_dialogue = _find_named_audio(src_probe, title)
        out_audio = [s for s in out_probe.get("streams", []) if s.get("codec_type") == "audio"]
        expected = len(src_audio) - len(src_clean) - len(src_dialogue) + 2
        if len(out_audio) != expected:
            raise RuntimeError(f"Validation failed: expected {expected} audio streams, found {len(out_audio)}")

        if bool(dcfg.get("make_default", False)):
            stream, _rel = dialogue[0]
            if not bool((stream.get("disposition") or {}).get("default")):
                raise RuntimeError("Validation failed: dialogue-enhanced audio was expected to be marked default")

    pc.remux_with_clean_track = remux_with_dialogue
    pc.validate_output = validate_with_dialogue
