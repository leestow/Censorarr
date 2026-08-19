"""Family-safe feature switches and independent completion tracking for Censorarr.

This development-branch shim gives profanity censoring and dialogue enhancement
independent master switches while keeping a single backward-compatible marker file.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from pathlib import Path


FEATURE_PROFANITY = "profanity_censoring"
FEATURE_DIALOGUE = "dialogue_enhancement"
LEGACY_PROFANITY_STATUSES = {
    "applied",
    "no-detections",
    "clean-exists",
    "skipped-clean-exists",
}


def install(pc, dialogue) -> None:
    pc.DEFAULT_CONFIG.setdefault("profanity", {}).setdefault("enabled", True)
    pc.DEFAULT_CONFIG.setdefault("dialogue_enhancement", {}).setdefault("enabled", False)

    original_process_file = pc.process_file
    original_marker_load = pc.marker_load

    def _hash_payload(payload: dict, extra_files: list[Path] | None = None) -> str:
        h = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8"))
        for extra in extra_files or []:
            try:
                h.update(extra.read_bytes())
            except OSError:
                pass
        return h.hexdigest()[:20]

    def profanity_signature(cfg: dict) -> str:
        profanity_cfg = dict(cfg.get("profanity", {}) or {})
        profanity_cfg.pop("enabled", None)
        relevant = {
            "whisper": cfg.get("whisper", {}),
            "profanity": profanity_cfg,
            "rescue": cfg.get("rescue", {}),
            "precision_alignment": cfg.get("precision_alignment", {}),
            "subtitle_assist": cfg.get("subtitle_assist", {}),
            "clean_track": cfg.get("clean_track", {}),
            "audio_track": cfg.get("audio_track", "auto"),
        }
        profanity_path = Path(profanity_cfg.get("file", "/config/en.json"))
        return _hash_payload(
            relevant,
            [
                profanity_path,
                Path("/config/profanity_overrides.json"),
                Path("/config/custom_profanity.json"),
                Path("/config/user_exceptions.json"),
            ],
        )

    def dialogue_signature(cfg: dict) -> str:
        dcfg = dict(cfg.get("dialogue_enhancement", {}) or {})
        dcfg.pop("enabled", None)
        return _hash_payload(
            {
                "dialogue_enhancement": dcfg,
                "audio_track": cfg.get("audio_track", "auto"),
            }
        )

    def _entry(path: Path, cfg: dict) -> tuple[dict, dict]:
        data = original_marker_load(path, cfg)
        return data, (data.get("files", {}) or {}).get(path.name, {}) or {}

    def _fingerprint_matches(path: Path, entry: dict) -> bool:
        try:
            return bool(entry) and entry.get("fingerprint") == pc.fingerprint(path)
        except OSError:
            return False

    def _legacy_feature_complete(entry: dict, feature: str) -> bool:
        status = str(entry.get("status") or "")
        if entry.get("done") is not True:
            return False
        if feature == FEATURE_PROFANITY:
            if status in LEGACY_PROFANITY_STATUSES:
                return True
            # The previous family-safe dialogue-only implementation overwrote the
            # old marker entry. A retained profanity report proves the profanity
            # analysis completed immediately before dialogue enhancement.
            if status == "dialogue-applied" and entry.get("report"):
                return True
            return False
        if feature == FEATURE_DIALOGUE:
            return status == "dialogue-applied"
        return False

    def _feature_record(entry: dict, feature: str) -> dict:
        return ((entry.get("features") or {}).get(feature) or {})

    def _feature_complete(path: Path, cfg: dict, feature: str, *, require_signature: bool = True) -> bool:
        _data, entry = _entry(path, cfg)
        if not _fingerprint_matches(path, entry):
            return False

        rec = _feature_record(entry, feature)
        if rec.get("complete") is True:
            if not require_signature:
                return True
            recorded = str(rec.get("signature") or "")
            current = profanity_signature(cfg) if feature == FEATURE_PROFANITY else dialogue_signature(cfg)
            # New records carry a signature. If an early development marker omitted it,
            # preserve completion instead of forcing a surprise library-wide reprocess.
            return not recorded or recorded == current

        # Legacy .censorarr.done.json entries predate per-feature tracking. Preserve
        # their old meaning so an existing CLEAN library does not suddenly re-run.
        return _legacy_feature_complete(entry, feature)

    def _physical_outputs(path: Path, cfg: dict) -> tuple[bool, bool]:
        """Infer existing outputs only when routing a pending feature job.

        This protects libraries created before feature markers existed: a physical
        CLEAN track counts as profanity output and a physical Dialogue Enhanced track
        counts as dialogue output, so enabling the other feature does not rebuild the
        one that is already present.
        """
        try:
            probe = pc.ffprobe(path)
        except Exception:
            return False, False
        clean_title = str((cfg.get("clean_track", {}) or {}).get("title", "English - CLEAN"))
        dtitle = str((cfg.get("dialogue_enhancement", {}) or {}).get("title") or dialogue.DEFAULTS["title"])
        return bool(pc.find_clean_audio_streams(probe, clean_title)), bool(dialogue._find_named_audio(probe, dtitle))

    def _feature_needs(path: Path, cfg: dict, *, infer_physical: bool = False) -> tuple[bool, bool]:
        profanity_enabled = bool((cfg.get("profanity", {}) or {}).get("enabled", True))
        dialogue_enabled = bool((cfg.get("dialogue_enhancement", {}) or {}).get("enabled", False))
        profanity_done = (not profanity_enabled) or _feature_complete(path, cfg, FEATURE_PROFANITY)
        dialogue_done = (not dialogue_enabled) or _feature_complete(path, cfg, FEATURE_DIALOGUE)

        if infer_physical and (not profanity_done or not dialogue_done):
            clean_exists, dialogue_exists = _physical_outputs(path, cfg)
            if profanity_enabled and not profanity_done and clean_exists:
                profanity_done = True
            if dialogue_enabled and not dialogue_done and dialogue_exists:
                dialogue_done = True

        return profanity_enabled and not profanity_done, dialogue_enabled and not dialogue_done

    def marker_matches_features(media: Path, cfg: dict) -> bool:
        """Return True only when every currently-enabled audio feature is complete."""
        profanity_enabled = bool((cfg.get("profanity", {}) or {}).get("enabled", True))
        dialogue_enabled = bool((cfg.get("dialogue_enhancement", {}) or {}).get("enabled", False))
        if not profanity_enabled and not dialogue_enabled:
            return True
        if not (cfg.get("marker", {}) or {}).get("enabled", True):
            return False

        _data, entry = _entry(media, cfg)
        if not _fingerprint_matches(media, entry):
            # No trusted marker. If Dialogue Enhancement is requested, let the file
            # pass the legacy CLEAN-track shortcut so process_file_with_switches can
            # inspect existing tracks and add only what is missing.
            if dialogue_enabled:
                (cfg.get("clean_track", {}) or {})["reprocess_existing_clean"] = True
            return False

        # Preserve rating-filter terminal markers exactly as the stable worker did.
        if entry.get("done") is True and str(entry.get("status") or "") == "skipped-rating":
            return True

        profanity_done = (not profanity_enabled) or _feature_complete(media, cfg, FEATURE_PROFANITY)
        dialogue_done = (not dialogue_enabled) or _feature_complete(media, cfg, FEATURE_DIALOGUE)
        complete = profanity_done and dialogue_done
        if not complete:
            # The stable daemon has an early "CLEAN track exists" return before it
            # calls process_file(). A pending tracked feature must be allowed through.
            features = entry.get("features") or {}
            tracked_profanity_stale = profanity_enabled and not profanity_done and FEATURE_PROFANITY in features
            if (dialogue_enabled and not dialogue_done) or tracked_profanity_stale:
                (cfg.get("clean_track", {}) or {})["reprocess_existing_clean"] = True
        return complete

    def _completed_at() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z")

    def _merge_marker(
        media: Path,
        cfg: dict,
        status: str,
        *,
        rating: str | None = None,
        report: str | None = None,
        completed_features: set[str] | None = None,
    ) -> None:
        if not (cfg.get("marker", {}) or {}).get("enabled", True) or cfg.get("dry_run", True):
            return

        mp = pc.marker_path(media, cfg)
        data = original_marker_load(media, cfg)
        files = data.setdefault("files", {})
        old = files.get(media.name, {}) or {}
        features = copy.deepcopy(old.get("features") or {})
        completed = set(completed_features or set())

        if status in LEGACY_PROFANITY_STATUSES:
            completed.add(FEATURE_PROFANITY)
        if status == "dialogue-applied":
            completed.add(FEATURE_DIALOGUE)
        if status == "applied" and bool((cfg.get("dialogue_enhancement", {}) or {}).get("enabled", False)):
            # dialogue_enhancement.install() wraps the CLEAN remux, so a successful
            # combined apply means both tracks passed validation.
            completed.add(FEATURE_DIALOGUE)

        now = _completed_at()
        if FEATURE_PROFANITY in completed:
            features[FEATURE_PROFANITY] = {
                "complete": True,
                "signature": profanity_signature(cfg),
                "status": "complete" if status == "dialogue-applied" else status,
                "completed_at": now,
                "report": report,
                "track": str((cfg.get("clean_track", {}) or {}).get("title", "English - CLEAN")),
            }
        if FEATURE_DIALOGUE in completed:
            dcfg = cfg.get("dialogue_enhancement", {}) or {}
            features[FEATURE_DIALOGUE] = {
                "complete": True,
                "signature": dialogue_signature(cfg),
                "status": status,
                "completed_at": now,
                "track": str(dcfg.get("title") or dialogue.DEFAULTS["title"]),
                "strength": str(dcfg.get("strength", "medium")),
                "codec": str(dcfg.get("codec", "aac")),
                "bitrate": str(dcfg.get("bitrate", "192k")),
            }

        # "done" remains for old Censorarr versions/tools. In family-safe it means
        # the marker entry itself is terminal, while "features" carries the precise
        # completion state for each audio feature.
        files[media.name] = {
            **old,
            "done": True,
            "status": status,
            "rating": rating,
            "media_type": pc.media_type_for(media, cfg),
            "fingerprint": pc.fingerprint(media),
            "version": pc.VERSION,
            "completed_at": now,
            "report": report,
            "features": features,
        }
        tmp = mp.with_suffix(mp.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, mp)

    def marker_write_features(
        media: Path,
        cfg: dict,
        status: str,
        rating: str | None = None,
        report: str | None = None,
        *,
        completed_features: set[str] | None = None,
    ) -> None:
        _merge_marker(
            media,
            cfg,
            status,
            rating=rating,
            report=report,
            completed_features=completed_features,
        )

    # Install feature-aware marker behavior before the daemon starts.
    pc.marker_matches = marker_matches_features
    pc.marker_write = marker_write_features

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

    def dialogue_only(
        path: Path,
        cfg: dict,
        report: str | None = None,
        *,
        profanity_complete: bool = False,
    ) -> dict:
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
                lambda pct: pc.update_heartbeat(
                    "remuxing", str(path), progress=min(35.0, pct * 0.35), dialogue_only=True
                ),
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
            completed = {FEATURE_DIALOGUE}
            if profanity_complete:
                completed.add(FEATURE_PROFANITY)
            pc.marker_write(
                path,
                cfg,
                "dialogue-applied",
                report=report,
                completed_features=completed,
            )
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

        if not profanity_enabled and not dialogue_enabled:
            pc.logging.info("Skipping media: Profanity Censoring and Dialogue Enhancement are both disabled")
            pc.update_heartbeat("completed", str(path), progress=100, features_disabled=True)
            return {"status": "features-disabled", "detections": 0}

        manual_force = False
        try:
            manual_force = bool(getattr(pc, "manual_processing_active", lambda: False)())
        except Exception:
            manual_force = False

        if manual_force:
            # A user-clicked Process/Reprocess is an explicit request to rebuild every
            # currently enabled feature. Do not let old completion markers or a physical
            # CLEAN/DIALOGUE track turn that request into a silent "features-present" no-op.
            profanity_needed = profanity_enabled
            dialogue_needed = dialogue_enabled
            pc.logging.info(
                "Manual Process/Reprocess: forcing enabled audio features (profanity=%s dialogue=%s): %s",
                profanity_enabled,
                dialogue_enabled,
                path,
            )
        else:
            profanity_needed, dialogue_needed = _feature_needs(path, cfg, infer_physical=True)

        if dialogue_enabled and dialogue_needed and not profanity_needed:
            return dialogue_only(
                path,
                cfg,
                profanity_complete=bool(profanity_enabled and not profanity_needed),
            )

        if profanity_enabled and profanity_needed:
            # If Dialogue Enhancement is already current, do not rebuild it while
            # refreshing profanity settings. The wrapped CLEAN remux sees this copied
            # config with Dialogue Enhancement temporarily disabled.
            run_cfg = cfg
            if dialogue_enabled and not dialogue_needed:
                run_cfg = copy.deepcopy(cfg)
                run_cfg.setdefault("dialogue_enhancement", {})["enabled"] = False

            result = original_process_file(path, run_cfg, model, matcher)
            status = str(result.get("status"))

            # A no-detections profanity result still means profanity analysis completed.
            # If Dialogue Enhancement is pending, add it without a second Whisper pass
            # and record BOTH feature completions in the same marker update.
            if dialogue_enabled and dialogue_needed and status == "no-detections":
                return dialogue_only(
                    path,
                    cfg,
                    report=result.get("report"),
                    profanity_complete=True,
                )

            return result

        # Physical output inference may discover that all requested work already exists
        # even though the old marker did not know about features. Upgrade the marker
        # without touching the media file.
        completed: set[str] = set()
        if profanity_enabled:
            completed.add(FEATURE_PROFANITY)
        if dialogue_enabled:
            completed.add(FEATURE_DIALOGUE)
        if completed:
            pc.marker_write(path, cfg, "features-present", completed_features=completed)
        return {"status": "features-present", "detections": 0}

    pc.process_file = process_file_with_switches
