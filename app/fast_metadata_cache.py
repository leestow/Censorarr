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

    def valid_catalog(data) -> bool:
        """Only cache a catalog that actually contains media rows.

        An optional integration can transiently return an empty successful payload while
        starting/reconnecting. Treating that as a durable snapshot hides the user's whole
        library until the cache expires, which is much worse than a slightly slower load.
        """
        return isinstance(data, dict) and isinstance(data.get("items"), list) and len(data.get("items") or []) > 0

    def discard_cache(kind: str) -> None:
        try:
            cache_path(kind).unlink()
        except OSError:
            pass

    def read_cache(kind: str):
        path = cache_path(kind)
        try:
            if not path.is_file():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            saved = float(payload.get("saved_at", 0) or 0)
            data = payload.get("data")
            if not saved or not valid_catalog(data):
                discard_cache(kind)
                return None
            age = time.time() - saved
            if age > MAX_STALE_SECONDS:
                discard_cache(kind)
                return None
            return {"saved_at": saved, "age": age, "data": data}
        except Exception:
            discard_cache(kind)
            return None

    def write_cache(kind: str, data: dict) -> None:
        if not valid_catalog(data):
            raise RuntimeError(f"Refusing to cache empty {kind} catalog")
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
        if not valid_catalog(data):
            raise RuntimeError(f"Canonical {kind} catalog returned no media rows")
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
                # Keep the last known-good snapshot. A transient empty/offline response
                # must never replace working metadata.
                core.pc.logging.debug("Background %s metadata refresh skipped: %s", kind, exc)
            finally:
                with _LOCK:
                    _REFRESHING.discard(kind)

        threading.Thread(target=work, name=f"metadata-refresh-{kind}", daemon=True).start()

    def cached_catalog(kind: str) -> dict:
        cached = read_cache(kind)
        data = cached["data"] if cached else None
        if cached and cached["age"] >= CACHE_TTL_SECONDS:
            refresh_background(kind)

        if valid_catalog(data):
            return data

        # If this is the first request after an upgrade/restart, use the canonical builder
        # once to seed the persistent cache. Its integration layer has its own short-lived
        # in-memory cache, so this normally remains cheap after the library page has loaded.
        try:
            data = core.media_catalog(kind=kind, force=False, _=True)
            if valid_catalog(data):
                write_cache(kind, data)
                return data
        except Exception as exc:
            raise HTTPException(502, f"Could not load cached {kind} metadata: {exc}")
        raise HTTPException(502, f"Could not load cached {kind} metadata")

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
            return cached["data"]

        # First-ever request has no known-good snapshot. Try to seed it once. If the
        # canonical builder is transiently empty, return an error so the browser can
        # fall back to the original endpoint instead of poisoning either cache layer.
        try:
            return refresh(kind)
        except Exception as exc:
            raise HTTPException(502, f"Could not load {kind} metadata: {exc}")

    @app.get("/api/media-detail-fast")
    def media_detail_fast(
        kind: str = Query(..., pattern="^(movie|series)$"),
        id: int = Query(..., ge=0),
        _: bool = Depends(core.auth),
    ):
        """Return cached movie/show metadata without blocking on expensive file/episode work.

        Movie details previously waited for a media-file probe before the page could paint.
        TV details waited for Sonarr's full episode list. The fast route uses the same
        persistent catalog already powering the Movies/TV pages. The browser then loads
        movie audio tracks or TV episodes independently after the page is visible.
        """
        catalog_kind = "movies" if kind == "movie" else "series"
        data = cached_catalog(catalog_kind)
        item = next(
            (x for x in (data.get("items") or []) if int(x.get("id", -1)) == int(id)),
            None,
        )
        if not item:
            label = "Movie" if kind == "movie" else "TV show"
            raise HTTPException(404, f"{label} not found in the cached {catalog_kind.title()} catalog")

        detail = dict(item)

        # Preserve fields intentionally omitted from the compact catalog when the matching
        # Arr manager's in-process cache is already warm. This reads memory only and never
        # performs network I/O.
        arr_name = "radarr" if kind == "movie" else "sonarr"
        try:
            arr_cache = (getattr(core.integ, "_ARR_CACHE", {}) or {}).get(arr_name, {}) or {}
            arr_item = next(
                (x for x in (arr_cache.get("items") or []) if int(x.get("id", -1)) == int(id)),
                None,
            )
            if arr_item:
                detail["runtime"] = arr_item.get("runtime")
                detail["genres"] = arr_item.get("genres") if isinstance(arr_item.get("genres"), list) else []
                detail["certification"] = arr_item.get("certification") or detail.get("certification") or ""
                if kind == "series":
                    detail["network"] = arr_item.get("network") or detail.get("network") or ""
                    detail["status"] = arr_item.get("status") or detail.get("status") or ""
        except Exception:
            pass

        if kind == "movie":
            detail.update({
                "kind": "movie",
                "id": int(id),
                "source": detail.get("source") or data.get("source") or "catalog-cache",
                "runtime": detail.get("runtime"),
                "genres": detail.get("genres") if isinstance(detail.get("genres"), list) else [],
                "report": detail.get("report"),
                "tracks": {"audio": [], "subtitles": []},
                "tracks_deferred": True,
                "metadata_cached": True,
            })
            return detail

        total = int(detail.get("episode_file_count") or detail.get("episode_count") or 0)
        detail.update({
            "kind": "series",
            "id": int(id),
            "source": detail.get("source") or data.get("source") or "catalog-cache",
            "runtime": detail.get("runtime"),
            "certification": detail.get("certification") or "",
            "genres": detail.get("genres") if isinstance(detail.get("genres"), list) else [],
            "network": detail.get("network") or "",
            "status": detail.get("status") or "",
            "episodes": [],
            "summary": {
                "cleaned": int(detail.get("censorarr_cleaned") or 0),
                "no_profanity": int(detail.get("censorarr_no_profanity") or 0),
                "failed": int(detail.get("censorarr_failed") or 0),
                "total": total,
            },
            "episodes_deferred": True,
            "metadata_cached": True,
        })
        return detail

    core.fast_metadata_cache_status = lambda: {
        kind: ({"cached": True, "age_seconds": round(read_cache(kind)["age"], 1)} if read_cache(kind) else {"cached": False})
        for kind in ("movies", "series")
    }
