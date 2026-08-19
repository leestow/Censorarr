"""Development-branch web API for Dialogue Enhancement settings and family-safe UI."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import Response

from dialogue_enhancement import DEFAULTS

DEV_VERSION = "1.6.8-dev"
WIKI_REPO = "leestow/Censorarr"
WIKI_BRANCH = "family-safe-media"
WIKI_TTL_SECONDS = 6 * 3600


def _payload(cfg: dict) -> dict:
    current = dict(DEFAULTS)
    current.update(cfg.get("dialogue_enhancement", {}) or {})
    current["profanity_censoring_enabled"] = bool((cfg.get("profanity", {}) or {}).get("enabled", True))
    return current


def _wiki_title(slug: str) -> str:
    return slug.replace("-", " ")


def _clean_family_wiki(markdown: str) -> str:
    """Hide retired-mode documentation if an older cached/source page still contains it."""
    lines = str(markdown or "").replace("\r", "").split("\n")
    out: list[str] = []
    skipping_section = False
    skip_level = 0
    for line in lines:
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2)
            if re.search(r"\bdry[ _-]?run\b", title, re.I):
                skipping_section = True
                skip_level = level
                continue
            if skipping_section and level <= skip_level:
                skipping_section = False
        if skipping_section:
            continue
        if re.search(r"\bdry[ _-]?run\b", line, re.I):
            continue
        out.append(line)
    return "\n".join(out)


def install(app, core) -> None:
    # Clearly identify the experimental runtime without changing the repository VERSION
    # file (which remains the stable release version and drives normal release workflows).
    core.VERSION = DEV_VERSION
    core.pc.VERSION = DEV_VERSION

    # A development checkout must never let the stable self-updater replace /app with
    # a release tarball. Keep update checking/release links available, but make the
    # install capability report unsupported while this feature branch is running.
    import updater
    updater._platform = lambda: "development"

    defaults = core.pc.DEFAULT_CONFIG.setdefault("dialogue_enhancement", {})
    for key, value in DEFAULTS.items():
        defaults.setdefault(key, value)
    core.pc.DEFAULT_CONFIG.setdefault("profanity", {}).setdefault("enabled", True)

    # Family-safe has one processing behavior. The underlying engine keeps its old config
    # field for backward compatibility, but this branch pins it off before any worker starts.
    core.pc.DEFAULT_CONFIG["dry_run"] = False
    os.environ.pop("DRY_RUN", None)

    def force_normal_processing_config(path) -> None:
        try:
            raw_cfg = core.yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            changed = False
            if raw_cfg.get("dry_run") is not False:
                raw_cfg["dry_run"] = False
                changed = True
            profanity = raw_cfg.setdefault("profanity", {})
            if "enabled" not in profanity:
                profanity["enabled"] = True
                changed = True
            if not changed:
                return
            tmp = path.with_suffix(".tmp")
            tmp.write_text(core.yaml.safe_dump(raw_cfg, sort_keys=False), encoding="utf-8")
            os.replace(tmp, path)
        except Exception as exc:
            core.pc.logging.warning("Could not migrate family-safe processing settings: %s", exc)

    # ensure_config runs immediately before the worker supervisor starts. Wrapping it makes
    # fresh installs safe too: the example config may omit retired/new feature fields, but
    # the worker receives explicit family-safe defaults before it starts.
    original_ensure_config = core.pc.ensure_config
    if not getattr(original_ensure_config, "_family_safe_single_mode", False):
        def ensure_config_single_mode(path) -> None:
            original_ensure_config(path)
            force_normal_processing_config(path)
        ensure_config_single_mode._family_safe_single_mode = True
        core.pc.ensure_config = ensure_config_single_mode

    if core.CONFIG.exists():
        force_normal_processing_config(core.CONFIG)

    @app.get("/api/dialogue-enhancement/settings")
    def get_dialogue_settings(_: bool = Depends(core.auth)):
        return _payload(core.pc.load_config(core.CONFIG))

    @app.post("/api/dialogue-enhancement/settings")
    async def save_dialogue_settings(request: Request, _: bool = Depends(core.auth)):
        body = await request.json()
        raw = core.yaml.safe_load(core.CONFIG.read_text(encoding="utf-8")) or {}
        current = raw.setdefault("dialogue_enhancement", {})

        current["enabled"] = bool(body.get("enabled", current.get("enabled", False)))
        if "profanity_censoring_enabled" in body:
            raw.setdefault("profanity", {})["enabled"] = bool(body.get("profanity_censoring_enabled"))

        title = str(body.get("title", current.get("title", DEFAULTS["title"])) or "").strip()
        if not title:
            raise HTTPException(400, "Dialogue-enhanced track name cannot be blank")
        current["title"] = title

        language = str(body.get("language", current.get("language", "eng")) or "eng").strip().lower()
        current["language"] = (language or "eng")[:12]

        strength = str(body.get("strength", current.get("strength", "medium")) or "medium").strip().lower()
        if strength not in {"light", "medium", "strong"}:
            raise HTTPException(400, "Dialogue enhancement strength must be light, medium, or strong")
        current["strength"] = strength

        codec = str(body.get("codec", current.get("codec", "aac")) or "aac").strip().lower()
        if codec not in {"aac", "ac3", "eac3"}:
            raise HTTPException(400, "Dialogue enhancement codec must be AAC, AC3, or EAC3")
        current["codec"] = codec

        bitrate = str(body.get("bitrate", current.get("bitrate", "192k")) or "192k").strip().lower()
        try:
            kbps = int(bitrate[:-1] if bitrate.endswith("k") else bitrate)
        except ValueError:
            raise HTTPException(400, "Dialogue enhancement bitrate must be a value such as 192k")
        if kbps < 64 or kbps > 1024:
            raise HTTPException(400, "Dialogue enhancement bitrate must be between 64k and 1024k")
        current["bitrate"] = f"{kbps}k"

        current["make_default"] = bool(body.get("make_default", current.get("make_default", False)))
        current["replace_existing"] = bool(body.get("replace_existing", current.get("replace_existing", True)))

        raw["dry_run"] = False
        tmp = core.CONFIG.with_suffix(".tmp")
        tmp.write_text(core.yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        os.replace(tmp, core.CONFIG)
        core.RESTART_AFTER_CURRENT.touch()
        return {
            "ok": True,
            "settings": _payload(raw),
            "message": "Audio feature settings saved. The worker will reload after the current item.",
        }

    def wiki_cache_dir():
        path = core.CONFIG.parent / "wiki-help-cache"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def fetch_text(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Censorarr-in-app-wiki"})
        with urllib.request.urlopen(req, timeout=12) as response:
            return response.read().decode("utf-8")

    def wiki_index(force: bool = False) -> tuple[list[dict], bool]:
        cache = wiki_cache_dir() / "index.json"
        if cache.exists() and not force and time.time() - cache.stat().st_mtime < WIKI_TTL_SECONDS:
            try:
                return json.loads(cache.read_text(encoding="utf-8")), True
            except Exception:
                pass
        url = f"https://api.github.com/repos/{WIKI_REPO}/contents/wiki?ref={WIKI_BRANCH}"
        try:
            data = json.loads(fetch_text(url))
            pages = []
            for item in data:
                name = str(item.get("name", ""))
                if item.get("type") != "file" or not name.endswith(".md"):
                    continue
                slug = name[:-3]
                pages.append({"slug": slug, "title": _wiki_title(slug)})
            priority = {"Home": 0, "Quick-Start": 1, "Setup-Wizard": 2}
            pages.sort(key=lambda x: (priority.get(x["slug"], 50), x["title"].lower()))
            cache.write_text(json.dumps(pages, indent=2), encoding="utf-8")
            return pages, False
        except Exception:
            if cache.exists():
                try:
                    return json.loads(cache.read_text(encoding="utf-8")), True
                except Exception:
                    pass
            raise

    def wiki_page(slug: str, force: bool = False) -> tuple[str, bool]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", slug or ""):
            raise HTTPException(400, "Invalid Wiki page")
        cache = wiki_cache_dir() / f"{slug}.md"
        if cache.exists() and not force and time.time() - cache.stat().st_mtime < WIKI_TTL_SECONDS:
            return _clean_family_wiki(cache.read_text(encoding="utf-8")), True
        url = f"https://raw.githubusercontent.com/{WIKI_REPO}/{WIKI_BRANCH}/wiki/{slug}.md"
        try:
            text = fetch_text(url)
            cache.write_text(text, encoding="utf-8")
            return _clean_family_wiki(text), False
        except Exception:
            if cache.exists():
                return _clean_family_wiki(cache.read_text(encoding="utf-8")), True
            raise

    @app.get("/api/help/wiki")
    def get_wiki_index(force: bool = Query(False), _: bool = Depends(core.auth)):
        try:
            pages, cached = wiki_index(force=bool(force))
            return {"pages": pages, "cached": cached, "source": WIKI_BRANCH}
        except Exception as exc:
            raise HTTPException(503, f"Wiki index unavailable: {exc}")

    @app.get("/api/help/wiki/{slug}")
    def get_wiki_page(slug: str, force: bool = Query(False), _: bool = Depends(core.auth)):
        try:
            text, cached = wiki_page(slug, force=bool(force))
            return {"slug": slug, "title": _wiki_title(slug), "markdown": text, "cached": cached, "source": WIKI_BRANCH}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, f"Wiki page unavailable: {exc}")

    @app.get("/dialogue-enhancement.js", include_in_schema=False)
    def dialogue_script(_: bool = Depends(core.auth)):
        js = core.STATIC / "dialogue-enhancement.js"
        if not js.is_file():
            raise HTTPException(404, "Dialogue Enhancement script not found")
        content = js.read_text(encoding="utf-8")
        preflight = core.STATIC / "ui-preflight.js"
        if preflight.is_file():
            content += "\n\n/* Family-safe UI preflight guards */\n" + preflight.read_text(encoding="utf-8")
        polish = core.STATIC / "ui-polish.js"
        if polish.is_file():
            content += "\n\n/* Family-safe UI polish bundle */\n" + polish.read_text(encoding="utf-8")
        brand = core.STATIC / "ui-brand-hotfix.js"
        if brand.is_file():
            content += "\n\n/* Family-safe branding hotfix */\n" + brand.read_text(encoding="utf-8")
        live_fix = core.STATIC / "ui-live-fix.js"
        if live_fix.is_file():
            content += "\n\n/* Family-safe live status fixes */\n" + live_fix.read_text(encoding="utf-8")
        final_fixes = core.STATIC / "ui-final-fixes.js"
        if final_fixes.is_file():
            content += "\n\n/* Family-safe final navigation and operations fixes */\n" + final_fixes.read_text(encoding="utf-8")
        wiki = core.STATIC / "ui-wiki.js"
        if wiki.is_file():
            content += "\n\n/* Full in-app Wiki */\n" + wiki.read_text(encoding="utf-8")
        usability = core.STATIC / "ui-usability-pass.js"
        if usability.is_file():
            content += "\n\n/* Family-safe usability pass */\n" + usability.read_text(encoding="utf-8")
        persistent_cache = core.STATIC / "ui-persistent-metadata-cache.js"
        if persistent_cache.is_file():
            content += "\n\n/* Persistent stale-while-revalidate media metadata cache */\n" + persistent_cache.read_text(encoding="utf-8")
        overview_controls = core.STATIC / "ui-overview-controls.js"
        if overview_controls.is_file():
            content += "\n\n/* Overview stop/pause controls */\n" + overview_controls.read_text(encoding="utf-8")
        return Response(content, media_type="application/javascript", headers={"Cache-Control": "no-cache"})
