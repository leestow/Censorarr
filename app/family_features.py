"""Family-safe feature switches for Censorarr.

This development-branch shim gives profanity censoring and dialogue enhancement
independent master switches without changing the stable processing engine.
"""
from __future__ import annotations

import os
from pathlib import Path


def install(pc, dialogue) -> None:
    pc.DEFAULT_CONFIG.setdefault("profanity", {}).setdefault("enabled", True)
    pc.DEFAULT_CONFIG.setdefault("dialogue_enhancement", {}).setdefault("enabled", False)

    original_process_file = pc.process_file

    def validate_dialogue_only(src_probe: dict, out_probe: dict, cfg: dict) -> None:
        title = str((cfg.get("dialogue_enhancement", {}) or {}).get("title") or dialogue.DEFAULTS["title"])
        dialogue_tracks = dialogue._find_named_audio(out_probe, title)
        if len(dialogue_tracks) != 1:
            raise RuntimeError(
                f"Dialogue Enhancement validation failed: expected exactly one track titled {title!r}, found {len(dialogue_tracks)}"
            )

        src_v = [s for s in src_probe.get("streams", []) if s.get("codec_type") == "video"]
        out_v = [s for s in out_probe.get("streams", []) if s.get("codec_type") == "video"]
        if len(src_v) != len(out_v):
            raise RuntimeError("Dialogue Enhancement validation failed: video stream count changed")
        for before, after in zip(src_v, out_v):
            if before.get("codec_name") != after.get("codec_name"):
                raise RuntimeError("Dialogue Enhancement validation failed: video codec changed")

        src_audio = [s for s in src_probe.get("streams", []) if s.get("codec_type") == "audio"]
        src_dialogue = dialogue._find_named_audio(src_probe, title)
        out_audio = [s for s in out_probe.get("streams", []) if s.get("codec_type") == "audio"]
        expected = len(src_audio) - len(src_dialogue) + 1
        if len(out_audio) != expected:
            raise RuntimeError(
                f"Dialogue Enhancement validation failed: expected {expected} audio streams, found {len(out_audio)}"
            )

        dur_a, dur_b = pc.duration_of(src_probe), pc.duration_of(out_probe)
        tol = float((cfg.get("safety", {}) or {}).get("duration_tolerance_seconds", 2.0))
        if dur_a and dur_b and abs(dur_a - dur_b) > tol:
            raise RuntimeError(
                f"Dialogue Enhancement validation failed: duration changed by {abs(dur_a-dur_b):.2f}s"
            )

        if bool((cfg.get("dialogue_enhancement", {}) or {}).get("make_default", False)):
            stream, _rel = dialogue_tracks[0]
            if not bool((stream.get("disposition") or {}).get("default")):
                raise RuntimeError("Dialogue Enhancement validation failed: enhanced track should be default")

    def dialogue_only(path: Path, cfg: dict, report: str | None = None) -> dict:
        src_stat = path.stat()
        src_probe = pc.ffprobe(path)
        _audio_stream, audio_rel = pc.select_audio_stream(src_probe, cfg.get("audio_track", "auto"))
        temp_out = path.with_name(path.name + ".censorarr.tmp" + path.suffix)
        if temp_out.exists():
            temp_out.unlink()

        pc.logging.info("Dialogue Enhancement only: building enhanced audio without profanity transcription")
        pc.update_heartbeat("remuxing", str(path), progress=0, dialogue_only=True)
        try:
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
                "-i", str(path), "-map", "0", "-map_metadata", "0", "-map_chapters", "0",
                "-c", "copy", str(temp_out),
            ]
            pc.run_ffmpeg_progress(
                cmd,
                pc.duration_of(src_probe),
                lambda pct: pc.update_heartbeat("remuxing", str(path), progress=min(35.0, pct * 0.35), dialogue_only=True),
            )
            dialogue._add_dialogue_track(
                pc,
                path,
                temp_out,
                audio_rel,
                cfg,
                progress_callback=lambda pct: pc.update_heartbeat(
                    "remuxing", str(path), progress=35.0 + min(64.0, pct * 0.64), dialogue_only=True
                ),
            )
            pc.update_heartbeat("validating", str(path), progress=0, dialogue_only=True)
            out_probe = pc.ffprobe(temp_out)
            if bool((cfg.get("safety", {}) or {}).get("validate_output", True)):
                validate_dialogue_only(src_probe, out_probe, cfg)
            pc.preserve_metadata(src_stat, temp_out, cfg)

            if bool((cfg.get("safety", {}) or {}).get("backup_original", False)):
                backup = path.with_name(path.name + ".preclean.bak")
                if backup.exists():
                    raise RuntimeError(f"Backup already exists: {backup}")
                os.replace(path, backup)
                try:
                    os.replace(temp_out, path)
                except Exception:
                    os.replace(backup, path)
                    raise
            else:
                os.replace(temp_out, path)

            pc.logging.info("SUCCESS: added/replaced Dialogue Enhanced track: %s", path)
            pc.update_heartbeat("completed", str(path), progress=100, detections=0, dialogue_enhanced=True)
            # Write a durable marker ourselves because the stable daemon only recognizes CLEAN statuses.
            pc.marker_write(path, cfg, "dialogue-applied", report=report)
            pc.after_success(path, cfg, "dialogue-applied", None, report)
            return {"status": "dialogue-applied", "report": report, "detections": 0}
        finally:
            try:
                if temp_out.exists():
                    temp_out.unlink()
            except OSError:
                pass

    def process_file_with_switches(path: Path, cfg: dict, model, matcher) -> dict:
        profanity_enabled = bool((cfg.get("profanity", {}) or {}).get("enabled", True))
        dialogue_enabled = bool((cfg.get("dialogue_enhancement", {}) or {}).get("enabled", False))

        if not profanity_enabled:
            if not dialogue_enabled:
                pc.logging.info("Skipping media: Profanity Censoring and Dialogue Enhancement are both disabled")
                pc.update_heartbeat("completed", str(path), progress=100, features_disabled=True)
                return {"status": "features-disabled", "detections": 0}
            return dialogue_only(path, cfg)

        result = original_process_file(path, cfg, model, matcher)
        # If profanity scanning found nothing, Dialogue Enhancement should still be produced when enabled.
        if dialogue_enabled and str(result.get("status")) == "no-detections":
            return dialogue_only(path, cfg, report=result.get("report"))
        return result

    pc.process_file = process_file_with_switches
