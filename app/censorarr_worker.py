"""Docker/Synology worker entrypoint for Censorarr.

The web server and media worker are separate Python processes. Runtime patches made
inside webapp.py do not cross that process boundary, so worker-specific safety and
post-processing fixes must be installed here before censorarr.main() starts.
"""
from __future__ import annotations

import os
from pathlib import Path

import automation_audio_source_finalize
import automation_audio_sources
import censorarr as pc
import dialogue_enhancement
import family_features
import manual_processing
import plex_metadata_cache
import worker_preflight_guard

VERSION = "1.6.8-dev"
pc.VERSION = VERSION
pc.DEFAULT_CONFIG.setdefault("safety", {})["ensure_readable_output"] = True

# The family-safe branch no longer has an approval/Needs Review workflow. Force this
# off even for upgraded installations whose config.yaml still contains review_mode:
# enabled: true. The stable core still understands that legacy key, so make every
# worker-side config load present it as disabled until the stable core is cleaned up.
pc.DEFAULT_CONFIG["review_mode"] = {"enabled": False}
_original_load_config = pc.load_config


def load_config_without_review(path):
    cfg = _original_load_config(path)
    cfg.setdefault("review_mode", {})["enabled"] = False
    cfg["dry_run"] = False
    return cfg


pc.load_config = load_config_without_review

# Keep the stable persistent Plex cache on the development worker too. This is
# installed before experimental audio features because it only replaces Plex metadata
# indexing and is independent of the remux/validation hooks below.
plex_metadata_cache.install(pc)

# Explicit Process/Reprocess requests bypass automation-only content-rating selection.
# This is installed before main() because the stable worker's handle_one() resolves
# rating_decision dynamically from the censorarr module globals.
manual_processing.install(pc)

# Manual-job preflight is visible in the heartbeat, and ffprobe can no longer hang
# indefinitely. The default worker-side probe timeout is 60 seconds and can be
# overridden with CENSORARR_FFPROBE_TIMEOUT_SECONDS.
worker_preflight_guard.install(pc, manual_processing)


def preserve_processed_media_metadata(src_stat, temp_out: Path, cfg: dict) -> None:
    """Preserve source metadata while guaranteeing Plex-readable output.

    Censorarr remuxes to a new inode and replaces the original media file. A source
    mode such as 0600/0700 must not be copied verbatim to that replacement because
    Plex commonly runs as a different user. Ownership is restored first because a
    POSIX chown may clear special mode bits; chmod is deliberately last.
    """
    safety = cfg.get("safety", {}) or {}
    preserve_owner_mode = bool(safety.get("preserve_owner_mode", True))
    ensure_readable_output = bool(safety.get("ensure_readable_output", True))

    if not preserve_owner_mode and not ensure_readable_output:
        return

    if preserve_owner_mode:
        try:
            os.chown(temp_out, src_stat.st_uid, src_stat.st_gid)
        except (OSError, AttributeError, PermissionError) as exc:
            pc.logging.debug("Could not preserve owner/group on %s: %s", temp_out, exc)

    if preserve_owner_mode:
        target_mode = src_stat.st_mode & 0o7777
    else:
        try:
            target_mode = temp_out.stat().st_mode & 0o7777
        except OSError as exc:
            pc.logging.warning("Could not read output permissions for %s: %s", temp_out, exc)
            return

    if ensure_readable_output:
        target_mode |= 0o444

    try:
        os.chmod(temp_out, target_mode)
    except OSError as exc:
        pc.logging.warning("Could not set processed-media permissions on %s: %s", temp_out, exc)


pc.preserve_metadata = preserve_processed_media_metadata

# Experimental feature branch only. Dialogue enhancement wraps the normal CLEAN
# remux/validation path when both features are active.
dialogue_enhancement.install(pc)


_original_after_success = pc.after_success


def _plex_scan_after_analyze_unavailable(path: Path, cfg: dict, reason: str) -> bool:
    """Ask Plex to scan the containing library when per-item Analyze is unavailable."""
    media_type = pc.media_type_for(path, cfg)
    try:
        if pc.integ.plex_scan_library(cfg, media_type):
            pc.logging.info(
                "Plex per-item analyze unavailable (%s); requested %s library scan for %s",
                reason,
                "TV" if media_type == "episode" else "Movies",
                path.name,
            )
            return True
    except Exception as exc:
        pc.logging.debug("Plex library-scan fallback raised for %s: %s", path.name, exc)
    return False


def after_success_with_plex_analyze(
    path: Path,
    cfg: dict,
    status: str,
    rating: str | None,
    report: str | None,
) -> None:
    """Run normal completion actions, then ask Plex to refresh/analyze changed media."""
    _original_after_success(path, cfg, status, rating, report)

    plex_cfg = cfg.get("plex_activity", {}) or {}
    if status not in {"applied", "dialogue-applied"} or not bool(plex_cfg.get("refresh_after_processing", True)):
        return

    try:
        item, _why = pc.plex_item_for(path, cfg, force_refresh=False)
        rating_key = item.get("ratingKey") if item else None
        if not rating_key:
            if not _plex_scan_after_analyze_unavailable(path, cfg, "no ratingKey"):
                pc.logging.warning("Plex refresh/analyze skipped; no ratingKey found for %s", path.name)
            return

        # The stable completion hook already requests Refresh for CLEAN-track changes.
        # Dialogue-only changes need the same refresh before Analyze.
        if status == "dialogue-applied":
            try:
                pc.integ.plex_refresh_rating_key(cfg, rating_key)
                pc.logging.info("Requested Plex refresh for dialogue-enhanced %s", path.name)
            except Exception as exc:
                pc.logging.warning("Plex refresh after dialogue enhancement failed for %s: %s", path.name, exc)

        try:
            # Plex's own clients invoke /analyze as a normal GET action. Some PMS
            # versions do not expose per-item Analyze at all; those get a library-scan
            # fallback below so the changed media file is still rediscovered.
            pc.integ.plex_request(
                cfg,
                f"/library/metadata/{rating_key}/analyze",
                method="GET",
                timeout=30,
            )
            pc.logging.info("Requested Plex analyze for %s", path.name)
        except Exception as exc:
            message = str(exc)
            if "HTTP 404" in message and _plex_scan_after_analyze_unavailable(path, cfg, "HTTP 404"):
                return
            pc.logging.warning("Plex analyze after processing failed for %s: %s", path.name, exc)
    except Exception as exc:
        pc.logging.warning("Plex post-processing refresh/analyze failed for %s: %s", path.name, exc)


pc.after_success = after_success_with_plex_analyze

# Independent master switches and per-feature completion markers are installed first.
family_features.install(pc, dialogue_enhancement)

# Automation source selection is installed after feature tracking so it can wrap the
# feature-aware process and marker hooks.
automation_audio_sources.install(pc, dialogue_enhancement)

# CLEAN-only/Skip is a terminal per-feature decision for the current source/settings
# signature; this last guard makes that durable even when no media remux was needed.
automation_audio_source_finalize.install(pc, automation_audio_sources)


if __name__ == "__main__":
    raise SystemExit(pc.main())
