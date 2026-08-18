"""Stable-release update checker and safe Docker/Synology source updater.

Censorarr's Synology install bind-mounts ./app to /app. That makes source-only
updates safe to install in place without rebuilding the image. Releases that change
container dependencies or mounted root files are detected and require a manual
container/project update instead of being applied blindly.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = "leestow/Censorarr"
API = f"https://api.github.com/repos/{REPO}"
CACHE = Path("/config/update-status.json")
BACKUP_ROOT = Path("/config/update-backups")
APP_ROOT = Path("/app")
USER_AGENT = "Censorarr-Updater/1"

# If any of these change, replacing /app alone is not enough for a Synology/Docker
# install. The GUI still announces the release but requires a manual project update.
DOCKER_REBUILD_FILES = {
    "Dockerfile",
    "requirements.txt",
    "docker-entrypoint.sh",
    "docker-compose.yml",
    "en.json",
    "config.example.yaml",
}

_update_lock = threading.RLock()


def _version_tuple(value: str) -> tuple[int, ...]:
    raw = str(value or "").strip().lower()
    if raw.startswith("v"):
        raw = raw[1:]
    raw = raw.split("-", 1)[0].split("+", 1)[0]
    out: list[int] = []
    for part in raw.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        out.append(int(digits))
    return tuple(out or [0])


def _newer(latest: str, current: str) -> bool:
    a = list(_version_tuple(latest))
    b = list(_version_tuple(current))
    width = max(len(a), len(b))
    a.extend([0] * (width - len(a)))
    b.extend([0] * (width - len(b)))
    return tuple(a) > tuple(b)


def _request_json(url: str, timeout: float = 15.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, dest: Path, timeout: float = 120.0) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out, length=1024 * 1024)


def _read_cache() -> dict:
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_cache(data: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, CACHE)
    except OSError:
        pass


def _platform() -> str:
    configured = str(os.environ.get("CENSORARR_PLATFORM", "")).strip().lower()
    if configured == "linux-native":
        return "linux-native"
    if os.name == "nt":
        return "windows"
    # Docker/Synology is the standard POSIX webapp.py runtime. Native Linux sets the
    # explicit platform variable in its launcher/package.
    return "docker"


def _compare_files(current_version: str, latest_tag: str) -> tuple[list[str] | None, str | None]:
    latest = urllib.parse.quote(str(latest_tag), safe="")
    candidates = [f"v{str(current_version).lstrip('v')}", str(current_version).lstrip("v")]
    seen: set[str] = set()
    errors: list[str] = []
    for base in candidates:
        if base in seen:
            continue
        seen.add(base)
        url = f"{API}/compare/{urllib.parse.quote(base, safe='')}...{latest}"
        try:
            payload = _request_json(url, timeout=20)
            rows = payload.get("files") or []
            if not isinstance(rows, list):
                return None, "GitHub did not return a changed-file list"
            return [str(row.get("filename") or "") for row in rows if row.get("filename")], None
        except urllib.error.HTTPError as exc:
            errors.append(f"{base}: HTTP {exc.code}")
        except Exception as exc:
            errors.append(f"{base}: {exc}")
    return None, "; ".join(errors[-2:]) or "Unable to compare releases"


def _install_capability(current_version: str, latest_tag: str, update_available: bool) -> dict:
    platform = _platform()
    if not update_available:
        return {"supported": False, "reason": "Already up to date", "changed_files": []}
    if platform != "docker":
        return {
            "supported": False,
            "reason": "Automatic install is currently available for Docker/Synology source updates; use the release installer for this platform.",
            "changed_files": [],
        }

    changed, error = _compare_files(current_version, latest_tag)
    if changed is None:
        return {
            "supported": False,
            "reason": f"Could not verify that this is a source-only update: {error}",
            "changed_files": [],
        }

    rebuild = sorted(path for path in changed if path in DOCKER_REBUILD_FILES)
    if rebuild:
        return {
            "supported": False,
            "reason": "This release changes container/project files and requires a manual Synology/Docker update.",
            "changed_files": changed,
            "requires_manual_files": rebuild,
        }
    return {"supported": True, "reason": "Safe source-only Docker/Synology update", "changed_files": changed}


def check(current_version: str, *, force: bool = False, cache_seconds: int = 21600) -> dict:
    now = time.time()
    cached = _read_cache()
    if not force:
        checked = float(cached.get("checked_at", 0) or 0)
        if checked and now - checked < max(300, int(cache_seconds)) and cached.get("current_version") == current_version:
            return cached

    result: dict[str, Any] = {
        "ok": False,
        "current_version": str(current_version),
        "platform": _platform(),
        "checked_at": now,
        "update_available": False,
    }
    try:
        release = _request_json(f"{API}/releases/latest", timeout=15)
        tag = str(release.get("tag_name") or "").strip()
        latest_version = tag.lstrip("vV")
        available = bool(tag and _newer(latest_version, current_version))
        capability = _install_capability(current_version, tag, available)
        body = str(release.get("body") or "")
        result.update({
            "ok": True,
            "latest_version": latest_version or str(current_version),
            "latest_tag": tag,
            "update_available": available,
            "release_url": str(release.get("html_url") or f"https://github.com/{REPO}/releases"),
            "published_at": release.get("published_at"),
            "release_name": str(release.get("name") or tag),
            "release_notes": body[:4000],
            "tarball_url": str(release.get("tarball_url") or ""),
            "install": capability,
        })
    except Exception as exc:
        result["error"] = str(exc)
        result["install"] = {"supported": False, "reason": "Update check failed", "changed_files": []}
    _write_cache(result)
    return result


def _safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            target = (destination / member.name).resolve()
            if destination != target and destination not in target.parents:
                raise RuntimeError("Unsafe path found in release archive")
        tf.extractall(destination)


def _copy_tree(source: Path, destination: Path, *, skip_names: set[str] | None = None) -> None:
    skip = skip_names or set()
    for item in source.rglob("*"):
        rel = item.relative_to(source)
        if any(part in skip for part in rel.parts):
            continue
        target = destination / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if item.is_symlink():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def install(current_version: str) -> dict:
    """Install the newest verified source-only release into the /app bind mount.

    The caller should terminate/restart the web process only after the HTTP response is
    sent. This function intentionally does not kill its own process.
    """
    with _update_lock:
        status = check(current_version, force=True)
        if not status.get("ok"):
            raise RuntimeError(f"Update check failed: {status.get('error', 'unknown error')}")
        if not status.get("update_available"):
            return {"ok": True, "updated": False, "message": "Censorarr is already up to date", "status": status}
        capability = status.get("install") or {}
        if not capability.get("supported"):
            raise RuntimeError(str(capability.get("reason") or "This update cannot be installed automatically"))
        tarball_url = str(status.get("tarball_url") or "").strip()
        if not tarball_url:
            raise RuntimeError("Latest GitHub release did not provide a source tarball")
        if not APP_ROOT.is_dir() or not os.access(APP_ROOT, os.W_OK):
            raise RuntimeError("/app is not writable; automatic Docker/Synology update is unavailable")

        work_parent = Path("/work") if Path("/work").is_dir() else Path(tempfile.gettempdir())
        staging = Path(tempfile.mkdtemp(prefix="censorarr-update-", dir=str(work_parent)))
        archive = staging / "release.tar.gz"
        extracted = staging / "release"
        extracted.mkdir(parents=True, exist_ok=True)
        try:
            _download(tarball_url, archive)
            _safe_extract(archive, extracted)
            roots = [p for p in extracted.iterdir() if p.is_dir()]
            if len(roots) != 1:
                raise RuntimeError("Unexpected GitHub release archive layout")
            new_app = roots[0] / "app"
            if not (new_app / "webapp.py").is_file() or not (new_app / "censorarr.py").is_file():
                raise RuntimeError("Release archive does not contain a valid Censorarr app directory")

            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup = BACKUP_ROOT / f"{str(current_version).replace('/', '_')}-{stamp}"
            backup.mkdir(parents=True, exist_ok=True)
            _copy_tree(APP_ROOT, backup, skip_names={"__pycache__"})

            # en.json and config.example.yaml are separate read-only bind mounts in the
            # standard Synology project. They are intentionally not touched here.
            _copy_tree(new_app, APP_ROOT, skip_names={"en.json", "__pycache__"})
            marker = Path("/config/last-update.json")
            marker.write_text(json.dumps({
                "from": current_version,
                "to": status.get("latest_version"),
                "tag": status.get("latest_tag"),
                "installed_at": time.time(),
                "backup": str(backup),
            }, indent=2), encoding="utf-8")
            try:
                CACHE.unlink()
            except OSError:
                pass
            return {
                "ok": True,
                "updated": True,
                "from": current_version,
                "to": status.get("latest_version"),
                "backup": str(backup),
                "restart_required": True,
            }
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def schedule_restart(delay_seconds: float = 1.5) -> None:
    """Gracefully terminate the web process after an update response can be sent.

    Docker's standard restart: unless-stopped policy starts the container again with
    the newly copied /app source. Native platforms never call this updater path.
    """
    def stop_later() -> None:
        time.sleep(max(0.5, float(delay_seconds)))
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            os._exit(0)

    threading.Thread(target=stop_later, daemon=True, name="censorarr-update-restart").start()
