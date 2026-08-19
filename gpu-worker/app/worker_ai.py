"""AI-capable entrypoint layered over the stable Censorarr GPU ASR worker."""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import HTTPException, Query, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

import dialogue_ai
import worker as base


VERSION = "1.6.8-ai-dev"
base.VERSION = VERSION

# Preserve the stable ASR worker while teaching its shared status/cancel machinery about
# the second, mutually-exclusive AI dialogue job type.
_original_gpu_info = base.gpu_info
_original_status = base.engine.status
_original_cancel = base.engine.cancel
_original_run = base.engine.run


def gpu_info_with_features() -> dict:
    data = dict(_original_gpu_info())
    data["features"] = {
        "transcription": True,
        "dialogue_ai": dialogue_ai.manager.available(),
    }
    data["dialogue_ai_model_default"] = dialogue_ai.DEFAULT_MODEL
    return data


def status_with_dialogue() -> dict:
    stable = dict(_original_status())
    dialogue = dialogue_ai.manager.status().get("current_job")
    if dialogue:
        stable["current_job"] = dialogue
    return stable


def cancel_any(job_id: str) -> dict:
    result = dialogue_ai.manager.cancel(job_id, base.log_line)
    if result.get("cancelled"):
        return result
    return _original_cancel(job_id)


def run_asr_guarded(job_id: str, audio_path: Path, params: dict) -> dict:
    if dialogue_ai.manager.status().get("current_job"):
        raise RuntimeError(f"GPU worker is busy with AI dialogue job {dialogue_ai.manager.status()['current_job'].get('job_id')}")
    return _original_run(job_id, audio_path, params)


base.gpu_info = gpu_info_with_features
base.engine.status = status_with_dialogue
base.engine.cancel = cancel_any
base.engine.run = run_asr_guarded

app = base.app
app.title = "Censorarr GPU ASR + AI Dialogue Worker"
app.version = VERSION


def _cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


@app.post("/dialogue/isolate")
async def dialogue_isolate(
    request: Request,
    job_id: str = Query(default=""),
    model: str = Query(default=dialogue_ai.DEFAULT_MODEL),
    segment: int = Query(default=4, ge=2, le=8),
    allow_cpu_fallback: int = Query(default=1),
):
    base.auth(request)
    if not dialogue_ai.manager.available():
        raise HTTPException(503, "AI Dialogue Isolation is not installed in this GPU worker")
    if not base.gpu_info().get("cuda_devices") and not bool(allow_cpu_fallback):
        raise HTTPException(503, "No CUDA device visible to the worker and CPU fallback is disabled")
    with base.engine.lock:
        if base.engine.current_job is not None:
            raise HTTPException(409, f"GPU worker is busy with transcription job {base.engine.current_job.get('job_id')}")
    if dialogue_ai.manager.status().get("current_job"):
        raise HTTPException(409, "GPU worker is already running an AI dialogue job")

    clen = request.headers.get("content-length")
    if clen and int(clen) > int(base.MAX_UPLOAD_GB * 1024**3):
        raise HTTPException(413, "Audio upload exceeds ASR_MAX_UPLOAD_GB")

    jid = (job_id or request.headers.get("X-Censorarr-Job-ID") or uuid.uuid4().hex).strip()
    root = Path(tempfile.mkdtemp(prefix="censorarr-dialogue-ai-worker-"))
    source = root / "source.flac"
    output = root / "separated"
    output.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with source.open("wb") as fh:
            async for chunk in request.stream():
                if not chunk:
                    continue
                total += len(chunk)
                if total > int(base.MAX_UPLOAD_GB * 1024**3):
                    raise HTTPException(413, "Audio upload too large")
                fh.write(chunk)
        base.log_line(f"Received AI dialogue job {jid[:8]} model={model} bytes={total}")

        try:
            vocals, device = await asyncio.to_thread(
                dialogue_ai.manager.run,
                jid,
                source,
                output,
                model,
                segment,
                bool(allow_cpu_fallback),
                base.engine.shutdown,
                base.engine.start,
                base.log_line,
            )
        except InterruptedError:
            raise HTTPException(499, "AI dialogue isolation cancelled")
        except RuntimeError as exc:
            if "busy with job" in str(exc):
                raise HTTPException(409, str(exc))
            raise HTTPException(500, str(exc))

        base.log_line(f"Completed AI dialogue job {jid[:8]} model={model} device={device}")
        return FileResponse(
            path=str(vocals),
            media_type="audio/flac",
            filename="dialogue.flac",
            headers={
                "X-Censorarr-Dialogue-Model": str(model),
                "X-Censorarr-Dialogue-Device": str(device),
                "X-Censorarr-Job-ID": jid,
            },
            background=BackgroundTask(_cleanup, root),
        )
    except HTTPException:
        _cleanup(root)
        raise
    except Exception as exc:
        _cleanup(root)
        base.log_line(f"AI dialogue job {jid[:8]} failed: {type(exc).__name__}: {exc}", "ERROR")
        raise HTTPException(500, str(exc))
