from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable

mp.freeze_support()

APP_NAME = "Censorarr GPU Worker"
VERSION = "1.6.5"
DEFAULT_PORT = 9000

WINDOWS = os.name == "nt"
if WINDOWS:
    DATA_ROOT = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "CensorarrGPUWorker"
    DEFAULT_CONFIG = DATA_ROOT / "worker.env"
else:
    DATA_ROOT = Path("/var/lib/censorarr-gpu-worker")
    DEFAULT_CONFIG = Path("/etc/censorarr-gpu-worker.env")

CONFIG_FILE = Path(os.environ.get("CENSORARR_GPU_CONFIG") or DEFAULT_CONFIG)
RUNTIME_DIR = Path(os.environ.get("ASR_RUNTIME_DIR") or (DATA_ROOT / "runtime"))
MODEL_DIR = Path(os.environ.get("ASR_MODEL_DIR") or (DATA_ROOT / "models"))

BUNDLE_ROOT = (
    Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
MANIFEST_FILE = Path(
    os.environ.get("CENSORARR_GPU_RUNTIME_MANIFEST")
    or (Path(sys.executable).resolve().parent / "runtime-manifest.json" if getattr(sys, "frozen", False)
        else BUNDLE_ROOT / "runtime-manifest.json")
)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _ensure_config(path: Path = CONFIG_FILE) -> Path:
    # Create only the paths selected by the active configuration/environment.
    # The Debian package's postinst owns creation of /var/lib/censorarr-gpu-worker;
    # native/CI launches may intentionally redirect all writable state elsewhere.
    path.parent.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path

    token = secrets.token_urlsafe(36)
    text = "\n".join([
        "# Censorarr GPU Worker native configuration",
        "# Use the same ASR_WORKER_TOKEN in the main Censorarr transcription settings.",
        f"ASR_WORKER_TOKEN={token}",
        "ASR_MODEL=small.en",
        "ASR_COMPUTE_TYPE=int8_float32",
        f"ASR_MODEL_DIR={MODEL_DIR}",
        "ASR_CHUNK_SECONDS=600",
        "ASR_CHUNK_OVERLAP_SECONDS=2",
        "ASR_MAX_UPLOAD_GB=2",
        f"ASR_RUNTIME_DIR={RUNTIME_DIR}",
        "CENSORARR_GPU_HOST=0.0.0.0",
        f"CENSORARR_GPU_PORT={DEFAULT_PORT}",
        "",
    ])
    path.write_text(text, encoding="utf-8")
    try:
        if not WINDOWS:
            path.chmod(0o640)
    except OSError:
        pass
    return path


def _config_value(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _driver_info() -> tuple[bool, str]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return False, "nvidia-smi was not found. Install a compatible NVIDIA display/compute driver first."
    try:
        proc = subprocess.run(
            [exe, "--query-gpu=name,driver_version", "--format=csv,noheader"],
            text=True, capture_output=True, timeout=15, check=False,
        )
    except Exception as exc:
        return False, f"Could not run nvidia-smi: {exc}"
    text = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode != 0 or not text:
        return False, text or f"nvidia-smi exited with code {proc.returncode}"
    return True, text


def _manifest() -> dict:
    if not MANIFEST_FILE.exists():
        raise RuntimeError(f"NVIDIA runtime manifest is missing: {MANIFEST_FILE}")
    data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    if int(data.get("schema", 0)) != 1:
        raise RuntimeError("Unsupported NVIDIA runtime manifest schema")
    expected = "windows-amd64" if WINDOWS else "linux-amd64"
    if data.get("platform") != expected:
        raise RuntimeError(f"Runtime manifest is for {data.get('platform')}, expected {expected}")
    return data


def _safe_extract(zf: zipfile.ZipFile, destination: Path) -> None:
    base = destination.resolve()
    for member in zf.infolist():
        target = (destination / member.filename).resolve()
        if target != base and base not in target.parents:
            raise RuntimeError(f"Unsafe path in runtime wheel: {member.filename}")
    zf.extractall(destination)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(4 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, expected_sha256: str, expected_size: int | None = None) -> None:
    h = hashlib.sha256()
    done = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": f"Censorarr-GPU-Worker/{VERSION}"})
    with urllib.request.urlopen(req, timeout=60) as response, dest.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if done and done % (100 * 1024 * 1024) < len(chunk):
                total = f"/{expected_size}" if expected_size else ""
                print(f"Downloaded {done}{total} bytes: {dest.name}", flush=True)
    actual = h.hexdigest().lower()
    if actual != expected_sha256.lower():
        try:
            dest.unlink()
        except OSError:
            pass
        raise RuntimeError(f"SHA-256 mismatch for {dest.name}: {actual} != {expected_sha256}")
    if expected_size and dest.stat().st_size != int(expected_size):
        raise RuntimeError(f"Size mismatch for {dest.name}")


def _runtime_library_dirs(runtime_dir: Path = RUNTIME_DIR) -> list[Path]:
    wanted = "bin" if WINDOWS else "lib"
    dirs: list[Path] = []
    if runtime_dir.exists():
        for p in runtime_dir.rglob(wanted):
            if p.is_dir() and p not in dirs:
                dirs.append(p)
    return dirs


def _runtime_ready(runtime_dir: Path = RUNTIME_DIR) -> bool:
    marker = runtime_dir / "runtime-installed.json"
    if not marker.exists():
        return False
    try:
        installed = json.loads(marker.read_text(encoding="utf-8"))
        manifest = _manifest()
    except Exception:
        return False
    expected = [(x.get("name"), x.get("version"), x.get("sha256")) for x in manifest.get("packages", [])]
    actual = [(x.get("name"), x.get("version"), x.get("sha256")) for x in installed.get("packages", [])]
    return bool(expected) and expected == actual and bool(_runtime_library_dirs(runtime_dir))


def install_runtime(*, require_driver: bool = True) -> int:
    if os.environ.get("CENSORARR_GPU_SKIP_RUNTIME_INSTALL") == "1":
        print("Skipping NVIDIA runtime download because CENSORARR_GPU_SKIP_RUNTIME_INSTALL=1")
        return 0

    if require_driver:
        ok, info = _driver_info()
        if not ok:
            print("NVIDIA driver check failed:", info, file=sys.stderr)
            print("The worker was installed, but the CUDA runtime was not downloaded.", file=sys.stderr)
            return 3
        print("NVIDIA driver:", info)

    manifest = _manifest()
    if _runtime_ready():
        print("Pinned NVIDIA runtime is already installed.")
        return 0

    total_download = sum(int(x.get("size") or 0) for x in manifest.get("packages", []))
    usage = shutil.disk_usage(RUNTIME_DIR.parent if RUNTIME_DIR.parent.exists() else DATA_ROOT.parent)
    # Wheels are compressed and then extracted. Keep comfortable headroom.
    required_free = max(4 * 1024**3, total_download * 3)
    if usage.free < required_free:
        raise RuntimeError(
            f"Not enough free disk space for NVIDIA runtime. Need about {required_free / 1024**3:.1f} GiB free."
        )

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    packages_dir = RUNTIME_DIR / "packages"
    downloads_dir = RUNTIME_DIR / ".downloads"
    packages_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)

    installed_packages = []
    for item in manifest.get("packages", []):
        name = str(item["name"])
        filename = str(item["filename"])
        url = str(item["url"])
        sha256 = str(item["sha256"])
        size = int(item.get("size") or 0)
        version = str(item["version"])
        print(f"Installing {name} {version} ({size / 1024**2:.1f} MiB download)...", flush=True)

        wheel_path = downloads_dir / filename
        if wheel_path.exists():
            actual = _sha256_file(wheel_path)
            if actual.lower() != sha256.lower():
                wheel_path.unlink()
        if not wheel_path.exists():
            _download(url, wheel_path, sha256, size)

        target = packages_dir / name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(wheel_path) as zf:
            _safe_extract(zf, target)

        installed_packages.append({
            "name": name, "version": version, "filename": filename,
            "sha256": sha256, "size": size,
        })
        try:
            wheel_path.unlink()
        except OSError:
            pass

    marker = {
        "schema": 1,
        "platform": manifest.get("platform"),
        "packages": installed_packages,
    }
    (RUNTIME_DIR / "runtime-installed.json").write_text(
        json.dumps(marker, indent=2) + "\n", encoding="utf-8"
    )
    print("NVIDIA CUDA runtime libraries installed successfully.")
    return 0


_DLL_HANDLES: list[object] = []


def _activate_runtime() -> None:
    dirs = _runtime_library_dirs()
    if not dirs:
        return

    if WINDOWS:
        joined = os.pathsep.join(str(p) for p in dirs)
        os.environ["PATH"] = joined + os.pathsep + os.environ.get("PATH", "")
        add = getattr(os, "add_dll_directory", None)
        if add:
            for p in dirs:
                try:
                    _DLL_HANDLES.append(add(str(p)))
                except OSError:
                    pass
        return

    current = os.environ.get("LD_LIBRARY_PATH", "")
    wanted = [str(p) for p in dirs]
    current_parts = [x for x in current.split(":") if x]
    if all(p in current_parts for p in wanted):
        return
    if os.environ.get("_CENSORARR_GPU_LD_READY") == "1":
        return
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = ":".join(wanted + current_parts)
    env["_CENSORARR_GPU_LD_READY"] = "1"
    if getattr(sys, "frozen", False):
        os.execve(sys.executable, [sys.executable, *sys.argv[1:]], env)
    else:
        os.execve(sys.executable, [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env)


def _install_windows_task() -> int:
    if os.environ.get("CENSORARR_GPU_SKIP_SERVICE_INSTALL") == "1":
        print("Skipping Windows startup task because CENSORARR_GPU_SKIP_SERVICE_INSTALL=1")
        return 0
    if not WINDOWS:
        print("--install-service is Windows-only", file=sys.stderr)
        return 2
    exe = str(Path(sys.executable).resolve())
    task_name = "Censorarr GPU Worker"
    command = f'"{exe}" --background'
    proc = subprocess.run([
        "schtasks.exe", "/Create", "/F", "/TN", task_name,
        "/SC", "ONSTART", "/RU", "SYSTEM", "/RL", "HIGHEST",
        "/TR", command,
    ], text=True, capture_output=True)
    if proc.returncode != 0:
        print((proc.stdout or "") + (proc.stderr or ""), file=sys.stderr)
        return proc.returncode or 1
    print("Installed Windows startup task:", task_name)
    return 0


def _remove_windows_task() -> int:
    if not WINDOWS:
        return 0
    proc = subprocess.run(
        ["schtasks.exe", "/Delete", "/F", "/TN", "Censorarr GPU Worker"],
        text=True, capture_output=True,
    )
    if proc.returncode != 0 and "cannot find" not in (proc.stderr or "").lower():
        print((proc.stdout or "") + (proc.stderr or ""), file=sys.stderr)
    return 0


def _start_windows_task() -> int:
    if os.environ.get("CENSORARR_GPU_SKIP_SERVICE_INSTALL") == "1":
        return 0
    if not WINDOWS:
        return 0
    proc = subprocess.run(
        ["schtasks.exe", "/Run", "/TN", "Censorarr GPU Worker"],
        text=True, capture_output=True,
    )
    if proc.returncode != 0:
        print((proc.stdout or "") + (proc.stderr or ""), file=sys.stderr)
        return proc.returncode or 1
    return 0


def _prepare_worker_environment() -> None:
    _ensure_config()
    _load_env_file(CONFIG_FILE)
    os.environ.setdefault("ASR_MODEL_DIR", str(MODEL_DIR))
    os.environ.setdefault("ASR_RUNTIME_DIR", str(RUNTIME_DIR))
    os.environ.setdefault("ASR_MODEL", "small.en")
    os.environ.setdefault("ASR_COMPUTE_TYPE", "int8_float32")
    os.environ.setdefault("ASR_CHUNK_SECONDS", "600")
    os.environ.setdefault("ASR_CHUNK_OVERLAP_SECONDS", "2")
    os.environ.setdefault("CENSORARR_GPU_PORT", str(DEFAULT_PORT))


def run_server() -> int:
    _prepare_worker_environment()
    _activate_runtime()

    import uvicorn
    import worker

    host = os.environ.get("CENSORARR_GPU_HOST", "0.0.0.0")
    port = int(os.environ.get("CENSORARR_GPU_PORT", DEFAULT_PORT))
    uvicorn.run(worker.app, host=host, port=port, workers=1, log_level="info")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="CensorarrGPUWorker")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--ensure-config", action="store_true")
    parser.add_argument("--show-token", action="store_true")
    parser.add_argument("--check-driver", action="store_true")
    parser.add_argument("--install-runtime", action="store_true")
    parser.add_argument("--skip-driver-check", action="store_true")
    parser.add_argument("--runtime-plan", action="store_true")
    parser.add_argument("--install-service", action="store_true")
    parser.add_argument("--remove-service", action="store_true")
    parser.add_argument("--start-service", action="store_true")
    args = parser.parse_args()

    if args.ensure_config:
        path = _ensure_config()
        print(path)
        return 0
    if args.show_token:
        path = _ensure_config()
        token = _config_value(path, "ASR_WORKER_TOKEN")
        print(token)
        return 0 if token else 1
    if args.check_driver:
        ok, info = _driver_info()
        print(info)
        return 0 if ok else 3
    if args.runtime_plan:
        data = _manifest()
        print(json.dumps(data, indent=2))
        return 0
    if args.install_runtime:
        _ensure_config()
        _load_env_file(CONFIG_FILE)
        return install_runtime(require_driver=not args.skip_driver_check)
    if args.install_service:
        return _install_windows_task()
    if args.remove_service:
        return _remove_windows_task()
    if args.start_service:
        return _start_windows_task()

    return run_server()


if __name__ == "__main__":
    raise SystemExit(main())
