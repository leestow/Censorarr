#!/usr/bin/env python3
"""Small dependency-free self-test for the persistent Plex metadata cache."""
from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import plex_metadata_cache as cache


def main() -> int:
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    movie = root / "Movies" / "Example (2026)" / "Example (2026).mkv"
    movie.parent.mkdir(parents=True)
    movie.write_bytes(b"x")

    calls: list[str] = []
    revision = {"value": "100"}
    items = [
        {
            "ratingKey": "42",
            "title": "Example",
            "contentRating": "PG-13",
            "Media": [{"Part": [{"file": "/plex/Movies/Example (2026)/Example (2026).mkv"}]}],
        }
    ]

    def plex_get(_cfg, path, _rcfg=None):
        calls.append(path)
        if path == "/library/sections":
            return {"MediaContainer": {"Directory": [{
                "key": "1", "title": "Movies", "type": "movie", "updatedAt": revision["value"]
            }]}}
        if "/library/sections/1/all?type=1" in path:
            start = 0
            size = 500
            for part in path.split("?")[-1].split("&"):
                if part.startswith("X-Plex-Container-Start="):
                    start = int(part.split("=", 1)[1])
                elif part.startswith("X-Plex-Container-Size="):
                    size = int(part.split("=", 1)[1])
            page = items[start:start + size]
            return {"MediaContainer": {"Metadata": page, "totalSize": len(items)}}
        raise AssertionError(f"Unexpected fake Plex path: {path}")

    def map_path(raw, mappings):
        value = str(raw)
        for mapping in mappings:
            src = str(mapping.get("from", "")).rstrip("/")
            dst = str(mapping.get("to", "")).rstrip("/")
            if value == src or value.startswith(src + "/"):
                value = dst + value[len(src):]
                break
        return Path(value)

    cfg = {
        "media_roots": [str(root / "Movies")],
        "rating_filter": {
            "plex_url": "http://plex.test:32400",
            "plex_library": "Movies",
            "plex_path_mappings": [{"from": "/plex/Movies", "to": str(root / "Movies")}],
        },
        "plex_metadata_cache": {
            "database": str(root / "plex_metadata.db"),
            "check_interval_seconds": 30,
            "max_full_refresh_age_seconds": 3600,
            "stale_while_refresh": True,
            "page_size": 50,
        },
    }

    pc = SimpleNamespace()
    pc.DEFAULT_CONFIG = {}
    pc.logging = logging.getLogger("plex-cache-selftest")
    pc._PLEX_CACHE = {}
    pc._plex_get = plex_get
    pc._map_plex_path = map_path
    pc._resolved_path = lambda p: Path(p).resolve()
    pc.tv_media_roots = lambda _cfg: []
    pc.rating_cfg_for = lambda _path, c: c["rating_filter"]
    pc._plex_library_index = lambda *_args, **_kwargs: ({}, {})

    cache.install(pc)

    # Initial lookup must build the persistent cache and map the Plex path locally.
    by_path, _ = pc._plex_library_index(cfg, "movie")
    expected = str(movie.resolve())
    assert expected in by_path, (expected, list(by_path))
    assert by_path[expected]["ratingKey"] == "42"
    assert Path(cfg["plex_metadata_cache"]["database"]).exists()
    full_calls = sum("/all?type=1" in x for x in calls)
    assert full_calls == 1, calls

    # Normal repeated lookup inside the check interval must not contact Plex at all.
    calls.clear()
    by_path2, _ = pc._plex_library_index(cfg, "movie")
    assert expected in by_path2
    assert calls == [], calls

    # Simulate a worker/container restart: clear RAM, keep SQLite. It should load from
    # disk immediately without rebuilding the whole library.
    cache._MEMORY.clear()
    calls.clear()
    by_path3, _ = pc._plex_library_index(cfg, "movie")
    assert expected in by_path3
    assert not any("/all?type=1" in x for x in calls), calls

    # Force remains an explicit synchronous full refresh for a future Refresh button.
    calls.clear()
    pc._plex_library_index(cfg, "movie", force=True)
    assert sum("/all?type=1" in x for x in calls) == 1, calls

    status = cache.status(cfg)
    assert status["ok"] is True
    assert status["libraries"] and status["libraries"][0]["item_count"] == 1

    print("Plex metadata cache self-test passed")
    temp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
