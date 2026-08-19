"""Development-branch web API for Dialogue Enhancement settings."""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response

from dialogue_enhancement import DEFAULTS

DEV_VERSION = "1.6.8-dev"


def _payload(cfg: dict) -> dict:
    current = dict(DEFAULTS)
    current.update(cfg.get("dialogue_enhancement", {}) or {})
    return current


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

    @app.get("/api/dialogue-enhancement/settings")
    def get_dialogue_settings(_: bool = Depends(core.auth)):
        return _payload(core.pc.load_config(core.CONFIG))

    @app.post("/api/dialogue-enhancement/settings")
    async def save_dialogue_settings(request: Request, _: bool = Depends(core.auth)):
        body = await request.json()
        raw = core.yaml.safe_load(core.CONFIG.read_text(encoding="utf-8")) or {}
        current = raw.setdefault("dialogue_enhancement", {})

        current["enabled"] = bool(body.get("enabled", current.get("enabled", False)))
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

        tmp = core.CONFIG.with_suffix(".tmp")
        tmp.write_text(core.yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        os.replace(tmp, core.CONFIG)
        core.RESTART_AFTER_CURRENT.touch()
        return {
            "ok": True,
            "settings": _payload(raw),
            "message": "Dialogue Enhancement settings saved. The worker will reload after the current item.",
        }

    @app.get("/dialogue-enhancement.js", include_in_schema=False)
    def dialogue_script(_: bool = Depends(core.auth)):
        js = core.STATIC / "dialogue-enhancement.js"
        if not js.is_file():
            raise HTTPException(404, "Dialogue Enhancement script not found")
        content = js.read_text(encoding="utf-8")
        polish = core.STATIC / "ui-polish.js"
        if polish.is_file():
            content += "\n\n/* Family-safe UI polish bundle */\n" + polish.read_text(encoding="utf-8")
        return Response(content, media_type="application/javascript", headers={"Cache-Control": "no-cache"})
