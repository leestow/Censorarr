"""Docker/Synology worker entrypoint for Censorarr.

The web server and media worker are separate Python processes. Runtime patches made
inside webapp.py do not cross that process boundary, so worker-specific safety and
post-processing fixes must be installed here before censorarr.main() starts.
"""
from __future__ import annotations

import os
from pathlib import Path

import censorarr as pc

VERSION = "1.6.7"
pc.VERSION = VERSION
pc.DEFAULT_CONFIG.setdefault("safety", {})["ensure_readable_output"] = True


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


_original_after_success = pc.after_success


def after_success_with_plex_analyze(
    path: Path,
    cfg: dict,
    status: str,
    rating: str | None,
    report: str | None,
) -> None:
    """Run normal completion actions, then ask Plex to re-analyze changed media.

    A metadata refresh alone can leave Plex's cached audio-stream list stale when
    Censorarr replaces a file in place. A targeted Analyze forces Plex to read the
    media properties again so newly-added CLEAN audio streams appear in the player.
    """
    _original_after_success(path, cfg, status, rating, report)

    plex_cfg = cfg.get("plex_activity", {}) or {}
    if status != "applied" or not bool(plex_cfg.get("refresh_after_processing", True)):
        return

    try:
        item, _why = pc.plex_item_for(path, cfg, force_refresh=True)
        rating_key = item.get("ratingKey") if item else None
        if not rating_key:
            pc.logging.warning("Plex analyze skipped; no ratingKey found for %s", path.name)
            return
        pc.integ.plex_request(
            cfg,
            f"/library/metadata/{rating_key}/analyze",
            method="PUT",
            timeout=30,
        )
        pc.logging.info("Requested Plex analyze for %s", path.name)
    except Exception as exc:
        pc.logging.warning("Plex analyze after processing failed for %s: %s", path.name, exc)


pc.after_success = after_success_with_plex_analyze


if __name__ == "__main__":
    raise SystemExit(pc.main())
