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
PROGRAM_DATA = _RealPath(os.environ.get("PROGRAMDATA") or (EXE_DIR / "ProgramData"))
DATA_ROOT = _RealPath(os.environ.get("CENSORARR_DATA_DIR") or (PROGRAM_DATA / APP_NAME))
CONFIG_DIR = DATA_ROOT / "config"
WORK_DIR = DATA_ROOT / "work"
MODELS_DIR = CONFIG_DIR / "models"
LOG_DIR = DATA_ROOT / "logs"
WINDOWS_LOG = LOG_DIR / "windows-launcher.log"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
SECRETS_FILE = CONFIG_DIR / "secrets.json"
WEB_URL = f"http://127.0.0.1:{int(os.environ.get('CENSORARR_PORT', DEFAULT_PORT))}"

for directory in (DATA_ROOT, CONFIG_DIR, WORK_DIR, MODELS_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def _ensure_stdio() -> None:
    """Give GUI/frozen builds real streams for libraries that expect a console.

    PyInstaller's --windowed mode intentionally sets sys.stdout/sys.stderr to None
    when launched normally from Explorer. Uvicorn's default logging formatter
    calls .isatty() on those streams, so provide a line-buffered log file instead.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    stream = open(WINDOWS_LOG, "a", encoding="utf-8", errors="replace", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


_ensure_stdio()

# Keep the native build fully self-contained and put bundled ffmpeg/ffprobe first.
os.environ["PATH"] = str(EXE_DIR) + os.pathsep + os.environ.get("PATH", "")
os.environ.setdefault("CENSORARR_CONFIG", str(CONFIG_FILE))
os.environ.setdefault("CENSORARR_SECRETS", str(SECRETS_FILE))
os.environ.setdefault("HF_HOME", str(MODELS_DIR))
os.environ.setdefault("XDG_CACHE_HOME", str(MODELS_DIR))
# Hugging Face's default cache uses symlinks. Those can be unreliable for a normal
# non-elevated Windows desktop process, leaving a snapshot whose model.bin points at
# a missing/unreadable blob. Force real files into snapshots and use regular HTTP.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("CENSORARR_PLATFORM", "windows")


def _repair_broken_whisper_cache() -> None:
    """Remove only unusable Faster-Whisper repo caches left by older Windows builds.

    A valid Hugging Face snapshot must contain a readable model.bin. If a snapshot
    exists but model.bin is missing/broken, remove that model repo so the next
    WhisperModel construction performs a clean no-symlink download.
    """
    try:
        repos = list(MODELS_DIR.glob("models--Systran--faster-whisper-*"))
    except OSError:
        return
    for repo in repos:
        snapshots = repo / "snapshots"
        if not snapshots.is_dir():
            continue
        broken = False
        try:
            snapshot_dirs = [p for p in snapshots.iterdir() if p.is_dir()]
        except OSError:
            snapshot_dirs = []
        for snapshot in snapshot_dirs:
            model_file = snapshot / "model.bin"
            try:
                if not model_file.is_file() or model_file.stat().st_size < 1024 * 1024:
                    broken = True
                    break
            except OSError:
                broken = True
                break
        if broken:
            try:
                with open(WINDOWS_LOG, "a", encoding="utf-8", errors="replace") as log:
                    log.write(f"Repairing broken Whisper cache: {repo}\n")
            except OSError:
                pass
            shutil.rmtree(repo, ignore_errors=True)


_repair_broken_whisper_cache()

# Linux containers expose these identity helpers; the existing UI reports them for diagnostics.
# Windows has no equivalent uid/gid concept, so expose harmless sentinel values.
for _name in ("getuid", "geteuid", "getgid", "getegid"):
    if not hasattr(os, _name):
        setattr(os, _name, lambda: -1)


class _MappedPathFactory:
    """Map Censorarr's container-internal paths to native Windows data locations."""

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
    """Translate a Linux/container path passed as a plain string into its Windows location.

    This is separate from MappedPath because third-party libraries such as
    faster-whisper receive download_root as a string and never construct a pathlib.Path
    through Censorarr's patched Path symbol.
    """
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

    # Make future Path(...) calls understand Censorarr's logical container paths.
    for module in (pc, integ, remote_asr, secret_store, subassist, webapp):
        if hasattr(module, "Path"):
            module.Path = MappedPath

    # Rebind constants that were created at import time before the mapping above.
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

    webapp.CONFIG = CONFIG_FILE
    webapp.LOG = CONFIG_DIR / "censorarr.log"
    webapp.HEARTBEAT = CONFIG_DIR / "heartbeat.json"
    webapp.STATE = CONFIG_DIR / "state.json"
    webapp.QUEUE = CONFIG_DIR / "manual_queue.json"
    webapp.CANCELLED = CONFIG_DIR / "cancelled.json"
    webapp.PAUSED = CONFIG_DIR / "paused.flag"
    webapp.SCAN_NOW = CONFIG_DIR / "scan-now.flag"
    webapp.RESTART_AFTER_CURRENT = CONFIG_DIR / "restart-after-current.flag"
    webapp.SUBTITLE_WAIT = CONFIG_DIR / "subtitle_wait.json"
    webapp.INVENTORY = CONFIG_DIR / "inventory.json"
    webapp.CUSTOM_PROFANITY = CONFIG_DIR / "custom_profanity.json"
    webapp.PROFANITY_OVERRIDES = CONFIG_DIR / "profanity_overrides.json"
    webapp.USER_EXCEPTIONS = CONFIG_DIR / "user_exceptions.json"
    webapp.STATIC = BUNDLE_ROOT / "static"
    webapp.FIRST_RUN = CONFIG_DIR / ".censorarr-first-run"

    # A native first run copies the same shipped configuration/dictionary into ProgramData.
    def ensure_config_windows(config_path):
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

    pc.ensure_config = ensure_config_windows

    # The main worker creates WhisperModel directly with download_root="/config/models".
    # Patch the module-level constructor so all local/fallback model loads use ProgramData,
    # including paths passed to faster-whisper as plain strings.
    original_whisper_model = pc.WhisperModel

    def whisper_model_windows(model_size_or_path, *args, **kwargs):
        model_size_or_path = _map_container_path_string(model_size_or_path)
        download_root = kwargs.get("download_root")
        if download_root is None:
            kwargs["download_root"] = str(MODELS_DIR)
        else:
            kwargs["download_root"] = _map_container_path_string(download_root)
        return original_whisper_model(model_size_or_path, *args, **kwargs)

    pc.WhisperModel = whisper_model_windows

    # Keep faster-whisper models under ProgramData rather than C:\\config.
    model_cache = {}

    def local_model_windows(cfg: dict, existing=None):
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
                key[0], device=key[1], compute_type=key[2], download_root=str(MODELS_DIR)
            )
        return model_cache[key]

    pc._local_model = local_model_windows

    def configured_media_roots():
        try:
            cfg = pc.load_config(CONFIG_FILE)
        except Exception:
            return [], False
        completed = bool((cfg.get("setup", {}) or {}).get("completed", True))
        roots = []
        for raw in pc.all_media_roots(cfg):
            text = str(raw or "").strip()
            if text in {"/media", "/tv"}:
                continue
            p = _RealPath(text)
            if p.is_absolute():
                try:
                    p = p.resolve()
                except Exception:
                    pass
                roots.append(p)
        return roots, completed

    def allowed_media_mounts_windows():
        roots, _completed = configured_media_roots()
        if roots:
            return roots
        videos = _RealPath(os.environ.get("USERPROFILE", str(_RealPath.home()))) / "Videos"
        return [videos if videos.exists() else _RealPath.home()]

    def safe_media_path_windows(raw: str, must_exist: bool = True):
        roots, completed = configured_media_roots()
        text = str(raw or "").strip()
        if text in {"", "/media"}:
            p = roots[0] if roots else allowed_media_mounts_windows()[0]
        elif text == "/tv":
            p = roots[1] if len(roots) > 1 else (roots[0] if roots else allowed_media_mounts_windows()[0])
        else:
            p = _RealPath(text)
            if not p.is_absolute():
                base = roots[0] if roots else allowed_media_mounts_windows()[0]
                p = base / p
        try:
            resolved = p.resolve(strict=must_exist)
        except FileNotFoundError:
            raise webapp.HTTPException(404, "Path does not exist")

        # First-run setup is localhost-only, so allow selecting any existing absolute folder.
        # Once setup is complete, all browse/process calls are constrained to configured roots.
        if completed and roots:
            if not any(resolved == root or root in resolved.parents for root in roots):
                raise webapp.HTTPException(403, "Only paths inside the configured media roots are allowed")
        return resolved

    webapp._allowed_media_mounts = allowed_media_mounts_windows
    webapp.safe_media_path = safe_media_path_windows

    # Spawn the worker as another copy of this same frozen executable.
    def supervisor_start_windows(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return
            env = os.environ.copy()
            env.pop("DRY_RUN", None)
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--worker"]
            else:
                cmd = [sys.executable, str(_RealPath(__file__).resolve()), "--worker"]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.proc = subprocess.Popen(
                cmd,
                env=env,
                cwd=str(EXE_DIR),
                creationflags=creationflags,
            )
        if not self.monitor_thread or not self.monitor_thread.is_alive():
            self.monitor_thread = threading.Thread(
                target=self._monitor, daemon=True, name="worker-supervisor"
            )
            self.monitor_thread.start()

    webapp.WorkerSupervisor.start = supervisor_start_windows

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
        # censorarr.main() has its own parser for --once/--file/--version and should not
        # see the launcher's private --worker switch.
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
        host="127.0.0.1",
        port=int(os.environ.get("CENSORARR_PORT", DEFAULT_PORT)),
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
