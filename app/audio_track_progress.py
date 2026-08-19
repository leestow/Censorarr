"""Background/progress wrapper for safe per-media audio-track removal."""
from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

from fastapi import Depends, HTTPException, Query, Request

import audio_track_management as track_manager

_JOB_LOCK = threading.RLock()
_JOBS: dict[str, dict] = {}
_ACTIVE_JOB: str | None = None


def _update(job_id: str, **values) -> None:
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        if "progress" in values:
            try:
                values["progress"] = max(0.0, min(100.0, float(values["progress"])))
            except (TypeError, ValueError):
                values.pop("progress", None)
        job.update(values)
        job["updated_at"] = time.time()


def _snapshot(job_id: str) -> dict | None:
    with _JOB_LOCK:
        raw = _JOBS.get(job_id)
        if not raw:
            return None
        job = dict(raw)
    started = float(job.get("started_at") or job.get("created_at") or time.time())
    elapsed = max(0.0, time.time() - started)
    job["elapsed_seconds"] = round(elapsed, 1)
    progress = float(job.get("progress") or 0.0)
    if job.get("status") == "running" and 1.0 <= progress < 99.0:
        # Best-effort ETA. The final few percent are validation/atomic replacement,
        # so keep the estimate conservative rather than pretending it is exact.
        eta = elapsed * (100.0 - progress) / progress
        job["eta_seconds"] = round(max(0.0, eta), 1)
    else:
        job["eta_seconds"] = None
    return job


def _prune_jobs() -> None:
    with _JOB_LOCK:
        if len(_JOBS) <= 50:
            return
        finished = sorted(
            (
                (float(v.get("finished_at") or 0), k)
                for k, v in _JOBS.items()
                if v.get("status") in {"complete", "error"}
            )
        )
        for _when, key in finished[: max(0, len(_JOBS) - 40)]:
            _JOBS.pop(key, None)


def _same_path(a: str | Path, b: Path) -> bool:
    try:
        return Path(a).resolve() == b.resolve()
    except Exception:
        return str(a) == str(b)


def _restore_pause(core, job_id: str, pause_owned: bool, *, safe_to_resume: bool) -> None:
    if not pause_owned or not safe_to_resume:
        return
    token = f"audio-track-remove:{job_id}"
    try:
        if core.PAUSED.exists() and core.PAUSED.read_text(encoding="utf-8").strip() == token:
            core.PAUSED.unlink()
            core.SCAN_NOW.touch()
    except OSError:
        pass


def _run_job(core, job_id: str, media: Path, requested_index: int, expected_fingerprint: str) -> None:
    global _ACTIVE_JOB
    pause_owned = bool((_JOBS.get(job_id) or {}).get("pause_owned"))
    replaced = False
    suppression_saved = False
    safe_to_resume = True
    temp: Path | None = None
    try:
        _update(job_id, status="running", stage="Preparing", progress=1.0, started_at=time.time())
        # Give the normal worker a moment to observe the pause flag before touching this file.
        time.sleep(0.25)
        hb = core.read_json(core.HEARTBEAT, {})
        current = str(hb.get("current") or "").strip()
        if current and _same_path(current, media):
            raise RuntimeError("This movie began processing before audio removal could start. Stop or finish that job and try again.")

        with track_manager._LOCK:
            cfg = core.pc.load_config(core.CONFIG)
            if str(core.pc.fingerprint(media)) != str(expected_fingerprint):
                raise RuntimeError("The movie file changed after you opened its details. Reload the movie and try again.")

            src_probe = core.pc.ffprobe(media)
            rows = track_manager._track_rows(core, media, cfg, src_probe)
            selected = next((x for x in rows if int(x["stream_index"]) == requested_index), None)
            if not selected:
                raise RuntimeError("The selected audio track no longer exists")
            if not selected.get("removable") or not selected.get("feature"):
                raise RuntimeError("The selected track is protected and cannot be removed")
            if sum(1 for x in rows if x.get("protected")) < 1:
                raise RuntimeError("No protected original/pre-existing audio could be verified")

            global_stream = next(
                (s for s in src_probe.get("streams", []) or [] if int(s.get("index", -1)) == requested_index),
                None,
            )
            if not global_stream or global_stream.get("codec_type") != "audio":
                raise RuntimeError("The selected stream is no longer the same audio track")
            if track_manager._stream_title(global_stream) != str(selected.get("title") or ""):
                raise RuntimeError("The selected audio track changed; reload movie details and try again")

            src_stat = media.stat()
            temp = media.with_name(media.stem + f".censorarr-remove-{job_id[:8]}.tmp" + media.suffix)
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass

            duration = core.pc.duration_of(src_probe)
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
                "-i", str(media),
                "-map", "0", "-map", f"-0:{requested_index}",
                "-map_metadata", "0", "-map_chapters", "0", "-c", "copy",
                str(temp),
            ]
            core.pc.logging.info(
                "Removing Censorarr-generated audio track with progress: %s stream=%s feature=%s",
                selected.get("title") or "(untitled)", requested_index, selected.get("feature"),
            )
            _update(job_id, stage="Removing audio track", progress=2.0)

            def progress(value) -> None:
                try:
                    pct = float(value)
                except (TypeError, ValueError):
                    return
                _update(job_id, stage="Removing audio track", progress=2.0 + max(0.0, min(100.0, pct)) * 0.90)

            core.pc.run_ffmpeg_progress(cmd, duration, progress)

            _update(job_id, stage="Validating protected streams", progress=94.0)
            out_probe = core.pc.ffprobe(temp)
            track_manager._validate_remux(core, src_probe, out_probe, requested_index, cfg)

            _update(job_id, stage="Preserving metadata", progress=97.0)
            if hasattr(core.pc, "preserve_metadata"):
                core.pc.preserve_metadata(src_stat, temp, cfg)

            _update(job_id, stage="Replacing movie safely", progress=99.0)
            os.replace(temp, media)
            replaced = True

            track_manager._record_suppression(
                core, media, cfg, str(selected["feature"]), str(selected.get("title") or ""), requested_index
            )
            suppression_saved = True
            message = (
                f"Removed {selected.get('title') or 'Censorarr audio track'}. "
                "Automation will not recreate it unless you manually Process/Reprocess this media."
            )
            _update(
                job_id,
                status="complete",
                stage="Complete",
                progress=100.0,
                finished_at=time.time(),
                removed=selected,
                message=message,
            )
    except Exception as exc:
        # If replacement succeeded but suppression could not be saved, leave automation
        # paused rather than risk immediately recreating the track the user just removed.
        if replaced and not suppression_saved:
            safe_to_resume = False
            message = (
                f"The audio track was removed, but Censorarr could not save the 'do not recreate' marker: {exc}. "
                "Automatic processing has been left paused for safety."
            )
        else:
            message = str(exc)
        _update(job_id, status="error", stage="Failed", error=message, finished_at=time.time())
        core.pc.logging.error("Audio-track removal job %s failed: %s", job_id[:8], message)
    finally:
        if temp is not None:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass
        _restore_pause(core, job_id, pause_owned, safe_to_resume=safe_to_resume)
        with _JOB_LOCK:
            if _ACTIVE_JOB == job_id:
                _ACTIVE_JOB = None
        _prune_jobs()


def install(app, core) -> None:
    @app.post("/api/audio-tracks/remove-job")
    async def start_remove_job(request: Request, _: bool = Depends(core.auth)):
        global _ACTIVE_JOB
        body = await request.json()
        media = core.safe_media_path(str(body.get("path") or ""))
        if not media.is_file():
            raise HTTPException(400, "Choose a media file")
        try:
            requested_index = int(body.get("stream_index"))
        except (TypeError, ValueError):
            raise HTTPException(400, "A valid audio stream index is required")

        with _JOB_LOCK:
            if _ACTIVE_JOB:
                active = _snapshot(_ACTIVE_JOB)
                if active and active.get("status") in {"queued", "running"}:
                    raise HTTPException(409, "Another audio-track removal is already in progress")
                _ACTIVE_JOB = None

        hb = core.read_json(core.HEARTBEAT, {})
        current = str(hb.get("current") or "").strip()
        if current and _same_path(current, media):
            raise HTTPException(409, "This file is currently processing. Finish or stop that job before removing a track.")

        cfg = core.pc.load_config(core.CONFIG)
        try:
            probe = core.pc.ffprobe(media)
            rows = track_manager._track_rows(core, media, cfg, probe)
            selected = next((x for x in rows if int(x["stream_index"]) == requested_index), None)
        except Exception as exc:
            raise HTTPException(500, f"Could not inspect audio tracks: {exc}")
        if not selected:
            raise HTTPException(404, "Audio track was not found")
        if not selected.get("removable") or not selected.get("feature"):
            raise HTTPException(403, "Original and pre-existing audio tracks are protected and cannot be removed")
        if sum(1 for x in rows if x.get("protected")) < 1:
            raise HTTPException(409, "Removal refused because no protected original audio track could be verified")

        fingerprint = str(core.pc.fingerprint(media))
        job_id = uuid.uuid4().hex
        pause_owned = not core.PAUSED.exists()
        if pause_owned:
            try:
                core.PAUSED.write_text(f"audio-track-remove:{job_id}", encoding="utf-8")
            except OSError as exc:
                raise HTTPException(500, f"Could not pause automatic processing for safe removal: {exc}")

        job = {
            "job_id": job_id,
            "status": "queued",
            "stage": "Queued",
            "progress": 0.0,
            "path": str(media),
            "stream_index": requested_index,
            "track_title": selected.get("title") or f"Audio {int(selected.get('relative_index', 0)) + 1}",
            "feature": selected.get("feature"),
            "created_at": time.time(),
            "pause_owned": pause_owned,
        }
        with _JOB_LOCK:
            _JOBS[job_id] = job
            _ACTIVE_JOB = job_id

        try:
            thread = threading.Thread(
                target=_run_job,
                args=(core, job_id, media, requested_index, fingerprint),
                daemon=True,
                name=f"audio-remove-{job_id[:8]}",
            )
            thread.start()
        except Exception as exc:
            with _JOB_LOCK:
                _ACTIVE_JOB = None
                _JOBS.pop(job_id, None)
            _restore_pause(core, job_id, pause_owned, safe_to_resume=True)
            raise HTTPException(500, f"Could not start audio-track removal: {exc}")

        return {"ok": True, "job_id": job_id, "job": _snapshot(job_id)}

    @app.get("/api/audio-tracks/remove-job/{job_id}")
    def remove_job_status(job_id: str, _: bool = Depends(core.auth)):
        if not job_id or len(job_id) > 80:
            raise HTTPException(400, "Invalid removal job id")
        job = _snapshot(job_id)
        if not job:
            raise HTTPException(404, "Audio-track removal job not found")
        # Do not expose the internal pause-ownership implementation detail to the UI.
        job.pop("pause_owned", None)
        return {"ok": True, "job": job}
