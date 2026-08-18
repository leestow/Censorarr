"""Persistent, change-aware Plex metadata cache for Censorarr.

The legacy worker kept a full Plex library index only in memory for five minutes.
Large libraries therefore had to be downloaded repeatedly and every worker restart
started cold. This module replaces that index with a SQLite-backed cache that:

* survives container restarts;
* returns stale-but-valid metadata immediately while a changed library refreshes;
* checks Plex's small /library/sections response before downloading a library again;
* paginates large movie/episode/show listings; and
* refreshes at most one copy of a library at a time.

It is installed as a runtime patch by the Docker/Synology worker so the existing
rating/filtering code can keep calling ``plex_item_for`` unchanged.
"""
from __future__ import annotations

import copy
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "database": "/config/plex_metadata.db",
    "check_interval_seconds": 300,
    "max_full_refresh_age_seconds": 86400,
    "stale_while_refresh": True,
    "page_size": 500,
}

_DB_LOCK = threading.RLock()
_MEMORY_LOCK = threading.RLock()
_MEMORY: dict[str, dict[str, Any]] = {}
_REFRESHING: set[str] = set()
_INSTALLED_FOR: set[int] = set()


def _settings(cfg: dict) -> dict[str, Any]:
    out = dict(DEFAULTS)
    out.update(cfg.get("plex_metadata_cache", {}) or {})
    out["check_interval_seconds"] = max(30, int(out.get("check_interval_seconds", 300) or 300))
    out["max_full_refresh_age_seconds"] = max(
        out["check_interval_seconds"], int(out.get("max_full_refresh_age_seconds", 86400) or 86400)
    )
    out["page_size"] = min(2000, max(50, int(out.get("page_size", 500) or 500)))
    return out


def _db_path(cfg: dict) -> Path:
    raw = str(_settings(cfg).get("database") or "/config/plex_metadata.db").strip()
    return Path(raw or "/config/plex_metadata.db")


def _connect(cfg: dict) -> sqlite3.Connection:
    path = _db_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=20.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.DatabaseError:
        pass
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS libraries (
            cache_key TEXT PRIMARY KEY,
            media_type TEXT NOT NULL,
            plex_url TEXT NOT NULL,
            library_name TEXT NOT NULL,
            section_key TEXT,
            section_updated_at TEXT,
            checked_at REAL NOT NULL DEFAULT 0,
            synced_at REAL NOT NULL DEFAULT 0,
            item_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS items (
            cache_key TEXT NOT NULL,
            path TEXT NOT NULL,
            basename TEXT NOT NULL,
            payload TEXT NOT NULL,
            PRIMARY KEY (cache_key, path)
        );
        CREATE INDEX IF NOT EXISTS idx_plex_items_basename
            ON items(cache_key, basename);
        """
    )
    return conn


def _rating_cfg(pc, cfg: dict, media_type: str) -> dict:
    if media_type == "episode":
        root = Path((pc.tv_media_roots(cfg) or ["/tv"])[0])
    else:
        root = Path((cfg.get("media_roots") or ["/media"])[0])
    return pc.rating_cfg_for(root, cfg)


def _cache_key(media_type: str, rcfg: dict) -> str:
    return json.dumps(
        {
            "media_type": media_type,
            "plex_url": str(rcfg.get("plex_url", "")).rstrip("/"),
            "library": str(rcfg.get("plex_library", "TV Shows" if media_type == "episode" else "Movies")),
            "path_mappings": rcfg.get("plex_path_mappings", []) or [],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _library_meta(cfg: dict, key: str) -> dict[str, Any]:
    with _DB_LOCK:
        try:
            conn = _connect(cfg)
            try:
                row = conn.execute("SELECT * FROM libraries WHERE cache_key=?", (key,)).fetchone()
                return _row_dict(row)
            finally:
                conn.close()
        except Exception:
            return {}


def _load_disk(cfg: dict, key: str) -> tuple[dict[str, Any], dict[str, list[Any]], dict[str, Any]]:
    by_path: dict[str, Any] = {}
    by_basename: dict[str, list[Any]] = {}
    meta: dict[str, Any] = {}
    with _DB_LOCK:
        conn = _connect(cfg)
        try:
            meta = _row_dict(conn.execute("SELECT * FROM libraries WHERE cache_key=?", (key,)).fetchone())
            if not meta:
                return by_path, by_basename, meta
            for row in conn.execute("SELECT path, basename, payload FROM items WHERE cache_key=?", (key,)):
                try:
                    item = json.loads(row["payload"])
                except Exception:
                    continue
                path = str(row["path"])
                basename = str(row["basename"])
                by_path[path] = item
                by_basename.setdefault(basename, []).append(item)
        finally:
            conn.close()
    return by_path, by_basename, meta


def _save_disk(
    cfg: dict,
    key: str,
    media_type: str,
    rcfg: dict,
    section_key: str,
    section_updated_at: str,
    by_path: dict[str, Any],
) -> dict[str, Any]:
    now = time.time()
    library = str(rcfg.get("plex_library", "TV Shows" if media_type == "episode" else "Movies"))
    base = str(rcfg.get("plex_url", "")).rstrip("/")
    rows = [
        (key, path, Path(path).name.lower(), json.dumps(item, ensure_ascii=False, separators=(",", ":")))
        for path, item in by_path.items()
    ]
    with _DB_LOCK:
        conn = _connect(cfg)
        try:
            with conn:
                conn.execute("DELETE FROM items WHERE cache_key=?", (key,))
                if rows:
                    conn.executemany(
                        "INSERT OR REPLACE INTO items(cache_key,path,basename,payload) VALUES(?,?,?,?)",
                        rows,
                    )
                conn.execute(
                    """
                    INSERT INTO libraries(
                        cache_key,media_type,plex_url,library_name,section_key,section_updated_at,
                        checked_at,synced_at,item_count,last_error
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        media_type=excluded.media_type,
                        plex_url=excluded.plex_url,
                        library_name=excluded.library_name,
                        section_key=excluded.section_key,
                        section_updated_at=excluded.section_updated_at,
                        checked_at=excluded.checked_at,
                        synced_at=excluded.synced_at,
                        item_count=excluded.item_count,
                        last_error=''
                    """,
                    (key, media_type, base, library, section_key, section_updated_at, now, now, len(by_path), ""),
                )
        finally:
            conn.close()
    return {
        "cache_key": key,
        "media_type": media_type,
        "plex_url": base,
        "library_name": library,
        "section_key": section_key,
        "section_updated_at": section_updated_at,
        "checked_at": now,
        "synced_at": now,
        "item_count": len(by_path),
        "last_error": "",
    }


def _touch_check(cfg: dict, key: str, *, error: str = "", updated_at: str | None = None) -> None:
    now = time.time()
    with _DB_LOCK:
        try:
            conn = _connect(cfg)
            try:
                with conn:
                    if updated_at is None:
                        conn.execute(
                            "UPDATE libraries SET checked_at=?, last_error=? WHERE cache_key=?",
                            (now, error, key),
                        )
                    else:
                        conn.execute(
                            "UPDATE libraries SET checked_at=?, section_updated_at=?, last_error=? WHERE cache_key=?",
                            (now, str(updated_at), error, key),
                        )
            finally:
                conn.close()
        except Exception:
            pass
    with _MEMORY_LOCK:
        if key in _MEMORY:
            _MEMORY[key]["checked_at"] = now
            if updated_at is not None:
                _MEMORY[key]["section_updated_at"] = str(updated_at)
            _MEMORY[key]["last_error"] = error


def _section_info(pc, cfg: dict, rcfg: dict, media_type: str) -> tuple[str, str]:
    library = str(rcfg.get("plex_library", "TV Shows" if media_type == "episode" else "Movies"))
    expected_type = "show" if media_type == "episode" else "movie"
    sections = pc._plex_get(cfg, "/library/sections", rcfg).get("MediaContainer", {}).get("Directory", [])
    for section in sections or []:
        if str(section.get("title", "")).lower() != library.lower():
            continue
        if str(section.get("type", "")).lower() != expected_type:
            continue
        return str(section.get("key") or ""), str(section.get("updatedAt") or "")
    raise RuntimeError(f"Plex {expected_type} library not found: {library}")


def _paged_metadata(pc, cfg: dict, rcfg: dict, path: str, page_size: int) -> list[dict]:
    out: list[dict] = []
    start = 0
    while True:
        sep = "&" if "?" in path else "?"
        page_path = (
            f"{path}{sep}X-Plex-Container-Start={start}"
            f"&X-Plex-Container-Size={page_size}"
        )
        container = pc._plex_get(cfg, page_path, rcfg).get("MediaContainer", {}) or {}
        rows = container.get("Metadata", []) or []
        if not isinstance(rows, list):
            rows = []
        out.extend(rows)
        returned = len(rows)
        try:
            total = int(container.get("totalSize"))
        except (TypeError, ValueError):
            total = None

        if returned == 0:
            break
        start += returned
        if total is not None and start >= total:
            break
        # A server/proxy that ignores Plex pagination may return the entire library.
        # Do not issue the same giant response repeatedly in that case.
        if returned > page_size:
            break
        if total is None and returned < page_size:
            break
    return out


def _build_index(pc, cfg: dict, rcfg: dict, media_type: str, section: str, page_size: int):
    plex_type = 4 if media_type == "episode" else 1
    data = _paged_metadata(pc, cfg, rcfg, f"/library/sections/{section}/all?type={plex_type}", page_size)
    show_ratings: dict[str, str] = {}
    if media_type == "episode":
        try:
            shows = _paged_metadata(pc, cfg, rcfg, f"/library/sections/{section}/all?type=2", page_size)
            show_ratings = {
                str(x.get("ratingKey")): str(x.get("contentRating"))
                for x in shows
                if x.get("ratingKey") and x.get("contentRating")
            }
        except Exception as exc:
            pc.logging.debug("Could not load Plex show rating fallback: %s", exc)

    by_path: dict[str, Any] = {}
    by_basename: dict[str, list[Any]] = {}
    mappings = rcfg.get("plex_path_mappings", []) or []
    for original in data:
        item = dict(original)
        if media_type == "episode" and not item.get("contentRating"):
            inherited = show_ratings.get(str(item.get("grandparentRatingKey")))
            if inherited:
                item["contentRating"] = inherited
                item["contentRatingInherited"] = True
        for med in item.get("Media", []) or []:
            for part in med.get("Part", []) or []:
                raw = part.get("file")
                if not raw:
                    continue
                mapped = pc._map_plex_path(str(raw), mappings)
                keypath = str(pc._resolved_path(mapped))
                by_path[keypath] = item
                by_basename.setdefault(mapped.name.lower(), []).append(item)
    return by_path, by_basename


def _remember(key: str, by_path: dict[str, Any], by_basename: dict[str, list[Any]], meta: dict[str, Any]) -> None:
    with _MEMORY_LOCK:
        _MEMORY[key] = {
            "by_path": by_path,
            "by_basename": by_basename,
            **meta,
        }


def _cached(key: str) -> dict[str, Any] | None:
    with _MEMORY_LOCK:
        row = _MEMORY.get(key)
        return row if row is not None else None


def _refresh_full(pc, cfg: dict, media_type: str, rcfg: dict, key: str) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    settings = _settings(cfg)
    section, updated_at = _section_info(pc, cfg, rcfg, media_type)
    started = time.time()
    by_path, by_basename = _build_index(pc, cfg, rcfg, media_type, section, settings["page_size"])
    meta = _save_disk(cfg, key, media_type, rcfg, section, updated_at, by_path)
    _remember(key, by_path, by_basename, meta)
    pc.logging.info(
        "Persistent Plex metadata cache refreshed: %d %s paths in %.1fs",
        len(by_path),
        "episode" if media_type == "episode" else "movie",
        time.time() - started,
    )
    return by_path, by_basename


def _background_refresh(pc, cfg: dict, media_type: str, rcfg: dict, key: str) -> None:
    with _MEMORY_LOCK:
        if key in _REFRESHING:
            return
        _REFRESHING.add(key)

    cfg_copy = copy.deepcopy(cfg)
    rcfg_copy = copy.deepcopy(rcfg)

    def run() -> None:
        try:
            _refresh_full(pc, cfg_copy, media_type, rcfg_copy, key)
        except Exception as exc:
            _touch_check(cfg_copy, key, error=str(exc))
            pc.logging.warning("Background Plex metadata refresh failed: %s", exc)
        finally:
            with _MEMORY_LOCK:
                _REFRESHING.discard(key)

    threading.Thread(
        target=run,
        daemon=True,
        name=f"plex-cache-{media_type}",
    ).start()


def _persistent_library_index(pc, cfg: dict, media_type: str, force: bool = False):
    settings = _settings(cfg)
    if not bool(settings.get("enabled", True)):
        return pc._plex_library_index_before_persistent(cfg, media_type, force=force)

    rcfg = _rating_cfg(pc, cfg, media_type)
    key = _cache_key(media_type, rcfg)
    mem = _cached(key)
    if mem is None:
        try:
            by_path, by_basename, meta = _load_disk(cfg, key)
        except Exception as exc:
            pc.logging.warning("Could not load persistent Plex metadata cache: %s", exc)
            by_path, by_basename, meta = {}, {}, {}
        if meta:
            _remember(key, by_path, by_basename, meta)
            mem = _cached(key)

    # A manual/explicit force remains synchronous and truly fresh. Normal lookups are
    # change-aware and can return stale cache immediately while refreshing in background.
    if force:
        return _refresh_full(pc, cfg, media_type, rcfg, key)

    if not mem:
        pc.logging.info("Persistent Plex metadata cache is empty; performing initial %s sync", media_type)
        return _refresh_full(pc, cfg, media_type, rcfg, key)

    now = time.time()
    checked_at = float(mem.get("checked_at", 0) or 0)
    if now - checked_at < settings["check_interval_seconds"]:
        return mem["by_path"], mem["by_basename"]

    try:
        section, updated_at = _section_info(pc, cfg, rcfg, media_type)
        old_updated = str(mem.get("section_updated_at") or "")
        synced_at = float(mem.get("synced_at", 0) or 0)
        max_age_due = now - synced_at >= settings["max_full_refresh_age_seconds"]
        changed = (
            str(mem.get("section_key") or "") != section
            or (bool(updated_at) and bool(old_updated) and updated_at != old_updated)
            or (bool(updated_at) and not old_updated)
            or max_age_due
        )
        if not changed:
            _touch_check(cfg, key, updated_at=updated_at)
            pc.logging.debug("Plex %s library unchanged; using persistent metadata cache", media_type)
            return mem["by_path"], mem["by_basename"]

        reason = "library changed" if not max_age_due else "maximum cache age reached"
        if bool(settings.get("stale_while_refresh", True)):
            pc.logging.info("Plex %s %s; using cached metadata while refreshing", media_type, reason)
            _background_refresh(pc, cfg, media_type, rcfg, key)
            _touch_check(cfg, key, updated_at=updated_at)
            return mem["by_path"], mem["by_basename"]
        return _refresh_full(pc, cfg, media_type, rcfg, key)
    except Exception as exc:
        _touch_check(cfg, key, error=str(exc))
        pc.logging.warning("Plex metadata change check failed; using persistent cache: %s", exc)
        return mem["by_path"], mem["by_basename"]


def status(cfg: dict) -> dict[str, Any]:
    """Return cache health without contacting Plex."""
    path = _db_path(cfg)
    rows: list[dict[str, Any]] = []
    if path.exists():
        with _DB_LOCK:
            try:
                conn = _connect(cfg)
                try:
                    rows = [dict(row) for row in conn.execute(
                        "SELECT media_type,library_name,section_updated_at,checked_at,synced_at,item_count,last_error "
                        "FROM libraries ORDER BY media_type"
                    )]
                finally:
                    conn.close()
            except Exception as exc:
                return {"ok": False, "database": str(path), "error": str(exc), "libraries": []}
    return {"ok": True, "database": str(path), "libraries": rows}


def install(pc) -> None:
    """Patch Censorarr's Plex library index with the persistent implementation."""
    ident = id(pc)
    if ident in _INSTALLED_FOR:
        return
    defaults = pc.DEFAULT_CONFIG.setdefault("plex_metadata_cache", {})
    for name, value in DEFAULTS.items():
        defaults.setdefault(name, value)

    if not hasattr(pc, "_plex_library_index_before_persistent"):
        pc._plex_library_index_before_persistent = pc._plex_library_index

    def persistent(cfg: dict, media_type: str, force: bool = False):
        return _persistent_library_index(pc, cfg, media_type, force=force)

    pc._plex_library_index = persistent
    _INSTALLED_FOR.add(ident)
