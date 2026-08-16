from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import subprocess
import threading
import time
import uuid
import zlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

import integrations as integ
import censorarr as pc
import subtitle_assist as subassist
import remote_asr
import secrets_store as secret_store

VERSION = "1.6.3"
CONFIG = Path(os.environ.get("CENSORARR_CONFIG", "/config/config.yaml"))
LOG = Path("/config/censorarr.log")
HEARTBEAT = Path("/config/heartbeat.json")
STATE = Path("/config/state.json")
QUEUE = Path("/config/manual_queue.json")
CANCELLED = Path("/config/cancelled.json")
PAUSED = Path("/config/paused.flag")
SCAN_NOW = Path("/config/scan-now.flag")
RESTART_AFTER_CURRENT = Path("/config/restart-after-current.flag")
SUBTITLE_WAIT = Path("/config/subtitle_wait.json")
INVENTORY = Path("/config/inventory.json")
CUSTOM_PROFANITY = Path("/config/custom_profanity.json")
PROFANITY_OVERRIDES = Path("/config/profanity_overrides.json")
USER_EXCEPTIONS = Path("/config/user_exceptions.json")
STATIC = Path("/app/static")
FIRST_RUN = Path("/config/.censorarr-first-run")

_MEDIA_HISTORY_CACHE: dict[str, Any] = {"key": None, "items": {}}

security = HTTPBasic(auto_error=False)


def auth(credentials: HTTPBasicCredentials | None = Depends(security)):
    password = os.environ.get("WEB_PASSWORD", "")
    username = os.environ.get("WEB_USERNAME", "admin")
    if not password:
        return True
    ok = credentials is not None and secrets.compare_digest(credentials.username, username) and secrets.compare_digest(credentials.password, password)
    if not ok:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": 'Basic realm="Censorarr"'})
    return True


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _allowed_media_mounts() -> list[Path]:
    # Container-level security boundary. GUI browsing/processing may use Movies and TV, but never
    # arbitrary host paths such as /config, /work, or the container filesystem.
    roots: list[Path] = []
    for raw in ("/media", "/tv"):
        p = Path(raw)
        if p.exists():
            try: roots.append(p.resolve())
            except Exception: roots.append(p)
    return roots or [Path("/media")]


def safe_media_path(raw: str, must_exist: bool = True) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = Path("/media") / p
    try:
        resolved = p.resolve(strict=must_exist)
    except FileNotFoundError:
        raise HTTPException(404, "Path does not exist")
    roots = _allowed_media_mounts()
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise HTTPException(403, "Only paths inside the configured media mounts are allowed")
    return resolved


def report_json_path(report: str | None) -> Path | None:
    if not report:
        return None
    p = Path(report)
    if p.suffix.lower() == ".txt":
        p = p.with_suffix(".json")
    return p


def state_row_for(path: Path) -> dict:
    state = read_json(STATE, {"files": {}})
    return state.get("files", {}).get(str(path), {}) or {}


def queue_process(path: Path, *, mode: str = "process", report: str | None = None,
                  excluded_indices: list[int] | None = None) -> dict:
    q = read_json(QUEUE, [])
    if not isinstance(q, list): q = []
    job = {"id": uuid.uuid4().hex, "path": str(path), "requested_at": time.time(), "mode": mode}
    if report: job["report"] = report
    if excluded_indices is not None: job["excluded_indices"] = [int(x) for x in excluded_indices]
    # Don't stack identical processing jobs.
    if not any(x.get("path") == str(path) and x.get("mode", "process") == mode for x in q):
        q.append(job); write_json(QUEUE, q)
    c = read_json(CANCELLED, {})
    if str(path) in c:
        c.pop(str(path), None); write_json(CANCELLED, c)
    return job


def reset_one(path: Path) -> None:
    cfg = pc.load_config(CONFIG)
    mp = pc.marker_path(path, cfg)
    if mp.exists():
        data = read_json(mp, {})
        files = data.get("files", {})
        files.pop(path.name, None)
        if files:
            data["files"] = files; write_json(mp, data)
        else:
            try: mp.unlink()
            except OSError: pass
    state = read_json(STATE, {"files": {}}); state.setdefault("files", {}).pop(str(path), None); write_json(STATE, state)
    c = read_json(CANCELLED, {}); c.pop(str(path), None); write_json(CANCELLED, c)
    w = read_json(SUBTITLE_WAIT, {}); w.pop(str(path), None); write_json(SUBTITLE_WAIT, w)


class WorkerSupervisor:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.lock = threading.RLock()
        self.stopping = False
        self.monitor_thread: threading.Thread | None = None

    def start(self):
        with self.lock:
            if self.proc and self.proc.poll() is None: return
            env = os.environ.copy(); env.pop("DRY_RUN", None)
            self.proc = subprocess.Popen(["python", "/app/censorarr.py"], env=env)
        if not self.monitor_thread or not self.monitor_thread.is_alive():
            self.monitor_thread = threading.Thread(target=self._monitor, daemon=True, name="worker-supervisor")
            self.monitor_thread.start()

    def _monitor(self):
        while not self.stopping:
            time.sleep(1)
            hb = read_json(HEARTBEAT, {})
            if RESTART_AFTER_CURRENT.exists() and hb.get("status") in {"idle", "paused", "scanning", "starting", "blocked", "waiting-subtitle", "setup-required"}:
                try: RESTART_AFTER_CURRENT.unlink()
                except OSError: pass
                self.restart(); continue
            with self.lock:
                dead = self.proc is None or self.proc.poll() is not None
            if dead and not self.stopping:
                time.sleep(1); self.start()

    def stop_process(self, graceful_seconds: float = 2.0):
        with self.lock: proc = self.proc
        if not proc or proc.poll() is not None: return
        proc.terminate()
        try: proc.wait(timeout=graceful_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            try: proc.wait(timeout=2)
            except Exception: pass

    def restart(self):
        self.stop_process()
        if not self.stopping: self.start()

    def stop_current(self) -> dict:
        hb = read_json(HEARTBEAT, {}); current = hb.get("current")
        remote_cancel = None
        # Cancel the GPU-side child process before killing the local Censorarr worker. This
        # immediately releases GPU/CPU/RAM instead of leaving an abandoned ASR request running.
        try:
            cfg = pc.load_config(CONFIG)
            if remote_asr.enabled(cfg):
                remote_cancel = remote_asr.cancel_active(cfg, timeout=4.0)
        except Exception as e:
            remote_cancel = {"ok": False, "cancelled": False, "error": str(e)}
        self.stop_process(graceful_seconds=0.75)
        if current:
            p = Path(current)
            temp_out = p.with_name(p.name + ".censorarr.tmp" + p.suffix)
            try:
                if temp_out.exists(): temp_out.unlink()
            except OSError: pass
            if p.exists():
                data = read_json(CANCELLED, {})
                try:
                    data[str(p)] = {"fingerprint": pc.fingerprint(p), "cancelled_at": time.time()}; write_json(CANCELLED, data)
                except OSError: pass
            state = read_json(STATE, {"files": {}}); state.setdefault("files", {}).setdefault(str(p), {})
            state["files"][str(p)].update({"status": "cancelled", "time": time.time()}); write_json(STATE, state)
        self.start(); return {"ok": True, "cancelled": current, "remote_gpu": remote_cancel}

    def shutdown(self):
        self.stopping = True; self.stop_process(graceful_seconds=2.0)


supervisor = WorkerSupervisor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    CONFIG.parent.mkdir(parents=True, exist_ok=True); pc.ensure_config(CONFIG); supervisor.start()
    yield
    supervisor.shutdown()


app = FastAPI(title="Censorarr", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/", response_class=HTMLResponse)
def index(_: bool = Depends(auth)):
    return FileResponse(STATIC / "index.html")


@app.get("/assets/{name}")
def static_asset(name: str):
    # Branding assets only; keep arbitrary filesystem paths inaccessible.
    if Path(name).name != name or not name.lower().endswith((".png", ".webp", ".svg", ".ico")):
        raise HTTPException(404, "Asset not found")
    p = STATIC / "assets" / name
    if not p.is_file():
        raise HTTPException(404, "Asset not found")
    return FileResponse(p)


@app.get("/api/health")
def health():
    return {"ok": True, "version": VERSION, "worker_alive": bool(supervisor.proc and supervisor.proc.poll() is None)}


@app.get("/api/status")
def status(_: bool = Depends(auth)):
    cfg = pc.load_config(CONFIG); hb = read_json(HEARTBEAT, {}); state = read_json(STATE, {"files": {}})
    q = read_json(QUEUE, []); waits = read_json(SUBTITLE_WAIT, {}); inv = read_json(INVENTORY, {})
    # Dashboard counts must describe the CURRENT library, not every historical row ever
    # left in state.json.  Media pages already reconcile state with durable completion
    # markers and current file fingerprints; use the same canonical view here so a
    # replaced/deleted movie cannot remain counted as CLEAN forever.
    current_files = _current_media_history(cfg, state.get("files", {}))
    counts: dict[str, int] = {}
    counts_by_type: dict[str, dict[str, int]] = {"movie": {}, "episode": {}}
    durations = []
    for media_path, rec in current_files.items():
        st = _normalize_media_status(rec.get("status", "unknown")); counts[st] = counts.get(st, 0) + 1
        try:
            media_kind = pc.media_type_for(Path(media_path), cfg)
        except Exception:
            media_kind = "movie"
        bucket = counts_by_type.setdefault(media_kind, {})
        bucket[st] = bucket.get(st, 0) + 1
        if st in {"applied", "no-detections"} and rec.get("processing_seconds"):
            durations.append(float(rec["processing_seconds"]))
    avg = sum(durations[-20:]) / len(durations[-20:]) if durations else None
    library_total = int(inv.get("total", 0) or 0)
    # Approximate the whole-library backlog, not just the explicit manual queue. State has one row per movie
    # once Censorarr has touched it; anything not terminal is still work/attention outstanding.
    terminal_statuses = {"applied", "no-detections", "clean-exists", "skipped-rating", "review-skipped"}
    terminal_count = sum(1 for rec in current_files.values() if _normalize_media_status(rec.get("status")) in terminal_statuses)
    unfinished_library = max(0, library_total - terminal_count) if library_total else 0
    explicit_backlog = (len(q) if isinstance(q, list) else 0) + len(waits if isinstance(waits, dict) else {}) + counts.get("waiting-rating", 0)
    backlog = max(unfinished_library, explicit_backlog)
    schedule_ok, schedule_reason = integ.schedule_allows_now(cfg)
    return {
        "version": VERSION, "worker_alive": bool(supervisor.proc and supervisor.proc.poll() is None),
        "worker_pid": supervisor.proc.pid if supervisor.proc and supervisor.proc.poll() is None else None,
        "paused": PAUSED.exists(), "dry_run": bool(cfg.get("dry_run", True)), "heartbeat": hb,
        "counts": counts, "counts_by_type": counts_by_type, "history_total": len(current_files), "library_total": library_total,
        "inventory": {"movies": int(inv.get("movies",0) or 0), "episodes": int(inv.get("episodes",0) or 0), "total": library_total},
        "estimated_pending_movies": backlog, "estimated_pending_items": backlog,
        "queue_count": len(q) if isinstance(q, list) else 0, "subtitle_wait_count": len(waits) if isinstance(waits, dict) else 0,
        "media_roots": pc.all_media_roots(cfg), "minimum_rating": cfg.get("rating_filter", {}).get("minimum", "PG-13"),
        "tv_enabled": bool(cfg.get("tv",{}).get("enabled",False)), "tv_minimum_rating": cfg.get("tv",{}).get("rating_filter",{}).get("minimum","TV-14"),
        "average_processing_seconds": avg, "estimated_backlog_seconds": avg * backlog if avg is not None else None,
        "schedule_ok": schedule_ok, "schedule_reason": schedule_reason,
        "system": integ.system_stats(str((cfg.get("media_roots") or ["/media"])[0])),
        "secrets": {k: v["set"] for k,v in secret_store.statuses(_secret_spec(cfg)).items()},
    }


@app.post("/api/control/pause")
def pause(_: bool = Depends(auth)):
    PAUSED.write_text(str(time.time()), encoding="utf-8"); return {"ok": True, "message": "Automatic processing will pause after the current movie."}


@app.post("/api/control/resume")
def resume(_: bool = Depends(auth)):
    try: PAUSED.unlink()
    except OSError: pass
    SCAN_NOW.touch(); return {"ok": True}


@app.post("/api/control/scan-now")
def scan_now(_: bool = Depends(auth)):
    SCAN_NOW.touch(); return {"ok": True}


@app.post("/api/control/stop-current")
def stop_current(_: bool = Depends(auth)):
    return supervisor.stop_current()


@app.get("/api/log/tail")
def log_tail(lines: int = Query(250, ge=10, le=5000), _: bool = Depends(auth)):
    if not LOG.exists(): return {"lines": []}
    data = LOG.read_text(encoding="utf-8", errors="replace").splitlines(); return {"lines": data[-lines:]}


@app.get("/api/log/download")
def log_download(_: bool = Depends(auth)):
    if not LOG.exists(): raise HTTPException(404, "Log not found")
    return FileResponse(LOG, filename="censorarr.log", media_type="text/plain")


@app.post("/api/log/clear")
def log_clear(_: bool = Depends(auth)):
    LOG.write_text("", encoding="utf-8"); return {"ok": True}


@app.get("/api/log/stream")
async def log_stream(request: Request, _: bool = Depends(auth)):
    async def events():
        pos = LOG.stat().st_size if LOG.exists() else 0
        while True:
            if await request.is_disconnected(): break
            if LOG.exists():
                size = LOG.stat().st_size
                if size < pos: pos = 0
                if size > pos:
                    with LOG.open("r", encoding="utf-8", errors="replace") as f:
                        f.seek(pos); chunk = f.read(); pos = f.tell()
                    for line in chunk.splitlines(): yield "data: " + json.dumps(line) + "\n\n"
            yield ": keepalive\n\n"; await asyncio.sleep(1)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/history")
def history(limit: int = Query(500, ge=1, le=5000), q: str = "", status_filter: str = "", _: bool = Depends(auth)):
    state = read_json(STATE, {"files": {}}); rows = [{"path": k, **v} for k, v in state.get("files", {}).items()]
    if q: rows = [x for x in rows if q.lower() in x["path"].lower()]
    if status_filter: rows = [x for x in rows if str(x.get("status")) == status_filter]
    rows.sort(key=lambda r: float(r.get("time", 0)), reverse=True); return {"items": rows[:limit]}


@app.get("/api/failures")
def failures(_: bool = Depends(auth)):
    state = read_json(STATE, {"files": {}}); rows = [{"path": k, **v} for k, v in state.get("files", {}).items() if v.get("status") in {"error", "cancelled"}]
    rows.sort(key=lambda r: float(r.get("time", 0)), reverse=True); return {"items": rows}


@app.get("/api/reviews")
def reviews(_: bool = Depends(auth)):
    state = read_json(STATE, {"files": {}}); rows = [{"path": k, **v} for k, v in state.get("files", {}).items() if v.get("status") == "awaiting-review"]
    rows.sort(key=lambda r: float(r.get("time", 0)), reverse=True); return {"items": rows}


@app.get("/api/queue")
def queue(_: bool = Depends(auth)):
    q = read_json(QUEUE, []); waits = read_json(SUBTITLE_WAIT, {})
    waiting_items = [{"id": "subtitle:" + str(abs(hash(k))), "path": k, "mode": "waiting-subtitle", **v} for k, v in (waits.items() if isinstance(waits, dict) else [])]
    return {"items": (q if isinstance(q, list) else []) + waiting_items}


@app.post("/api/process")
async def process_movie(request: Request, _: bool = Depends(auth)):
    body = await request.json(); p = safe_media_path(str(body.get("path", "")))
    if not p.is_file() or p.suffix.lower() not in {".mkv", ".mp4", ".m4v"}: raise HTTPException(400, "Choose an MKV, MP4, or M4V media file")
    job = queue_process(p); return {"ok": True, "path": str(p), "job": job}


@app.delete("/api/queue/{job_id}")
def remove_queue(job_id: str, _: bool = Depends(auth)):
    if job_id.startswith("subtitle:"):
        return {"ok": False, "message": "Subtitle waits are automatic. Reprocess the item manually to bypass the wait."}
    q = read_json(QUEUE, [])
    if isinstance(q, list): write_json(QUEUE, [x for x in q if str(x.get("id")) != job_id])
    return {"ok": True}


@app.get("/api/browse")
def browse(path: str = "/media", _: bool = Depends(auth)):
    p = safe_media_path(path)
    if not p.is_dir(): raise HTTPException(400, "Not a directory")
    items = []
    try: children = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except OSError as e: raise HTTPException(403, str(e))
    for x in children[:1500]:
        if x.name.startswith("."): continue
        if x.is_dir(): items.append({"name": x.name, "path": str(x), "type": "dir"})
        elif x.suffix.lower() in {".mkv", ".mp4", ".m4v"}: items.append({"name": x.name, "path": str(x), "type": "file", "size": x.stat().st_size})
    roots = _allowed_media_mounts(); containing = next((r for r in roots if p == r or r in p.parents), None)
    parent = str(p.parent) if containing is not None and p != containing else None
    return {"path": str(p), "parent": parent, "items": items, "roots": [str(r) for r in roots]}


@app.post("/api/reset-movie")
async def reset_movie(request: Request, _: bool = Depends(auth)):
    body = await request.json(); p = safe_media_path(str(body.get("path", ""))); reset_one(p); return {"ok": True}


@app.post("/api/bulk")
async def bulk(request: Request, _: bool = Depends(auth)):
    body = await request.json(); action = str(body.get("action", "")); raw_paths = body.get("paths") or []
    paths = [safe_media_path(str(x)) for x in raw_paths]
    if action in {"reprocess", "retry"}:
        for p in paths: queue_process(p)
    elif action == "reset":
        for p in paths: reset_one(p)
    else: raise HTTPException(400, "Unknown bulk action")
    return {"ok": True, "count": len(paths), "action": action}


@app.get("/api/reports")
def reports(_: bool = Depends(auth)):
    cfg = pc.load_config(CONFIG); d = Path(cfg.get("reports", {}).get("directory", "/config/reports")); items=[]
    if d.exists():
        for p in sorted(d.glob("*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)[:2000]:
            items.append({"name":p.name,"mtime":p.stat().st_mtime,"size":p.stat().st_size,"has_json":p.with_suffix('.json').exists()})
    return {"items": items}


@app.get("/api/reports/{name}")
def report(name: str, _: bool = Depends(auth)):
    if "/" in name or "\\" in name or not name.endswith(".txt"): raise HTTPException(400, "Invalid report")
    cfg=pc.load_config(CONFIG); p=Path(cfg.get("reports",{}).get("directory","/config/reports"))/name
    if not p.exists(): raise HTTPException(404,"Report not found")
    return {"name":name,"text":p.read_text(encoding="utf-8",errors="replace")}


@app.get("/api/report-data")
def report_data(path: str, _: bool = Depends(auth)):
    p = safe_media_path(path); rec = state_row_for(p); rp = report_json_path(rec.get("report"))
    if not rp or not rp.exists(): raise HTTPException(404, "No JSON analysis report for this movie")
    data = json.loads(rp.read_text(encoding="utf-8")); return {"report": rec.get("report"), "data": data}


@app.get("/api/movie-info")
def movie_info(path: str, _: bool = Depends(auth)):
    p = safe_media_path(path); cfg = pc.load_config(CONFIG); probe = pc.ffprobe(p); rec = state_row_for(p)
    marker = pc.marker_load(p, cfg).get("files", {}).get(p.name)
    audio=[]; subtitles=[]
    for s in probe.get("streams", []):
        if s.get("codec_type") == "audio":
            audio.append({"index":s.get("index"),"codec":s.get("codec_name"),"channels":s.get("channels"),"layout":s.get("channel_layout"),
                          "language":(s.get("tags") or {}).get("language"),
                          "title":((s.get("tags") or {}).get("title") or (s.get("tags") or {}).get("handler_name")),
                          "default":bool((s.get("disposition") or {}).get("default"))})
        elif s.get("codec_type") == "subtitle":
            subtitles.append({"index":s.get("index"),"codec":s.get("codec_name"),"language":(s.get("tags") or {}).get("language"),
                              "title":(s.get("tags") or {}).get("title"),"forced":bool((s.get("disposition") or {}).get("forced"))})
    return {"path":str(p),"size":p.stat().st_size,"duration":pc.duration_of(probe),"state":rec,"marker":marker,
            "audio":audio,"subtitles":subtitles,"subtitle_sources":subassist.list_sources(p,probe,cfg),
            "image_subtitles":subassist.image_subtitle_summary(probe)}


@app.get("/api/preview")
def preview(path: str, start: float = Query(..., ge=0), end: float = Query(..., ge=0), _: bool = Depends(auth)):
    p = safe_media_path(path); rec = state_row_for(p); audio_rel = 0
    rp = report_json_path(rec.get("report"))
    if rp and rp.exists():
        try: audio_rel = int(json.loads(rp.read_text(encoding="utf-8")).get("audio_relative_index", 0))
        except Exception: pass
    center = (start + end) / 2; clip_start = max(0, center - 3.0); duration = min(10.0, max(4.0, end - start + 5.0))
    cmd = ["ffmpeg","-hide_banner","-loglevel","error","-ss",f"{clip_start:.3f}","-i",str(p),"-t",f"{duration:.3f}",
           "-map",f"0:a:{audio_rel}","-ac","2","-ar","44100","-c:a","pcm_s16le","-f","wav","pipe:1"]
    cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if cp.returncode != 0: raise HTTPException(500, cp.stderr.decode("utf-8","replace")[-500:])
    return Response(cp.stdout, media_type="audio/wav", headers={"Cache-Control":"no-store"})


@app.post("/api/review/approve")
async def review_approve(request: Request, _: bool = Depends(auth)):
    body = await request.json(); p = safe_media_path(str(body.get("path", ""))); rec = state_row_for(p)
    if rec.get("status") != "awaiting-review": raise HTTPException(409, "Movie is not awaiting review")
    report = rec.get("report"); job = queue_process(p, mode="apply-report", report=report, excluded_indices=list(body.get("excluded_indices") or []))
    return {"ok":True,"job":job}


@app.post("/api/review/skip")
async def review_skip(request: Request, _: bool = Depends(auth)):
    body = await request.json(); p = safe_media_path(str(body.get("path", ""))); cfg=pc.load_config(CONFIG)
    state=read_json(STATE,{"files":{}}); rec=state.setdefault("files",{}).setdefault(str(p),{}); rec.update({"status":"review-skipped","time":time.time()}); write_json(STATE,state)
    pc.marker_write(p,cfg,"review-skipped",rating=rec.get("rating"),report=rec.get("report")); return {"ok":True}


@app.get("/api/exceptions")
def get_exceptions(_: bool = Depends(auth)):
    return read_json(USER_EXCEPTIONS, {"phrases": [], "ids": []})


@app.post("/api/exceptions")
async def add_exception(request: Request, _: bool = Depends(auth)):
    body=await request.json(); data=read_json(USER_EXCEPTIONS,{"phrases":[],"ids":[]})
    kind=str(body.get("kind","phrase")); value=str(body.get("value","")).strip()
    if not value: raise HTTPException(400,"Value is blank")
    key="ids" if kind=="id" else "phrases"; vals=list(dict.fromkeys([*data.get(key,[]),value])); data[key]=vals; write_json(USER_EXCEPTIONS,data)
    RESTART_AFTER_CURRENT.touch(); return {"ok":True,"data":data}


@app.delete("/api/exceptions")
async def delete_exception(request: Request, _: bool = Depends(auth)):
    body=await request.json(); data=read_json(USER_EXCEPTIONS,{"phrases":[],"ids":[]}); kind=str(body.get("kind","phrase")); value=str(body.get("value",""))
    key="ids" if kind=="id" else "phrases"; data[key]=[x for x in data.get(key,[]) if str(x)!=value]; write_json(USER_EXCEPTIONS,data); RESTART_AFTER_CURRENT.touch(); return {"ok":True,"data":data}


def _base_profanity_entries() -> list[dict]:
    try:
        cfg = pc.load_config(CONFIG)
        path = Path(cfg.get("profanity", {}).get("file", "/config/en.json"))
    except Exception:
        path = Path("/config/en.json")
    if not path.exists():
        path = Path("/app/en.json")
    data = read_json(path, [])
    rows = [dict(x) for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    return pc.merge_dictionary_entries(rows)


def _clean_scope(value: Any) -> str:
    scope = str(value or "both").lower()
    return scope if scope in {"both", "normal", "rescue"} else "both"


def profanity_dictionary_payload() -> dict:
    base = _base_profanity_entries()
    overrides = read_json(PROFANITY_OVERRIDES, {})
    if not isinstance(overrides, dict): overrides = {}
    custom = read_json(CUSTOM_PROFANITY, [])
    if not isinstance(custom, list): custom = []
    items: list[dict] = []
    for raw in base:
        ident = str(raw.get("id", "")).strip()
        if not ident: continue
        default_match = str(raw.get("match", ""))
        default_sev = max(1, min(4, int(raw.get("severity", 3))))
        default_scope = _clean_scope(raw.get("scope", "both"))
        ov = overrides.get(ident, {}) if isinstance(overrides.get(ident, {}), dict) else {}
        items.append({
            "id": ident,
            "match": str(ov.get("match", default_match)),
            "severity": max(1, min(4, int(ov.get("severity", default_sev)))),
            "scope": _clean_scope(ov.get("scope", default_scope)),
            "enabled": bool(ov.get("enabled", True)),
            "origin": "builtin",
            "tags": list(raw.get("tags", [])),
            "overridden": bool(ov),
            "default_match": default_match,
            "default_severity": default_sev,
            "default_scope": default_scope,
        })
    base_ids = {str(x.get("id", "")) for x in base}
    for i, raw in enumerate(custom):
        if not isinstance(raw, dict): continue
        ident = str(raw.get("id") or f"custom-{i+1}").strip()
        if not ident or ident in base_ids: continue
        items.append({
            "id": ident,
            "match": str(raw.get("match", "")),
            "severity": max(1, min(4, int(raw.get("severity", 3)))),
            "scope": _clean_scope(raw.get("scope", "both")),
            "enabled": bool(raw.get("enabled", True)),
            "origin": "custom",
            "tags": list(raw.get("tags", ["custom"])),
            "overridden": False,
        })
    cfg = pc.load_config(CONFIG)
    return {
        "items": items,
        "minimum_severity": int(cfg.get("profanity", {}).get("min_severity", 3)),
        "builtin_count": sum(1 for x in items if x["origin"] == "builtin"),
        "custom_count": sum(1 for x in items if x["origin"] == "custom"),
        "enabled_count": sum(1 for x in items if x.get("enabled")),
    }


@app.get("/api/profanity-dictionary")
def profanity_dictionary(_: bool = Depends(auth)):
    return profanity_dictionary_payload()


@app.post("/api/profanity-dictionary")
async def save_profanity_dictionary(request: Request, _: bool = Depends(auth)):
    body = await request.json(); items = body.get("items") or []
    if not isinstance(items, list): raise HTTPException(400, "items must be a list")
    base = _base_profanity_entries(); base_by_id = {str(x.get("id", "")): x for x in base if str(x.get("id", ""))}
    overrides: dict[str, dict] = {}; custom: list[dict] = []; seen: set[str] = set()
    for i, raw in enumerate(items):
        if not isinstance(raw, dict): continue
        origin = str(raw.get("origin", "custom")).lower()
        ident = str(raw.get("id", "")).strip()
        if not ident and origin == "custom": ident = f"custom-{uuid.uuid4().hex[:10]}"
        if not ident: raise HTTPException(400, f"Dictionary row {i+1} has no ID")
        if ident in seen: raise HTTPException(400, f"Duplicate profanity ID: {ident}")
        seen.add(ident)
        enabled = bool(raw.get("enabled", True)); match = str(raw.get("match", "")).strip()
        sev = max(1, min(4, int(raw.get("severity", 3)))); scope = _clean_scope(raw.get("scope", "both"))
        if origin == "builtin" or ident in base_by_id:
            if ident not in base_by_id: raise HTTPException(400, f"Unknown built-in profanity ID: {ident}")
            default = base_by_id[ident]; ov: dict[str, Any] = {}
            dmatch = str(default.get("match", "")); dsev = max(1, min(4, int(default.get("severity", 3)))); dscope = _clean_scope(default.get("scope", "both"))
            if not enabled: ov["enabled"] = False
            if enabled and not match: raise HTTPException(400, f"Enabled word/pattern cannot be blank: {ident}")
            if match and match != dmatch: ov["match"] = match
            if sev != dsev: ov["severity"] = sev
            if scope != dscope: ov["scope"] = scope
            if ov: overrides[ident] = ov
        else:
            if not match: continue
            custom.append({"id": ident, "match": match, "severity": sev, "scope": scope,
                           "enabled": enabled, "tags": ["custom"]})
    write_json(PROFANITY_OVERRIDES, overrides); write_json(CUSTOM_PROFANITY, custom)
    RESTART_AFTER_CURRENT.touch()
    return {"ok": True, "built_in_overrides": len(overrides), "custom_count": len(custom),
            "message": "Profanity dictionary saved. Worker will reload after the current item."}


@app.post("/api/profanity-dictionary/reset-builtins")
def reset_builtin_profanity(_: bool = Depends(auth)):
    write_json(PROFANITY_OVERRIDES, {}); RESTART_AFTER_CURRENT.touch()
    return {"ok": True, "message": "Built-in profanity entries restored to defaults. Custom entries were kept."}


# Backward-compatible custom-only endpoints retained for older GUI/API clients.
@app.get("/api/custom-profanity")
def custom_profanity(_: bool = Depends(auth)):
    d=read_json(CUSTOM_PROFANITY,[]); return {"items": d if isinstance(d,list) else []}


@app.post("/api/custom-profanity")
async def save_custom_profanity(request: Request, _: bool = Depends(auth)):
    body=await request.json(); items=body.get("items") or []; clean=[]
    base_ids = {str(x.get("id", "")) for x in _base_profanity_entries()}
    for i,x in enumerate(items):
        match=str(x.get("match","")).strip()
        if not match: continue
        sev=max(1,min(4,int(x.get("severity",3)))); scope=_clean_scope(x.get("scope","both"))
        ident=str(x.get("id") or ("custom-"+str(i+1))).strip()
        if ident in base_ids: raise HTTPException(400, f"Custom ID conflicts with built-in ID: {ident}")
        clean.append({"id":ident,"match":match,"severity":sev,"tags":["custom"],"scope":scope,"enabled":bool(x.get("enabled",True))})
    write_json(CUSTOM_PROFANITY,clean); RESTART_AFTER_CURRENT.touch(); return {"ok":True,"count":len(clean)}


def _secret_spec(cfg: dict) -> dict[str, tuple[str | None, Any]]:
    sub = cfg.get("subtitle_assist", {}) or {}; baz = sub.get("bazarr", {}) or {}
    arr = cfg.get("arr_integrations", {}) or {}; n = cfg.get("notifications", {}) or {}
    return {
        "plex_token": ("PLEX_TOKEN", (cfg.get("rating_filter", {}) or {}).get("plex_token", "")),
        "asr_worker_token": ("ASR_WORKER_TOKEN", ((cfg.get("whisper", {}) or {}).get("remote", {}) or {}).get("token", "")),
        "bazarr_api_key": ("BAZARR_API_KEY", baz.get("api_key", "")),
        "radarr_api_key": ("RADARR_API_KEY", (arr.get("radarr", {}) or {}).get("api_key", "")),
        "sonarr_api_key": ("SONARR_API_KEY", (arr.get("sonarr", {}) or {}).get("api_key", "")),
        "pushover_app_token": ("PUSHOVER_APP_TOKEN", ((n.get("pushover", {}) or {}).get("app_token", ""))),
        "pushover_user_key": ("PUSHOVER_USER_KEY", ((n.get("pushover", {}) or {}).get("user_key", ""))),
        "smtp_password": ("SMTP_PASSWORD", ((n.get("email", {}) or {}).get("password", ""))),
    }


def settings_payload(cfg: dict) -> dict:
    # Secrets are deliberately never returned. The GUI receives only set/source metadata and blank
    # password inputs. New GUI-saved secrets live in /config/secrets.json (0600) and take precedence
    # over legacy environment/config values.
    subtitle = json.loads(json.dumps(cfg.get("subtitle_assist", {})))
    subtitle.setdefault("bazarr", {}).pop("api_key", None)
    notifications = json.loads(json.dumps(cfg.get("notifications", {})))
    notifications.setdefault("pushover", {}).pop("app_token", None)
    notifications.setdefault("pushover", {}).pop("user_key", None)
    notifications.setdefault("email", {}).pop("password", None)
    arrs = json.loads(json.dumps(cfg.get("arr_integrations", {})))
    for _name in ("radarr", "sonarr"):
        arrs.setdefault(_name, {}).pop("api_key", None)
    whisper = json.loads(json.dumps(cfg.get("whisper", {})))
    whisper.setdefault("remote", {}).pop("token", None)
    rating = json.loads(json.dumps(cfg.get("rating_filter", {}))); rating.pop("plex_token", None)
    tv = json.loads(json.dumps(cfg.get("tv", {}))); tv.setdefault("rating_filter", {}).pop("plex_token", None)
    return {
        "dry_run": bool(cfg.get("dry_run", True)),
        "media_roots": cfg.get("media_roots", ["/media"]),
        "extensions": cfg.get("extensions", [".mkv", ".mp4", ".m4v"]),
        "scan_interval_seconds": int(cfg.get("scan_interval_seconds",120)),
        "stable_seconds": int(cfg.get("stable_seconds",300)),
        "process_existing": bool(cfg.get("process_existing", True)),
        "setup": cfg.get("setup", {"completed": True, "wizard_version": 1}),
        "marker": cfg.get("marker", {"enabled":True,"filename":".censorarr.done.json"}),
        "rating_filter": rating,
        "tv": tv,
        "whisper": whisper,
        "audio_cache": cfg.get("audio_cache", {}),
        "profanity": cfg.get("profanity", {}),
        "precision_alignment": cfg.get("precision_alignment", {}),
        "rescue": cfg.get("rescue", {}),
        "subtitle_assist": subtitle,
        "review_mode": cfg.get("review_mode", {}),
        "clean_track": cfg.get("clean_track", {}),
        "processing_schedule": cfg.get("processing_schedule", {}),
        "plex_activity": cfg.get("plex_activity", {}),
        "arr_integrations": arrs,
        "worker": cfg.get("worker", {"max_concurrent_jobs":1}),
        "safety": cfg.get("safety", {}),
        "reports": cfg.get("reports", {}),
        "notifications": notifications,
        "logging": cfg.get("logging", {}),
        "secret_status": secret_store.statuses(_secret_spec(cfg)),
    }


@app.get("/api/settings")
def get_settings(_: bool = Depends(auth)):
    return settings_payload(pc.load_config(CONFIG))


@app.get("/api/setup/status")
def setup_status(_: bool = Depends(auth)):
    cfg = pc.load_config(CONFIG)
    setup = cfg.get("setup", {}) or {}
    completed = bool(setup.get("completed", True))
    return {
        "required": bool(FIRST_RUN.exists()) or not completed,
        "completed": completed,
        "wizard_version": int(setup.get("wizard_version", 1) or 1),
        "version": VERSION,
    }


@app.post("/api/setup/complete")
def setup_complete(_: bool = Depends(auth)):
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    raw["setup"] = {"completed": True, "wizard_version": 1}
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    os.replace(tmp, CONFIG)
    try:
        FIRST_RUN.unlink()
    except FileNotFoundError:
        pass
    RESTART_AFTER_CURRENT.touch()
    return {"ok": True, "message": "Setup complete. Censorarr is ready to scan and process media."}


def _bool_into(dst: dict, src: dict, key: str) -> None:
    if key in src: dst[key] = bool(src[key])


def _number_into(dst: dict, src: dict, key: str, cast=float, minimum=None, maximum=None) -> None:
    if key not in src: return
    v = cast(src[key])
    if minimum is not None: v = max(minimum, v)
    if maximum is not None: v = min(maximum, v)
    dst[key] = v


@app.post("/api/settings")
async def save_settings(request: Request, _: bool = Depends(auth)):
    body = await request.json(); raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    raw["dry_run"] = bool(body.get("dry_run", raw.get("dry_run", True)))
    raw["process_existing"] = bool(body.get("process_existing", raw.get("process_existing", True)))
    if "extensions" in body:
        ext = body.get("extensions") or []
        if isinstance(ext, str): ext = [x.strip() for x in ext.split(",")]
        cleaned=[]
        for x in ext:
            x=str(x).strip().lower()
            if not x: continue
            if not x.startswith("."): x="."+x
            if x not in cleaned: cleaned.append(x)
        if not cleaned: raise HTTPException(400,"At least one media extension is required")
        raw["extensions"] = cleaned
    roots = body.get("media_roots", raw.get("media_roots", ["/media"]))
    if not isinstance(roots,list) or not roots: raise HTTPException(400,"At least one media root is required")
    clean_roots=[]
    for r in roots:
        rp=safe_media_path(str(r))
        if not rp.is_dir(): raise HTTPException(400,f"Media root is not a directory: {rp}")
        clean_roots.append(str(rp))
    raw["media_roots"]=clean_roots
    raw["scan_interval_seconds"]=max(10,int(body.get("scan_interval_seconds",raw.get("scan_interval_seconds",120))))
    raw["stable_seconds"]=max(30,int(body.get("stable_seconds",raw.get("stable_seconds",300))))
    if "marker" in body:
        bm=body.get("marker") or {}; mk=raw.setdefault("marker",{})
        _bool_into(mk,bm,"enabled")
        if "filename" in bm:
            fn=Path(str(bm["filename"]).strip()).name
            if not fn: raise HTTPException(400,"Marker filename cannot be blank")
            mk["filename"]=fn

    brf=body.get("rating_filter",{}); rf=raw.setdefault("rating_filter",{})
    for k in ("minimum","source","plex_url","plex_library"):
        if k in brf: rf[k]=str(brf[k]).strip()
    _bool_into(rf,brf,"enabled"); _bool_into(rf,brf,"include_unrated")
    if "plex_path_mappings" in brf: rf["plex_path_mappings"]=brf["plex_path_mappings"]

    if "tv" in body:
        btv = body.get("tv") or {}; tv = raw.setdefault("tv", {})
        _bool_into(tv,btv,"enabled")
        tv_roots = btv.get("media_roots", tv.get("media_roots", ["/tv"]))
        if not isinstance(tv_roots, list) or not tv_roots: raise HTTPException(400, "TV needs at least one media root")
        clean_tv_roots=[]
        tv_enabled = bool(tv.get("enabled", False))
        for r in tv_roots:
            if tv_enabled:
                rp=safe_media_path(str(r))
                if not rp.is_dir(): raise HTTPException(400, f"TV media root is not a directory: {rp}")
                clean_tv_roots.append(str(rp))
            else:
                # Keep the intended container path for later without requiring the optional TV mount
                # to exist while TV processing is disabled.
                raw_root = str(r).strip() or "/tv"
                if not raw_root.startswith("/"):
                    raise HTTPException(400, "TV media root must be an absolute container path")
                clean_tv_roots.append(raw_root)
        tv["media_roots"] = clean_tv_roots
        btrf = btv.get("rating_filter", {}) or {}; trf = tv.setdefault("rating_filter", {})
        for k in ("minimum", "source", "plex_url", "plex_library"):
            if k in btrf: trf[k] = str(btrf[k]).strip()
        _bool_into(trf,btrf,"enabled"); _bool_into(trf,btrf,"include_unrated")
        if "plex_path_mappings" in btrf: trf["plex_path_mappings"] = btrf["plex_path_mappings"]

    if "whisper" in body:
        bw=body["whisper"] or {}; w=raw.setdefault("whisper",{})
        for k in ("model","device","compute_type","backend","language"):
            if k in bw: w[k]=str(bw[k]).strip()
        _number_into(w,bw,"beam_size",int,1,20); _bool_into(w,bw,"vad_filter"); _bool_into(w,bw,"condition_on_previous_text")
        if "remote" in bw:
            br=bw.get("remote") or {}; rr=w.setdefault("remote",{})
            for k in ("url","model"):
                if k in br: rr[k]=str(br[k]).strip().rstrip("/") if k=="url" else str(br[k]).strip()
            _bool_into(rr,br,"fallback_to_local"); _number_into(rr,br,"timeout_seconds",int,30,86400)
        w.setdefault("remote",{})["enabled"] = str(w.get("backend","local")).lower() in {"remote","auto"}

    if "audio_cache" in body:
        ba=body.get("audio_cache") or {}; ac=raw.setdefault("audio_cache",{})
        _bool_into(ac,ba,"enabled"); _bool_into(ac,ba,"keep_after_success")
        if "directory" in ba:
            d=str(ba["directory"]).strip()
            if not (d.startswith("/work/") or d=="/work" or d.startswith("/config/")): raise HTTPException(400,"Audio cache directory must be under /work or /config")
            ac["directory"]=d

    if "profanity" in body:
        bp=body.get("profanity") or {}; pr=raw.setdefault("profanity",{})
        _number_into(pr,bp,"min_severity",int,1,4); _number_into(pr,bp,"padding_before_ms",int,0,5000)
        _number_into(pr,bp,"padding_after_ms",int,0,5000); _number_into(pr,bp,"max_word_window",int,1,20)

    if "precision_alignment" in body:
        bi=body.get("precision_alignment") or {}; pa=raw.setdefault("precision_alignment",{})
        _bool_into(pa,bi,"enabled")
        _number_into(pa,bi,"padding_before_ms",int,0,1000); _number_into(pa,bi,"padding_after_ms",int,0,1000)
        _number_into(pa,bi,"edge_search_ms",int,0,1000); _number_into(pa,bi,"neighbor_guard_ms",int,0,250)
        _number_into(pa,bi,"energy_threshold_ratio",float,0.02,0.95); _number_into(pa,bi,"frame_ms",int,2,30)

    if "rescue" in body:
        bs=body.get("rescue") or {}; rr=raw.setdefault("rescue",{})
        _bool_into(rr,bs,"enabled"); _bool_into(rr,bs,"prefer_center_channel")
        for k in ("confidence_trigger","fuzzy_confidence_ceiling","fuzzy_similarity","window_before_seconds","window_after_seconds","merge_gap_seconds"):
            _number_into(rr,bs,k,float,0.0,30.0)
        _number_into(rr,bs,"max_windows",int,1,5000)
        if "prompt" in bs: rr["prompt"]=str(bs["prompt"])
        if "mild_evidence" in bs:
            me=bs["mild_evidence"]
            if isinstance(me,str): me=[x.strip() for x in me.split(",") if x.strip()]
            if isinstance(me,list): rr["mild_evidence"]=[str(x).strip() for x in me if str(x).strip()]

    if "subtitle_assist" in body:
        incoming=json.loads(json.dumps(body["subtitle_assist"] or {})); incoming.setdefault("bazarr",{}).pop("api_key",None)
        raw["subtitle_assist"]=pc.deep_merge(raw.get("subtitle_assist",{}),incoming)
    if "review_mode" in body: raw["review_mode"]=pc.deep_merge(raw.get("review_mode",{}),body["review_mode"])
    if "clean_track" in body:
        bct=body.get("clean_track") or {}; ct=raw.setdefault("clean_track",{})
        for k in ("title","language","codec"):
            if k in bct: ct[k]=str(bct[k]).strip()
        for k in ("make_default","place_clean_first","replace_existing_clean","reprocess_existing_clean"):_bool_into(ct,bct,k)
        if not ct.get("title"): ct["title"]="English - CLEAN"
    if "processing_schedule" in body: raw["processing_schedule"]=pc.deep_merge(raw.get("processing_schedule",{}),body["processing_schedule"])
    if "plex_activity" in body: raw["plex_activity"]=pc.deep_merge(raw.get("plex_activity",{}),body["plex_activity"])

    if "notifications" in body:
        inc=json.loads(json.dumps(body["notifications"] or {})); inc.setdefault("pushover",{}).pop("app_token",None); inc.setdefault("pushover",{}).pop("user_key",None); inc.setdefault("email",{}).pop("password",None)
        raw["notifications"]=pc.deep_merge(raw.get("notifications",{}),inc)
    if "arr_integrations" in body:
        incoming = body.get("arr_integrations") or {}; arr_root = raw.setdefault("arr_integrations", {})
        for name in ("radarr", "sonarr"):
            if name not in incoming: continue
            src = incoming.get(name) or {}; dst = arr_root.setdefault(name, {})
            _bool_into(dst,src,"enabled")
            if "url" in src: dst["url"] = str(src["url"]).strip().rstrip("/")
            if "path_mappings" in src and isinstance(src["path_mappings"], list): dst["path_mappings"] = src["path_mappings"]
            _number_into(dst,src,"cache_seconds",int,30,86400)

    if "safety" in body:
        bs=body.get("safety") or {}; sf=raw.setdefault("safety",{})
        for k in ("validate_output","preserve_owner_mode","backup_original"):_bool_into(sf,bs,k)
        _number_into(sf,bs,"duration_tolerance_seconds",float,0.0,60.0)
    if "reports" in body:
        br=body.get("reports") or {}; rp=raw.setdefault("reports",{})
        for k in ("keep_transcript_json","keep_rescue_details"):_bool_into(rp,br,k)
        if "directory" in br:
            d=str(br["directory"]).strip()
            if not d.startswith("/config/"): raise HTTPException(400,"Reports directory must be under /config")
            rp["directory"]=d
    if "logging" in body:
        bl=body.get("logging") or {}; lg=raw.setdefault("logging",{})
        if "level" in bl:
            level=str(bl["level"]).upper().strip()
            if level not in {"DEBUG","INFO","WARNING","ERROR"}: raise HTTPException(400,"Invalid logging level")
            lg["level"]=level

    # Censorarr intentionally keeps media mutation serialized. Expose the value read-only in the UI,
    # but do not allow a browser request to raise concurrency and create two simultaneous remuxes.
    raw.setdefault("worker",{})["max_concurrent_jobs"]=1

    # Secret values are optional. Blank password fields mean "leave the saved value alone".
    sec = body.get("secrets") or {}
    allowed=set(_secret_spec(raw))
    for name,value in sec.items():
        if name in allowed and str(value or "").strip(): secret_store.set_secret(name,str(value))
    for name in body.get("clear_secrets",[]) or []:
        if name in allowed: secret_store.clear(name)

    tmp=CONFIG.with_suffix(".tmp"); tmp.write_text(yaml.safe_dump(raw,sort_keys=False),encoding="utf-8"); os.replace(tmp,CONFIG); RESTART_AFTER_CURRENT.touch()
    return {"ok":True,"message":"Saved. Runtime-safe settings apply after the current movie; no Docker rebuild is required."}


@app.post("/api/integrations/asr/test")
def test_remote_asr(_: bool = Depends(auth)):
    cfg=pc.load_config(CONFIG)
    try:
        h=remote_asr.health(cfg)
        if not h.get("ok",False): raise HTTPException(503, f"GPU worker responded but no CUDA device is visible: {h}")
        return h
    except HTTPException: raise
    except Exception as e: raise HTTPException(502, f"Remote ASR test failed: {e}")


@app.get("/api/settings/export")
def export_settings(_: bool = Depends(auth)):
    if not CONFIG.exists(): pc.ensure_config(CONFIG)
    return PlainTextResponse(CONFIG.read_text(encoding="utf-8"), headers={"Content-Disposition":"attachment; filename=censorarr-config.yaml"})


@app.post("/api/settings/import")
async def import_settings(request: Request, _: bool = Depends(auth)):
    body=await request.json(); text=str(body.get("yaml", "")); raw=yaml.safe_load(text) or {}
    roots=raw.get("media_roots",["/media"])
    if not isinstance(roots,list) or not roots: raise HTTPException(400,"Imported config has no media roots")
    for r in roots: safe_media_path(str(r))
    tmp=CONFIG.with_suffix(".tmp"); tmp.write_text(yaml.safe_dump(raw,sort_keys=False),encoding="utf-8"); os.replace(tmp,CONFIG); RESTART_AFTER_CURRENT.touch(); return {"ok":True}


@app.get("/api/integrations/asr/status")
def remote_asr_status(_: bool = Depends(auth)):
    cfg=pc.load_config(CONFIG)
    if not remote_asr.enabled(cfg):
        return {"ok":False,"enabled":False,"message":"Remote GPU backend is not selected"}
    try:
        return {"enabled":True, **remote_asr.status(cfg, timeout=2.5)}
    except Exception as e:
        return {"ok":False,"enabled":True,"error":str(e)}


@app.get("/api/integrations/asr/logs")
def remote_asr_logs(lines: int = Query(300, ge=10, le=5000), _: bool = Depends(auth)):
    cfg=pc.load_config(CONFIG)
    if not remote_asr.enabled(cfg):
        return {"ok":False,"lines":[],"message":"Remote GPU backend is not selected"}
    try:
        return remote_asr.logs(cfg, lines=lines, timeout=3.0)
    except Exception as e:
        return {"ok":False,"lines":["GPU worker log unavailable: "+str(e)]}


@app.post("/api/integrations/asr/logs/clear")
def remote_asr_clear_logs(_: bool = Depends(auth)):
    cfg=pc.load_config(CONFIG)
    return remote_asr.clear_logs(cfg, timeout=3.0)


@app.get("/api/integrations/asr/logs/download")
def remote_asr_download_logs(_: bool = Depends(auth)):
    cfg=pc.load_config(CONFIG)
    data=remote_asr.logs(cfg, lines=5000, timeout=4.0)
    text="\n".join(data.get("lines",[]))+"\n"
    return Response(content=text, media_type="text/plain", headers={"Content-Disposition":"attachment; filename=censorarr-gpu-worker.log"})


@app.post("/api/integrations/bazarr/test")
def test_bazarr(_: bool = Depends(auth)):
    try: return integ.bazarr_test(pc.load_config(CONFIG))
    except Exception as e: raise HTTPException(400,str(e))



@app.post("/api/integrations/radarr/test")
def test_radarr(_: bool = Depends(auth)):
    try: return integ.arr_test(pc.load_config(CONFIG), "radarr")
    except Exception as e: raise HTTPException(400, str(e))


@app.post("/api/integrations/sonarr/test")
def test_sonarr(_: bool = Depends(auth)):
    try: return integ.arr_test(pc.load_config(CONFIG), "sonarr")
    except Exception as e: raise HTTPException(400, str(e))


def _image_url(item: dict, *wanted_types: str) -> str:
    images = item.get("images") or []
    if not isinstance(images, list):
        return ""
    wanted = [str(x).lower() for x in wanted_types if str(x).strip()]
    for kind in wanted:
        for image in images:
            if str(image.get("coverType", "")).lower() == kind:
                return str(image.get("remoteUrl") or image.get("url") or "")
    return ""


def _poster_url(item: dict) -> str:
    return _image_url(item, "poster", "cover") or (_image_url(item, str((item.get("images") or [{}])[0].get("coverType", ""))) if item.get("images") else "")


def _norm_media_path(path: str | Path) -> str:
    return str(path).replace("\\", "/").rstrip("/")


def _normalize_media_status(status: Any) -> str:
    s = str(status or "")
    # Older builds used skipped-clean-exists for a file that already had a valid CLEAN track.
    return "clean-exists" if s == "skipped-clean-exists" else s


def _current_media_history(cfg: dict, state_files: dict) -> dict[str, dict]:
    """Return history rows that still describe a current media file.

    state.json is intentionally historical and can retain rows for files that Radarr/Sonarr
    later replaced or deleted.  The Media pages are current-library views, so Dashboard KPI
    counts need the same semantics.  Reconcile durable markers, require the file to still
    exist, and reject a row whose saved fingerprint no longer matches the current file.
    """
    merged = _media_history_index(cfg, state_files)
    current: dict[str, dict] = {}
    for key, rec in merged.items():
        if not isinstance(rec, dict):
            continue
        media = Path(key)
        if not media.is_file():
            continue
        saved_fp = str(rec.get("fingerprint") or "")
        if saved_fp:
            try:
                if saved_fp != pc.fingerprint(media):
                    continue
            except OSError:
                continue
        row = dict(rec)
        row["status"] = _normalize_media_status(row.get("status"))
        current[_norm_media_path(media)] = row
    return current


def _media_history_index(cfg: dict, state_files: dict) -> dict[str, dict]:
    """Merge current state.json records with valid on-disk completion markers.

    The Media screens are a view of the current library, not just the in-memory/state history.
    A state file can be reset/rebuilt during upgrades, while .censorarr.done.json markers remain
    beside successfully processed media. Reading those markers lets Movies/TV correctly show
    CLEAN / No profanity after upgrades or state resets.
    """
    global _MEDIA_HISTORY_CACHE
    try:
        state_mtime = STATE.stat().st_mtime_ns
    except OSError:
        state_mtime = 0
    roots = tuple(_norm_media_path(x) for x in pc.all_media_roots(cfg))
    marker_name = str(cfg.get("marker", {}).get("filename", ".censorarr.done.json"))
    cache_key = (state_mtime, roots, marker_name)
    if _MEDIA_HISTORY_CACHE.get("key") == cache_key:
        return dict(_MEDIA_HISTORY_CACHE.get("items", {}))

    merged: dict[str, dict] = {}
    for key, rec in (state_files or {}).items():
        if not isinstance(rec, dict):
            continue
        row = dict(rec)
        row["status"] = _normalize_media_status(row.get("status"))
        merged[_norm_media_path(key)] = row

    # Scan for marker *files*, not every media file. This is much cheaper on large libraries.
    for root_raw in roots:
        root = Path(root_raw)
        if not root.is_dir():
            continue
        try:
            marker_paths = root.rglob(marker_name)
            for marker in marker_paths:
                data = read_json(marker, {})
                files = data.get("files", {}) if isinstance(data, dict) else {}
                if not isinstance(files, dict):
                    continue
                try:
                    marker_time = marker.stat().st_mtime
                except OSError:
                    marker_time = None
                for filename, ent in files.items():
                    if not isinstance(ent, dict) or ent.get("done") is not True:
                        continue
                    media = marker.parent / str(filename)
                    if not media.is_file():
                        continue
                    try:
                        current_fp = pc.fingerprint(media)
                    except OSError:
                        continue
                    # Ignore stale markers left behind after Radarr/Sonarr replaces a file.
                    if str(ent.get("fingerprint") or "") != current_fp:
                        continue
                    norm = _norm_media_path(media)
                    existing = merged.get(norm)
                    # A current matching state record is newer/more specific (for example a failed
                    # manual reprocess); otherwise restore the durable success marker into the view.
                    if existing and str(existing.get("fingerprint") or "") == current_fp and existing.get("status"):
                        continue
                    row = dict(ent)
                    row["status"] = _normalize_media_status(row.get("status"))
                    row["time"] = marker_time
                    merged[norm] = row
        except OSError:
            continue

    _MEDIA_HISTORY_CACHE = {"key": cache_key, "items": dict(merged)}
    return merged


def _state_for_path(state_files: dict, path: str) -> dict:
    if not path:
        return {}
    norm = _norm_media_path(path)
    if norm in state_files:
        return state_files[norm]
    # Compatibility with callers that still pass an un-normalized mapping.
    for key, rec in state_files.items():
        if _norm_media_path(key) == norm:
            return rec
    # Path mappings sometimes change while the media filename does not. Fall back to basename only
    # when it identifies exactly one current history record, avoiding ambiguous matches.
    name = Path(norm).name.lower()
    if name:
        matches = [rec for key, rec in state_files.items() if Path(_norm_media_path(key)).name.lower() == name]
        if len(matches) == 1:
            return matches[0]
    return {}


def _history_record_for_movie(history_files: dict, mapped_file: str, mapped_folder: str) -> tuple[dict, str]:
    """Resolve a Radarr movie to Censorarr's current file record conservatively.

    Prefer the exact mapped movieFile path, then a unique basename match, then a single
    current media record directly inside the mapped movie folder.  The folder fallback
    covers Radarr responses/path mappings that identify the movie directory correctly but
    do not expose the exact movieFile path.
    """
    norm_file = _norm_media_path(mapped_file) if mapped_file else ""
    if norm_file and norm_file in history_files:
        return history_files[norm_file], norm_file
    if norm_file:
        name = Path(norm_file).name.lower()
        matches = [(key, rec) for key, rec in history_files.items() if Path(_norm_media_path(key)).name.lower() == name]
        if len(matches) == 1:
            key, rec = matches[0]
            return rec, _norm_media_path(key)

    norm_folder = _norm_media_path(mapped_folder) if mapped_folder else ""
    if norm_folder:
        direct = []
        for key, rec in history_files.items():
            nk = _norm_media_path(key)
            if _norm_media_path(Path(nk).parent) == norm_folder:
                direct.append((nk, rec))
        if len(direct) == 1:
            key, rec = direct[0]
            return rec, key

        # A changed path prefix can still leave the movie-folder basename intact. Only use
        # this fallback when it resolves to exactly one current record in the whole library.
        folder_name = Path(norm_folder).name.lower()
        if folder_name:
            by_folder = []
            for key, rec in history_files.items():
                nk = _norm_media_path(key)
                if Path(nk).parent.name.lower() == folder_name:
                    by_folder.append((nk, rec))
            if len(by_folder) == 1:
                key, rec = by_folder[0]
                return rec, key
    return {}, ""


def _records_under_root(history_files: dict, root: str) -> list[dict]:
    norm_root = _norm_media_path(root)
    if not norm_root:
        return []
    related = [rec for key, rec in history_files.items() if _norm_media_path(key).startswith(norm_root + "/")]
    if related:
        return related
    # If the configured Sonarr root prefix changed, use the series folder name as a conservative
    # fallback. This only affects the summary card; episode detail still resolves individual files.
    folder = Path(norm_root).name.lower()
    if not folder:
        return []
    token = "/" + folder + "/"
    return [rec for key, rec in history_files.items() if token in ("/" + _norm_media_path(key).lower() + "/")]


def _fs_catalog_id(path: str | Path) -> int:
    """Stable positive integer ID for filesystem-only Media cards."""
    return zlib.crc32(_norm_media_path(path).encode("utf-8")) & 0x7FFFFFFF


def _pretty_media_name(raw: str) -> tuple[str, int | None]:
    text = Path(raw).stem
    # Prefer common library folder/file naming while avoiding destructive guessing.
    text = re.sub(r"[._]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    year_match = re.search(r"(?:^|[ (\[])(19\d{2}|20\d{2})(?:[ )\]]|$)", text)
    year = int(year_match.group(1)) if year_match else None
    if year_match:
        text = (text[:year_match.start()] + text[year_match.end():]).strip(" -_()[]")
    # Strip the most obvious release suffixes from a filename-only title.
    text = re.split(r"\b(?:2160p|1080p|720p|480p|BluRay|WEB[- ]?DL|WEBRip|HDTV|DVDRip)\b", text, maxsplit=1, flags=re.I)[0].strip(" -_") or Path(raw).stem
    return text, year


def _media_quality_hint(path: Path) -> str:
    m = re.search(r"\b(2160p|1080p|720p|480p)\b", path.name, re.I)
    return m.group(1).lower() if m else ""


def _iter_media_under(root: Path, cfg: dict):
    exts = {str(x).lower() for x in cfg.get("extensions", [".mkv", ".mp4", ".m4v"])}
    if not root.is_dir():
        return
    for media in root.rglob("*"):
        if not media.is_file() or media.suffix.lower() not in exts:
            continue
        low = media.name.lower()
        if ".censorarr.tmp" in low or low.endswith(".part") or low.endswith(".partial"):
            continue
        yield media


def _filesystem_movie_items(cfg: dict, history_files: dict) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for root_raw in cfg.get("media_roots", ["/media"]):
        root = Path(str(root_raw))
        for media in _iter_media_under(root, cfg) or []:
            norm = _norm_media_path(media)
            if norm in seen:
                continue
            seen.add(norm)
            # Movie managers normally put each movie in its own folder, which is a much better title
            # source than a release filename. Fall back to the filename for flat libraries.
            label_source = media.parent.name if media.parent != root else media.stem
            title, year = _pretty_media_name(label_source)
            rec = _state_for_path(history_files, norm)
            try:
                size = media.stat().st_size
            except OSError:
                size = None
            items.append({
                "id": _fs_catalog_id(norm), "source": "filesystem", "title": title or media.stem,
                "sortTitle": title or media.stem, "year": year, "poster": "", "fanart": "",
                "monitored": True, "certification": "", "path": str(media.parent), "media_path": norm,
                "has_file": True, "size": size, "quality": _media_quality_hint(media),
                "censorarr_status": rec.get("status") or "unprocessed", "censorarr_time": rec.get("time"),
                "rating": rec.get("rating") or "", "detections": rec.get("detections") or rec.get("detection_count"),
                "bazarr_linked": False, "bazarr_missing": [], "radarr_url": "", "overview": "",
            })
    items.sort(key=lambda z: str(z.get("sortTitle", "")).lower())
    return items


def _series_root_for_episode(media: Path, tv_root: Path) -> Path:
    try:
        rel = media.relative_to(tv_root)
    except ValueError:
        return media.parent
    if len(rel.parts) >= 2:
        return tv_root / rel.parts[0]
    return media.parent


def _filesystem_series_items(cfg: dict, history_files: dict) -> list[dict]:
    groups: dict[str, dict] = {}
    for root_raw in pc.tv_media_roots(cfg):
        tv_root = Path(str(root_raw))
        for media in _iter_media_under(tv_root, cfg) or []:
            show_root = _series_root_for_episode(media, tv_root)
            key = _norm_media_path(show_root)
            group = groups.setdefault(key, {"root": show_root, "files": []})
            group["files"].append(media)
    items: list[dict] = []
    clean_terminal = {"applied", "clean-exists", "skipped-clean-exists"}
    for key, group in groups.items():
        show_root: Path = group["root"]
        files: list[Path] = group["files"]
        title, year = _pretty_media_name(show_root.name)
        recs = [_state_for_path(history_files, str(x)) for x in files]
        cleaned = sum(1 for rec in recs if _normalize_media_status(rec.get("status")) in clean_terminal)
        no_prof = sum(1 for rec in recs if _normalize_media_status(rec.get("status")) == "no-detections")
        failed = sum(1 for rec in recs if _normalize_media_status(rec.get("status")) in {"error", "cancelled"})
        touched = sum(1 for rec in recs if rec.get("status"))
        items.append({
            "id": _fs_catalog_id(key), "source": "filesystem", "title": title or show_root.name,
            "sortTitle": title or show_root.name, "year": year, "poster": "", "fanart": "",
            "monitored": True, "network": "", "path": key, "episode_file_count": len(files),
            "episode_count": len(files), "censorarr_touched": touched, "censorarr_cleaned": cleaned,
            "censorarr_no_profanity": no_prof, "censorarr_failed": failed, "bazarr_linked": False,
            "sonarr_url": "", "overview": "",
        })
    items.sort(key=lambda z: str(z.get("sortTitle", "")).lower())
    return items


def _probe_tracks(media_path: str) -> dict | None:
    if not media_path:
        return None
    try:
        mp = safe_media_path(media_path)
        probe = pc.ffprobe(mp)
        tracks = {"audio": [], "subtitles": []}
        for st in probe.get("streams", []):
            tags = st.get("tags") or {}
            if st.get("codec_type") == "audio":
                tracks["audio"].append({"codec": st.get("codec_name"), "channels": st.get("channels"), "language": tags.get("language"), "title": tags.get("title") or tags.get("handler_name"), "default": bool((st.get("disposition") or {}).get("default"))})
            elif st.get("codec_type") == "subtitle":
                tracks["subtitles"].append({"codec": st.get("codec_name"), "language": tags.get("language"), "title": tags.get("title"), "forced": bool((st.get("disposition") or {}).get("forced"))})
        return tracks
    except Exception:
        return None


def _filesystem_movie_detail(cfg: dict, history_files: dict, item_id: int) -> dict | None:
    item = next((x for x in _filesystem_movie_items(cfg, history_files) if int(x.get("id", -1)) == item_id), None)
    if not item:
        return None
    return {
        "kind": "movie", **item, "runtime": None, "genres": [], "overview": item.get("overview") or "Local media file. Connect Radarr for posters, overview, genres, and richer metadata.",
        "tracks": _probe_tracks(str(item.get("media_path") or "")), "report": _state_for_path(history_files, str(item.get("media_path") or "")).get("report"),
    }


def _episode_numbers(path: Path) -> tuple[int | None, int | None]:
    m = re.search(r"(?i)\bS(\d{1,2})E(\d{1,3})\b", path.stem)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(?i)\b(\d{1,2})x(\d{1,3})\b", path.stem)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _filesystem_series_detail(cfg: dict, history_files: dict, item_id: int) -> dict | None:
    item = next((x for x in _filesystem_series_items(cfg, history_files) if int(x.get("id", -1)) == item_id), None)
    if not item:
        return None
    root = Path(str(item.get("path") or ""))
    episodes = []
    for media in _iter_media_under(root, cfg) or []:
        rec = _state_for_path(history_files, str(media))
        season, episode = _episode_numbers(media)
        title, _year = _pretty_media_name(media.stem)
        try:
            size = media.stat().st_size
        except OSError:
            size = None
        episodes.append({
            "id": _fs_catalog_id(media), "season": season, "episode": episode, "title": title or media.stem,
            "air_date": None, "monitored": True, "has_file": True, "media_path": str(media), "size": size,
            "quality": _media_quality_hint(media), "censorarr_status": _episode_status(rec, True),
            "censorarr_time": rec.get("time"), "detections": rec.get("detections") or rec.get("detection_count"),
            "report": rec.get("report"),
        })
    episodes.sort(key=lambda ep: (ep.get("season") if ep.get("season") is not None else 9999, ep.get("episode") if ep.get("episode") is not None else 9999, str(ep.get("title", "")).lower()))
    cleaned = sum(1 for ep in episodes if ep["censorarr_status"] in {"applied", "clean-exists", "skipped-clean-exists"})
    no_prof = sum(1 for ep in episodes if ep["censorarr_status"] == "no-detections")
    failed = sum(1 for ep in episodes if ep["censorarr_status"] in {"error", "cancelled"})
    return {
        "kind": "series", **item, "runtime": None, "certification": "", "genres": [], "network": "",
        "status": "", "overview": "Local TV folder. Connect Sonarr for posters, episode names, air dates, and richer metadata.",
        "episodes": episodes, "summary": {"cleaned": cleaned, "no_profanity": no_prof, "failed": failed, "total": len(episodes)},
    }


def _bazarr_movie_summary(cfg: dict) -> dict[int, dict]:
    out: dict[int, dict] = {}
    try:
        for row in integ.bazarr_movies(cfg):
            rid = row.get("radarrId")
            if rid is None: continue
            missing = row.get("missing_subtitles", row.get("missingSubtitles", []))
            subs = row.get("subtitles", [])
            out[int(rid)] = {"linked": True, "missing": missing if isinstance(missing, list) else [], "subtitles": subs if isinstance(subs, list) else []}
    except Exception:
        pass
    return out


def _bazarr_series_summary(cfg: dict) -> set[int]:
    out: set[int] = set()
    try:
        for row in integ.bazarr_series(cfg):
            sid = row.get("sonarrSeriesId")
            if sid is not None: out.add(int(sid))
    except Exception:
        pass
    return out


@app.get("/api/media-catalog")
def media_catalog(kind: str = Query("movies", pattern="^(movies|series)$"), force: bool = False, _: bool = Depends(auth)):
    cfg = pc.load_config(CONFIG)
    state_files = read_json(STATE, {"files": {}}).get("files", {})
    history_files = _current_media_history(cfg, state_files)

    if kind == "movies":
        if integ.arr_enabled(cfg, "radarr"):
            try:
                baz = _bazarr_movie_summary(cfg)
                items = []
                matched_history_paths: set[str] = set()
                for x in integ.radarr_movies(cfg, force=force):
                    mf = x.get("movieFile") or {}
                    mapped_file = str(x.get("_mapped_file") or "")
                    mapped_folder = str(x.get("_mapped_path") or "")
                    rec, matched_path = _history_record_for_movie(history_files, mapped_file, mapped_folder)
                    if matched_path:
                        matched_history_paths.add(_norm_media_path(matched_path))
                    quality = ""
                    try: quality = str((mf.get("quality") or {}).get("quality", {}).get("name", ""))
                    except Exception: pass
                    bid = x.get("id")
                    b = baz.get(int(bid), {}) if bid is not None else {}
                    items.append({
                        "id": bid, "source": "radarr", "title": x.get("title") or "Untitled", "year": x.get("year"),
                        "sortTitle": x.get("sortTitle") or x.get("title") or "", "poster": _poster_url(x), "fanart": _image_url(x, "fanart", "banner"),
                        "monitored": bool(x.get("monitored", False)), "certification": x.get("certification") or "",
                        "path": str(x.get("_mapped_path") or ""), "media_path": mapped_file,
                        "has_file": bool(x.get("hasFile", bool(mf))), "size": mf.get("size"), "quality": quality,
                        "censorarr_status": rec.get("status") or ("unprocessed" if mapped_file else "missing-file"),
                        "censorarr_time": rec.get("time"), "rating": rec.get("rating") or x.get("certification") or "",
                        "detections": rec.get("detections") or rec.get("detection_count"),
                        "bazarr_linked": bool(b.get("linked")), "bazarr_missing": b.get("missing", []),
                        "radarr_url": integ.arr_open_url(cfg, "radarr", x.get("titleSlug") or bid),
                        "overview": x.get("overview") or "",
                    })
                # Censorarr's scanner can legitimately know about a current movie file that Radarr
                # does not expose as its movieFile (for example a path-mapping mismatch or a local-only
                # media file). Surface those touched files instead of silently dropping them. This keeps
                # the Movies summary and Dashboard counts explainable and lets the user inspect the path.
                local_by_path = {_norm_media_path(x.get("media_path", "")): x for x in _filesystem_movie_items(cfg, history_files)}
                unmatched = 0
                for hist_path, hist_rec in history_files.items():
                    norm_hist = _norm_media_path(hist_path)
                    if norm_hist in matched_history_paths:
                        continue
                    try:
                        if pc.media_type_for(Path(norm_hist), cfg) != "movie":
                            continue
                    except Exception:
                        continue
                    local_item = local_by_path.get(norm_hist)
                    if not local_item:
                        continue
                    # Only add files Censorarr has actually tracked. Untouched local files remain
                    # represented by Radarr when Radarr is enabled, avoiding duplicate library cards.
                    if not str(hist_rec.get("status") or "").strip():
                        continue
                    local_item = dict(local_item)
                    local_item["source"] = "filesystem-unmatched"
                    local_item["local_only"] = True
                    items.append(local_item)
                    unmatched += 1

                items.sort(key=lambda z: str(z.get("sortTitle", "")).lower())
                msg = "Movie metadata is provided by Radarr."
                if unmatched:
                    msg += f" {unmatched} current Censorarr-tracked movie file(s) could not be matched to a Radarr movieFile and are shown as Local only."
                return {"kind": kind, "source": "radarr", "integration_enabled": True, "items": items,
                        "unmatched_local_count": unmatched, "message": msg}
            except Exception as e:
                # Media browsing should remain useful when an optional integration is offline.
                items = _filesystem_movie_items(cfg, history_files)
                return {"kind": kind, "source": "filesystem", "integration_enabled": True, "items": items,
                        "message": f"Radarr is enabled but unavailable ({e}). Showing local movie folders instead."}
        items = _filesystem_movie_items(cfg, history_files)
        return {"kind": kind, "source": "filesystem", "integration_enabled": False, "items": items,
                "message": "Showing local movie folders. Radarr is optional; connect it only if you want posters and richer metadata."}

    if integ.arr_enabled(cfg, "sonarr"):
        try:
            baz_series = _bazarr_series_summary(cfg)
            items = []
            for x in integ.sonarr_series(cfg, force=force):
                root = str(x.get("_mapped_path") or "").replace("\\", "/").rstrip("/")
                related = _records_under_root(history_files, root)
                clean_terminal = {"applied", "clean-exists", "skipped-clean-exists"}
                cleaned = sum(1 for rec in related if _normalize_media_status(rec.get("status")) in clean_terminal)
                no_profanity = sum(1 for rec in related if _normalize_media_status(rec.get("status")) == "no-detections")
                failed = sum(1 for rec in related if _normalize_media_status(rec.get("status")) in {"error", "cancelled"})
                stats = x.get("statistics") or {}
                sid = x.get("id")
                items.append({
                    "id": sid, "source": "sonarr", "title": x.get("title") or "Untitled", "year": x.get("year"),
                    "sortTitle": x.get("sortTitle") or x.get("title") or "", "poster": _poster_url(x), "fanart": _image_url(x, "fanart", "banner"),
                    "monitored": bool(x.get("monitored", False)), "network": x.get("network") or "",
                    "path": root, "episode_file_count": stats.get("episodeFileCount"), "episode_count": stats.get("episodeCount"),
                    "censorarr_touched": len(related), "censorarr_cleaned": cleaned, "censorarr_no_profanity": no_profanity, "censorarr_failed": failed,
                    "bazarr_linked": int(sid) in baz_series if sid is not None else False,
                    "sonarr_url": integ.arr_open_url(cfg, "sonarr", x.get("titleSlug") or sid), "overview": x.get("overview") or "",
                })
            items.sort(key=lambda z: str(z.get("sortTitle", "")).lower())
            return {"kind": kind, "source": "sonarr", "integration_enabled": True, "items": items,
                    "message": "TV metadata is provided by Sonarr."}
        except Exception as e:
            items = _filesystem_series_items(cfg, history_files)
            return {"kind": kind, "source": "filesystem", "integration_enabled": True, "items": items,
                    "message": f"Sonarr is enabled but unavailable ({e}). Showing local TV folders instead."}
    items = _filesystem_series_items(cfg, history_files)
    return {"kind": kind, "source": "filesystem", "integration_enabled": False, "items": items,
            "message": "Showing local TV folders. Sonarr is optional; connect it only if you want posters and richer metadata."}


def _episode_status(rec: dict, has_file: bool) -> str:
    if rec.get("status"):
        return str(rec.get("status"))
    return "unprocessed" if has_file else "missing-file"


@app.get("/api/media-detail")
def media_detail(kind: str = Query(..., pattern="^(movie|series)$"), id: int = Query(..., ge=0), _: bool = Depends(auth)):
    cfg = pc.load_config(CONFIG)
    state_files = read_json(STATE, {"files": {}}).get("files", {})
    history_files = _current_media_history(cfg, state_files)
    if kind == "movie":
        if integ.arr_enabled(cfg, "radarr"):
            try:
                x = next((m for m in integ.radarr_movies(cfg) if int(m.get("id", -1)) == id), None)
            except Exception:
                x = None
            if x:
                mf = x.get("movieFile") or {}
                media_path = str(x.get("_mapped_file") or "")
                rec, matched_path = _history_record_for_movie(history_files, media_path, str(x.get("_mapped_path") or ""))
                if matched_path:
                    media_path = matched_path
                quality = ""
                try: quality = str((mf.get("quality") or {}).get("quality", {}).get("name", ""))
                except Exception: pass
                return {
                    "kind": "movie", "source": "radarr", "id": id, "title": x.get("title") or "Untitled", "year": x.get("year"),
                    "poster": _poster_url(x), "fanart": _image_url(x, "fanart", "banner"), "overview": x.get("overview") or "",
                    "runtime": x.get("runtime"), "certification": x.get("certification") or "", "genres": x.get("genres") or [],
                    "monitored": bool(x.get("monitored", False)), "path": str(x.get("_mapped_path") or ""), "media_path": media_path,
                    "has_file": bool(x.get("hasFile", bool(mf))), "size": mf.get("size"), "quality": quality,
                    "censorarr_status": rec.get("status") or ("unprocessed" if media_path else "missing-file"), "censorarr_time": rec.get("time"),
                    "rating": rec.get("rating") or x.get("certification") or "", "detections": rec.get("detections") or rec.get("detection_count"),
                    "report": rec.get("report"), "radarr_url": integ.arr_open_url(cfg, "radarr", x.get("titleSlug") or id),
                    "tracks": _probe_tracks(media_path),
                }
        detail = _filesystem_movie_detail(cfg, history_files, id)
        if detail:
            return detail
        raise HTTPException(404, "Movie not found in the local Movies folder")

    if integ.arr_enabled(cfg, "sonarr"):
        try:
            x = next((m for m in integ.sonarr_series(cfg) if int(m.get("id", -1)) == id), None)
        except Exception:
            x = None
        if x:
            episodes = []
            try:
                source_episodes = integ.sonarr_episodes(cfg, id)
            except Exception:
                source_episodes = []
            for ep in source_episodes:
                ef = ep.get("episodeFile") or {}
                media_path = str(ef.get("_mapped_file") or "")
                rec = _state_for_path(history_files, media_path)
                quality = ""
                try: quality = str((ef.get("quality") or {}).get("quality", {}).get("name", ""))
                except Exception: pass
                episodes.append({
                    "id": ep.get("id"), "season": ep.get("seasonNumber"), "episode": ep.get("episodeNumber"),
                    "title": ep.get("title") or "Untitled", "air_date": ep.get("airDateUtc") or ep.get("airDate"),
                    "monitored": bool(ep.get("monitored", False)), "has_file": bool(ep.get("hasFile", bool(ef))),
                    "media_path": media_path, "size": ef.get("size"), "quality": quality,
                    "censorarr_status": _episode_status(rec, bool(media_path or ef)), "censorarr_time": rec.get("time"),
                    "detections": rec.get("detections") or rec.get("detection_count"), "report": rec.get("report"),
                })
            stats = x.get("statistics") or {}
            cleaned = sum(1 for ep in episodes if ep["censorarr_status"] in {"applied", "clean-exists", "skipped-clean-exists"})
            no_prof = sum(1 for ep in episodes if ep["censorarr_status"] == "no-detections")
            failed = sum(1 for ep in episodes if ep["censorarr_status"] in {"error", "cancelled"})
            return {
                "kind": "series", "source": "sonarr", "id": id, "title": x.get("title") or "Untitled", "year": x.get("year"),
                "poster": _poster_url(x), "fanart": _image_url(x, "fanart", "banner"), "overview": x.get("overview") or "",
                "runtime": x.get("runtime"), "certification": x.get("certification") or "", "genres": x.get("genres") or [],
                "network": x.get("network") or "", "status": x.get("status") or "", "monitored": bool(x.get("monitored", False)),
                "path": str(x.get("_mapped_path") or ""), "episode_file_count": stats.get("episodeFileCount"),
                "episode_count": stats.get("episodeCount"), "sonarr_url": integ.arr_open_url(cfg, "sonarr", x.get("titleSlug") or id),
                "episodes": episodes, "summary": {"cleaned": cleaned, "no_profanity": no_prof, "failed": failed, "total": len(episodes)},
            }
    detail = _filesystem_series_detail(cfg, history_files, id)
    if detail:
        return detail
    raise HTTPException(404, "TV show not found in the local TV folder")


@app.get("/api/integrations/plex/sessions")
def plex_sessions(_: bool = Depends(auth)):
    try: return {"ok":True,"sessions":integ.plex_active_sessions(pc.load_config(CONFIG))}
    except Exception as e: raise HTTPException(400,str(e))


@app.post("/api/notifications/test")
def notification_test(_: bool = Depends(auth)):
    cfg=pc.load_config(CONFIG); cfg=pc.deep_merge(cfg,{"notifications":{"enabled":True,"events":["test"]}}); integ.notify("test","Censorarr test notification",cfg); return {"ok":True}


@app.get("/api/update-info")
def update_info(_: bool = Depends(auth)):
    return {"version":VERSION,"update_method":"fast-bind-mount","message":"Code-only updates use the existing runtime image: replace /app files and restart. Rebuild only when Dockerfile or requirements change."}
