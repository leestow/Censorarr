"""Censorarr web entrypoint.

The main application remains in webapp_core.py. This thin entrypoint adds the
cross-platform media-folder picker, stable-release updater, and keeps media browsing
constrained to the configured libraries. Keeping these additions here also preserves
compatibility with launchers that already start ``webapp:app``.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

import updater
import webapp_core as core

VERSION = "1.6.7"
core.VERSION = VERSION
core.pc.VERSION = VERSION
core.pc.DEFAULT_CONFIG.setdefault("safety", {})["ensure_readable_output"] = True
core.pc.DEFAULT_CONFIG.setdefault("updates", {
    "check_enabled": True,
    "check_interval_hours": 6,
    "auto_install": False,
})


def _preserve_processed_media_metadata(src_stat, temp_out: Path, cfg: dict) -> None:
    safety = cfg.get("safety", {})
    preserve_owner_mode = bool(safety.get("preserve_owner_mode", True))
    ensure_readable_output = bool(safety.get("ensure_readable_output", True))

    if not preserve_owner_mode and not ensure_readable_output:
        return

    # Preserve ownership first because POSIX chown can clear special permission bits.
    if preserve_owner_mode:
        try:
            os.chown(temp_out, src_stat.st_uid, src_stat.st_gid)
        except (OSError, AttributeError, PermissionError) as exc:
            core.pc.logging.debug("Could not preserve owner/group on %s: %s", temp_out, exc)

    if preserve_owner_mode:
        target_mode = src_stat.st_mode & 0o7777
    else:
        try:
            target_mode = temp_out.stat().st_mode & 0o7777
        except OSError as exc:
            core.pc.logging.warning("Could not read output permissions for %s: %s", temp_out, exc)
            return

    # Preserve any broader source permissions, but never allow a processed media file
    # to become owner-only (0600/0700). Plex and other media services need read access.
    if ensure_readable_output:
        target_mode |= 0o444

    try:
        os.chmod(temp_out, target_mode)
    except OSError as exc:
        core.pc.logging.warning("Could not set processed-media permissions on %s: %s", temp_out, exc)


core.pc.preserve_metadata = _preserve_processed_media_metadata


# Docker/Synology runs the web server and media worker in separate Python processes.
# The child must start through censorarr_worker.py so the same metadata safety patch is
# installed inside the process that actually remuxes/replaces media files. Native
# launchers have their own worker bootstrap and are intentionally left alone here.
def _docker_worker_start(self) -> None:
    with self.lock:
        if self.proc and self.proc.poll() is None:
            return
        env = os.environ.copy()
        env.pop("DRY_RUN", None)
        self.proc = core.subprocess.Popen(["python", "/app/censorarr_worker.py"], env=env)
    if not self.monitor_thread or not self.monitor_thread.is_alive():
        self.monitor_thread = core.threading.Thread(
            target=self._monitor,
            daemon=True,
            name="worker-supervisor",
        )
        self.monitor_thread.start()


if os.name != "nt" and str(os.environ.get("CENSORARR_PLATFORM", "")).lower() != "linux-native":
    core.WorkerSupervisor.start = _docker_worker_start


# Re-export the ASGI application expected by existing Docker/Windows launchers.
app = core.app


def _configured_media_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        cfg = core.pc.load_config(core.CONFIG)
        for raw in core.pc.all_media_roots(cfg):
            if not str(raw).strip():
                continue
            p = Path(str(raw))
            if p.exists():
                try:
                    p = p.resolve()
                except Exception:
                    pass
                if p not in roots:
                    roots.append(p)
    except Exception:
        pass
    return roots


def _allowed_media_mounts() -> list[Path]:
    """Security boundary for manual media browsing/processing.

    Native Windows uses configured drive/UNC roots. Docker/Synology additionally
    exposes the conventional /media and /tv mounts so first-run installs work before
    the settings file has been finalized.
    """
    roots = _configured_media_roots()
    if os.name != "nt":
        for raw in ("/media", "/tv"):
            p = Path(raw)
            if p.exists():
                try:
                    p = p.resolve()
                except Exception:
                    pass
                if p not in roots:
                    roots.append(p)
    if roots:
        return roots
    return [] if os.name == "nt" else [Path("/media")]


def _configured_path_mappings(cfg: dict) -> list[dict]:
    """Return every configured external->local media path mapping.

    Media-detail pages may receive paths from Sonarr/Radarr/Plex/Bazarr while the
    process endpoint must operate on the local mounted path. Accepting all known
    mappings makes the Process button resilient to whichever integration supplied
    the media row.
    """
    out: list[dict] = []

    def add(rows) -> None:
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            src = str(row.get("from", "")).strip()
            dst = str(row.get("to", "")).strip()
            if src and dst:
                out.append({"from": src, "to": dst})

    rating = cfg.get("rating_filter", {}) or {}
    tv = cfg.get("tv", {}) or {}
    tv_rating = tv.get("rating_filter", {}) or {}
    arr = cfg.get("arr_integrations", {}) or {}
    radarr = arr.get("radarr", {}) or {}
    sonarr = arr.get("sonarr", {}) or {}
    subtitle = cfg.get("subtitle_assist", {}) or {}
    bazarr = subtitle.get("bazarr", {}) or {}

    add(rating.get("plex_path_mappings", []))
    add(tv_rating.get("plex_path_mappings", []))
    add(radarr.get("path_mappings", []))
    add(sonarr.get("path_mappings", []))
    add(bazarr.get("path_mappings", []))
    add(bazarr.get("tv_path_mappings", []))
    return out


def _mapped_media_candidate(raw: str, cfg: dict) -> Path | None:
    value = str(raw or "").strip()
    if not value:
        return None
    normalized = value.replace("\\", "/")
    compare_value = normalized.lower() if os.name == "nt" else normalized
    for mapping in _configured_path_mappings(cfg):
        src = str(mapping["from"]).rstrip("/\\").replace("\\", "/")
        dst = str(mapping["to"]).rstrip("/\\")
        compare_src = src.lower() if os.name == "nt" else src
        if compare_src and (compare_value == compare_src or compare_value.startswith(compare_src + "/")):
            suffix = normalized[len(src):]
            return Path(dst + suffix)
    return None


def safe_media_path(raw: str, must_exist: bool = True) -> Path:
    roots = _allowed_media_mounts()
    if not roots:
        raise HTTPException(403, "Configure a Movies or TV media folder first")

    raw_value = str(raw or "").strip()
    cfg = core.pc.load_config(core.CONFIG)
    candidates: list[Path] = []
    if raw_value:
        candidates.append(Path(raw_value))
        mapped = _mapped_media_candidate(raw_value, cfg)
        if mapped is not None and mapped not in candidates:
            candidates.append(mapped)

    if not candidates:
        raise HTTPException(400, "No media path was supplied")

    saw_existing_outside_root = False
    for candidate in candidates:
        p = candidate if candidate.is_absolute() else roots[0] / candidate
        try:
            resolved = p.resolve(strict=must_exist)
        except FileNotFoundError:
            continue
        if any(resolved == root or root in resolved.parents for root in roots):
            return resolved
        saw_existing_outside_root = True

    if saw_existing_outside_root:
        raise HTTPException(
            403,
            "Media path is outside Censorarr's configured Movies/TV roots. Check the Sonarr/Radarr/Plex path mapping.",
        )
    raise HTTPException(
        404,
        "Media file was not found at the reported path or any configured mapped path. Check the Sonarr/Radarr/Plex path mapping.",
    )


# Existing routes in webapp_core resolve these names from that module at request time.
# Replacing them here makes manual browsing/processing work with native Windows paths too.
core._allowed_media_mounts = _allowed_media_mounts
core.safe_media_path = safe_media_path


def _folder_picker_roots() -> list[Path]:
    if os.name == "nt":
        roots: list[Path] = []
        for code in range(ord("A"), ord("Z") + 1):
            p = Path(f"{chr(code)}:/")
            if p.exists():
                roots.append(p)
        return roots
    return _allowed_media_mounts()


def _folder_picker_path(raw: str) -> Path:
    p = Path(raw)
    try:
        resolved = p.resolve(strict=True)
    except FileNotFoundError:
        raise HTTPException(404, "Folder does not exist")
    if not resolved.is_dir():
        raise HTTPException(400, "Not a directory")
    if os.name == "nt":
        # Native Windows may select any locally reachable drive, mapped drive, or UNC path.
        return resolved
    roots = _folder_picker_roots()
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise HTTPException(403, "Folder chooser is limited to configured media mounts")
    return resolved


@app.get("/api/folders/browse")
def browse_folders(path: str = Query(""), _: bool = Depends(core.auth)):
    roots = _folder_picker_roots()
    root_strings = [str(x) for x in roots]

    # Windows starts with a virtual This PC view so drive letters can be selected.
    if os.name == "nt" and not str(path).strip():
        return {
            "path": "",
            "parent": None,
            "platform": "windows",
            "roots": root_strings,
            "items": [{"name": str(r), "path": str(r), "type": "dir"} for r in roots],
        }

    if not str(path).strip():
        if not roots:
            raise HTTPException(404, "No media folders are available to browse")
        p = roots[0]
    else:
        p = _folder_picker_path(path)

    try:
        children = sorted(
            (x for x in p.iterdir() if x.is_dir() and not x.name.startswith(".")),
            key=lambda x: x.name.lower(),
        )
    except (OSError, PermissionError) as exc:
        raise HTTPException(403, str(exc))

    if os.name == "nt":
        parent = None if p.parent == p else str(p.parent)
    else:
        containing = next((r for r in roots if p == r or r in p.parents), None)
        parent = str(p.parent) if containing is not None and p != containing else None

    return {
        "path": str(p),
        "parent": parent,
        "platform": "windows" if os.name == "nt" else "posix",
        "roots": root_strings,
        "items": [{"name": x.name, "path": str(x), "type": "dir"} for x in children[:2000]],
    }


@app.get("/api/media-roots")
def media_roots(_: bool = Depends(core.auth)):
    return {
        "platform": "windows" if os.name == "nt" else "posix",
        "roots": [str(x) for x in _allowed_media_mounts()],
        "configured": [str(x) for x in _configured_media_roots()],
    }


def _updates_cfg(cfg: dict) -> dict:
    raw = cfg.get("updates", {}) or {}
    return {
        "check_enabled": bool(raw.get("check_enabled", True)),
        "check_interval_hours": max(1, int(raw.get("check_interval_hours", 6) or 6)),
        "auto_install": bool(raw.get("auto_install", False)),
    }


def _worker_idle_for_update() -> tuple[bool, str]:
    hb = core.read_json(core.HEARTBEAT, {})
    status = str(hb.get("status") or "starting").lower()
    safe = {"idle", "paused", "scanning", "starting", "blocked", "setup-required", "waiting-subtitle", "permissions-error"}
    if status in safe:
        return True, status
    current = str(hb.get("current") or "").strip()
    return False, f"{status}: {current}" if current else status


def _save_update_preference(auto_install: bool) -> None:
    raw = core.yaml.safe_load(core.CONFIG.read_text(encoding="utf-8")) or {}
    updates = raw.setdefault("updates", {})
    updates["check_enabled"] = bool(updates.get("check_enabled", True))
    updates["check_interval_hours"] = max(1, int(updates.get("check_interval_hours", 6) or 6))
    updates["auto_install"] = bool(auto_install)
    tmp = core.CONFIG.with_suffix(".tmp")
    tmp.write_text(core.yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    os.replace(tmp, core.CONFIG)


@app.get("/api/update/status")
def update_status(force: bool = Query(False), _: bool = Depends(core.auth)):
    cfg = core.pc.load_config(core.CONFIG)
    pref = _updates_cfg(cfg)
    if not pref["check_enabled"] and not force:
        return {
            "ok": True,
            "current_version": VERSION,
            "latest_version": VERSION,
            "update_available": False,
            "checks_disabled": True,
            "auto_install_enabled": pref["auto_install"],
        }
    result = updater.check(
        VERSION,
        force=bool(force),
        cache_seconds=pref["check_interval_hours"] * 3600,
    )
    result["auto_install_enabled"] = pref["auto_install"]
    return result


@app.post("/api/update/preferences")
async def update_preferences(request: Request, _: bool = Depends(core.auth)):
    body = await request.json()
    enabled = bool(body.get("auto_install", False))
    _save_update_preference(enabled)
    return {"ok": True, "auto_install": enabled}


@app.post("/api/update/install")
def install_update(_: bool = Depends(core.auth)):
    idle, detail = _worker_idle_for_update()
    if not idle:
        raise HTTPException(409, f"Finish or stop the current media job before updating Censorarr ({detail}).")
    try:
        result = updater.install(VERSION)
    except Exception as exc:
        raise HTTPException(409, str(exc))
    if result.get("updated"):
        core.pc.logging.info("Installed Censorarr update %s -> %s; restarting container", result.get("from"), result.get("to"))
        updater.schedule_restart()
    return result


@app.get("/folder-picker.js", include_in_schema=False)
def folder_picker_script(_: bool = Depends(core.auth)):
    js = core.STATIC / "folder-picker.js"
    if not js.is_file():
        raise HTTPException(404, "Folder picker script not found")
    return Response(js.read_text(encoding="utf-8"), media_type="application/javascript")


@app.get("/updater.js", include_in_schema=False)
def updater_script(_: bool = Depends(core.auth)):
    js = core.STATIC / "updater.js"
    if not js.is_file():
        raise HTTPException(404, "Updater script not found")
    return Response(js.read_text(encoding="utf-8"), media_type="application/javascript")


# Replace only the root page route. All API/static routes remain the original application.
for route in list(app.router.routes):
    if getattr(route, "path", None) == "/" and "GET" in (getattr(route, "methods", set()) or set()):
        app.router.routes.remove(route)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index_with_folder_picker(_: bool = Depends(core.auth)):
    html = (core.STATIC / "index.html").read_text(encoding="utf-8")
    injection = r'''<script src="/folder-picker.js?v=2"></script>
<script src="/updater.js?v=1"></script>
<script>
window.reprocess = async function(path) {
  if (!confirm('Force reprocess ' + basename(path) + '? Existing CLEAN will be replaced, not duplicated.')) return;
  try {
    const result = await api('/api/process', {method:'POST', body:JSON.stringify({path})});
    if (typeof refreshQueueMini === 'function') await refreshQueueMini();
    if (typeof refresh === 'function') refresh();
    return result;
  } catch (e) {
    alert('Could not process ' + basename(path) + ':\n\n' + (e && e.message ? e.message : String(e)));
    throw e;
  }
};
</script>'''
    if '/updater.js?v=1' not in html:
        html = html.replace("</body>", injection + "</body>", 1)
    return HTMLResponse(html)


def _automatic_update_loop() -> None:
    # Give normal startup/media preflight time to settle before the first background check.
    time.sleep(45)
    while True:
        try:
            cfg = core.pc.load_config(core.CONFIG)
            pref = _updates_cfg(cfg)
            interval = max(1, pref["check_interval_hours"]) * 3600
            if pref["check_enabled"] and pref["auto_install"]:
                status = updater.check(VERSION, force=False, cache_seconds=interval)
                install = status.get("install") or {}
                if status.get("update_available") and install.get("supported"):
                    idle, detail = _worker_idle_for_update()
                    if idle:
                        result = updater.install(VERSION)
                        if result.get("updated"):
                            core.pc.logging.info(
                                "Automatically installed Censorarr update %s -> %s; restarting container",
                                result.get("from"), result.get("to"),
                            )
                            updater.schedule_restart()
                            return
                    else:
                        core.pc.logging.info("Censorarr update is available; automatic install deferred until idle (%s)", detail)
                elif status.get("update_available") and not install.get("supported"):
                    core.pc.logging.info("Censorarr update available but manual update is required: %s", install.get("reason"))
            time.sleep(interval)
        except Exception as exc:
            core.pc.logging.warning("Automatic update check failed: %s", exc)
            time.sleep(3600)


threading.Thread(target=_automatic_update_loop, daemon=True, name="censorarr-auto-updater").start()
