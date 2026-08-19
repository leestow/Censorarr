"""Worker-side preflight diagnostics and ffprobe hang protection."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


def install(pc, manual_processing) -> None:
    if getattr(pc, "_family_safe_preflight_guard_installed", False):
        return

    original_readable = pc.media_file_readable

    def manual_active() -> bool:
        try:
            return bool(manual_processing.is_manual_active())
        except Exception:
            return False

    def media_file_readable_guarded(path: Path):
        if manual_active():
            pc.logging.info("Manual preflight: checking media readability: %s", path)
            try:
                pc.update_heartbeat(
                    "preflight", str(path), stage_progress=0,
                    preflight_stage="checking-readability",
                )
            except Exception:
                pass
        started = time.time()
        result = original_readable(path)
        if manual_active():
            pc.logging.info(
                "Manual preflight: media readability check finished in %.2fs: %s",
                time.time() - started, path,
            )
        return result

    def ffprobe_guarded(path: Path) -> dict:
        timeout_seconds = float(os.environ.get("CENSORARR_FFPROBE_TIMEOUT_SECONDS", "60") or 60)
        if manual_active():
            pc.logging.info("Manual preflight: probing media streams (timeout %.0fs): %s", timeout_seconds, path)
            try:
                pc.update_heartbeat(
                    "preflight", str(path), stage_progress=5,
                    preflight_stage="probing-media",
                )
            except Exception:
                pass
        started = time.time()
        cmd = [
            "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
        ]
        try:
            cp = subprocess.run(
                cmd,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=max(5.0, timeout_seconds),
            )
        except subprocess.TimeoutExpired as exc:
            pc.logging.error("ffprobe timed out after %.0fs: %s", timeout_seconds, path)
            raise RuntimeError(
                f"ffprobe timed out after {timeout_seconds:.0f} seconds while inspecting {path.name}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            if exc.stderr:
                pc.logging.error("Command stderr: %s", exc.stderr.strip())
            raise
        if manual_active():
            pc.logging.info("Manual preflight: media probe finished in %.2fs: %s", time.time() - started, path)
            try:
                pc.update_heartbeat(
                    "preflight", str(path), stage_progress=10,
                    preflight_stage="probe-complete",
                )
            except Exception:
                pass
        return json.loads(cp.stdout)

    pc.media_file_readable = media_file_readable_guarded
    pc.ffprobe = ffprobe_guarded
    pc._family_safe_preflight_guard_installed = True
