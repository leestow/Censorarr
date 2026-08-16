from __future__ import annotations

import json
import logging
import os
import secrets_store as secret_store
import shutil
import smtplib
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from typing import Any

VERSION = "1.6.3"

_BAZARR_CACHE: dict[str, Any] = {"time": 0.0, "key": None, "items": []}
_BAZARR_SERIES_CACHE: dict[str, Any] = {"time": 0.0, "key": None, "items": []}
_BAZARR_SERIES_REQUESTS: dict[int, float] = {}
_ARR_CACHE: dict[str, dict[str, Any]] = {
    "radarr": {"time": 0.0, "key": None, "items": []},
    "sonarr": {"time": 0.0, "key": None, "items": []},
}


def _request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None,
             data: bytes | None = None, timeout: float = 15.0) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(r.status), r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        body = e.read()
        raise RuntimeError(f"HTTP {e.code} from {url}: {body.decode('utf-8', 'replace')[:500]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Unable to reach {url}: {e.reason}") from e


def _map_path(raw: str, mappings: list[dict]) -> Path:
    v = raw
    for m in mappings or []:
        a = str(m.get("from", "")).rstrip("/\\")
        b = str(m.get("to", "")).rstrip("/\\")
        # Normalize slash direction for matching but preserve the suffix text.
        vv = v.replace("\\", "/")
        aa = a.replace("\\", "/")
        if aa and (vv == aa or vv.startswith(aa + "/")):
            suffix = vv[len(aa):]
            return Path(b + suffix)
    return Path(v.replace("\\", "/"))


def _bazarr_cfg(cfg: dict) -> dict:
    return cfg.get("subtitle_assist", {}).get("bazarr", {})


def bazarr_api_key(cfg: dict) -> str:
    return secret_store.get("bazarr_api_key", env="BAZARR_API_KEY", legacy=_bazarr_cfg(cfg).get("api_key", ""))


def bazarr_headers(cfg: dict) -> dict[str, str]:
    key = bazarr_api_key(cfg)
    return {"X-API-KEY": key, "Accept": "application/json", "User-Agent": f"Censorarr/{VERSION}"}


def bazarr_enabled(cfg: dict) -> bool:
    b = _bazarr_cfg(cfg)
    return bool(cfg.get("subtitle_assist", {}).get("enabled", True) and b.get("enabled", False)
                and str(b.get("url", "")).strip() and bazarr_api_key(cfg))


def bazarr_test(cfg: dict) -> dict:
    b = _bazarr_cfg(cfg)
    base = str(b.get("url", "")).rstrip("/")
    if not base:
        raise RuntimeError("Bazarr URL is blank")
    if not bazarr_api_key(cfg):
        raise RuntimeError("Bazarr API key is blank. Add it in Censorarr Settings → Integrations.")
    headers = bazarr_headers(cfg)
    movie_count = None; series_count = None
    status_m = status_s = 0
    try:
        status_m, body, _ = _request(base + "/api/movies?start=0&length=1", headers=headers)
        data = json.loads(body.decode("utf-8", "replace") or "{}")
        movie_count = data.get("total")
    except Exception as e:
        logging.debug("Bazarr movie test endpoint failed: %s", e)
    try:
        status_s, body, _ = _request(base + "/api/series?start=0&length=1", headers=headers)
        data = json.loads(body.decode("utf-8", "replace") or "{}")
        series_count = data.get("total")
    except Exception as e:
        logging.debug("Bazarr series test endpoint failed: %s", e)
    ok = status_m == 200 or status_s == 200
    if not ok:
        raise RuntimeError("Bazarr connected but neither Movies nor Series API returned successfully")
    return {"ok": True, "status": max(status_m, status_s), "movie_count": movie_count, "series_count": series_count}

def bazarr_movies(cfg: dict, force: bool = False) -> list[dict]:
    global _BAZARR_CACHE
    b = _bazarr_cfg(cfg)
    base = str(b.get("url", "")).rstrip("/")
    key = (base, bazarr_api_key(cfg), json.dumps(b.get("path_mappings", []), sort_keys=True))
    ttl = max(30, int(b.get("cache_seconds", 300)))
    if not force and _BAZARR_CACHE.get("key") == key and time.time() - float(_BAZARR_CACHE.get("time", 0)) < ttl:
        return list(_BAZARR_CACHE.get("items", []))
    if not base or not bazarr_api_key(cfg):
        return []
    _status, body, _ = _request(base + "/api/movies?start=0&length=-1", headers=bazarr_headers(cfg), timeout=30)
    data = json.loads(body.decode("utf-8", "replace") or "{}")
    rows = data.get("data") or []
    if isinstance(rows, dict):
        rows = [rows]
    items: list[dict] = []
    mappings = b.get("path_mappings", [])
    for x in rows:
        raw = str(x.get("path", ""))
        mapped = _map_path(raw, mappings)
        items.append({**x, "_mapped_path": str(mapped)})
    _BAZARR_CACHE = {"time": time.time(), "key": key, "items": items}
    return items

def bazarr_movie_for(media: Path, cfg: dict, force_refresh: bool = False) -> dict | None:
    try:
        target = str(media.resolve())
    except Exception:
        target = str(media)
    rows = bazarr_movies(cfg, force=force_refresh)
    exact = []
    basename = []
    for x in rows:
        mp = Path(str(x.get("_mapped_path", "")))
        try:
            mps = str(mp.resolve())
        except Exception:
            mps = str(mp)
        if mps == target:
            exact.append(x)
        if mp.name.lower() == media.name.lower():
            basename.append(x)
    if len(exact) == 1:
        return exact[0]
    if len(basename) == 1:
        return basename[0]
    if not force_refresh:
        return bazarr_movie_for(media, cfg, force_refresh=True)
    return None

def bazarr_series(cfg: dict, force: bool = False) -> list[dict]:
    global _BAZARR_SERIES_CACHE
    b = _bazarr_cfg(cfg)
    base = str(b.get("url", "")).rstrip("/")
    mappings = b.get("tv_path_mappings", [{"from": "/tv", "to": "/tv"}])
    key = (base, bazarr_api_key(cfg), json.dumps(mappings, sort_keys=True))
    ttl = max(30, int(b.get("cache_seconds", 300)))
    if not force and _BAZARR_SERIES_CACHE.get("key") == key and time.time() - float(_BAZARR_SERIES_CACHE.get("time", 0)) < ttl:
        return list(_BAZARR_SERIES_CACHE.get("items", []))
    if not base or not bazarr_api_key(cfg):
        return []
    _status, body, _ = _request(base + "/api/series?start=0&length=-1", headers=bazarr_headers(cfg), timeout=30)
    data = json.loads(body.decode("utf-8", "replace") or "{}")
    rows = data.get("data") or []
    if isinstance(rows, dict):
        rows = [rows]
    items: list[dict] = []
    for x in rows:
        raw = str(x.get("path", ""))
        mapped = _map_path(raw, mappings)
        items.append({**x, "_mapped_path": str(mapped)})
    _BAZARR_SERIES_CACHE = {"time": time.time(), "key": key, "items": items}
    return items

def bazarr_series_for_episode(media: Path, cfg: dict, force_refresh: bool = False) -> dict | None:
    try:
        target = media.resolve()
    except Exception:
        target = media
    candidates: list[tuple[int, dict]] = []
    for x in bazarr_series(cfg, force=force_refresh):
        root = Path(str(x.get("_mapped_path", "")))
        try:
            rr = root.resolve()
        except Exception:
            rr = root
        if target == rr or rr in target.parents:
            candidates.append((len(str(rr)), x))
    if candidates:
        candidates.sort(key=lambda z: z[0], reverse=True)
        return candidates[0][1]
    if not force_refresh:
        return bazarr_series_for_episode(media, cfg, force_refresh=True)
    return None

def bazarr_request_missing(media: Path, cfg: dict, media_type: str = "movie") -> dict:
    if not bazarr_enabled(cfg):
        raise RuntimeError("Bazarr integration is disabled or incomplete")
    base = str(_bazarr_cfg(cfg).get("url", "")).rstrip("/")
    headers = bazarr_headers(cfg)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    if media_type == "episode":
        series = bazarr_series_for_episode(media, cfg)
        if not series:
            raise RuntimeError("TV series was not found in Bazarr. Check Bazarr/Sonarr TV path mappings.")
        series_id = series.get("sonarrSeriesId")
        if series_id is None:
            raise RuntimeError("Bazarr series record has no sonarrSeriesId")
        series_id = int(series_id)
        # A series-level search already covers all missing episodes in that series. Suppress duplicate
        # requests from neighboring episodes until the normal retry interval has elapsed.
        cooldown = max(30, int(_bazarr_cfg(cfg).get("retry_seconds", 300)))
        last = float(_BAZARR_SERIES_REQUESTS.get(series_id, 0))
        if time.time() - last < cooldown:
            return {"ok": True, "status": 204, "sonarrSeriesId": series_id, "title": series.get("title"),
                    "bazarr_path": series.get("path"), "suppressed_recent": True}
        payload = urllib.parse.urlencode({"seriesid": series_id, "action": "search-missing"}).encode()
        status, _body, _ = _request(base + "/api/series", method="PATCH", headers=headers, data=payload, timeout=30)
        if status in (200, 204):
            _BAZARR_SERIES_REQUESTS[series_id] = time.time()
        return {"ok": status in (200, 204), "status": status, "sonarrSeriesId": series_id,
                "title": series.get("title"), "bazarr_path": series.get("path"), "scope": "series"}
    movie = bazarr_movie_for(media, cfg)
    if not movie:
        raise RuntimeError("Movie was not found in Bazarr. Check Bazarr/Radarr path mappings.")
    radarr_id = movie.get("radarrId")
    if radarr_id is None:
        raise RuntimeError("Bazarr movie record has no radarrId")
    payload = urllib.parse.urlencode({"radarrid": int(radarr_id), "action": "search-missing"}).encode()
    status, _body, _ = _request(base + "/api/movies", method="PATCH", headers=headers, data=payload, timeout=30)
    return {"ok": status in (200, 204), "status": status, "radarrId": int(radarr_id),
            "title": movie.get("title"), "bazarr_path": movie.get("path"), "scope": "movie"}


def _arr_cfg(cfg: dict, name: str) -> dict:
    return (cfg.get("arr_integrations", {}) or {}).get(name, {}) or {}


def arr_api_key(cfg: dict, name: str) -> str:
    env_name = "RADARR_API_KEY" if name == "radarr" else "SONARR_API_KEY"
    return secret_store.get(f"{name}_api_key", env=env_name, legacy=_arr_cfg(cfg, name).get("api_key", ""))


def arr_headers(cfg: dict, name: str) -> dict[str, str]:
    return {
        "X-Api-Key": arr_api_key(cfg, name),
        "Accept": "application/json",
        "User-Agent": f"Censorarr/{VERSION}",
    }


def arr_enabled(cfg: dict, name: str) -> bool:
    c = _arr_cfg(cfg, name)
    return bool(c.get("enabled", False) and str(c.get("url", "")).strip() and arr_api_key(cfg, name))


def _arr_request(cfg: dict, name: str, path: str, timeout: float = 30.0) -> Any:
    c = _arr_cfg(cfg, name)
    base = str(c.get("url", "")).rstrip("/")
    if not base:
        raise RuntimeError(f"{name.title()} URL is blank")
    if not arr_api_key(cfg, name):
        raise RuntimeError(f"{name.title()} API key is blank. Add it in Censorarr Settings → Integrations.")
    status, body, _ = _request(base + path, headers=arr_headers(cfg, name), timeout=timeout)
    if status != 200:
        raise RuntimeError(f"{name.title()} returned HTTP {status}")
    return json.loads(body.decode("utf-8", "replace") or "null")


def arr_test(cfg: dict, name: str) -> dict:
    path = "/api/v3/movie" if name == "radarr" else "/api/v3/series"
    data = _arr_request(cfg, name, path, timeout=15)
    if not isinstance(data, list):
        raise RuntimeError(f"{name.title()} API returned an unexpected response")
    return {"ok": True, "service": name, "count": len(data), "version": VERSION}


def _arr_items(cfg: dict, name: str, force: bool = False) -> list[dict]:
    cache = _ARR_CACHE[name]
    c = _arr_cfg(cfg, name)
    base = str(c.get("url", "")).rstrip("/")
    mappings = c.get("path_mappings", []) or []
    key = (base, arr_api_key(cfg, name), json.dumps(mappings, sort_keys=True))
    ttl = max(30, int(c.get("cache_seconds", 300) or 300))
    if not force and cache.get("key") == key and time.time() - float(cache.get("time", 0)) < ttl:
        return list(cache.get("items", []))
    if not arr_enabled(cfg, name):
        return []
    path = "/api/v3/movie" if name == "radarr" else "/api/v3/series"
    data = _arr_request(cfg, name, path, timeout=30)
    if not isinstance(data, list):
        data = []
    items: list[dict] = []
    for raw in data:
        x = dict(raw)
        if x.get("path"):
            x["_mapped_path"] = str(_map_path(str(x.get("path")), mappings))
        # Radarr movieFile paths are more precise than the movie folder and let us match Censorarr state exactly.
        # Some Radarr versions return only movieFile.relativePath in the movie list, so reconstruct
        # the full host path from movie.path before applying the configured path mapping.
        mf = x.get("movieFile") or {}
        if isinstance(mf, dict):
            raw_file = str(mf.get("path") or "")
            if not raw_file and mf.get("relativePath") and x.get("path"):
                raw_file = str(Path(str(x.get("path"))) / str(mf.get("relativePath")))
            if raw_file:
                x["_mapped_file"] = str(_map_path(raw_file, mappings))
        items.append(x)
    cache.update({"time": time.time(), "key": key, "items": items})
    return items


def radarr_movies(cfg: dict, force: bool = False) -> list[dict]:
    return _arr_items(cfg, "radarr", force=force)


def sonarr_series(cfg: dict, force: bool = False) -> list[dict]:
    return _arr_items(cfg, "sonarr", force=force)


def sonarr_episodes(cfg: dict, series_id: int | str) -> list[dict]:
    """Return Sonarr episodes with mapped local file paths when an episode file exists.

    Sonarr exposes episode metadata and episode-file metadata separately. Censorarr joins them by
    episodeFileId so the GUI can show per-episode CLEAN status against the exact mounted file path.
    """
    sid = int(series_id)
    episodes = _arr_request(cfg, "sonarr", f"/api/v3/episode?seriesId={sid}&includeImages=true", timeout=30)
    try:
        files = _arr_request(cfg, "sonarr", f"/api/v3/episodefile?seriesId={sid}", timeout=30)
    except Exception as e:
        logging.debug("Sonarr episode-file list unavailable for series %s: %s", sid, e)
        files = []
    if not isinstance(episodes, list):
        episodes = []
    if not isinstance(files, list):
        files = []
    c = _arr_cfg(cfg, "sonarr")
    mappings = c.get("path_mappings", []) or []
    series = next((x for x in sonarr_series(cfg) if int(x.get("id", -1)) == sid), {})
    series_path = str(series.get("path") or "")
    file_map: dict[int, dict] = {}
    for raw in files:
        if not isinstance(raw, dict):
            continue
        try:
            fid = int(raw.get("id"))
        except (TypeError, ValueError):
            continue
        f = dict(raw)
        raw_path = str(f.get("path") or "")
        if not raw_path and f.get("relativePath") and series_path:
            raw_path = str(Path(series_path) / str(f.get("relativePath")))
        if raw_path:
            f["_mapped_file"] = str(_map_path(raw_path, mappings))
        file_map[fid] = f
    out: list[dict] = []
    for raw in episodes:
        if not isinstance(raw, dict):
            continue
        e = dict(raw)
        ef = e.get("episodeFile") if isinstance(e.get("episodeFile"), dict) else None
        if ef is None:
            try:
                ef = file_map.get(int(e.get("episodeFileId"))) if e.get("episodeFileId") is not None else None
            except (TypeError, ValueError):
                ef = None
        if ef:
            ef = dict(ef)
            raw_path = str(ef.get("path") or "")
            if not raw_path and ef.get("relativePath") and series_path:
                raw_path = str(Path(series_path) / str(ef.get("relativePath")))
            if raw_path and not ef.get("_mapped_file"):
                ef["_mapped_file"] = str(_map_path(raw_path, mappings))
            e["episodeFile"] = ef
        out.append(e)
    out.sort(key=lambda x: (int(x.get("seasonNumber", 0) or 0), int(x.get("episodeNumber", 0) or 0)))
    return out


def arr_open_url(cfg: dict, name: str, item_id: int | str | None = None) -> str:
    base = str(_arr_cfg(cfg, name).get("url", "")).rstrip("/")
    if not base:
        return ""
    if item_id is None:
        return base
    # These routes are stable UI entry points; if an install changes them the base URL still remains useful.
    if name == "radarr":
        return base + "/movie/" + str(item_id)
    return base + "/series/" + str(item_id)


def _plex_cfg(cfg: dict) -> tuple[str, str]:
    rcfg = cfg.get("rating_filter", {})
    base = str(rcfg.get("plex_url", "")).rstrip("/")
    token = secret_store.get("plex_token", env="PLEX_TOKEN", legacy=rcfg.get("plex_token", ""))
    return base, token


def plex_request(cfg: dict, path: str, *, method: str = "GET", timeout: float = 15) -> dict:
    base, token = _plex_cfg(cfg)
    if not base or not token:
        raise RuntimeError("Plex URL/token not configured")
    headers = {
        "Accept": "application/json", "X-Plex-Token": token,
        "X-Plex-Client-Identifier": "censorarr-docker", "X-Plex-Product": "Censorarr",
        "X-Plex-Version": VERSION,
    }
    status, body, _ = _request(base + path, method=method, headers=headers, timeout=timeout)
    if not body:
        return {"status": status}
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return {"status": status, "text": body.decode("utf-8", "replace")[:500]}


def plex_active_sessions(cfg: dict) -> list[dict]:
    data = plex_request(cfg, "/status/sessions")
    items = data.get("MediaContainer", {}).get("Metadata", []) or []
    out = []
    for x in items:
        # Audio-only sessions are cheap enough that they normally should not block ASR.
        if str(x.get("type", "")).lower() not in {"movie", "episode", "clip"}:
            continue
        user = ((x.get("User") or [{}])[0] if isinstance(x.get("User"), list) else x.get("User") or {})
        player = ((x.get("Player") or [{}])[0] if isinstance(x.get("Player"), list) else x.get("Player") or {})
        out.append({"title": x.get("title"), "grandparentTitle": x.get("grandparentTitle"),
                    "user": user.get("title"), "player": player.get("title"),
                    "state": player.get("state")})
    return out


def plex_refresh_rating_key(cfg: dict, rating_key: str | int) -> bool:
    try:
        plex_request(cfg, f"/library/metadata/{rating_key}/refresh", method="PUT", timeout=20)
        return True
    except Exception as e:
        logging.warning("Plex item refresh failed for ratingKey %s: %s", rating_key, e)
        return False


def plex_scan_library(cfg: dict, media_type: str = "movie") -> bool:
    try:
        if media_type == "episode":
            tv = cfg.get("tv", {})
            rcfg = dict(tv.get("rating_filter", {}))
            shared = cfg.get("rating_filter", {})
            if not str(rcfg.get("plex_url", "")).strip(): rcfg["plex_url"] = shared.get("plex_url", "")
            title = str(rcfg.get("plex_library", "TV Shows")).lower()
        else:
            rcfg = cfg.get("rating_filter", {})
            title = str(rcfg.get("plex_library", "Movies")).lower()
        # Library refresh uses the same Plex server/token as normal requests.
        data = plex_request(cfg, "/library/sections")
        dirs = data.get("MediaContainer", {}).get("Directory", []) or []
        expected = "show" if media_type == "episode" else "movie"
        section = next((str(d.get("key")) for d in dirs if str(d.get("title", "")).lower() == title and str(d.get("type", "")).lower() == expected), None)
        if not section:
            return False
        plex_request(cfg, f"/library/sections/{section}/refresh", timeout=20)
        return True
    except Exception as e:
        logging.warning("Plex library scan request failed: %s", e)
        return False

def schedule_allows_now(cfg: dict, now: time.struct_time | None = None) -> tuple[bool, str]:
    s = cfg.get("processing_schedule", {})
    if not s.get("enabled", False):
        return True, "schedule-disabled"
    now = now or time.localtime()
    days = s.get("days", [0, 1, 2, 3, 4, 5, 6])
    try:
        days = {int(x) for x in days}
    except Exception:
        days = set(range(7))
    start_s = str(s.get("start", "00:00"))
    end_s = str(s.get("end", "23:59"))
    def mins(v: str) -> int:
        h, m = [int(x) for x in v.split(":", 1)]
        return h * 60 + m
    try:
        start = mins(start_s); end = mins(end_s)
    except Exception:
        return True, "invalid-schedule"
    cur = now.tm_hour * 60 + now.tm_min
    dow = (now.tm_wday)  # Monday=0
    if start <= end:
        ok = dow in days and start <= cur <= end
    else:
        # Overnight window: e.g. 23:00-06:00. After midnight belongs to previous day's window.
        if cur >= start:
            ok = dow in days
        else:
            prev = (dow - 1) % 7
            ok = prev in days and cur <= end
    return ok, "inside-window" if ok else "outside-window"


def processing_gate(cfg: dict) -> tuple[bool, str, dict]:
    # A fresh install stays idle until the guided setup wizard is completed. Older configs inherit
    # setup.completed=True from DEFAULT_CONFIG, so upgrades are not blocked.
    if not bool((cfg.get("setup", {}) or {}).get("completed", True)):
        return False, "setup-required", {"reason": "Complete the Setup Wizard before automatic processing starts."}
    ok, why = schedule_allows_now(cfg)
    if not ok:
        return False, "schedule", {"reason": why}
    pcfg = cfg.get("plex_activity", {})
    if pcfg.get("pause_when_streaming", False):
        try:
            sessions = plex_active_sessions(cfg)
            active = [x for x in sessions if str(x.get("state", "")).lower() not in {"paused", "stopped"}]
            if active:
                return False, "plex-active", {"sessions": active}
        except Exception as e:
            # Fail open by default; a broken Plex query should not deadlock the cleaner.
            logging.warning("Could not check Plex sessions; continuing: %s", e)
    return True, "ok", {}


def system_stats(media_path: str = "/media") -> dict:
    stats: dict[str, Any] = {"load": None, "memory": {}, "disk": {}, "temperatures": []}
    try:
        stats["load"] = list(os.getloadavg())
    except Exception:
        pass
    try:
        vals = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            vals[k] = int(v.strip().split()[0]) * 1024
        total = vals.get("MemTotal", 0); available = vals.get("MemAvailable", 0)
        stats["memory"] = {"total": total, "available": available, "used": max(0, total - available)}
    except Exception:
        pass
    try:
        du = shutil.disk_usage(media_path)
        stats["disk"] = {"total": du.total, "used": du.used, "free": du.free}
    except Exception:
        pass
    try:
        temps = []
        for p in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
            try:
                raw = float(p.read_text().strip())
                c = raw / 1000.0 if raw > 200 else raw
                if -20 < c < 150:
                    temps.append(round(c, 1))
            except Exception:
                continue
        stats["temperatures"] = temps
    except Exception:
        pass
    return stats


def notify(event: str, message: str, cfg: dict, extra: dict | None = None) -> None:
    ncfg = cfg.get("notifications", {})
    if not ncfg.get("enabled", False):
        return
    events = set(str(x) for x in ncfg.get("events", ["completed", "failed", "queue-finished"]))
    if event not in events:
        return
    extra = extra or {}
    # Generic/Discord webhook.
    wcfg = ncfg.get("webhook", {})
    if wcfg.get("enabled", False) and str(wcfg.get("url", "")).strip():
        try:
            kind = str(wcfg.get("type", "generic")).lower()
            body = {"content": message} if kind == "discord" else {"event": event, "message": message, **extra}
            data = json.dumps(body).encode()
            _request(str(wcfg["url"]), method="POST", headers={"Content-Type": "application/json"}, data=data, timeout=10)
        except Exception as e:
            logging.warning("Webhook notification failed: %s", e)
    # Pushover.
    pcfg = ncfg.get("pushover", {})
    if pcfg.get("enabled", False):
        token = secret_store.get("pushover_app_token", env="PUSHOVER_APP_TOKEN", legacy=pcfg.get("app_token", ""))
        user = secret_store.get("pushover_user_key", env="PUSHOVER_USER_KEY", legacy=pcfg.get("user_key", ""))
        if token and user:
            try:
                data = urllib.parse.urlencode({"token": token, "user": user, "message": message,
                                               "title": str(pcfg.get("title", "Censorarr"))}).encode()
                _request("https://api.pushover.net/1/messages.json", method="POST",
                         headers={"Content-Type": "application/x-www-form-urlencoded"}, data=data, timeout=10)
            except Exception as e:
                logging.warning("Pushover notification failed: %s", e)
    # SMTP email.
    ecfg = ncfg.get("email", {})
    if ecfg.get("enabled", False) and ecfg.get("host") and ecfg.get("to"):
        try:
            em = EmailMessage()
            em["Subject"] = f"Censorarr: {event}"
            em["From"] = str(ecfg.get("from") or ecfg.get("username") or "censorarr@localhost")
            em["To"] = str(ecfg.get("to"))
            em.set_content(message)
            host = str(ecfg.get("host")); port = int(ecfg.get("port", 587))
            user = str(ecfg.get("username", "")); password = secret_store.get("smtp_password", env="SMTP_PASSWORD", legacy=ecfg.get("password", ""))
            use_ssl = bool(ecfg.get("ssl", False)); starttls = bool(ecfg.get("starttls", True))
            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, timeout=10, context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(host, port, timeout=10)
                if starttls:
                    server.starttls(context=ssl.create_default_context())
            with server:
                if user and password:
                    server.login(user, password)
                server.send_message(em)
        except Exception as e:
            logging.warning("Email notification failed: %s", e)
