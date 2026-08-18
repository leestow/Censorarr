"""Censorarr web entrypoint.

The main application remains in webapp_core.py.  This thin entrypoint adds the
cross-platform media-folder picker and keeps media browsing constrained to the
configured libraries.  Keeping these additions here also preserves compatibility
with launchers that already start ``webapp:app``.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

import webapp_core as core

# v1.6.6: keep processed replacements readable by Plex/media services.  The engine
# already centralizes post-remux metadata handling in pc.preserve_metadata(); patching
# that hook here covers Docker, Synology, Windows, and native Linux launchers that all
# enter through webapp:app, while preserving the source owner/group whenever possible.
VERSION = "1.6.6"
core.VERSION = VERSION
core.pc.VERSION = VERSION
core.pc.DEFAULT_CONFIG.setdefault("safety", {})["ensure_readable_output"] = True


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


def safe_media_path(raw: str, must_exist: bool = True) -> Path:
    roots = _allowed_media_mounts()
    if not roots:
        raise HTTPException(403, "Configure a Movies or TV media folder first")
    p = Path(raw)
    if not p.is_absolute():
        p = roots[0] / p
    try:
        resolved = p.resolve(strict=must_exist)
    except FileNotFoundError:
        raise HTTPException(404, "Path does not exist")
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise HTTPException(403, "Only paths inside the configured media roots are allowed")
    return resolved


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


@app.get("/folder-picker.js", include_in_schema=False)
def folder_picker_script(_: bool = Depends(core.auth)):
    js = core.STATIC / "folder-picker.js"
    if not js.is_file():
        raise HTTPException(404, "Folder picker script not found")
    return Response(js.read_text(encoding="utf-8"), media_type="application/javascript")


# Replace only the root page route. All API/static routes remain the original application.
for route in list(app.router.routes):
    if getattr(route, "path", None) == "/" and "GET" in (getattr(route, "methods", set()) or set()):
        app.router.routes.remove(route)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index_with_folder_picker(_: bool = Depends(core.auth)):
    html = (core.STATIC / "index.html").read_text(encoding="utf-8")
    injection = '<script src="/folder-picker.js?v=1"></script>'
    if injection not in html:
        html = html.replace("</body>", injection + "</body>", 1)
    return HTMLResponse(html)
