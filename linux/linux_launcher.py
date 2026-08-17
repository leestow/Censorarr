from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path as _RealPath


APP_NAME = "Censorarr"
DEFAULT_PORT = 8087


def _bundle_root() -> _RealPath:
    if getattr(sys, "frozen", False):
        return _RealPath(getattr(sys, "_MEIPASS", _RealPath(sys.executable).resolve().parent))
    return _RealPath(__file__).resolve().parents[1]


BUNDLE_ROOT = _bundle_root()
EXE_DIR = _RealPath(sys.executable).resolve().parent if getattr(sys, "frozen", False) else BUNDLE_ROOT
DATA_ROOT = _RealPath(os.environ.get("CENSORARR_DATA_DIR") or "/var/lib/censorarr")
CONFIG_DIR = DATA_ROOT / "config"
WORK_DIR = DATA_ROOT / "work"
MODELS_DIR = CONFIG_DIR / "models"
LOG_DIR = DATA_ROOT / "logs"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
SECRETS_FILE = CONFIG_DIR / "secrets.json"
WEB_HOST = os.environ.get("CENSORARR_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("CENSORARR_PORT", DEFAULT_PORT))
WEB_URL = f"http://127.0.0.1:{WEB_PORT}"

for directory in (DATA_ROOT, CONFIG_DIR, WORK_DIR, MODELS_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("CENSORARR_CONFIG", str(CONFIG_FILE))
os.environ.setdefault("CENSORARR_SECRETS", str(SECRETS_FILE))
os.environ.setdefault("HF_HOME", str(MODELS_DIR))
os.environ.setdefault("XDG_CACHE_HOME", str(MODELS_DIR))
os.environ.setdefault("CENSORARR_PLATFORM", "linux-native")


class _MappedPathFactory:
    """Map Censorarr's logical container paths to native Linux data locations."""

    _prefixes = {
        "/config": CONFIG_DIR,
        "/work": WORK_DIR,
        "/app": BUNDLE_ROOT,
    }

    def __call__(self, *parts):
        if not parts:
            return _RealPath()
        first = parts[0]
        try:
            raw = os.fspath(first)
        except TypeError:
            return _RealPath(*parts)
        if isinstance(raw, str):
            normalized = raw.replace("\\", "/")
            for logical, target in self._prefixes.items():
                if normalized == logical or normalized.startswith(logical + "/"):
                    suffix = normalized[len(logical):].lstrip("/")
                    mapped = target / suffix if suffix else target
                    return _RealPath(mapped, *parts[1:])
        return _RealPath(*parts)

    def __getattr__(self, name):
        return getattr(_RealPath, name)


MappedPath = _MappedPathFactory()


def _map_container_path_string(value):
    if value is None:
        return None
    try:
        raw = os.fspath(value)
    except TypeError:
        return value
    if not isinstance(raw, str):
        return value
    normalized = raw.replace("\\", "/")
    for logical, target in _MappedPathFactory._prefixes.items():
        if normalized == logical or normalized.startswith(logical + "/"):
            suffix = normalized[len(logical):].lstrip("/")
            return str(target / suffix) if suffix else str(target)
    return value


def _prepare_modules():
    import censorarr as pc
    import integrations as integ
    import remote_asr
    import secrets_store as secret_store
    import subtitle_assist as subassist
    import webapp
    import webapp_core as core

    # Native Linux uses the current webapp.py wrapper plus webapp_core.py.
    # Patch both modules so all logical container paths resolve into /var/lib/censorarr.
    for module in (pc, integ, remote_asr, secret_store, subassist, webapp, core):
        if hasattr(module, "Path"):
            module.Path = MappedPath

    secret_store.SECRETS_FILE = SECRETS_FILE
    remote_asr.ACTIVE_JOB_FILE = CONFIG_DIR / "remote_asr_active.json"

    pc.CONTROL_DIR = CONFIG_DIR
    pc.PAUSED_FLAG = CONFIG_DIR / "paused.flag"
    pc.SCAN_NOW_FLAG = CONFIG_DIR / "scan-now.flag"
    pc.MANUAL_QUEUE = CONFIG_DIR / "manual_queue.json"
    pc.CANCELLED_FILE = CONFIG_DIR / "cancelled.json"
    pc.SUBTITLE_WAIT_FILE = CONFIG_DIR / "subtitle_wait.json"
    pc.INVENTORY_FILE = CONFIG_DIR / "inventory.json"
    pc.QUEUE_ACTIVITY_FILE = CONFIG_DIR / "queue-active.flag"

    core.CONFIG = CONFIG_FILE
    core.LOG = CONFIG_DIR / "censorarr.log"
    core.HEARTBEAT = CONFIG_DIR / "heartbeat.json"
    core.STATE = CONFIG_DIR / "state.json"
    core.QUEUE = CONFIG_DIR / "manual_queue.json"
    core.CANCELLED = CONFIG_DIR / "cancelled.json"
    core.PAUSED = CONFIG_DIR / "paused.flag"
    core.SCAN_NOW = CONFIG_DIR / "scan-now.flag"
    core.RESTART_AFTER_CURRENT = CONFIG_DIR / "restart-after-current.flag"
    core.SUBTITLE_WAIT = CONFIG_DIR / "subtitle_wait.json"
    core.INVENTORY = CONFIG_DIR / "inventory.json"
    core.CUSTOM_PROFANITY = CONFIG_DIR / "custom_profanity.json"
    core.PROFANITY_OVERRIDES = CONFIG_DIR / "profanity_overrides.json"
    core.USER_EXCEPTIONS = CONFIG_DIR / "user_exceptions.json"
    core.STATIC = BUNDLE_ROOT / "static"
    core.FIRST_RUN = CONFIG_DIR / ".censorarr-first-run"

    def ensure_config_linux(config_path):
        config_path = _RealPath(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if not config_path.exists():
            shutil.copy2(BUNDLE_ROOT / "config.example.yaml", config_path)
            try:
                (config_path.parent / ".censorarr-first-run").write_text("1\n", encoding="utf-8")
            except OSError:
                pass
        profanity_path = config_path.parent / "en.json"
        if not profanity_path.exists():
            shutil.copy2(BUNDLE_ROOT / "en.json", profanity_path)

    pc.ensure_config = ensure_config_linux

    original_whisper_model = pc.WhisperModel

    def whisper_model_linux(model_size_or_path, *args, **kwargs):
        model_size_or_path = _map_container_path_string(model_size_or_path)
        download_root = kwargs.get("download_root")
        kwargs["download_root"] = (
            str(MODELS_DIR)
            if download_root is None
            else _map_container_path_string(download_root)
        )
        return original_whisper_model(model_size_or_path, *args, **kwargs)

    pc.WhisperModel = whisper_model_linux

    model_cache = {}

    def local_model_linux(cfg: dict, existing=None):
        if existing is not None:
            return existing
        wcfg = cfg.get("whisper", {})
        key = (
            str(wcfg.get("model", "small")),
            str(wcfg.get("device", "cpu")),
            str(wcfg.get("compute_type", "int8")),
        )
        if key not in model_cache:
            pc.logging.info("Loading local Whisper fallback model %s on %s/%s", *key)
            model_cache[key] = pc.WhisperModel(
                key[0],
                device=key[1],
                compute_type=key[2],
                download_root=str(MODELS_DIR),
            )
        return model_cache[key]

    pc._local_model = local_model_linux

    def configured_media_roots():
        try:
            cfg = pc.load_config(CONFIG_FILE)
        except Exception:
            return [], False
        completed = bool((cfg.get("setup", {}) or {}).get("completed", True))
        roots = []
        for raw in pc.all_media_roots(cfg):
            text = str(raw or "").strip()
            if not text or text in {"/media", "/tv"}:
                continue
            p = _RealPath(text)
            if p.is_absolute():
                try:
                    p = p.resolve()
                except Exception:
                    pass
                if p not in roots:
                    roots.append(p)
        return roots, completed

    def allowed_media_mounts_linux():
        roots, completed = configured_media_roots()
        if completed and roots:
            return roots
        # Native Linux binds to localhost by default. During first-run setup, allow
        # browsing from / so users can choose /mnt, /media, /srv, /data, /home, etc.
        return [_RealPath("/")]

    def safe_media_path_linux(raw: str, must_exist: bool = True):
        roots, completed = configured_media_roots()
        text = str(raw or "").strip()
        if text in {"", "/media", "/tv"}:
            p = roots[0] if roots else _RealPath("/")
        else:
            p = _RealPath(text)
            if not p.is_absolute():
                p = (roots[0] if roots else _RealPath("/")) / p
        try:
            resolved = p.resolve(strict=must_exist)
        except FileNotFoundError:
            raise core.HTTPException(404, "Path does not exist")

        if completed and roots:
            if not any(resolved == root or root in resolved.parents for root in roots):
                raise core.HTTPException(
                    403, "Only paths inside the configured media roots are allowed"
                )
        return resolved

    # Existing core routes and the cross-platform folder-picker wrapper resolve these
    # globals at request time, so patch both.
    core._allowed_media_mounts = allowed_media_mounts_linux
    core.safe_media_path = safe_media_path_linux
    webapp._allowed_media_mounts = allowed_media_mounts_linux
    webapp.safe_media_path = safe_media_path_linux

    def supervisor_start_linux(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return
            env = os.environ.copy()
            env.pop("DRY_RUN", None)
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--worker"]
            else:
                cmd = [sys.executable, str(_RealPath(__file__).resolve()), "--worker"]
            self.proc = subprocess.Popen(cmd, env=env, cwd=str(EXE_DIR))
        if not self.monitor_thread or not self.monitor_thread.is_alive():
            self.monitor_thread = threading.Thread(
                target=self._monitor, daemon=True, name="worker-supervisor"
            )
            self.monitor_thread.start()

    core.WorkerSupervisor.start = supervisor_start_linux

    return pc, webapp


def _server_responding() -> bool:
    try:
        with urllib.request.urlopen(WEB_URL + "/api/health", timeout=0.6) as response:
            return 200 <= int(response.status) < 500
    except Exception:
        return False


def _open_when_ready(timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _server_responding():
            webbrowser.open(WEB_URL)
            return
        time.sleep(0.4)
    webbrowser.open(WEB_URL)


def _run_worker(pc) -> int:
    original_argv = sys.argv[:]
    try:
        sys.argv = [original_argv[0]]
        return int(pc.main())
    finally:
        sys.argv = original_argv


def _run_server(webapp, open_browser: bool) -> int:
    if _server_responding():
        if open_browser:
            webbrowser.open(WEB_URL)
        return 0

    if open_browser:
        threading.Thread(target=_open_when_ready, daemon=True).start()

    import uvicorn

    uvicorn.run(
        webapp.app,
        host=WEB_HOST,
        port=WEB_PORT,
        workers=1,
        log_level="info",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--open-browser", action="store_true")
    args, _unknown = parser.parse_known_args()

    pc, webapp = _prepare_modules()
    if args.worker:
        return _run_worker(pc)
    return _run_server(webapp, open_browser=args.open_browser and not args.background)


if __name__ == "__main__":
    raise SystemExit(main())
