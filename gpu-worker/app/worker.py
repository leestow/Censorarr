from __future__ import annotations

import asyncio
import base64
import multiprocessing as mp
import os
import queue
import tempfile
import threading
import time
import traceback
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import ctranslate2
from fastapi import FastAPI, HTTPException, Query, Request

VERSION = '1.6.4'
MODEL_DIR = Path(os.environ.get('ASR_MODEL_DIR', '/models'))
DEFAULT_MODEL = os.environ.get('ASR_MODEL', 'small.en')
DEFAULT_COMPUTE = os.environ.get('ASR_COMPUTE_TYPE', 'int8_float32')
TOKEN = os.environ.get('ASR_WORKER_TOKEN', '')
MAX_UPLOAD_GB = float(os.environ.get('ASR_MAX_UPLOAD_GB', '2'))
LOG_LINES = max(250, int(os.environ.get('ASR_LOG_LINES', '4000')))

_log = deque(maxlen=LOG_LINES)
_log_lock = threading.RLock()


def log_line(message: str, level: str = 'INFO') -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {level} {message}"
    with _log_lock:
        _log.append(line)
    print(line, flush=True)


def _engine_log(event_q, message: str, level: str = 'INFO') -> None:
    try:
        event_q.put({'type': 'log', 'level': level, 'message': message})
    except Exception:
        pass


def _fmt_clock(seconds: float | int | None) -> str:
    try:
        total = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        total = 0
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    return f'{h:02d}:{m:02d}:{sec:02d}'



def _transcribe_chunked(asr, audio_path: str, event_q, job_id: str, **kwargs):
    import gc
    import wave
    from types import SimpleNamespace

    chunk_seconds = float(os.environ.get("ASR_CHUNK_SECONDS", "600"))
    overlap_seconds = float(os.environ.get("ASR_CHUNK_OVERLAP_SECONDS", "2"))

    chunk_seconds = max(60.0, chunk_seconds)
    overlap_seconds = max(0.0, min(10.0, overlap_seconds))

    try:
        with wave.open(audio_path, "rb") as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            total_frames = wf.getnframes()
            compression = wf.getcomptype()
    except Exception:
        return asr.transcribe(audio_path, **kwargs)

    if compression != "NONE" or rate <= 0:
        return asr.transcribe(audio_path, **kwargs)

    duration = total_frames / float(rate)
    chunk_frames = max(1, int(chunk_seconds * rate))
    overlap_frames = max(0, int(overlap_seconds * rate))

    # Leave short clips/rescue passes exactly as they were.
    if total_frames <= chunk_frames:
        return asr.transcribe(audio_path, **kwargs)

    step_frames = max(1, chunk_frames - overlap_frames)

    chunk_count = 1 + (
        (total_frames - chunk_frames + step_frames - 1)
        // step_frames
    )

    info = SimpleNamespace(
        duration=duration,
        language=kwargs.get("language") or "",
        language_probability=0.0,
    )

    _engine_log(
        event_q,
        f"Chunking PCM WAV for job {job_id[:8]}: "
        f"{_fmt_clock(duration)} into {chunk_count} chunk(s) "
        f"of up to {_fmt_clock(chunk_seconds)} "
        f"with {overlap_seconds:.1f}s overlap",
    )

    def segment_generator():
        with wave.open(audio_path, "rb") as wf:
            start_frame = 0
            chunk_index = 0

            while start_frame < total_frames:
                chunk_index += 1

                end_frame = min(
                    total_frames,
                    start_frame + chunk_frames,
                )

                frame_count = end_frame - start_frame
                chunk_start = start_frame / float(rate)
                chunk_end = end_frame / float(rate)

                wf.setpos(start_frame)
                raw = wf.readframes(frame_count)

                fd, chunk_path = tempfile.mkstemp(
                    prefix="censorarr-chunk-",
                    suffix=".wav",
                )
                os.close(fd)

                try:
                    with wave.open(chunk_path, "wb") as out:
                        out.setnchannels(channels)
                        out.setsampwidth(width)
                        out.setframerate(rate)
                        out.writeframes(raw)

                    _engine_log(
                        event_q,
                        f"GPU job {job_id[:8]} chunk "
                        f"{chunk_index}/{chunk_count}: "
                        f"{_fmt_clock(chunk_start)}-"
                        f"{_fmt_clock(chunk_end)}",
                    )

                    chunk_segs, chunk_info = asr.transcribe(
                        chunk_path,
                        **kwargs,
                    )

                    if chunk_index == 1:
                        info.language = (
                            getattr(chunk_info, "language", None)
                            or info.language
                        )
                        info.language_probability = float(
                            getattr(
                                chunk_info,
                                "language_probability",
                                0,
                            ) or 0
                        )

                    # Give half of the overlap to each adjacent chunk.
                    left_owner = chunk_start
                    right_owner = chunk_end

                    if chunk_index > 1:
                        left_owner += overlap_seconds / 2.0

                    if end_frame < total_frames:
                        right_owner -= overlap_seconds / 2.0

                    for seg in chunk_segs:
                        adjusted_words = []

                        for w in (seg.words or []):
                            abs_start = (
                                chunk_start + float(w.start)
                            )
                            abs_end = (
                                chunk_start + float(w.end)
                            )

                            midpoint = (
                                abs_start + abs_end
                            ) / 2.0

                            if midpoint < left_owner:
                                continue

                            if midpoint >= right_owner:
                                continue

                            adjusted_words.append(
                                SimpleNamespace(
                                    start=abs_start,
                                    end=abs_end,
                                    word=w.word,
                                    probability=w.probability,
                                )
                            )

                        yield SimpleNamespace(
                            start=chunk_start + float(
                                getattr(seg, "start", 0) or 0
                            ),
                            end=min(
                                duration,
                                chunk_start + float(
                                    getattr(seg, "end", 0) or 0
                                ),
                            ),
                            words=adjusted_words,
                        )

                finally:
                    try:
                        os.unlink(chunk_path)
                    except OSError:
                        pass

                del raw
                gc.collect()

                if end_frame >= total_frames:
                    break

                start_frame += step_frames

    return segment_generator(), info

def _engine_main(cmd_q, result_q, event_q, model_dir: str, default_compute: str) -> None:
    # CUDA and faster-whisper live only in this child process. If a transcription must be
    # cancelled, the API process can terminate this engine and immediately start a fresh one.
    from faster_whisper import WhisperModel

    models: dict[tuple[str, str], WhisperModel] = {}
    model_root = Path(model_dir)
    model_root.mkdir(parents=True, exist_ok=True)
    _engine_log(event_q, f'ASR engine started pid={os.getpid()}')
    while True:
        cmd = cmd_q.get()
        if not isinstance(cmd, dict):
            continue
        if cmd.get('op') == 'shutdown':
            _engine_log(event_q, 'ASR engine shutting down')
            return
        if cmd.get('op') != 'transcribe':
            continue

        job_id = str(cmd.get('job_id') or '')
        name = str(cmd.get('model') or DEFAULT_MODEL)
        compute = str(cmd.get('compute') or default_compute)
        audio_path = str(cmd.get('audio_path') or '')
        started = time.time()
        try:
            event_q.put({'type': 'status', 'job_id': job_id, 'stage': 'loading-model', 'model': name, 'started': started})
            key = (name, compute)
            if key not in models:
                _engine_log(event_q, f'Loading Whisper model {name} on cuda/{compute} for job {job_id[:8]}')
                models[key] = WhisperModel(name, device='cuda', compute_type=compute, download_root=str(model_root))
                event_q.put({'type': 'model-loaded', 'model': name, 'compute': compute})
                _engine_log(event_q, f'Loaded Whisper model {name} on cuda/{compute}')
            asr = models[key]
            event_q.put({'type': 'status', 'job_id': job_id, 'stage': 'transcribing', 'model': name, 'started': started})
            segs, info = _transcribe_chunked(
                asr,
                audio_path,
                event_q,
                job_id,
                language=cmd.get('language') or None,
                word_timestamps=True,
                beam_size=int(cmd.get('beam_size', 5)),
                vad_filter=bool(cmd.get('vad_filter', False)),
                condition_on_previous_text=bool(cmd.get('condition_on_previous_text', False)),
                initial_prompt=cmd.get('prompt') or None,
            )
            duration = float(getattr(info, 'duration', 0) or 0)
            words: list[dict[str, Any]] = []
            segments_done = 0
            last_status_at = 0.0
            last_log_bucket = 0
            event_q.put({
                'type': 'status', 'job_id': job_id, 'stage': 'transcribing', 'model': name,
                'started': started, 'progress': 0.0, 'position_seconds': 0.0,
                'duration_seconds': duration, 'segments_done': 0, 'words_count': 0,
            })
            for seg in segs:
                segments_done += 1
                for w in (seg.words or []):
                    words.append({
                        'start': float(w.start),
                        'end': float(w.end),
                        'word': (w.word or '').strip(),
                        'probability': float(w.probability) if w.probability is not None else None,
                    })
                position = max(0.0, float(getattr(seg, 'end', 0) or 0))
                progress = min(99.9, max(0.0, 100.0 * position / duration)) if duration > 0 else None
                now = time.time()
                if now - last_status_at >= 1.0:
                    event_q.put({
                        'type': 'status', 'job_id': job_id, 'stage': 'transcribing', 'model': name,
                        'started': started, 'progress': round(progress, 1) if progress is not None else None,
                        'position_seconds': round(position, 3), 'duration_seconds': duration,
                        'segments_done': segments_done, 'words_count': len(words),
                    })
                    last_status_at = now
                if progress is not None:
                    bucket = min(95, int(progress // 5) * 5)
                    if bucket >= 5 and bucket > last_log_bucket:
                        last_log_bucket = bucket
                        _engine_log(
                            event_q,
                            f'GPU job {job_id[:8]}: {bucket}% — {_fmt_clock(position)} / {_fmt_clock(duration)} '
                            f'· elapsed {_fmt_clock(now - started)} · words={len(words)}',
                        )
            event_q.put({
                'type': 'status', 'job_id': job_id, 'stage': 'finishing', 'model': name,
                'started': started, 'progress': 100.0, 'position_seconds': duration,
                'duration_seconds': duration, 'segments_done': segments_done, 'words_count': len(words),
            })
            elapsed = round(time.time() - started, 3)
            result_q.put({
                'job_id': job_id,
                'ok': True,
                'data': {
                    'ok': True,
                    'version': VERSION,
                    'job_id': job_id,
                    'model': name,
                    'compute_type': compute,
                    'device': 'cuda',
                    'duration': float(getattr(info, 'duration', 0) or 0),
                    'language': getattr(info, 'language', cmd.get('language') or ''),
                    'language_probability': float(getattr(info, 'language_probability', 0) or 0),
                    'elapsed_seconds': elapsed,
                    'words': words,
                },
            })
            _engine_log(event_q, f'Completed job {job_id[:8]} model={name} elapsed={elapsed}s words={len(words)}')
        except BaseException as exc:
            result_q.put({'job_id': job_id, 'ok': False, 'error': f'{type(exc).__name__}: {exc}'})
            _engine_log(event_q, f'Job {job_id[:8]} failed: {type(exc).__name__}: {exc}', 'ERROR')
            _engine_log(event_q, traceback.format_exc(limit=8), 'DEBUG')
        finally:
            try:
                event_q.put({'type': 'status', 'job_id': job_id, 'stage': 'idle'})
            except Exception:
                pass


class EngineManager:
    def __init__(self) -> None:
        self.ctx = mp.get_context('spawn')
        self.cmd_q = self.ctx.Queue()
        self.result_q = self.ctx.Queue()
        self.event_q = self.ctx.Queue()
        self.proc: mp.Process | None = None
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.results: dict[str, dict] = {}
        self.cancelled_jobs: set[str] = set()
        self.current_job: dict[str, Any] | None = None
        self.loaded_models: set[str] = set()
        self.started = False
        self.result_thread: threading.Thread | None = None
        self.event_thread: threading.Thread | None = None

    def start(self) -> None:
        with self.lock:
            if not self.started:
                self.started = True
                self.result_thread = threading.Thread(target=self._result_pump, daemon=True, name='asr-result-pump')
                self.event_thread = threading.Thread(target=self._event_pump, daemon=True, name='asr-event-pump')
                self.result_thread.start(); self.event_thread.start()
            self._start_engine_locked()

    def _start_engine_locked(self) -> None:
        if self.proc and self.proc.is_alive():
            return
        self.proc = self.ctx.Process(
            target=_engine_main,
            args=(self.cmd_q, self.result_q, self.event_q, str(MODEL_DIR), DEFAULT_COMPUTE),
            daemon=True,
            name='censorarr-asr-engine',
        )
        self.proc.start()
        log_line(f'ASR engine process launched pid={self.proc.pid}')

    def shutdown(self) -> None:
        with self.lock:
            p = self.proc
            if not p:
                return
            if p.is_alive():
                try: self.cmd_q.put({'op': 'shutdown'})
                except Exception: pass
                p.join(timeout=3)
            if p.is_alive():
                p.terminate(); p.join(timeout=2)
            self.proc = None

    def _result_pump(self) -> None:
        while True:
            try:
                item = self.result_q.get()
            except Exception:
                time.sleep(.1); continue
            if not isinstance(item, dict):
                continue
            jid = str(item.get('job_id') or '')
            with self.cond:
                if jid in self.cancelled_jobs:
                    continue
                self.results[jid] = item
                self.cond.notify_all()

    def _event_pump(self) -> None:
        while True:
            try:
                ev = self.event_q.get()
            except Exception:
                time.sleep(.1); continue
            if not isinstance(ev, dict):
                continue
            typ = ev.get('type')
            if typ == 'log':
                log_line(str(ev.get('message', '')), str(ev.get('level', 'INFO')))
            elif typ == 'model-loaded':
                with self.lock:
                    self.loaded_models.add(f"{ev.get('model')}/{ev.get('compute')}")
            elif typ == 'status':
                jid = str(ev.get('job_id') or '')
                with self.lock:
                    if self.current_job and str(self.current_job.get('job_id')) == jid:
                        if ev.get('stage') == 'idle':
                            self.current_job['stage'] = 'finishing'
                        else:
                            self.current_job.update({
                                k: v for k, v in ev.items()
                                if k in {'stage', 'model', 'started', 'progress', 'position_seconds',
                                         'duration_seconds', 'segments_done', 'words_count'}
                            })

    def run(self, job_id: str, audio_path: Path, params: dict[str, Any]) -> dict:
        with self.cond:
            if self.current_job is not None:
                raise RuntimeError(f"GPU worker is busy with job {self.current_job.get('job_id')}")
            self._start_engine_locked()
            self.current_job = {
                'job_id': job_id, 'stage': 'queued', 'model': params.get('model'),
                'started': time.time(), 'audio_bytes': audio_path.stat().st_size,
                'progress': 0.0, 'position_seconds': 0.0, 'duration_seconds': None,
                'segments_done': 0, 'words_count': 0,
            }
            self.results.pop(job_id, None)
            self.cancelled_jobs.discard(job_id)
            self.cmd_q.put({'op': 'transcribe', 'job_id': job_id, 'audio_path': str(audio_path), 'compute': DEFAULT_COMPUTE, **params})
            while True:
                item = self.results.pop(job_id, None)
                if item is not None:
                    if self.current_job and self.current_job.get('job_id') == job_id:
                        self.current_job = None
                    if item.get('cancelled'):
                        self.cancelled_jobs.discard(job_id)
                        raise InterruptedError('Remote GPU job cancelled')
                    if not item.get('ok'):
                        raise RuntimeError(str(item.get('error') or 'ASR engine failed'))
                    data = dict(item.get('data') or {})
                    data['gpu'] = gpu_info()
                    return data
                p = self.proc
                if not p or not p.is_alive():
                    self.current_job = None
                    raise RuntimeError('ASR engine process exited unexpectedly')
                self.cond.wait(timeout=.5)

    def cancel(self, job_id: str) -> dict:
        with self.cond:
            cur = self.current_job
            if not cur or str(cur.get('job_id')) != job_id:
                return {'ok': False, 'cancelled': False, 'job_id': job_id, 'message': 'Job is not currently running'}
            log_line(f'Cancelling GPU job {job_id[:8]} by terminating ASR engine', 'WARNING')
            p = self.proc
            if p and p.is_alive():
                p.terminate(); p.join(timeout=3)
                if p.is_alive():
                    p.kill(); p.join(timeout=2)
            self.proc = None
            self.loaded_models.clear()  # GPU model memory was released with the engine.
            self.cancelled_jobs.add(job_id)
            self.results[job_id] = {'job_id': job_id, 'ok': False, 'cancelled': True}
            self.current_job = None
            self._start_engine_locked()
            self.cond.notify_all()
            return {'ok': True, 'cancelled': True, 'job_id': job_id, 'message': 'GPU job cancelled; ASR engine restarted'}

    def status(self) -> dict:
        with self.lock:
            p = self.proc
            cur = dict(self.current_job) if self.current_job else None
            if cur and cur.get('started'):
                cur['elapsed_seconds'] = round(time.time() - float(cur['started']), 1)
                try:
                    pct = float(cur.get('progress'))
                    if 0.1 <= pct < 100.0:
                        cur['eta_seconds'] = round(cur['elapsed_seconds'] * (100.0 - pct) / pct, 1)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
            return {
                'engine_alive': bool(p and p.is_alive()),
                'engine_pid': p.pid if p and p.is_alive() else None,
                'current_job': cur,
                'loaded_models': sorted(self.loaded_models),
            }


engine = EngineManager()


def gpu_info() -> dict:
    out = {'cuda_devices': 0, 'supported_compute_types': []}
    try: out['cuda_devices'] = int(ctranslate2.get_cuda_device_count())
    except Exception: pass
    if out['cuda_devices']:
        try: out['supported_compute_types'] = sorted(ctranslate2.get_supported_compute_types('cuda'))
        except Exception: pass
    return out


def auth(request: Request) -> None:
    if TOKEN and request.headers.get('X-Censorarr-Token', '') != TOKEN:
        raise HTTPException(401, 'Invalid worker token')


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.start()
    log_line(f'Censorarr GPU worker {VERSION} ready; default_model={DEFAULT_MODEL} compute={DEFAULT_COMPUTE}')
    yield
    engine.shutdown()


app = FastAPI(title='Censorarr GPU ASR Worker', version=VERSION, lifespan=lifespan)


@app.get('/health')
def health(request: Request):
    auth(request); g = gpu_info(); s = engine.status()
    return {
        'ok': bool(g['cuda_devices']), 'version': VERSION, 'device': 'cuda', 'default_model': DEFAULT_MODEL,
        'compute_type': DEFAULT_COMPUTE, 'loaded_models': s['loaded_models'], **g,
        'engine_alive': s['engine_alive'], 'engine_pid': s['engine_pid'],
    }


@app.get('/status')
def status(request: Request):
    auth(request); g = gpu_info(); s = engine.status()
    return {'ok': bool(g['cuda_devices']), 'version': VERSION, 'default_model': DEFAULT_MODEL,
            'compute_type': DEFAULT_COMPUTE, **g, **s}


@app.get('/logs')
def logs(request: Request, lines: int = Query(default=250, ge=10, le=5000)):
    auth(request)
    with _log_lock:
        data = list(_log)[-lines:]
    return {'ok': True, 'lines': data}


@app.post('/logs/clear')
def clear_logs(request: Request):
    auth(request)
    with _log_lock: _log.clear()
    log_line('GPU worker log cleared')
    return {'ok': True}


@app.delete('/jobs/{job_id}')
def cancel_job(job_id: str, request: Request):
    auth(request)
    return engine.cancel(job_id)


@app.post('/transcribe')
async def transcribe(
    request: Request,
    job_id: str = Query(default=''),
    model: str = Query(default=''),
    language: str = Query(default='en'),
    beam_size: int = Query(default=5, ge=1, le=10),
    vad_filter: int = Query(default=0),
    condition_on_previous_text: int = Query(default=0),
):
    auth(request)
    if not gpu_info()['cuda_devices']:
        raise HTTPException(503, 'No CUDA device visible to the worker')
    clen = request.headers.get('content-length')
    if clen and int(clen) > int(MAX_UPLOAD_GB * 1024**3):
        raise HTTPException(413, 'Audio upload exceeds ASR_MAX_UPLOAD_GB')
    prompt = ''
    if request.headers.get('X-Censorarr-Prompt-B64'):
        try: prompt = base64.b64decode(request.headers['X-Censorarr-Prompt-B64']).decode('utf-8')
        except Exception: raise HTTPException(400, 'Invalid prompt header')
    name = (model or DEFAULT_MODEL).strip()
    jid = (job_id or request.headers.get('X-Censorarr-Job-ID') or uuid.uuid4().hex).strip()
    total = 0
    fd, tmp = tempfile.mkstemp(prefix='censorarr-asr-', suffix='.wav'); os.close(fd); p = Path(tmp)
    try:
        with p.open('wb') as f:
            async for chunk in request.stream():
                total += len(chunk)
                if total > int(MAX_UPLOAD_GB * 1024**3):
                    raise HTTPException(413, 'Audio upload too large')
                f.write(chunk)
        log_line(f'Received job {jid[:8]} model={name} bytes={total}')
        params = {
            'model': name, 'language': language or None, 'beam_size': beam_size,
            'vad_filter': bool(vad_filter), 'condition_on_previous_text': bool(condition_on_previous_text),
            'prompt': prompt or None,
        }
        try:
            return await asyncio.to_thread(engine.run, jid, p, params)
        except InterruptedError:
            raise HTTPException(499, 'GPU transcription cancelled')
        except RuntimeError as exc:
            if 'busy with job' in str(exc):
                raise HTTPException(409, str(exc))
            raise HTTPException(500, str(exc))
    finally:
        try: p.unlink()
        except OSError: pass
