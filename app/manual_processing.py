"""Manual Process/Reprocess behavior for the family-safe worker.

An explicit per-media Process/Reprocess request is a user override of automation
selection gates. Automatic scans still use content-rating rules exactly as configured,
but a manual job must not block on Plex rating lookup before reaching the selected
audio features.
"""
from __future__ import annotations

import threading

_CTX = threading.local()


def is_manual_active() -> bool:
    return bool(getattr(_CTX, "bypass_automation_rating", False))


def current_job() -> dict | None:
    job = getattr(_CTX, "job", None)
    return job if isinstance(job, dict) else None


def install(pc) -> None:
    if getattr(pc, "_family_safe_manual_processing_installed", False):
        return

    original_pop = pc.pop_manual_job
    original_remove = pc.remove_manual_job
    original_rating_decision = pc.rating_decision

    def pop_manual_job_with_context():
        job = original_pop()
        active = False
        if isinstance(job, dict):
            mode = str(job.get("mode", "process") or "process").strip().lower()
            active = mode in {"process", "reprocess", "retry"}
        _CTX.bypass_automation_rating = active
        _CTX.job = job if active else None
        return job

    def remove_manual_job_with_context(job_id: str) -> None:
        try:
            original_remove(job_id)
        finally:
            _CTX.bypass_automation_rating = False
            _CTX.job = None

    def rating_decision_manual_aware(media, cfg):
        if is_manual_active():
            pc.logging.info(
                "Manual Process/Reprocess: bypassing automation content-rating gate: %s",
                media,
            )
            return "process", None, "manual-request"
        return original_rating_decision(media, cfg)

    pc.pop_manual_job = pop_manual_job_with_context
    pc.remove_manual_job = remove_manual_job_with_context
    pc.rating_decision = rating_decision_manual_aware
    pc._family_safe_manual_processing_installed = True
