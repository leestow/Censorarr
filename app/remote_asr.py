from __future__ import annotations

import base64
import http.client
import json
import logging
import os
import secrets_store as secret_store
import ssl
import threading
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Callable

ACTIVE_JOB_FILE = Path('/config/remote_asr_active.json')


class RemoteASRError(RuntimeError):
    pass


class RemoteASRCancelled(RemoteASRError):
    pass


def config(cfg: dict) -> dict:
    return (cfg.get('whisper', {}) or {}).get('remote', {}) or {}


def enabled(cfg: dict) -> bool:
    # The backend selector is the source of truth. Older 1.3.0 configs also contained
    # remote.enabled, which could disagree with the GUI and silently force local CPU.
    rcfg = config(cfg)
    mode = str((cfg.get('whisper', {}) or {}).get('backend', 'local')).lower().strip()
    return mode in {'remote', 'auto'} and bool(str(rcfg.get('url', '') or '').strip())


def _token(cfg: dict) -> str:
    return secret_store.get('asr_worker_token', env='ASR_WORKER_TOKEN', legacy=config(cfg).get('token', ''))


def _connection(url: str, timeout: float):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in {'http', 'https'} or not u.hostname:
        raise RemoteASRError(f'Invalid remote ASR URL: {url!r}')
    port = u.port or (443 if u.scheme == 'https' else 80)
    if u.scheme == 'https':
        return http.client.HTTPSConnection(u.hostname, port, timeout=timeout, context=ssl.create_default_context()), u
    return http.client.HTTPConnection(u.hostname, port, timeout=timeout), u


def _headers(cfg: dict) -> dict[str, str]:
    headers = {'Accept': 'application/json'}
    tok = _token(cfg)
    if tok:
        headers['X-Censorarr-Token'] = tok
    return headers


def _json_request(cfg: dict, method: str, endpoint: str, timeout: float = 8.0, body: bytes | None = None) -> dict:
    rcfg = config(cfg); base = str(rcfg.get('url', '')).rstrip('/')
    if not base:
        raise RemoteASRError('Remote ASR URL is blank')
    conn, u = _connection(base, timeout)
    prefix = u.path.rstrip('/') if u.path else ''
    path = prefix + endpoint
    headers = _headers(cfg)
    if body is not None:
        headers['Content-Type'] = 'application/json'; headers['Content-Length'] = str(len(body))
    try:
        conn.request(method, path or '/', body=body, headers=headers)
        r = conn.getresponse(); raw = r.read()
        if r.status >= 300:
            msg = raw.decode(errors='replace')[-1000:]
            raise RemoteASRError(f'Worker {method} {endpoint} returned HTTP {r.status}: {msg}')
        return json.loads(raw.decode('utf-8')) if raw else {'ok': True}
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as e:
        if isinstance(e, RemoteASRError): raise
        raise RemoteASRError(str(e)) from e
    finally:
        conn.close()


def health(cfg: dict, timeout: float = 8.0) -> dict:
    return _json_request(cfg, 'GET', '/health', timeout=timeout)


def status(cfg: dict, timeout: float = 3.0) -> dict:
    return _json_request(cfg, 'GET', '/status', timeout=timeout)


def logs(cfg: dict, lines: int = 250, timeout: float = 3.0) -> dict:
    n = max(10, min(5000, int(lines)))
    return _json_request(cfg, 'GET', f'/logs?lines={n}', timeout=timeout)


def clear_logs(cfg: dict, timeout: float = 3.0) -> dict:
    return _json_request(cfg, 'POST', '/logs/clear', timeout=timeout, body=b'{}')


def _write_active(data: dict) -> None:
    try:
        ACTIVE_JOB_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = ACTIVE_JOB_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
        os.replace(tmp, ACTIVE_JOB_FILE)
    except OSError:
        pass


def active_job() -> dict:
    try:
        return json.loads(ACTIVE_JOB_FILE.read_text(encoding='utf-8')) if ACTIVE_JOB_FILE.exists() else {}
    except Exception:
        return {}


def _clear_active(job_id: str | None = None) -> None:
    try:
        if not ACTIVE_JOB_FILE.exists(): return
        if job_id:
            data = active_job()
            if str(data.get('job_id') or '') != str(job_id): return
        ACTIVE_JOB_FILE.unlink()
    except OSError:
        pass


def cancel_job(cfg: dict, job_id: str, timeout: float = 4.0) -> dict:
    jid = str(job_id or '').strip()
    if not jid:
        return {'ok': False, 'cancelled': False, 'message': 'No remote GPU job id is active'}
    try:
        return _json_request(cfg, 'DELETE', '/jobs/' + urllib.parse.quote(jid, safe=''), timeout=timeout)
    finally:
        _clear_active(jid)


def cancel_active(cfg: dict, timeout: float = 4.0) -> dict:
    data = active_job(); jid = str(data.get('job_id') or '')
    if not jid:
        return {'ok': True, 'cancelled': False, 'message': 'No remote GPU job is active'}
    return cancel_job(cfg, jid, timeout=timeout)


def transcribe(audio: Path, cfg: dict, prompt: str | None = None,
               progress_callback: Callable[[dict], None] | None = None) -> tuple[list[dict], dict]:
    rcfg = config(cfg); wcfg = cfg.get('whisper', {}) or {}
    base = str(rcfg.get('url', '')).rstrip('/')
    if not base:
        raise RemoteASRError('Remote ASR URL is blank')
    timeout = float(rcfg.get('timeout_seconds', 1800))
    model = str(rcfg.get('model') or wcfg.get('model') or 'small.en')
    job_id = uuid.uuid4().hex
    params = {
        'job_id': job_id,
        'model': model,
        'language': str(wcfg.get('language', 'en')),
        'beam_size': str(int(wcfg.get('beam_size', 5))),
        'vad_filter': '1' if bool(wcfg.get('vad_filter', False)) else '0',
        'condition_on_previous_text': '1' if bool(wcfg.get('condition_on_previous_text', False)) else '0',
    }
    conn, u = _connection(base, timeout)
    prefix = u.path.rstrip('/') if u.path else ''
    path = prefix + '/transcribe?' + urllib.parse.urlencode(params)
    size = audio.stat().st_size
    headers = {
        'Content-Type': 'audio/wav', 'Content-Length': str(size), 'Accept': 'application/json',
        'X-Censorarr-Client': 'Censorarr', 'X-Censorarr-Job-ID': job_id,
    }
    tok = _token(cfg)
    if tok:
        headers['X-Censorarr-Token'] = tok
    if prompt:
        headers['X-Censorarr-Prompt-B64'] = base64.b64encode(prompt.encode('utf-8')).decode('ascii')
    started = time.time()
    stop_progress = threading.Event()
    progress_thread: threading.Thread | None = None
    _write_active({'job_id': job_id, 'started': started, 'model': model, 'audio': str(audio), 'worker_url': base})

    def poll_progress() -> None:
        while not stop_progress.wait(1.0):
            try:
                payload = status(cfg, timeout=2.5)
                cur = payload.get('current_job') if isinstance(payload, dict) else None
                if not isinstance(cur, dict) or str(cur.get('job_id') or '') != job_id:
                    continue
                if progress_callback is not None:
                    try:
                        progress_callback(dict(cur))
                    except Exception:
                        logging.debug('Remote GPU progress callback failed', exc_info=True)
            except Exception:
                # Progress reporting is best-effort and must never fail the transcription itself.
                continue

    try:
        conn.putrequest('POST', path)
        for k, v in headers.items(): conn.putheader(k, v)
        conn.endheaders()
        with audio.open('rb') as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk: break
                conn.send(chunk)
        if progress_callback is not None:
            progress_thread = threading.Thread(target=poll_progress, daemon=True, name=f'remote-asr-progress-{job_id[:8]}')
            progress_thread.start()
        r = conn.getresponse(); raw = r.read()
        if r.status == 499:
            raise RemoteASRCancelled('Remote GPU transcription was cancelled')
        if r.status >= 300:
            msg = raw.decode('utf-8', errors='replace')[-1500:]
            raise RemoteASRError(f'Remote ASR HTTP {r.status}: {msg}')
        data = json.loads(raw.decode('utf-8'))
        words = data.get('words')
        if not isinstance(words, list):
            raise RemoteASRError('Remote ASR response did not contain a word list')
        meta = {k: data.get(k) for k in ('job_id','duration','language','language_probability','model','compute_type','device','elapsed_seconds','gpu')}
        meta['round_trip_seconds'] = round(time.time() - started, 3)
        return words, meta
    except RemoteASRCancelled:
        raise
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as e:
        raise RemoteASRError(str(e)) from e
    finally:
        stop_progress.set()
        if progress_thread is not None and progress_thread.is_alive():
            progress_thread.join(timeout=1.5)
        _clear_active(job_id)
        conn.close()
