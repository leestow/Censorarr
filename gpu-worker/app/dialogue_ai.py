"""Low-memory Demucs dialogue/vocal isolation manager for the Censorarr GPU worker."""
from __future__ import annotations

import importlib.util
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable


SUPPORTED_MODELS = {"mdx_q", "htdemucs"}
DEFAULT_MODEL = "mdx_q"


def _fmt_clock(seconds: float | int | None) -> str:
    try:
        total = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        total = 0
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


class DialogueAIManager:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.current_job: dict | None = None
        self.proc: subprocess.Popen | None = None
        self.cancelled: set[str] = set()

    def available(self) -> bool:
        return importlib.util.find_spec("demucs") is not None

    def status(self) -> dict:
        with self.lock:
            cur = dict(self.current_job) if self.current_job else None
            if cur and cur.get("started"):
                cur["elapsed_seconds"] = round(time.time() - float(cur["started"]), 1)
                try:
                    pct = float(cur.get("progress") or 0)
                    if 0.1 <= pct < 100:
                        cur["eta_seconds"] = round(cur["elapsed_seconds"] * (100.0 - pct) / pct, 1)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
            return {"current_job": cur, "available": self.available()}

    def cancel(self, job_id: str, log: Callable[[str, str], None] | None = None) -> dict:
        jid = str(job_id or "")
        with self.lock:
            if not self.current_job or str(self.current_job.get("job_id")) != jid:
                return {"ok": False, "cancelled": False, "job_id": jid}
            if log:
                log(f"Cancelling AI dialogue job {jid[:8]}", "WARNING")
            self.cancelled.add(jid)
            p = self.proc
            if p and p.poll() is None:
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                    p.wait(timeout=4)
                except Exception:
                    try:
                        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                    except Exception:
                        try:
                            p.kill()
                        except Exception:
                            pass
            self.proc = None
            self.current_job = None
            return {"ok": True, "cancelled": True, "job_id": jid, "message": "AI dialogue job cancelled"}

    def _run_demucs(
        self,
        job_id: str,
        source: Path,
        output_root: Path,
        model: str,
        segment: int,
        device: str,
        log: Callable[[str, str], None] | None,
    ) -> Path:
        cmd = [
            sys.executable, "-m", "demucs.separate",
            "-n", model,
            "--two-stems", "vocals",
            "--flac",
            "--shifts", "0",
            "--overlap", "0.10",
            "--segment", str(segment),
            "-d", device,
            "-o", str(output_root),
            str(source),
        ]
        started = time.time()
        if log:
            log(
                f"AI dialogue job {job_id[:8]} starting model={model} device={device} "
                f"segment={segment}s source={source.stat().st_size / 1024 / 1024:.1f}MB",
                "INFO",
            )
        with self.lock:
            if job_id in self.cancelled:
                raise InterruptedError("AI dialogue job cancelled")
            self.current_job.update({"stage": "separating-dialogue", "device": device, "progress": 1.0})
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            proc = self.proc

        percent_re = re.compile(r"(?<!\d)(\d{1,3})%")
        last_log_bucket = 0
        heartbeat_stop = threading.Event()

        def heartbeat() -> None:
            while not heartbeat_stop.wait(30.0):
                with self.lock:
                    cur = dict(self.current_job) if self.current_job and self.current_job.get("job_id") == job_id else None
                if not cur or not log:
                    continue
                elapsed = max(0.0, time.time() - started)
                try:
                    pct = float(cur.get("progress") or 0)
                except (TypeError, ValueError):
                    pct = 0.0
                eta = elapsed * (100.0 - pct) / pct if 0.1 <= pct < 100 else None
                eta_text = _fmt_clock(eta) if eta is not None else "calculating"
                log(
                    f"AI dialogue job {job_id[:8]} still running: stage={cur.get('stage') or 'separating-dialogue'} "
                    f"progress={pct:.1f}% device={cur.get('device') or device} "
                    f"elapsed={_fmt_clock(elapsed)} eta={eta_text}",
                    "INFO",
                )

        heartbeat_thread = threading.Thread(
            target=heartbeat,
            daemon=True,
            name=f"dialogue-heartbeat-{job_id[:8]}",
        )
        heartbeat_thread.start()

        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.strip()
                if not line:
                    continue
                match = percent_re.search(line)
                if match:
                    try:
                        pct = max(1.0, min(99.0, float(match.group(1))))
                        with self.lock:
                            if self.current_job and self.current_job.get("job_id") == job_id:
                                self.current_job["progress"] = pct
                        bucket = min(95, int(pct // 5) * 5)
                        if log and bucket >= 5 and bucket > last_log_bucket:
                            last_log_bucket = bucket
                            elapsed = max(0.0, time.time() - started)
                            eta = elapsed * (100.0 - pct) / pct if pct > 0 else None
                            log(
                                f"AI dialogue job {job_id[:8]}: {bucket}% · model={model} device={device} "
                                f"elapsed={_fmt_clock(elapsed)} eta={_fmt_clock(eta)}",
                                "INFO",
                            )
                    except Exception:
                        pass
                if log and ("%" not in line or "error" in line.lower() or "warning" in line.lower()):
                    log("Demucs: " + line[-1000:], "INFO")
            rc = proc.wait()
        finally:
            heartbeat_stop.set()
            if heartbeat_thread.is_alive():
                heartbeat_thread.join(timeout=1.0)
            with self.lock:
                if self.proc is proc:
                    self.proc = None
        if job_id in self.cancelled:
            raise InterruptedError("AI dialogue job cancelled")
        if rc != 0:
            raise RuntimeError(f"Demucs exited with code {rc}")

        candidates = list(output_root.rglob("vocals.flac"))
        if not candidates:
            raise RuntimeError("Demucs completed but vocals.flac was not created")
        result = max(candidates, key=lambda p: p.stat().st_mtime)
        if log:
            log(
                f"AI dialogue job {job_id[:8]} separation complete on {device}: "
                f"stem={result.stat().st_size / 1024 / 1024:.1f}MB elapsed={_fmt_clock(time.time() - started)}",
                "INFO",
            )
        return result

    def run(
        self,
        job_id: str,
        source: Path,
        output_root: Path,
        model: str,
        segment: int,
        allow_cpu_fallback: bool,
        before_gpu: Callable[[], None],
        after_gpu: Callable[[], None],
        log: Callable[[str, str], None] | None = None,
    ) -> tuple[Path, str]:
        if not self.available():
            raise RuntimeError("Demucs is not installed in this GPU worker")
        name = str(model or DEFAULT_MODEL).strip().lower()
        if name not in SUPPORTED_MODELS:
            name = DEFAULT_MODEL
        seg = max(2, min(8, int(segment or 4)))
        with self.lock:
            if self.current_job is not None:
                raise RuntimeError(f"GPU worker is busy with job {self.current_job.get('job_id')}")
            self.cancelled.discard(job_id)
            self.current_job = {
                "job_id": job_id,
                "kind": "dialogue-ai",
                "stage": "freeing-gpu",
                "model": name,
                "device": "cuda",
                "started": time.time(),
                "progress": 0.0,
                "audio_bytes": source.stat().st_size,
            }

        try:
            # Release CTranslate2/Whisper VRAM before loading PyTorch/Demucs. This is
            # essential for small cards such as the GTX 1060 3 GB.
            if log:
                log(f"AI dialogue job {job_id[:8]}: releasing Whisper/CTranslate2 GPU memory", "INFO")
            before_gpu()
            if log:
                log(f"AI dialogue job {job_id[:8]}: GPU memory released; launching Demucs", "INFO")
            try:
                path = self._run_demucs(job_id, source, output_root, name, seg, "cuda", log)
                device = "cuda"
            except InterruptedError:
                raise
            except Exception as gpu_exc:
                if not allow_cpu_fallback:
                    raise
                if log:
                    log(f"AI dialogue CUDA attempt failed ({gpu_exc}); retrying on CPU", "WARNING")
                # Remove partial model output before retrying.
                for candidate in output_root.rglob("vocals.flac"):
                    try:
                        candidate.unlink()
                    except OSError:
                        pass
                path = self._run_demucs(job_id, source, output_root, name, max(seg, 6), "cpu", log)
                device = "cpu"
            with self.lock:
                if self.current_job and self.current_job.get("job_id") == job_id:
                    self.current_job.update({"stage": "finishing", "progress": 100.0, "device": device})
            if log:
                log(f"AI dialogue job {job_id[:8]}: separation phase finished; preparing stem response", "INFO")
            return path, device
        finally:
            try:
                if log:
                    log(f"AI dialogue job {job_id[:8]}: restarting Whisper ASR engine", "INFO")
                after_gpu()
                if log:
                    log(f"AI dialogue job {job_id[:8]}: Whisper ASR engine ready again", "INFO")
            finally:
                with self.lock:
                    self.current_job = None
                    self.proc = None
                    self.cancelled.discard(job_id)


manager = DialogueAIManager()
