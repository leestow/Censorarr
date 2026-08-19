"""Persistent stale-while-revalidate metadata cache for the family-safe dashboard."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from fastapi import Depends, HTTPException, Query

CACHE_TTL_SECONDS = 5 * 60
MAX_STALE_SECONDS = 7 * 24 * 60 * 60
_LOCK = threading.RLock()
_REFRESHING: set[str] = set()


def install(app, core) -> None:
    cache_dir = core.CONFIG.parent / "media-catalog-cache"

    def cache_path(kind: str) -> Path:
        return cache_dir / f"{kind}.json"

    def read_cache(kind: str):
        path = cache_path(kind)
        try:
            if not path.is_file():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            saved = float(payload.get("saved_at", 0) or 0)
            data = payload.get("data")
            if not isinstance(data, dict) or not saved:
                return None
            age = time.time() - saved
            if age > MAX_STALE_SECONDS:
                return None
            return {"saved_at": saved, "age": age, "data": data}
        except Exception:
            return None

    def write_cache(kind: str, data: dict) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_path(kind)
        tmp = path.with_suffix(".tmp")
        payload = {"saved_at": time.time(), "data": data}
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def refresh(kind: str) -> dict:
        # Call the existing canonical catalog builder directly. force=True refreshes
        # Radarr/Sonarr/Bazarr's own caches before the result is snapshotted.
        data = core.media_catalog(kind=kind, force=True, _=True)
        if not isinstance(data, dict):
            raise RuntimeError("Media catalog returned an unexpected payload")
        write_cache(kind, data)
        return data

    def refresh_background(kind: str) -> None:
        with _LOCK:
            if kind in _REFRESHING:
                return
            _REFRESHING.add(kind)

        def work():
            try:
                refresh(kind)
            except Exception as exc:
                core.pc.logging.debug("Background %s metadata refresh failed: %s", kind, exc)
            finally:
                with _LOCK:
                    _REFRESHING.discard(kind)

        threading.Thread(target=work, name=f"metadata-refresh-{kind}", daemon=True).start()

    @app.get("/api/media-catalog-fast")
    def media_catalog_fast(
        kind: str = Query("movies", pattern="^(movies|series)$"),
        force: bool = Query(False),
        _: bool = Depends(core.auth),
    ):
        if force:
            try:
                return refresh(kind)
            except Exception as exc:
                raise HTTPException(502, f"Could not refresh {kind} metadata: {exc}")

        cached = read_cache(kind)
        if cached:
            if cached["age"] >= CACHE_TTL_SECONDS:
                refresh_background(kind)
            # Do not mutate the cached catalog shape; existing UI code should not need
            # to know whether its response was fresh or a persisted snapshot.
            return cached["data"]

        # First-ever request has no snapshot. It must seed once; later requests, browser
        # reloads, and container restarts can use the persisted copy immediately.
        try:
            return refresh(kind)
        except Exception as exc:
            raise HTTPException(502, f"Could not load {kind} metadata: {exc}")

    # Expose a tiny helper for diagnostics/tests without changing normal API payloads.
    core.fast_metadata_cache_status = lambda: {
        kind: ({"cached": True, "age_seconds": round(read_cache(kind)["age"], 1)} if read_cache(kind) else {"cached": False})
        for kind in ("movies", "series")
    }
