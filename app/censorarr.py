#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import wave
from array import array
import urllib.request
import urllib.parse
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

import yaml
from faster_whisper import WhisperModel

import integrations as integ
import subtitle_assist as subassist
import remote_asr
import secrets_store as secret_store

VERSION = "1.6.3"
STOP = False

FAMILY_ALIASES: dict[str, list[str]] = {
    "arsehole": ["asshole", "assholes", "ass hole", "ass holes", "arsehole", "arseholes"],
    "shit": ["shit", "shits", "shit's", "shitty", "shittier", "shittiest", "shitting"],
    "fuck": ["fuck", "fucks", "fucked", "fucking", "fucker", "fuckers", "fuckin", "fuckin'"],
    "motherfucker": [
        "motherfucker", "motherfuckers", "motherfucking", "mother fucker",
        "mother fuckers", "mother fucking", "mother-fucker", "mother-fuckers",
    ],
    "bitch": ["bitch", "bitches", "bitching", "bitched"],
    "bastard": ["bastard", "bastards"],
    "cunt": ["cunt", "cunts"],
    "fuckhead": ["fuckhead", "fuckheads"],
    "fucktard": ["fucktard", "fucktards"],
    "fuckwad": ["fuckwad", "fuckwads"],
    "fuckwit": ["fuckwit", "fuckwits"],
    "bullshit": ["bullshit", "bull shit", "bull-shit"],
    "dogshit": ["dogshit", "dog shit", "dog-shit"],
    "horseshit": ["horseshit", "horse shit", "horse-shit"],
}

DEFAULT_CONFIG: dict[str, Any] = {
    "media_roots": ["/media"],
    "extensions": [".mkv", ".mp4", ".m4v"],
    "scan_interval_seconds": 120,
    "stable_seconds": 300,
    "process_existing": True,
    "dry_run": True,
    "marker": {"enabled": True, "filename": ".censorarr.done.json"},
    # DEFAULT_CONFIG is also used to deep-merge older installations. Existing explicit values win.
    # The example config for a brand-new install marks setup incomplete; legacy installs default to
    # complete so an upgrade never unexpectedly blocks an already-running library.
    "setup": {"completed": True, "wizard_version": 1},
    "rating_filter": {
        "enabled": False, "source": "plex", "minimum": "PG-13",
        "plex_url": "http://PLEX_SERVER_IP:32400", "plex_library": "Movies",
        "plex_token": "",
        "plex_path_mappings": [{"from": "/volume1/video/Movies", "to": "/media"}],
        "include_unrated": False,
    },
    "tv": {
        "enabled": True,
        "media_roots": ["/tv"],
        "rating_filter": {
            "enabled": False, "source": "plex", "minimum": "TV-14",
            "plex_url": "", "plex_library": "TV Shows", "plex_token": "",
            "plex_path_mappings": [{"from": "/volume1/TV Shows", "to": "/tv"}],
            "include_unrated": False,
        },
    },
    "whisper": {
        "model": "small", "device": "cpu", "compute_type": "int8", "language": "en",
        "beam_size": 5, "vad_filter": False, "condition_on_previous_text": False,
        "backend": "local",
        "remote": {
            "enabled": False, "url": "http://GPU_WORKER_IP:9000", "token": "",
            "model": "small.en", "timeout_seconds": 1800, "fallback_to_local": True,
        },
    },
    "profanity": {
        "file": "/config/en.json", "min_severity": 3, "padding_before_ms": 120,
        "padding_after_ms": 160, "max_word_window": 4,
    },
    "precision_alignment": {
        "enabled": True,
        "padding_before_ms": 25,
        "padding_after_ms": 40,
        "edge_search_ms": 120,
        "neighbor_guard_ms": 12,
        "energy_threshold_ratio": 0.22,
        "frame_ms": 5,
    },
    "rescue": {
        "enabled": True, "confidence_trigger": 0.18, "fuzzy_confidence_ceiling": 0.70,
        "fuzzy_similarity": 0.72, "window_before_seconds": 1.5, "window_after_seconds": 1.5,
        "merge_gap_seconds": 0.75, "max_windows": 250, "prefer_center_channel": True,
        "prompt": (
            "Transcribe the dialogue verbatim, including profanity. Possible words may include: "
            "asshole, ass, fuck, fucking, fucker, shit, shitty, bitch, bastard, damn, "
            "goddamn, dick, cunt, motherfucker. Do not censor or euphemize spoken words."
        ),
        "mild_evidence": ["ass"],
    },
    "clean_track": {
        "title": "English - CLEAN", "language": "eng", "make_default": True,
        "place_clean_first": True,
        "replace_existing_clean": True, "reprocess_existing_clean": False, "codec": "auto",
    },
    "safety": {
        "validate_output": True, "duration_tolerance_seconds": 2.0,
        "preserve_owner_mode": True, "backup_original": False,
    },
    "reports": {
        "directory": "/config/reports", "keep_transcript_json": True,
        "keep_rescue_details": True,
    },
    "subtitle_assist": {
        "enabled": True, "use_embedded": True, "use_external": True,
        "ignore_forced_only": True, "accept_untagged_english": True,
        "use_dialogue_as_rescue_prompt": True, "whisper_overrides_omissions": True,
        "alignment_tolerance_seconds": 2.0, "minimum_alignment_ratio": 0.45,
        "global_text_alignment": True, "global_context_cues": 1,
        "global_minimum_ratio": 0.58, "global_minimum_anchor_words": 3,
        "bazarr": {
            "enabled": False, "url": "http://BAZARR_SERVER_IP:6767", "api_key": "",
            "path_mappings": [{"from": "/movies", "to": "/media"}],
            "tv_path_mappings": [{"from": "/tv", "to": "/tv"}],
            "wait_for_download": True, "timeout_minutes": 30, "check_interval_seconds": 30,
            "retry_seconds": 300, "max_attempts": 3, "cache_seconds": 300,
        },
    },
    "review_mode": {"enabled": False},
    "processing_schedule": {
        "enabled": False, "start": "00:00", "end": "23:59",
        "days": [0, 1, 2, 3, 4, 5, 6],
    },
    "arr_integrations": {
        "radarr": {
            "enabled": False, "url": "http://RADARR_SERVER_IP:7878", "api_key": "",
            "path_mappings": [{"from": "/movies", "to": "/media"}], "cache_seconds": 300,
        },
        "sonarr": {
            "enabled": False, "url": "http://SONARR_SERVER_IP:8989", "api_key": "",
            "path_mappings": [{"from": "/tv", "to": "/tv"}], "cache_seconds": 300,
        },
    },
    "plex_activity": {"pause_when_streaming": False, "refresh_after_processing": False},
    "worker": {"max_concurrent_jobs": 1},
    "audio_cache": {"enabled": True, "directory": "/work/audio-cache", "keep_after_success": False},
    "notifications": {
        "enabled": False, "events": ["completed", "failed", "queue-finished"],
        "webhook": {"enabled": False, "type": "discord", "url": ""},
        "pushover": {"enabled": False, "title": "Censorarr", "app_token": "", "user_key": ""},
        "email": {"enabled": False, "host": "", "port": 587, "username": "", "from": "", "to": "", "starttls": True, "ssl": False},
    },
    "logging": {"level": "INFO", "file": "/config/censorarr.log"},
}


RATING_ORDER = {"G":0, "PG":1, "PG-13":2, "R":3, "NC-17":4}
TV_RATING_ORDER = {"TV-Y":0, "TV-Y7":1, "TV-G":2, "TV-PG":3, "TV-14":4, "TV-MA":5}
UNRATED = {"NR", "UNRATED", "NOT RATED", "NOT_RATED", "NONE", "N/A"}
_PLEX_CACHE: dict[str, Any] = {}

def _resolved_path(path: Path) -> Path:
    try:
        return path.resolve()
    except Exception:
        return path

def _is_under(path: Path, root: Path) -> bool:
    p = _resolved_path(path); r = _resolved_path(root)
    return p == r or r in p.parents

def tv_media_roots(cfg: dict) -> list[str]:
    tv = cfg.get("tv", {})
    if not tv.get("enabled", False):
        return []
    roots = tv.get("media_roots", ["/tv"])
    return [str(x) for x in roots if str(x).strip()]

def all_media_roots(cfg: dict) -> list[str]:
    roots = [str(x) for x in cfg.get("media_roots", ["/media"]) if str(x).strip()]
    roots.extend(tv_media_roots(cfg))
    return list(dict.fromkeys(roots))

def media_type_for(media: Path, cfg: dict) -> str:
    # TV roots are checked first so a nested TV mount cannot be mistaken for a movie root.
    for root in tv_media_roots(cfg):
        if _is_under(media, Path(root)):
            return "episode"
    return "movie"

def rating_cfg_for(media: Path, cfg: dict) -> dict:
    if media_type_for(media, cfg) == "episode":
        tv = cfg.get("tv", {})
        rcfg = dict(tv.get("rating_filter", {}))
        shared = cfg.get("rating_filter", {})
        # Plex URL/token are normally shared between both libraries. Blank TV values inherit Movies.
        if not str(rcfg.get("plex_url", "")).strip():
            rcfg["plex_url"] = shared.get("plex_url", "")
        if not str(rcfg.get("plex_token", "")).strip():
            rcfg["plex_token"] = shared.get("plex_token", "")
        return rcfg
    return cfg.get("rating_filter", {})

def marker_path(media: Path, cfg: dict) -> Path:
    return media.parent / str(cfg.get("marker", {}).get("filename", ".censorarr.done.json"))

def marker_load(media: Path, cfg: dict) -> dict:
    mp = marker_path(media, cfg)
    if not mp.exists(): return {}
    try: return json.loads(mp.read_text(encoding="utf-8"))
    except Exception: return {}

def marker_matches(media: Path, cfg: dict) -> bool:
    if not cfg.get("marker", {}).get("enabled", True): return False
    data = marker_load(media, cfg)
    ent = data.get("files", {}).get(media.name, {})
    try: return ent.get("fingerprint") == fingerprint(media) and ent.get("done") is True
    except OSError: return False

def marker_write(media: Path, cfg: dict, status: str, rating: str|None=None, report: str|None=None) -> None:
    if not cfg.get("marker", {}).get("enabled", True) or cfg.get("dry_run", True): return
    mp=marker_path(media,cfg); data=marker_load(media,cfg); data.setdefault("files", {})
    data["files"][media.name] = {"done":True,"status":status,"rating":rating,"media_type":media_type_for(media,cfg),"fingerprint":fingerprint(media),"version":VERSION,"completed_at":time.strftime("%Y-%m-%dT%H:%M:%S%z"),"report":report}
    tmp=mp.with_suffix(mp.suffix+".tmp"); tmp.write_text(json.dumps(data,indent=2),encoding="utf-8"); os.replace(tmp,mp)

def _plex_get(cfg: dict, path: str, rcfg: dict | None = None) -> dict:
    rcfg = rcfg or cfg.get("rating_filter", {})
    base=str(rcfg.get("plex_url","")).rstrip('/')
    token=secret_store.get("plex_token", env="PLEX_TOKEN", legacy=rcfg.get("plex_token", ""))
    if not base or not token: raise RuntimeError("Plex rating filter needs a Plex URL and token (Settings → Plex)")
    req=urllib.request.Request(base+path,headers={"Accept":"application/json","X-Plex-Token":token,"X-Plex-Client-Identifier":"censorarr-docker","X-Plex-Product":"Censorarr","X-Plex-Version":VERSION})
    with urllib.request.urlopen(req,timeout=20) as r: return json.loads(r.read().decode('utf-8'))

def _map_plex_path(raw: str, mappings: list[dict]) -> Path:
    v=raw.replace("\\", "/")
    for m in mappings or []:
        a=str(m.get("from","")).replace("\\", "/").rstrip('/')
        b=str(m.get("to","")).replace("\\", "/").rstrip('/')
        if a and (v==a or v.startswith(a+'/')): v=b+v[len(a):]; break
    return Path(v)

def _plex_library_index(cfg: dict, media_type: str, force: bool = False) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    rcfg = rating_cfg_for(Path((tv_media_roots(cfg) or ["/tv"])[0]) if media_type == "episode" else Path((cfg.get("media_roots") or ["/media"])[0]), cfg)
    cache_seconds = int(rcfg.get("plex_cache_seconds", 300))
    library = str(rcfg.get("plex_library", "TV Shows" if media_type == "episode" else "Movies"))
    cache_key = (media_type, str(rcfg.get("plex_url", "")), library, json.dumps(rcfg.get("plex_path_mappings", []), sort_keys=True))
    cached = _PLEX_CACHE.get(str(cache_key))
    if not force and cached and time.time() - float(cached.get("time", 0)) < cache_seconds:
        return cached["by_path"], cached["by_basename"]
    sections = _plex_get(cfg, "/library/sections", rcfg).get("MediaContainer", {}).get("Directory", [])
    title = library.lower(); section = None
    expected_type = "show" if media_type == "episode" else "movie"
    for d in sections:
        if str(d.get("title", "")).lower() == title and str(d.get("type", "")).lower() == expected_type:
            section = str(d.get("key")); break
    if not section:
        raise RuntimeError(f"Plex {expected_type} library not found: {library}")
    plex_type = 4 if media_type == "episode" else 1
    data = _plex_get(cfg, f"/library/sections/{section}/all?type={plex_type}", rcfg).get("MediaContainer", {}).get("Metadata", [])
    show_ratings: dict[str, str] = {}
    if media_type == "episode":
        try:
            shows = _plex_get(cfg, f"/library/sections/{section}/all?type=2", rcfg).get("MediaContainer", {}).get("Metadata", [])
            show_ratings = {str(x.get("ratingKey")): str(x.get("contentRating")) for x in shows if x.get("ratingKey") and x.get("contentRating")}
        except Exception as e:
            logging.debug("Could not load Plex show rating fallback: %s", e)
    by_path: dict[str, Any] = {}; by_basename: dict[str, list[Any]] = {}
    mappings = rcfg.get("plex_path_mappings", [])
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
                if not raw: continue
                mapped = _map_plex_path(str(raw), mappings)
                keypath = str(_resolved_path(mapped))
                by_path[keypath] = item
                by_basename.setdefault(mapped.name.lower(), []).append(item)
    _PLEX_CACHE[str(cache_key)] = {"time": time.time(), "by_path": by_path, "by_basename": by_basename}
    logging.info("Plex metadata cache refreshed: %d %s paths", len(by_path), "episode" if media_type == "episode" else "movie")
    return by_path, by_basename

def plex_item_for(media: Path, cfg: dict, force_refresh: bool = False) -> tuple[dict | None, str]:
    kind = media_type_for(media, cfg)
    target = str(_resolved_path(media))
    by_path, by_basename = _plex_library_index(cfg, kind, force=force_refresh)
    item = by_path.get(target)
    if item is not None:
        return item, "matched-path" + ("-refresh" if force_refresh else "")
    hits = by_basename.get(media.name.lower(), [])
    if len(hits) == 1:
        return hits[0], "matched-basename" + ("-refresh" if force_refresh else "")
    # A fresh library item may not yet be in the cache; one forced refresh is cheap and avoids waiting a full TTL.
    if not force_refresh:
        return plex_item_for(media, cfg, force_refresh=True)
    return None, f"{kind}-not-found"

def plex_rating_for(media: Path, cfg: dict) -> tuple[str|None, str]:
    item, why = plex_item_for(media, cfg)
    return (item.get("contentRating") if item else None), why

def _normalize_rating(rating: str, media_type: str) -> str:
    r = str(rating).upper().replace("RATED ", "").strip().replace("_", "-")
    if media_type == "episode":
        aliases = {"TVY":"TV-Y", "TVY7":"TV-Y7", "TV-Y7-FV":"TV-Y7", "TVG":"TV-G", "TVPG":"TV-PG", "TV14":"TV-14", "TVMA":"TV-MA"}
        r = aliases.get(r, r)
    return r

def rating_decision(media: Path, cfg: dict) -> tuple[str,str|None,str]:
    kind = media_type_for(media, cfg)
    rcfg = rating_cfg_for(media, cfg)
    if not rcfg.get("enabled",True): return "process",None,"disabled"
    if str(rcfg.get("source","plex")).lower()!="plex": return "process",None,"non-plex"
    try: rating,why=plex_rating_for(media,cfg)
    except Exception as e:
        logging.warning("Plex rating lookup failed for %s: %s",media,e); return "wait",None,"plex-error"
    if not rating: return "wait",None,why
    r=_normalize_rating(str(rating), kind)
    if r in UNRATED: return ("process" if rcfg.get("include_unrated",False) else "skip"),str(rating),"unrated"
    if kind == "episode":
        minimum=_normalize_rating(str(rcfg.get("minimum","TV-14")), kind); order=TV_RATING_ORDER; threshold=order.get(minimum,4)
    else:
        minimum=_normalize_rating(str(rcfg.get("minimum","PG-13")), kind); order=RATING_ORDER; threshold=order.get(minimum,2)
    level=order.get(r)
    if level is None: return "wait",str(rating),"unknown-rating"
    return ("process" if level>=threshold else "skip"),str(rating),"rating-order"

def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def ensure_config(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        shutil.copy2("/app/config.example.yaml", config_path)
        # Only a genuinely new installation gets this marker. Upgrades with an existing config do not,
        # so the onboarding wizard never interrupts an established installation.
        try:
            (config_path.parent / ".censorarr-first-run").write_text("1\n", encoding="utf-8")
        except OSError:
            pass
    profanity_path = config_path.parent / "en.json"
    if not profanity_path.exists():
        shutil.copy2("/app/en.json", profanity_path)


def load_config(path: Path) -> dict:
    ensure_config(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = deep_merge(DEFAULT_CONFIG, raw)
    env_dry = os.environ.get("DRY_RUN")
    if env_dry is not None:
        cfg["dry_run"] = env_dry.strip().lower() in {"1", "true", "yes", "on"}
    return cfg


def setup_logging(cfg: dict) -> None:
    level = getattr(logging, str(cfg["logging"].get("level", "INFO")).upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    logfile = Path(cfg["logging"].get("file", "/config/censorarr.log"))
    logfile.parent.mkdir(parents=True, exist_ok=True)
    handlers.append(logging.FileHandler(logfile, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


def run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    logging.debug("RUN: %s", " ".join(cmd))
    try:
        return subprocess.run(
            cmd,
            check=check,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except subprocess.CalledProcessError as exc:
        if capture and exc.stderr:
            logging.error("Command stderr: %s", exc.stderr.strip())
        raise


def run_ffmpeg_progress(cmd: list[str], duration_seconds: float | None, progress_callback=None) -> subprocess.CompletedProcess:
    """Run FFmpeg while parsing its machine-readable progress stream.

    The callback receives a 0..100 stage percentage. This is used only for long
    FFmpeg stages (audio extraction/remux); it does not change the media command.
    """
    if not progress_callback or not duration_seconds or duration_seconds <= 0:
        return run(cmd)
    progress_cmd = list(cmd)
    # -progress is a global FFmpeg option. Put it immediately after the executable
    # so it applies regardless of how many outputs the command has.
    progress_cmd[1:1] = ["-progress", "pipe:1", "-nostats"]
    logging.debug("RUN(progress): %s", " ".join(progress_cmd))
    proc = subprocess.Popen(
        progress_cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    last_pct = -1.0
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            seconds = None
            if key == "out_time_us":
                try: seconds = float(value) / 1_000_000.0
                except ValueError: pass
            elif key == "out_time_ms":
                # Despite the historical name, FFmpeg reports this in microseconds.
                try: seconds = float(value) / 1_000_000.0
                except ValueError: pass
            elif key == "progress" and value == "end":
                try: progress_callback(100.0)
                except Exception: logging.debug("FFmpeg progress callback failed", exc_info=True)
            if seconds is not None:
                pct = max(0.0, min(99.9, 100.0 * seconds / float(duration_seconds)))
                if pct >= last_pct + 0.5:
                    last_pct = pct
                    try: progress_callback(pct)
                    except Exception: logging.debug("FFmpeg progress callback failed", exc_info=True)
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        rc = proc.wait()
        cp = subprocess.CompletedProcess(progress_cmd, rc, "", stderr)
        if rc != 0:
            if stderr:
                logging.error("Command stderr: %s", stderr.strip())
            raise subprocess.CalledProcessError(rc, progress_cmd, output="", stderr=stderr)
        try: progress_callback(100.0)
        except Exception: logging.debug("FFmpeg progress callback failed", exc_info=True)
        return cp
    finally:
        if proc.poll() is None:
            proc.kill()


def ffprobe(path: Path) -> dict:
    cp = run([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
    ])
    return json.loads(cp.stdout)


def duration_of(probe: dict) -> float:
    try:
        return float(probe.get("format", {}).get("duration") or 0)
    except Exception:
        return 0.0


def norm_token(text: str) -> str:
    text = text.lower().replace("’", "'").strip()
    return re.sub(r"^[^a-z0-9']+|[^a-z0-9']+$", "", text)


def canonicalize_pattern(text: str) -> str:
    text = text.lower().replace("*", "").replace("-", " ")
    text = re.sub(r"[^a-z0-9' ]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def compile_alt(alt: str) -> re.Pattern:
    alt = alt.lower().strip()
    pieces: list[str] = []
    i = 0
    while i < len(alt):
        ch = alt[i]
        if ch in " -":
            while i + 1 < len(alt) and alt[i + 1] in " -":
                i += 1
            pieces.append(r"[\s-]+")
        elif i + 1 < len(alt) and alt[i + 1] == "*" and ch.isalnum():
            pieces.append(re.escape(ch) + "+")
            i += 1
        elif ch == "*":
            # A stray leading '*' in the source list is intended for substring exceptions;
            # match alternatives themselves do not need that behavior.
            pass
        else:
            pieces.append(re.escape(ch))
        i += 1
    return re.compile("^" + "".join(pieces) + "$", re.IGNORECASE)


def merge_dictionary_entries(data: list[dict]) -> list[dict]:
    """Merge duplicate dictionary IDs into one effective entry while preserving all match alternatives/tags."""
    merged: dict[str, dict] = {}
    order: list[str] = []
    for raw in data or []:
        if not isinstance(raw, dict):
            continue
        ident = str(raw.get("id", "")).strip()
        if not ident:
            continue
        if ident not in merged:
            merged[ident] = dict(raw); order.append(ident); continue
        cur = merged[ident]
        alts = [x.strip() for x in str(cur.get("match", "")).split("|") if x.strip()]
        alts += [x.strip() for x in str(raw.get("match", "")).split("|") if x.strip()]
        cur["match"] = "|".join(dict.fromkeys(alts))
        cur["severity"] = max(int(cur.get("severity", 0)), int(raw.get("severity", 0)))
        cur["tags"] = list(dict.fromkeys([*list(cur.get("tags", [])), *list(raw.get("tags", []))]))
        if str(cur.get("scope", "both")).lower() != str(raw.get("scope", "both")).lower():
            cur["scope"] = "both"
    return [merged[x] for x in order]


@dataclass
class PatternEntry:
    id: str
    severity: int
    tags: list[str]
    alternatives: list[str]
    regexes: list[re.Pattern]
    canonicals: list[str]
    scope: str = "both"


@dataclass
class Detection:
    start: float
    end: float
    text: str
    matched_id: str
    severity: int
    source: str
    confidence: float | None = None
    baseline_text: str | None = None
    rescue_text: str | None = None


class ProfanityMatcher:
    def __init__(self, json_path: Path, min_severity: int, max_window: int = 4):
        # The shipped/base dictionary is never destructively edited from the GUI. User changes
        # are layered through persistent overrides so upgrades can replace en.json safely.
        data = merge_dictionary_entries(json.loads(json_path.read_text(encoding="utf-8")))
        overrides_path = Path("/config/profanity_overrides.json")
        overrides: dict[str, dict] = {}
        if overrides_path.exists():
            try:
                loaded = json.loads(overrides_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    overrides = {str(k): v for k, v in loaded.items() if isinstance(v, dict)}
            except Exception as e:
                logging.warning("Could not load profanity overrides: %s", e)

        effective: list[dict] = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            ident = str(item.get("id", ""))
            ov = overrides.get(ident, {})
            if ov.get("enabled") is False:
                continue
            for field in ("match", "severity", "scope"):
                if field in ov:
                    item[field] = ov[field]
            effective.append(item)
        data = effective

        custom_path = Path("/config/custom_profanity.json")
        if custom_path.exists():
            try:
                custom = json.loads(custom_path.read_text(encoding="utf-8"))
                if isinstance(custom, list):
                    data.extend(x for x in custom if isinstance(x, dict) and x.get("enabled", True) is not False)
            except Exception as e:
                logging.warning("Could not load custom profanity list: %s", e)
        self.user_exceptions = {"phrases": set(), "ids": set()}
        exc_path = Path("/config/user_exceptions.json")
        if exc_path.exists():
            try:
                ex = json.loads(exc_path.read_text(encoding="utf-8")) or {}
                self.user_exceptions["phrases"] = {canonicalize_pattern(str(x)) for x in ex.get("phrases", [])}
                self.user_exceptions["ids"] = {str(x) for x in ex.get("ids", [])}
            except Exception as e:
                logging.warning("Could not load user exceptions: %s", e)
        self.entries: list[PatternEntry] = []
        self.max_window = max_window
        for item in data:
            severity = int(item.get("severity", 0))
            alternatives = [x.strip() for x in str(item.get("match", "")).split("|") if x.strip()]
            alternatives.extend(FAMILY_ALIASES.get(str(item.get("id", "")), []))
            # Preserve order while deduplicating.
            alternatives = list(dict.fromkeys(alternatives))
            regexes = [compile_alt(a) for a in alternatives]
            canonicals = [canonicalize_pattern(a) for a in alternatives]
            self.entries.append(PatternEntry(
                id=str(item.get("id", "")), severity=severity, tags=list(item.get("tags", [])),
                alternatives=alternatives, regexes=regexes, canonicals=canonicals,
                scope=str(item.get("scope", "both")).lower(),
            ))
        self.active = [e for e in self.entries if e.severity >= min_severity and e.scope in {"both", "normal", ""}]
        self.active_rescue = [e for e in self.entries if e.severity >= min_severity and e.scope in {"both", "normal", "rescue", ""}]
        self.fuzzy_variants: list[tuple[str, str, int]] = []
        for e in self.active_rescue:
            for c in e.canonicals:
                joined = c.replace(" ", "").replace("'", "")
                if len(joined) >= 4 and joined.isalnum():
                    self.fuzzy_variants.append((joined, e.id, e.severity))

    def match_words(self, words: list[dict], source: str = "normal") -> list[Detection]:
        detections: list[Detection] = []
        seen: set[tuple] = set()
        cleaned = [norm_token(w.get("word", "")) for w in words]
        n = len(words)
        entries = self.active_rescue if source.startswith("rescue") or source.startswith("subtitle-rescue") else self.active
        for i in range(n):
            if not cleaned[i]:
                continue
            for width in range(1, min(self.max_window, n - i) + 1):
                toks = cleaned[i:i + width]
                if any(not t for t in toks):
                    break
                space = " ".join(toks)
                concat = "".join(toks)
                candidates = (space, concat) if concat != space else (space,)
                matched = False
                for entry in entries:
                    if entry.id in self.user_exceptions["ids"]:
                        continue
                    for rgx in entry.regexes:
                        if any(rgx.fullmatch(c) for c in candidates):
                            candidate_phrase = canonicalize_pattern(space)
                            if candidate_phrase in self.user_exceptions["phrases"]:
                                continue
                            start = float(words[i]["start"])
                            end = float(words[i + width - 1]["end"])
                            key = (round(start, 3), round(end, 3), entry.id)
                            if key not in seen:
                                probs = [w.get("probability") for w in words[i:i + width] if w.get("probability") is not None]
                                conf = min(float(p) for p in probs) if probs else None
                                detections.append(Detection(
                                    start=start, end=end,
                                    text=" ".join(w.get("word", "").strip() for w in words[i:i + width]),
                                    matched_id=entry.id, severity=entry.severity, source=source,
                                    confidence=conf,
                                ))
                                seen.add(key)
                            matched = True
                            break
                    if matched:
                        break
        detections.sort(key=lambda d: (d.start, d.end))
        return detections

    def fuzzy_targets(self, word: str, threshold: float) -> list[tuple[str, str, float]]:
        w = norm_token(word).replace("'", "")
        if len(w) < 4:
            return []
        out: list[tuple[str, str, float]] = []
        for canonical, entry_id, _severity in self.fuzzy_variants:
            if abs(len(canonical) - len(w)) > 4:
                continue
            score = SequenceMatcher(None, w, canonical).ratio()
            if score >= threshold:
                out.append((entry_id, canonical, score))
        out.sort(key=lambda x: x[2], reverse=True)
        return out[:5]


def select_audio_stream(probe: dict, configured: Any = "auto") -> tuple[dict, int]:
    audio = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
    if not audio:
        raise RuntimeError("No audio streams found")
    if isinstance(configured, int):
        if configured < 0 or configured >= len(audio):
            raise RuntimeError(f"audio_track index {configured} is out of range")
        return audio[configured], configured
    for rel, s in enumerate(audio):
        lang = str(s.get("tags", {}).get("language", "")).lower()
        if lang in {"eng", "en", "english"}:
            return s, rel
    return audio[0], 0


def find_clean_audio_streams(probe: dict, title: str) -> list[tuple[dict, int]]:
    """Find the CLEAN audio track across MKV and MP4-style metadata.

    Matroska normally exposes a stream name as ``tags.title``. MP4/M4V commonly
    exposes the audio track name as ``tags.handler_name`` instead, even when FFmpeg
    was given a stream title. Recognize either field so validation/reprocessing works
    consistently across supported containers.
    """
    want = title.strip().lower()
    audio = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
    found = []
    for rel, s in enumerate(audio):
        tags = s.get("tags", {}) or {}
        names = {
            str(tags.get("title", "")).strip().lower(),
            str(tags.get("handler_name", "")).strip().lower(),
        }
        if want in names:
            found.append((s, rel))
    return found


def extract_transcription_audio(src: Path, audio_rel: int, dest: Path, center_only: bool = False,
                                duration_seconds: float | None = None, progress_callback=None) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-map", f"0:a:{audio_rel}", "-vn"]
    if center_only:
        cmd += ["-af", "pan=mono|c0=FC"]
    else:
        cmd += ["-ac", "1"]
    cmd += ["-ar", "16000", "-c:a", "pcm_s16le", str(dest)]
    run_ffmpeg_progress(cmd, duration_seconds, progress_callback)


def extract_transcription_audio_pair(src: Path, audio_rel: int, mono: Path, center: Path | None = None,
                                     duration_seconds: float | None = None, progress_callback=None) -> None:
    """Extract the normal mono ASR audio and optional center channel in one FFmpeg input pass."""
    mono.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
        "-map", f"0:a:{audio_rel}", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(mono),
    ]
    if center is not None:
        center.parent.mkdir(parents=True, exist_ok=True)
        cmd += [
            "-map", f"0:a:{audio_rel}", "-vn", "-af", "pan=mono|c0=FC",
            "-ar", "16000", "-c:a", "pcm_s16le", str(center),
        ]
    run_ffmpeg_progress(cmd, duration_seconds, progress_callback)


def audio_cache_paths(src: Path, audio_rel: int, cfg: dict, need_center: bool) -> tuple[Path | None, Path, Path | None]:
    acfg = cfg.get("audio_cache", {}) or {}
    if not bool(acfg.get("enabled", True)):
        return None, Path(), None
    key_src = f"{src}|{fingerprint(src)}|a{audio_rel}|pcm16k-v1"
    key = hashlib.sha1(key_src.encode("utf-8", "ignore")).hexdigest()[:24]
    root = Path(str(acfg.get("directory", "/work/audio-cache"))) / key
    return root, root / "transcribe-mono.wav", (root / "rescue-center.wav" if need_center else None)


def valid_audio_cache(path: Path | None) -> bool:
    try:
        return bool(path and path.is_file() and path.stat().st_size > 4096)
    except OSError:
        return False


_LOCAL_MODEL_CACHE: dict[tuple[str, str, str], WhisperModel] = {}


def _local_model(cfg: dict, existing: WhisperModel | None = None) -> WhisperModel:
    if existing is not None:
        return existing
    wcfg = cfg.get("whisper", {})
    key = (str(wcfg.get("model", "small")), str(wcfg.get("device", "cpu")), str(wcfg.get("compute_type", "int8")))
    if key not in _LOCAL_MODEL_CACHE:
        logging.info("Loading local Whisper fallback model %s on %s/%s", *key)
        _LOCAL_MODEL_CACHE[key] = WhisperModel(key[0], device=key[1], compute_type=key[2], download_root="/config/models")
    return _LOCAL_MODEL_CACHE[key]


def transcribe(model: WhisperModel | None, audio: Path, cfg: dict, prompt: str | None = None,
               stage: str | None = None, current: str | None = None) -> list[dict]:
    wcfg = cfg.get("whisper", {})
    if remote_asr.enabled(cfg):
        try:
            remote_model = remote_asr.config(cfg).get("model") or wcfg.get("model")
            last_remote_log_bucket = -10

            def on_remote_progress(cur: dict) -> None:
                nonlocal last_remote_log_bucket
                if not (stage and current):
                    return
                progress = cur.get("progress")
                update_heartbeat(
                    "remote-gpu", current, progress=progress, remote_model=cur.get("model") or remote_model,
                    remote_stage=cur.get("stage"), remote_job_id=cur.get("job_id"),
                    gpu_position_seconds=cur.get("position_seconds"), gpu_duration_seconds=cur.get("duration_seconds"),
                    gpu_elapsed_seconds=cur.get("elapsed_seconds"), gpu_eta_seconds=cur.get("eta_seconds"),
                    gpu_words_count=cur.get("words_count"),
                )
                try:
                    pct = float(progress)
                except (TypeError, ValueError):
                    return
                bucket = int(pct // 10) * 10
                if bucket >= 10 and bucket > last_remote_log_bucket:
                    last_remote_log_bucket = bucket
                    logging.info(
                        "Remote GPU progress: %d%% position=%.1fs/%.1fs elapsed=%ss eta=%ss model=%s job=%s",
                        bucket, float(cur.get("position_seconds") or 0), float(cur.get("duration_seconds") or 0),
                        cur.get("elapsed_seconds"), cur.get("eta_seconds"), cur.get("model") or remote_model,
                        str(cur.get("job_id") or "")[:8],
                    )

            if stage and current:
                update_heartbeat("remote-gpu", current, progress=0, remote_model=remote_model, remote_stage="submitting")
                logging.info("Submitting audio to remote GPU ASR: model=%s file=%s", remote_model, audio.name)
            words, meta = remote_asr.transcribe(audio, cfg, prompt=prompt, progress_callback=on_remote_progress)
            logging.info("Remote GPU ASR: model=%s elapsed=%ss roundtrip=%ss words=%d",
                         meta.get("model"), meta.get("elapsed_seconds"), meta.get("round_trip_seconds"), len(words))
            return words
        except remote_asr.RemoteASRCancelled:
            logging.info("Remote GPU ASR job cancelled")
            raise
        except Exception as e:
            if not bool(remote_asr.config(cfg).get("fallback_to_local", True)):
                raise
            logging.warning("Remote GPU ASR unavailable; falling back to local CPU Whisper: %s", e)
    model = _local_model(cfg, model)
    segments, info = model.transcribe(
        str(audio), language=wcfg.get("language", "en"), word_timestamps=True,
        beam_size=int(wcfg.get("beam_size", 5)),
        condition_on_previous_text=bool(wcfg.get("condition_on_previous_text", False)),
        vad_filter=bool(wcfg.get("vad_filter", False)), initial_prompt=prompt,
    )
    words: list[dict] = []
    duration = float(getattr(info, "duration", 0) or 0)
    last_update = 0.0
    for seg in segments:
        if stage and current and duration:
            now = time.time()
            if now - last_update >= 1.0:
                update_heartbeat(stage, current, progress=min(99.0, 100.0 * float(seg.end) / duration))
                last_update = now
        if not seg.words:
            continue
        for w in seg.words:
            words.append({"start": float(w.start), "end": float(w.end), "word": (w.word or "").strip(),
                          "probability": float(w.probability) if w.probability is not None else None})
    return words


def build_rescue_windows(words: list[dict], matcher: ProfanityMatcher, cfg: dict) -> list[dict]:
    rcfg = cfg["rescue"]
    threshold = float(rcfg.get("confidence_trigger", 0.18))
    fuzzy_ceiling = float(rcfg.get("fuzzy_confidence_ceiling", 0.70))
    fuzzy_similarity = float(rcfg.get("fuzzy_similarity", 0.72))
    before = float(rcfg.get("window_before_seconds", 1.5))
    after = float(rcfg.get("window_after_seconds", 1.5))
    raw: list[dict] = []
    for w in words:
        p = w.get("probability")
        pval = 1.0 if p is None else float(p)
        fuzzy = matcher.fuzzy_targets(w.get("word", ""), fuzzy_similarity) if pval <= fuzzy_ceiling else []
        if pval <= threshold or fuzzy:
            raw.append({
                "start": max(0.0, float(w["start"]) - before),
                "end": float(w["end"]) + after,
                "triggers": [{
                    "word": w.get("word", ""), "start": float(w["start"]), "end": float(w["end"]),
                    "probability": p, "fuzzy": fuzzy,
                }],
            })
    if not raw:
        return []
    raw.sort(key=lambda x: x["start"])
    merged: list[dict] = [raw[0]]
    gap = float(rcfg.get("merge_gap_seconds", 0.75))
    for item in raw[1:]:
        last = merged[-1]
        if item["start"] <= last["end"] + gap:
            last["end"] = max(last["end"], item["end"])
            last["triggers"].extend(item["triggers"])
        else:
            merged.append(item)
    return merged[: int(rcfg.get("max_windows", 250))]


def extract_clip(source_audio: Path, start: float, end: float, dest: Path) -> None:
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-i", str(source_audio), "-t", f"{max(0.1, end-start):.3f}",
        "-c:a", "pcm_s16le", str(dest),
    ])


def detect_rescue(
    model: WhisperModel,
    rescue_audio: Path,
    windows: list[dict],
    matcher: ProfanityMatcher,
    cfg: dict,
    workdir: Path,
) -> tuple[list[Detection], list[dict]]:
    if not windows:
        return [], []
    rcfg = cfg["rescue"]
    prompt = str(rcfg.get("prompt", "")) or None
    mild = {norm_token(x) for x in rcfg.get("mild_evidence", ["ass"])}
    all_det: list[Detection] = []
    details: list[dict] = []

    for idx, win in enumerate(windows):
        # Keep the dashboard alive during targeted rescue work.
        hb = _read_json(Path("/config/heartbeat.json"), {})
        update_heartbeat("rescue", hb.get("current"), progress=round(100.0 * idx / max(1, len(windows)), 1), rescue_windows=len(windows))
        clip = workdir / f"rescue-{idx:04d}.wav"
        extract_clip(rescue_audio, win["start"], win["end"], clip)
        local_words = transcribe(model, clip, cfg, prompt=prompt)
        local_det = matcher.match_words(local_words, source="rescue")
        window_detail = {
            "start": win["start"], "end": win["end"], "triggers": win["triggers"],
            "rescue_words": local_words, "accepted": [],
        }
        for d in local_det:
            gd = Detection(
                start=d.start + win["start"], end=d.end + win["start"], text=d.text,
                matched_id=d.matched_id, severity=d.severity, source="rescue", confidence=d.confidence,
            )
            all_det.append(gd)
            window_detail["accepted"].append(asdict(gd))

        # Special mild-evidence rule: only accept mild words when the baseline trigger
        # itself was fuzzy-close to a stronger profanity. This is what safely handles
        # baseline "hassle" -> prompted "ass" as evidence for "asshole".
        fuzzy_triggers = []
        for trig in win["triggers"]:
            if trig.get("fuzzy"):
                fuzzy_triggers.append(trig)
        if fuzzy_triggers and mild:
            for rw in local_words:
                tok = norm_token(rw.get("word", ""))
                if tok not in mild:
                    continue
                # Associate with the nearest fuzzy baseline trigger in time.
                global_mid = win["start"] + (float(rw["start"]) + float(rw["end"])) / 2
                nearest = min(
                    fuzzy_triggers,
                    key=lambda t: abs(global_mid - ((float(t["start"]) + float(t["end"])) / 2)),
                )
                # Require temporal proximity so a prompted mild word elsewhere in the clip
                # cannot cause a false mute.
                base_mid = (float(nearest["start"]) + float(nearest["end"])) / 2
                if abs(global_mid - base_mid) > 0.9:
                    continue
                fuzzy_ids = [x[0] for x in nearest.get("fuzzy", [])]
                if tok == "ass" and not any("ass" in x.replace("arse", "ass") for x in fuzzy_ids):
                    continue
                gd = Detection(
                    start=float(nearest["start"]), end=float(nearest["end"]),
                    text=tok, matched_id=(fuzzy_ids[0] if fuzzy_ids else "rescue-mild"), severity=3,
                    source="rescue-mild", confidence=rw.get("probability"),
                    baseline_text=str(nearest.get("word", "")), rescue_text=tok,
                )
                all_det.append(gd)
                window_detail["accepted"].append(asdict(gd))
                break
        details.append(window_detail)
        try:
            clip.unlink()
        except OSError:
            pass

    # Deduplicate rescue detections by overlap/id.
    dedup: list[Detection] = []
    for d in sorted(all_det, key=lambda x: (x.start, x.end)):
        if any(abs(d.start - x.start) < 0.08 and abs(d.end - x.end) < 0.08 and d.matched_id == x.matched_id for x in dedup):
            continue
        dedup.append(d)
    return dedup, details


def detect_subtitle_assist(
    model: WhisperModel,
    media: Path,
    probe: dict,
    transcript_words: list[dict],
    rescue_audio: Path,
    normal_detections: list[Detection],
    matcher: ProfanityMatcher,
    cfg: dict,
    workdir: Path,
) -> tuple[list[Detection], dict]:
    scfg = cfg.get("subtitle_assist", {})
    detail: dict[str, Any] = {"enabled": bool(scfg.get("enabled", True)), "source": None, "errors": [], "candidates": []}
    if not scfg.get("enabled", True):
        return [], detail
    subtitle_path, source, errors = subassist.materialize_best(media, probe, cfg, workdir)
    detail["source"] = source
    detail["errors"] = errors
    detail["image_subtitles"] = subassist.image_subtitle_summary(probe)
    if not subtitle_path or not source:
        return [], detail
    cues = subassist.parse_srt(subtitle_path)
    candidates = subassist.build_candidates(cues, transcript_words, matcher, cfg)
    detail["cue_count"] = len(cues)
    detail["candidate_count"] = len(candidates)
    aligned_offsets=[float(x.get("subtitle_offset_seconds",0)) for x in candidates if x.get("strong_alignment") and x.get("alignment_method")=="global-text"]
    if aligned_offsets:
        vals=sorted(aligned_offsets); mid=len(vals)//2
        med=vals[mid] if len(vals)%2 else (vals[mid-1]+vals[mid])/2
        detail["global_alignment"]={"aligned_candidates":len(vals),"median_subtitle_offset_seconds":round(med,3),
                                    "minimum_offset_seconds":round(min(vals),3),"maximum_offset_seconds":round(max(vals),3)}
    accepted: list[Detection] = []
    use_prompt = bool(scfg.get("use_dialogue_as_rescue_prompt", True))
    for idx, c in enumerate(candidates):
        # Normal Whisper has priority; subtitles only add evidence that the normal pass missed.
        if any(x.matched_id == c["matched_id"] and not (x.end < c["start"] - .25 or x.start > c["end"] + .25)
               for x in normal_detections):
            c["result"] = "already-detected-normal"
            detail["candidates"].append(c)
            continue
        chosen: Detection | None = None
        prompt_words: list[dict] = []
        if use_prompt:
            if c.get("alignment_method") == "global-text":
                # Global text alignment has already located the dialogue in actual ASR time; do not stretch the
                # rescue clip back to a badly shifted subtitle timestamp.
                clip_start = max(0.0, float(c["start"]) - 1.5)
                clip_end = float(c["end"]) + 1.5
            else:
                clip_start = max(0.0, min(float(c["cue_start"]), float(c["start"])) - 0.8)
                clip_end = max(float(c["cue_end"]), float(c["end"])) + 0.8
            clip = workdir / f"subtitle-rescue-{idx:04d}.wav"
            try:
                extract_clip(rescue_audio, clip_start, clip_end, clip)
                prompt = "Transcribe this dialogue verbatim, including profanity. Dialogue context: " + str(c["subtitle_text"])
                prompt_words = transcribe(model, clip, cfg, prompt=prompt)
                pd = matcher.match_words(prompt_words, source="subtitle-rescue")
                same = [x for x in pd if x.matched_id == c["matched_id"]]
                if same:
                    # Use the prompted ASR word timing when available; it is more precise than the subtitle cue.
                    x = min(same, key=lambda d: abs((d.start + d.end) / 2 - ((float(c["start"]) + float(c["end"])) / 2 - clip_start)))
                    chosen = Detection(
                        start=x.start + clip_start, end=x.end + clip_start, text=x.text,
                        matched_id=x.matched_id, severity=x.severity, source="subtitle-rescue",
                        confidence=x.confidence, baseline_text=str(c.get("baseline_text") or ""),
                        rescue_text=str(c.get("subtitle_text") or ""),
                    )
            except Exception as e:
                c["prompt_error"] = str(e)
            finally:
                try: clip.unlink()
                except Exception: pass
        if chosen is None and bool(c.get("strong_alignment")):
            # Strong subtitle/ASR alignment is safe enough to accept when the target ASR token was replaced
            # (e.g. subtitle "asshole" aligned to Whisper "hassle") and nearby words line up.
            chosen = Detection(
                start=float(c["start"]), end=float(c["end"]), text=str(c["text"]),
                matched_id=str(c["matched_id"]), severity=int(c["severity"]), source="subtitle-align",
                confidence=float(c.get("alignment_ratio", 0)), baseline_text=str(c.get("baseline_text") or ""),
                rescue_text=str(c.get("subtitle_text") or ""),
            )
        if chosen is not None:
            accepted.append(chosen)
            c["result"] = chosen.source
            c["accepted"] = asdict(chosen)
        else:
            c["result"] = "not-confirmed"
        if prompt_words:
            c["prompt_words"] = prompt_words
        detail["candidates"].append(c)
    # Dedup subtitle-assisted detections.
    dedup: list[Detection] = []
    for d in sorted(accepted, key=lambda x: (x.start, x.end, x.matched_id)):
        if any(d.matched_id == x.matched_id and abs(d.start - x.start) < .12 and abs(d.end - x.end) < .25 for x in dedup):
            continue
        dedup.append(d)
    return dedup, detail


def _neighbor_word_bounds(d: Detection, words: list[dict]) -> tuple[float | None, float | None]:
    """Return the closest transcript word ending before / starting after a detection.

    Whisper word timestamps are approximate, but neighboring words are still useful guard rails: we can
    keep safety padding from eating into the previous/next spoken word even when there is no clean silence.
    """
    prev_end = None
    next_start = None
    for w in words or []:
        try:
            ws, we = float(w.get("start", 0)), float(w.get("end", 0))
        except (TypeError, ValueError):
            continue
        # Ignore transcript tokens that are clearly part of the same detected phrase.
        if we <= d.start + 0.005:
            if prev_end is None or we > prev_end:
                prev_end = we
        if ws >= d.end - 0.005:
            if next_start is None or ws < next_start:
                next_start = ws
    return prev_end, next_start


def _quiet_edge(wf: wave.Wave_read, target: float, *, before: bool, search_seconds: float,
                frame_seconds: float, threshold_ratio: float) -> float | None:
    """Find a nearby low-energy frame around a Whisper word edge.

    This is deliberately conservative: the start search only looks *before* Whisper's start, and the end
    search only looks *after* Whisper's end. It therefore never contracts inside Whisper's detected word;
    it only chooses a cleaner place for the small safety margin to begin/end.
    """
    rate = int(wf.getframerate() or 16000)
    channels = int(wf.getnchannels() or 1)
    width = int(wf.getsampwidth() or 2)
    if width != 2 or channels != 1 or rate <= 0:
        return None
    duration = wf.getnframes() / rate
    if before:
        start, end = max(0.0, target - search_seconds), max(0.0, target)
    else:
        start, end = max(0.0, target), min(duration, target + search_seconds)
    if end <= start:
        return None
    frame_n = max(1, int(rate * frame_seconds))
    start_frame = max(0, int(start * rate))
    total_frames = max(1, int((end - start) * rate))
    try:
        wf.setpos(min(start_frame, max(0, wf.getnframes() - 1)))
        raw = wf.readframes(total_frames)
    except Exception:
        return None
    samples = array('h')
    try:
        samples.frombytes(raw)
    except Exception:
        return None
    if not samples:
        return None
    rms: list[tuple[int, float]] = []
    for i in range(0, len(samples), frame_n):
        chunk = samples[i:i + frame_n]
        if not chunk:
            continue
        # Integer PCM squared sum is inexpensive for these tiny (~120 ms) windows.
        val = (sum(int(x) * int(x) for x in chunk) / len(chunk)) ** 0.5
        rms.append((i, val))
    if not rms:
        return None
    peak = max(v for _, v in rms)
    if peak <= 0:
        return target
    threshold = max(80.0, peak * max(0.02, min(0.95, threshold_ratio)))
    quiet = [(i, v) for i, v in rms if v <= threshold]
    if not quiet:
        return None
    # Closest quiet frame to the word edge. For start that is the last quiet frame; for end it is first.
    idx = quiet[-1][0] if before else quiet[0][0]
    # Use the frame center as a stable, click-resistant edge.
    return start + (idx + frame_n / 2) / rate


def merge_mute_ranges(detections: list[Detection], cfg: dict, words: list[dict] | None = None,
                      audio_path: Path | None = None) -> list[tuple[float, float]]:
    pcfg = cfg.get("precision_alignment", {}) or {}
    precision = bool(pcfg.get("enabled", False))
    if precision:
        pre = float(pcfg.get("padding_before_ms", 25)) / 1000.0
        post = float(pcfg.get("padding_after_ms", 40)) / 1000.0
        search = float(pcfg.get("edge_search_ms", 120)) / 1000.0
        guard = float(pcfg.get("neighbor_guard_ms", 12)) / 1000.0
        threshold = float(pcfg.get("energy_threshold_ratio", 0.22))
        frame_seconds = max(0.002, float(pcfg.get("frame_ms", 5)) / 1000.0)
    else:
        pre = float(cfg["profanity"].get("padding_before_ms", 120)) / 1000.0
        post = float(cfg["profanity"].get("padding_after_ms", 160)) / 1000.0
        search = guard = threshold = 0.0
        frame_seconds = 0.005

    wf = None
    if precision and audio_path is not None:
        try:
            wf = wave.open(str(audio_path), 'rb')
        except Exception as e:
            logging.debug("Precision mute waveform refinement unavailable for %s: %s", audio_path, e)

    ranges: list[tuple[float, float]] = []
    try:
        for d in detections:
            start = max(0.0, float(d.start) - pre)
            end = float(d.end) + post
            if precision:
                prev_end, next_start = _neighbor_word_bounds(d, words or [])
                # Protect adjacent transcript words. If timestamps overlap, never move inside the profanity edge.
                if prev_end is not None and prev_end < d.start:
                    start = max(start, min(float(d.start), prev_end + guard))
                if next_start is not None and next_start > d.end:
                    end = min(end, max(float(d.end), next_start - guard))
                if wf is not None and search > 0:
                    qstart = _quiet_edge(wf, float(d.start), before=True, search_seconds=search,
                                         frame_seconds=frame_seconds, threshold_ratio=threshold)
                    qend = _quiet_edge(wf, float(d.end), before=False, search_seconds=search,
                                       frame_seconds=frame_seconds, threshold_ratio=threshold)
                    if qstart is not None:
                        # Quiet-edge refinement may safely extend into silence, but not through the previous word.
                        lower = (prev_end + guard) if (prev_end is not None and prev_end < d.start) else 0.0
                        start = max(lower, min(start, qstart))
                    if qend is not None:
                        upper = (next_start - guard) if (next_start is not None and next_start > d.end) else qend
                        end = min(max(end, qend), max(float(d.end), upper))
            if end > start:
                ranges.append((start, end))
    finally:
        if wf is not None:
            try: wf.close()
            except Exception: pass

    ranges.sort()
    if not ranges:
        return []
    merged = [list(ranges[0])]
    # 20 ms is enough to avoid tiny click-sized gaps without swallowing meaningful adjacent speech.
    merge_gap = 0.02 if precision else 0.04
    for s, e in ranges[1:]:
        if s <= merged[-1][1] + merge_gap:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(float(a), float(b)) for a, b in merged]


def choose_clean_codec(src: Path, channels: int, configured: str) -> tuple[str, list[str]]:
    configured = configured.lower().strip()
    if configured != "auto":
        if configured == "aac":
            return "aac", ["-b:a", "256k"]
        if configured == "ac3":
            return "ac3", ["-b:a", "640k"]
        if configured in {"eac3", "e-ac3"}:
            return "eac3", ["-b:a", "768k"]
        return configured, []
    if src.suffix.lower() in {".mp4", ".m4v"}:
        return "aac", ["-b:a", "384k" if channels > 2 else "256k"]
    if channels <= 2:
        return "aac", ["-b:a", "256k"]
    if channels <= 6:
        return "ac3", ["-b:a", "640k"]
    return "eac3", ["-b:a", "1024k"]


def build_mute_filter(ranges: list[tuple[float, float]]) -> str:
    if not ranges:
        return "anull"
    # FFmpeg's expression evaluator fails when a single enable expression contains
    # more than ~100 summed between() terms.  Split large mute lists into a chain
    # of independent volume filters so profanity-heavy movies remain reliable.
    max_terms_per_filter = 80
    filters = []
    for i in range(0, len(ranges), max_terms_per_filter):
        batch = ranges[i:i + max_terms_per_filter]
        expr = "+".join(f"between(t,{start:.3f},{end:.3f})" for start, end in batch)
        filters.append(f"volume=volume=0:enable='{expr}'")
    return ",".join(filters)


def remux_with_clean_track(src: Path, out: Path, audio_rel: int, probe: dict, ranges: list[tuple[float, float]], cfg: dict, progress_callback=None) -> None:
    clean_cfg = cfg["clean_track"]
    title = str(clean_cfg.get("title", "English - CLEAN"))
    existing = find_clean_audio_streams(probe, title)
    replace = bool(clean_cfg.get("replace_existing_clean", True))
    if existing and not replace:
        raise RuntimeError(f"Clean track already exists and replace_existing_clean=false: {title}")

    audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
    excluded_global_indices = [int(s["index"]) for s, _rel in existing] if replace else []
    remaining_audio_count = len(audio_streams) - len(excluded_global_indices)
    channels = int(audio_streams[audio_rel].get("channels") or 2)
    codec, codec_args = choose_clean_codec(src, channels, str(clean_cfg.get("codec", "auto")))
    filt = build_mute_filter(ranges)

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-i", str(src)]
    cmd += ["-filter_complex", f"[0:a:{audio_rel}]{filt}[clean]"]

    # Plex does not reliably honor the MKV default-audio flag. It generally chooses
    # the first audio stream matching the account's preferred language instead.
    # When requested, insert CLEAN immediately before the first retained original
    # audio stream while preserving the relative order of every other input stream.
    place_clean_first = bool(clean_cfg.get("place_clean_first", True))
    clean_audio_rel = 0 if place_clean_first else remaining_audio_count
    clean_mapped = False
    for stream in sorted(probe.get("streams", []), key=lambda x: int(x.get("index", 0))):
        gi = int(stream.get("index", 0))
        if gi in excluded_global_indices:
            continue
        if place_clean_first and not clean_mapped and stream.get("codec_type") == "audio":
            cmd += ["-map", "[clean]"]
            clean_mapped = True
        cmd += ["-map", f"0:{gi}"]
    if not clean_mapped:
        cmd += ["-map", "[clean]"]

    cmd += ["-c", "copy"]
    cmd += [f"-c:a:{clean_audio_rel}", codec]
    if codec_args:
        # Convert generic -b:a into stream-specific option.
        for i in range(0, len(codec_args), 2):
            opt, val = codec_args[i], codec_args[i + 1]
            if opt == "-b:a":
                cmd += [f"-b:a:{clean_audio_rel}", val]
            else:
                cmd += [opt, val]
    cmd += [f"-metadata:s:a:{clean_audio_rel}", f"title={title}"]
    # MP4/M4V stream names are exposed by ffprobe as handler_name rather than title.
    # Write both fields so the CLEAN track is visible to players and can be validated.
    if src.suffix.lower() in {".mp4", ".m4v"}:
        cmd += [f"-metadata:s:a:{clean_audio_rel}", f"handler_name={title}"]
    cmd += [f"-metadata:s:a:{clean_audio_rel}", f"language={clean_cfg.get('language', 'eng')}"]
    if bool(clean_cfg.get("make_default", False)):
        # Unset every original default and mark CLEAN default. This helps players that
        # honor dispositions, while CLEAN-first handles Plex's language-first behavior.
        total_audio_count = remaining_audio_count + 1
        for i in range(total_audio_count):
            cmd += [f"-disposition:a:{i}", "0"]
        cmd += [f"-disposition:a:{clean_audio_rel}", "default"]
    else:
        cmd += [f"-disposition:a:{clean_audio_rel}", "0"]
    cmd += [str(out)]
    run_ffmpeg_progress(cmd, duration_of(probe), progress_callback)


def validate_output(src_probe: dict, out_probe: dict, cfg: dict) -> None:
    title = str(cfg["clean_track"].get("title", "English - CLEAN"))
    clean = find_clean_audio_streams(out_probe, title)
    if len(clean) != 1:
        raise RuntimeError(f"Validation failed: expected exactly one clean track titled {title!r}, found {len(clean)}")
    clean_stream, clean_rel = clean[0]
    clean_cfg = cfg.get("clean_track", {})
    if bool(clean_cfg.get("place_clean_first", True)) and clean_rel != 0:
        raise RuntimeError(f"Validation failed: CLEAN audio was expected first but is audio stream {clean_rel}")
    if bool(clean_cfg.get("make_default", False)) and not bool((clean_stream.get("disposition") or {}).get("default")):
        raise RuntimeError("Validation failed: CLEAN audio was expected to be marked default")
    src_v = [s for s in src_probe.get("streams", []) if s.get("codec_type") == "video"]
    out_v = [s for s in out_probe.get("streams", []) if s.get("codec_type") == "video"]
    if len(src_v) != len(out_v):
        raise RuntimeError("Validation failed: video stream count changed")
    for a, b in zip(src_v, out_v):
        if a.get("codec_name") != b.get("codec_name"):
            raise RuntimeError("Validation failed: video codec changed")
    dur_a, dur_b = duration_of(src_probe), duration_of(out_probe)
    tol = float(cfg["safety"].get("duration_tolerance_seconds", 2.0))
    if dur_a and dur_b and abs(dur_a - dur_b) > tol:
        raise RuntimeError(f"Validation failed: duration changed by {abs(dur_a-dur_b):.2f}s")
    src_audio = [s for s in src_probe.get("streams", []) if s.get("codec_type") == "audio"]
    out_audio = [s for s in out_probe.get("streams", []) if s.get("codec_type") == "audio"]
    src_existing = find_clean_audio_streams(src_probe, title)
    expected = len(src_audio) - len(src_existing) + 1
    if len(out_audio) != expected:
        raise RuntimeError(f"Validation failed: expected {expected} audio streams, found {len(out_audio)}")


def preserve_metadata(src_stat: os.stat_result, temp_out: Path, cfg: dict) -> None:
    if not cfg["safety"].get("preserve_owner_mode", True):
        return
    try:
        os.chmod(temp_out, src_stat.st_mode)
    except OSError:
        pass
    try:
        os.chown(temp_out, src_stat.st_uid, src_stat.st_gid)
    except (OSError, AttributeError, PermissionError):
        pass


def fmt_time(seconds: float) -> str:
    ms = int(round((seconds - int(seconds)) * 1000))
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"


def report_name(path: Path) -> str:
    h = hashlib.sha1(str(path).encode("utf-8", "ignore")).hexdigest()[:10]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem)[:90]
    return f"{safe}-{h}"


def write_report(path: Path, cfg: dict, payload: dict) -> Path:
    report_dir = Path(cfg["reports"].get("directory", "/config/reports"))
    report_dir.mkdir(parents=True, exist_ok=True)
    base = report_dir / (report_name(path) + ".json")
    base.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    txt = base.with_suffix(".txt")
    lines = [
        f"Censorarr {VERSION}",
        f"File: {path}",
        f"Mode: {'DRY RUN' if payload.get('dry_run') else 'APPLY'}",
        f"Normal detections: {payload.get('normal_count', 0)}",
        f"Rescue detections: {payload.get('rescue_count', 0)}",
        f"Subtitle-assisted detections: {payload.get('subtitle_count', 0)}",
        f"Mute ranges: {len(payload.get('mute_ranges', []))}",
        "",
    ]
    for d in payload.get("detections", []):
        extra = ""
        if d.get("source", "").startswith("rescue"):
            extra = f" baseline={d.get('baseline_text')!r} rescue={d.get('rescue_text')!r}"
        lines.append(
            f"{fmt_time(float(d['start']))}  {d['source']:<11}  {d['matched_id']:<20}  {d['text']!r}{extra}"
        )
    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return txt


def config_signature(cfg: dict, profanity_path: Path) -> str:
    relevant = {
        "whisper": cfg["whisper"], "profanity": cfg["profanity"], "rescue": cfg["rescue"],
        "clean_track": cfg["clean_track"], "rating_filter": cfg.get("rating_filter"), "tv": cfg.get("tv"), "marker": cfg.get("marker"),
        "subtitle_assist": cfg.get("subtitle_assist"), "review_mode": cfg.get("review_mode"),
        "dry_run": cfg.get("dry_run"), "version": VERSION,
    }
    h = hashlib.sha256(json.dumps(relevant, sort_keys=True, default=str).encode())
    for extra in (profanity_path, Path("/config/profanity_overrides.json"), Path("/config/custom_profanity.json"), Path("/config/user_exceptions.json")):
        try:
            h.update(extra.read_bytes())
        except OSError:
            pass
    return h.hexdigest()[:20]


def fingerprint(path: Path) -> str:
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def state_load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def state_save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def process_file(path: Path, cfg: dict, model: WhisperModel, matcher: ProfanityMatcher) -> dict:
    logging.info("Processing: %s", path)
    update_heartbeat("preparing", str(path), progress=0)
    src_stat = path.stat()
    src_probe = ffprobe(path)
    media_duration = duration_of(src_probe)
    clean_title = str(cfg["clean_track"].get("title", "English - CLEAN"))
    existing = find_clean_audio_streams(src_probe, clean_title)
    if existing and not cfg["clean_track"].get("replace_existing_clean", True):
        logging.info("Skipping; clean track already exists: %s", path)
        return {"status": "skipped-clean-exists"}

    audio_stream, audio_rel = select_audio_stream(src_probe, cfg.get("audio_track", "auto"))
    workroot = Path("/work")
    workroot.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="censorarr-", dir=str(workroot)))
    # The normal pass and rescue/subtitle passes can share one source-file read. Keep the
    # extracted audio in a fingerprinted cache until the job succeeds so a stopped/failed
    # retry does not spend another minute re-extracting the same movie.
    need_center = (cfg.get("rescue", {}).get("enabled", True) or cfg.get("subtitle_assist", {}).get("enabled", True))
    need_center = bool(need_center and cfg.get("rescue", {}).get("prefer_center_channel", True) and int(audio_stream.get("channels") or 2) >= 3)
    cache_dir, cached_mono, cached_center = audio_cache_paths(path, audio_rel, cfg, need_center)
    mono = cached_mono if cache_dir else workdir / "transcribe-mono.wav"
    center = cached_center if cache_dir else (workdir / "rescue-center.wav" if need_center else None)
    rescue_audio = center if (center is not None and valid_audio_cache(center)) else mono
    analysis_ok = False
    try:
        mono_ready = valid_audio_cache(mono)
        center_ready = (not need_center) or valid_audio_cache(center)
        if mono_ready and center_ready:
            logging.info("Using cached transcription audio for audio track %s", audio_rel)
            update_heartbeat("preparing", str(path), progress=100, preparation="cached-audio")
        else:
            logging.info("Extracting transcription%s audio from audio track %s (%s ch)",
                         " + center-channel rescue" if need_center else "", audio_rel, audio_stream.get("channels"))
            if cache_dir:
                cache_dir.mkdir(parents=True, exist_ok=True)
                mono_tmp = mono.with_name(mono.stem + ".tmp.wav")
                center_tmp = center.with_name(center.stem + ".tmp.wav") if center is not None else None
            else:
                mono_tmp, center_tmp = mono, center
            try:
                extract_transcription_audio_pair(
                    path, audio_rel, mono_tmp, center_tmp, media_duration,
                    lambda pct: update_heartbeat("preparing", str(path), progress=pct, preparation="extracting-audio")
                )
                if cache_dir:
                    os.replace(mono_tmp, mono)
                    if center is not None and center_tmp is not None:
                        os.replace(center_tmp, center)
            except subprocess.CalledProcessError:
                # Some uncommon layouts have no FC channel even though they report 3+ channels.
                # Fall back to normal mono extraction rather than failing the whole movie.
                if need_center:
                    logging.warning("Combined center-channel extraction failed; retrying normal mono only")
                    for x in (mono_tmp, center_tmp):
                        try:
                            if x and x.exists(): x.unlink()
                        except OSError: pass
                    extract_transcription_audio(
                        path, audio_rel, mono_tmp, center_only=False, duration_seconds=media_duration,
                        progress_callback=lambda pct: update_heartbeat("preparing", str(path), progress=pct, preparation="extracting-audio")
                    )
                    if cache_dir: os.replace(mono_tmp, mono)
                    center = None
                else:
                    raise
        rescue_audio = center if (center is not None and valid_audio_cache(center)) else mono
        if rescue_audio != mono:
            logging.info("Center-channel rescue audio is ready")
        update_heartbeat("transcribing", str(path), progress=0)
        words = transcribe(model, mono, cfg, stage="transcribing", current=str(path))
        update_heartbeat("matching", str(path), progress=100)
        normal = matcher.match_words(words, source="normal")
        logging.info("Normal pass: %d profanity detections", len(normal))

        rescue_det: list[Detection] = []
        rescue_details: list[dict] = []
        windows: list[dict] = []
        if cfg["rescue"].get("enabled", True):
            windows = build_rescue_windows(words, matcher, cfg)
            logging.info("Rescue candidates: %d windows", len(windows))
            update_heartbeat("rescue", str(path), progress=0, rescue_windows=len(windows), normal_count=len(normal))
            if windows:
                rescue_det, rescue_details = detect_rescue(model, rescue_audio, windows, matcher, cfg, workdir)
                update_heartbeat("rescue", str(path), progress=100, rescue_windows=len(windows), normal_count=len(normal), rescue_count=len(rescue_det))
                logging.info("Rescue pass: %d accepted detections", len(rescue_det))

        subtitle_det: list[Detection] = []
        subtitle_details: dict = {}
        if cfg.get("subtitle_assist", {}).get("enabled", True):
            update_heartbeat("subtitle-assist", str(path), progress=0, normal_count=len(normal), rescue_count=len(rescue_det))
            subtitle_det, subtitle_details = detect_subtitle_assist(
                model, path, src_probe, words, rescue_audio, normal + rescue_det, matcher, cfg, workdir
            )
            logging.info("Subtitle assist: %d accepted detections%s", len(subtitle_det),
                         f" using {subtitle_details.get('source')}" if subtitle_details.get("source") else " (no usable text subtitle)")
            update_heartbeat("subtitle-assist", str(path), progress=100, subtitle_count=len(subtitle_det),
                             normal_count=len(normal), rescue_count=len(rescue_det))

        # Union and deduplicate normal/rescue/subtitle detections.
        detections: list[Detection] = []
        for d in sorted(normal + rescue_det + subtitle_det, key=lambda x: (x.start, x.end, x.matched_id)):
            if any(abs(d.start - x.start) < 0.12 and abs(d.end - x.end) < 0.25 and d.matched_id == x.matched_id for x in detections):
                continue
            detections.append(d)
        ranges = merge_mute_ranges(detections, cfg, words=words, audio_path=mono)

        payload = {
            "version": VERSION, "file": str(path), "dry_run": bool(cfg.get("dry_run", True)),
            "source_fingerprint": fingerprint(path), "audio_relative_index": audio_rel,
            "normal_count": len(normal), "rescue_count": len(rescue_det), "subtitle_count": len(subtitle_det),
            "detections": [asdict(d) for d in detections],
            "mute_ranges": [{"start": a, "end": b} for a, b in ranges],
            "precision_alignment": dict(cfg.get("precision_alignment", {}) or {}),
            "rescue_windows": windows, "subtitle_assist": subtitle_details,
            "audio_stream": {k: audio_stream.get(k) for k in ("index", "codec_name", "channels", "channel_layout", "tags")},
        }
        if cfg["reports"].get("keep_transcript_json", True):
            payload["transcript_words"] = words
        if cfg["reports"].get("keep_rescue_details", True):
            payload["rescue_details"] = rescue_details
        report = write_report(path, cfg, payload)
        logging.info("Report: %s", report)

        if cfg.get("dry_run", True):
            logging.info("DRY RUN: media file was not modified")
            update_heartbeat("completed", str(path), progress=100, detections=len(detections), dry_run=True)
            analysis_ok = True
            return {"status": "dry-run", "report": str(report), "detections": len(detections)}
        if cfg.get("review_mode", {}).get("enabled", False):
            logging.info("REVIEW: analysis complete; waiting for approval before building CLEAN track")
            update_heartbeat("awaiting-review", str(path), progress=100, detections=len(detections), report=str(report))
            analysis_ok = True
            return {"status": "awaiting-review", "report": str(report), "detections": len(detections)}
        if not ranges:
            logging.info("No profanity detections; no clean track added")
            update_heartbeat("completed", str(path), progress=100, detections=0)
            analysis_ok = True
            return {"status": "no-detections", "report": str(report)}

        suffix = path.suffix
        temp_out = path.with_name(path.name + ".censorarr.tmp" + suffix)
        if temp_out.exists():
            temp_out.unlink()
        logging.info("Building clean track (%d mute ranges) into temporary output", len(ranges))
        update_heartbeat("remuxing", str(path), progress=0, normal_count=len(normal), rescue_count=len(rescue_det), mute_ranges=len(ranges))
        remux_with_clean_track(
            path, temp_out, audio_rel, src_probe, ranges, cfg,
            progress_callback=lambda pct: update_heartbeat("remuxing", str(path), progress=pct, normal_count=len(normal), rescue_count=len(rescue_det), mute_ranges=len(ranges))
        )
        update_heartbeat("validating", str(path), progress=0)
        out_probe = ffprobe(temp_out)
        if cfg["safety"].get("validate_output", True):
            validate_output(src_probe, out_probe, cfg)
        update_heartbeat("validating", str(path), progress=100)
        preserve_metadata(src_stat, temp_out, cfg)

        if cfg["safety"].get("backup_original", False):
            backup = path.with_name(path.name + ".preclean.bak")
            if backup.exists():
                raise RuntimeError(f"Backup already exists: {backup}")
            os.replace(path, backup)
            try:
                os.replace(temp_out, path)
            except Exception:
                os.replace(backup, path)
                raise
            logging.info("Original retained as backup: %s", backup)
        else:
            os.replace(temp_out, path)
        logging.info("SUCCESS: added/replaced clean track: %s", path)
        update_heartbeat("completed", str(path), progress=100, detections=len(detections))
        analysis_ok = True
        return {"status": "applied", "report": str(report), "detections": len(detections)}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        if analysis_ok and cache_dir and not bool((cfg.get("audio_cache", {}) or {}).get("keep_after_success", False)):
            shutil.rmtree(cache_dir, ignore_errors=True)


def report_json_from_txt(report: str | Path) -> Path:
    p = Path(report)
    return p.with_suffix(".json") if p.suffix.lower() == ".txt" else p


def apply_report_to_file(path: Path, report: str | Path, cfg: dict, excluded_indices: list[int] | None = None) -> dict:
    """Apply an already-analyzed report without retranscribing the movie."""
    rp = report_json_from_txt(report)
    if not rp.exists():
        raise RuntimeError(f"Analysis JSON report not found: {rp}")
    payload = json.loads(rp.read_text(encoding="utf-8"))
    if str(payload.get("file")) != str(path):
        raise RuntimeError("Report does not belong to this movie")
    expected = str(payload.get("source_fingerprint") or "")
    if expected and expected != fingerprint(path):
        raise RuntimeError("Movie changed after analysis; re-analyze it before applying the review")
    excluded = {int(x) for x in (excluded_indices or [])}
    dets = []
    for i, d in enumerate(payload.get("detections", [])):
        if i in excluded:
            continue
        dets.append(Detection(
            start=float(d["start"]), end=float(d["end"]), text=str(d.get("text", "")),
            matched_id=str(d.get("matched_id", "")), severity=int(d.get("severity", 3)),
            source=str(d.get("source", "review")), confidence=d.get("confidence"),
            baseline_text=d.get("baseline_text"), rescue_text=d.get("rescue_text"),
        ))
    audio_rel = int(payload.get("audio_relative_index", 0))
    cache_dir, cached_mono, _ = audio_cache_paths(path, audio_rel, cfg, False)
    precision_audio = cached_mono if cache_dir and valid_audio_cache(cached_mono) else None
    ranges = merge_mute_ranges(
        dets, cfg, words=list(payload.get("transcript_words") or []), audio_path=precision_audio
    )
    if not ranges:
        return {"status": "no-detections", "report": str(Path(report)), "detections": 0}
    src_stat = path.stat(); probe = ffprobe(path)
    temp_out = path.with_name(path.name + ".censorarr.tmp" + path.suffix)
    if temp_out.exists(): temp_out.unlink()
    logging.info("REVIEW APPLY: building CLEAN track with %d approved mute ranges", len(ranges))
    update_heartbeat("remuxing", str(path), progress=None, mute_ranges=len(ranges), review_apply=True)
    remux_with_clean_track(path, temp_out, audio_rel, probe, ranges, cfg)
    out_probe = ffprobe(temp_out)
    if cfg.get("safety", {}).get("validate_output", True):
        validate_output(probe, out_probe, cfg)
    preserve_metadata(src_stat, temp_out, cfg)
    if cfg.get("safety", {}).get("backup_original", False):
        backup = path.with_name(path.name + ".preclean.bak")
        if backup.exists(): raise RuntimeError(f"Backup already exists: {backup}")
        os.replace(path, backup)
        try: os.replace(temp_out, path)
        except Exception:
            os.replace(backup, path); raise
    else:
        os.replace(temp_out, path)
    payload["review"] = {"applied_at": time.time(), "excluded_indices": sorted(excluded),
                         "approved_detections": len(dets), "approved_mute_ranges": len(ranges)}
    payload["dry_run"] = False
    rp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info("SUCCESS: review-approved CLEAN track applied: %s", path)
    return {"status": "applied", "report": str(Path(report)), "detections": len(dets)}


_OVERALL_STAGE_SPANS: dict[str, tuple[float, float]] = {
    "processing": (0.0, 0.0),
    "preparing": (0.0, 8.0),
    "transcribing": (8.0, 55.0),
    "remote-gpu": (8.0, 55.0),
    "matching": (55.0, 57.0),
    "rescue": (57.0, 77.0),
    "subtitle-assist": (77.0, 85.0),
    "awaiting-review": (85.0, 85.0),
    "remuxing": (85.0, 98.0),
    "validating": (98.0, 100.0),
    "completed": (100.0, 100.0),
}


def _overall_progress(status: str, stage_progress) -> float | None:
    span = _OVERALL_STAGE_SPANS.get(status)
    if span is None:
        return None
    lo, hi = span
    if hi <= lo:
        return hi
    try:
        pct = max(0.0, min(100.0, float(stage_progress)))
    except (TypeError, ValueError):
        pct = 0.0
    return round(lo + (hi - lo) * pct / 100.0, 1)


def update_heartbeat(status: str = "idle", current: str | None = None, **extra) -> None:
    p = Path("/config/heartbeat.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    stage_progress = extra.get("progress")
    overall = extra.pop("overall_progress", None)
    if overall is None:
        overall = _overall_progress(status, stage_progress)

    # Overall job progress must never move backward for the same media item, even
    # though the per-stage bar intentionally resets to 0 for each new stage.
    prev = {}
    try:
        if p.exists():
            prev = json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        prev = {}
    if overall is not None and current and prev.get("current") == current:
        try:
            old_overall = float(prev.get("overall_progress"))
            overall = max(float(overall), old_overall)
        except (TypeError, ValueError):
            pass

    data = {"timestamp": time.time(), "status": status, "current": current, "version": VERSION}
    data.update(extra)
    data["stage_progress"] = stage_progress
    if overall is not None:
        data["overall_progress"] = round(float(overall), 1)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, p)


def media_files(cfg: dict) -> Iterable[Path]:
    exts = {str(x).lower() for x in cfg.get("extensions", [".mkv"])}
    seen: set[str] = set()
    for root_s in all_media_roots(cfg):
        root = Path(root_s)
        if not root.exists():
            logging.warning("Media root does not exist: %s", root)
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in exts:
                continue
            name = p.name.lower()
            if ".censorarr.tmp" in name or name.endswith(".part") or name.endswith(".partial"):
                continue
            rp = str(_resolved_path(p))
            if rp in seen:
                continue
            seen.add(rp)
            yield p



CONTROL_DIR = Path("/config")
PAUSED_FLAG = CONTROL_DIR / "paused.flag"
SCAN_NOW_FLAG = CONTROL_DIR / "scan-now.flag"
MANUAL_QUEUE = CONTROL_DIR / "manual_queue.json"
CANCELLED_FILE = CONTROL_DIR / "cancelled.json"
SUBTITLE_WAIT_FILE = CONTROL_DIR / "subtitle_wait.json"
INVENTORY_FILE = CONTROL_DIR / "inventory.json"
QUEUE_ACTIVITY_FILE = CONTROL_DIR / "queue-active.flag"

def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default

def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def cancelled_matches(path: Path) -> bool:
    data = _read_json(CANCELLED_FILE, {})
    try:
        return data.get(str(path), {}).get("fingerprint") == fingerprint(path)
    except OSError:
        return False

def clear_cancelled(path: Path) -> None:
    data = _read_json(CANCELLED_FILE, {})
    if str(path) in data:
        data.pop(str(path), None); _write_json(CANCELLED_FILE, data)

def pop_manual_job() -> dict | None:
    q = _read_json(MANUAL_QUEUE, [])
    return q[0] if isinstance(q, list) and q else None

def remove_manual_job(job_id: str) -> None:
    q = _read_json(MANUAL_QUEUE, [])
    if isinstance(q, list):
        _write_json(MANUAL_QUEUE, [x for x in q if str(x.get("id")) != str(job_id)])


def subtitle_wait_records() -> dict:
    d = _read_json(SUBTITLE_WAIT_FILE, {})
    return d if isinstance(d, dict) else {}


def clear_subtitle_wait(path: Path) -> None:
    d = subtitle_wait_records()
    if str(path) in d:
        d.pop(str(path), None)
        _write_json(SUBTITLE_WAIT_FILE, d)


def subtitle_gate(path: Path, probe: dict, cfg: dict, fp: str) -> tuple[str, dict]:
    """Return process/defer. A Bazarr request never blocks the scanner thread."""
    scfg = cfg.get("subtitle_assist", {})
    recs = subtitle_wait_records()
    previous_wait = recs.get(str(path), {})
    if not scfg.get("enabled", True):
        clear_subtitle_wait(path)
        return "process", {"reason": "subtitle-assist-disabled"}
    sources = subassist.list_sources(path, probe, cfg)
    if sources:
        if previous_wait:
            logging.info("Usable text subtitle appeared; resuming processing: %s", path)
        clear_subtitle_wait(path)
        return "process", {"reason": "subtitle-found", "source": sources[0]}
    bcfg = scfg.get("bazarr", {})
    if not (integ.bazarr_enabled(cfg) and bcfg.get("wait_for_download", True)):
        clear_subtitle_wait(path)
        return "process", {"reason": "no-subtitle-bazarr-not-waiting",
                           "image_subtitles": subassist.image_subtitle_summary(probe)}
    now = time.time(); rec = recs.get(str(path), {})
    if rec.get("fingerprint") != fp:
        rec = {}
    timeout_s = max(60, int(float(bcfg.get("timeout_minutes", 30)) * 60))
    max_attempts = max(1, int(bcfg.get("max_attempts", 3)))
    retry_s = max(30, int(bcfg.get("retry_seconds", 300)))
    if rec and now >= float(rec.get("expires_at", 0)):
        logging.info("Subtitle wait expired; continuing with Whisper only: %s", path)
        recs.pop(str(path), None); _write_json(SUBTITLE_WAIT_FILE, recs)
        return "process", {"reason": "bazarr-timeout", "attempts": rec.get("attempts", 0)}
    should_request = not rec or (int(rec.get("attempts", 0)) < max_attempts and now >= float(rec.get("next_request_at", 0)))
    if should_request:
        attempts = int(rec.get("attempts", 0)) + 1
        try:
            result = integ.bazarr_request_missing(path, cfg, media_type_for(path, cfg))
            if not rec:
                rec = {"fingerprint": fp, "requested_at": now, "expires_at": now + timeout_s}
            rec.update({"attempts": attempts, "last_request_at": now, "next_request_at": now + retry_s,
                        "last_result": result, "status": "waiting"})
            recs[str(path)] = rec; _write_json(SUBTITLE_WAIT_FILE, recs)
            logging.info("Requested English subtitle from Bazarr; deferring %s: %s (attempt %d/%d)", media_type_for(path, cfg), path, attempts, max_attempts)
        except Exception as e:
            logging.warning("Bazarr subtitle request failed for %s: %s; continuing with Whisper-only processing", path, e)
            recs.pop(str(path), None); _write_json(SUBTITLE_WAIT_FILE, recs)
            return "process", {"reason": "bazarr-request-failed", "error": str(e)}
    # The poll is intentionally a filesystem/source check rather than a long blocking
    # Bazarr request. The scanner comes back at check_interval_seconds, notices an SRT/ASS/VTT
    # as soon as Bazarr writes it, and periodically reissues search-missing until max_attempts.
    check_s = max(10, int(bcfg.get("check_interval_seconds", 30)))
    if rec and now - float(rec.get("last_poll_log_at", 0)) >= max(30, check_s):
        rec["last_poll_log_at"] = now
        rec["last_checked_at"] = now
        recs[str(path)] = rec
        _write_json(SUBTITLE_WAIT_FILE, recs)
        next_retry = max(0, int(float(rec.get("next_request_at", now)) - now))
        left = max(0, int(float(rec.get("expires_at", now)) - now))
        logging.info(
            "Still waiting for Bazarr subtitle: %s (attempt %s/%s, next search in %ss, timeout in %ss)",
            path, rec.get("attempts", 0), max_attempts, next_retry, left
        )
    return "defer", {"reason": "waiting-for-bazarr", **rec}


def after_success(path: Path, cfg: dict, status: str, rating: str | None, report: str | None) -> None:
    # Plex only needs a media refresh when the file itself changed. A no-detections completion writes
    # state/marker only and should not cause an unnecessary library refresh.
    if status == "applied" and cfg.get("plex_activity", {}).get("refresh_after_processing", True):
        try:
            item, _why = plex_item_for(path, cfg)
            key = item.get("ratingKey") if item else None
            if key:
                if integ.plex_refresh_rating_key(cfg, key):
                    logging.info("Requested Plex refresh for %s", path.name)
            else:
                integ.plex_scan_library(cfg, media_type_for(path, cfg))
        except Exception as e:
            logging.warning("Plex refresh after processing failed: %s", e)
    integ.notify("completed", f"Censorarr completed {path.name} ({status})", cfg,
                 {"path": str(path), "status": status, "rating": rating, "report": report})


def daemon(cfg: dict, args: argparse.Namespace) -> None:
    # A brand-new installation should not download/load a Whisper model or touch media before the
    # user finishes the guided setup. Re-read config in place so choosing a GPU worker in the wizard
    # does not first waste time downloading a local model.
    if not args.file:
        config_path = Path(os.environ.get("CENSORARR_CONFIG", "/config/config.yaml"))
        announced = False
        while not STOP and not bool((cfg.get("setup", {}) or {}).get("completed", True)):
            if not announced:
                logging.info("Fresh install is waiting for the Setup Wizard before processing starts")
                announced = True
            update_heartbeat("setup-required", None, gate="setup-required", reason="Complete the Setup Wizard in the web interface")
            time.sleep(2)
            cfg = load_config(config_path)
        if STOP:
            return

    profanity_path = Path(cfg["profanity"].get("file", "/config/en.json"))
    matcher = ProfanityMatcher(
        profanity_path,
        int(cfg["profanity"].get("min_severity", 3)),
        int(cfg["profanity"].get("max_word_window", 4)),
    )
    logging.info("Loaded %d active profanity entries (severity >= %s)", len(matcher.active), cfg["profanity"].get("min_severity", 3))
    wcfg = cfg["whisper"]
    model: WhisperModel | None = None
    if remote_asr.enabled(cfg):
        rcfg = remote_asr.config(cfg)
        logging.info("Remote GPU ASR enabled: %s model=%s (local fallback=%s)", rcfg.get("url"), rcfg.get("model") or wcfg.get("model"), rcfg.get("fallback_to_local", True))
        try:
            h = remote_asr.health(cfg)
            logging.info("Remote GPU worker online: %s", h)
        except Exception as e:
            logging.warning("Remote GPU worker health check failed at startup: %s", e)
            if not bool(rcfg.get("fallback_to_local", True)):
                raise
    else:
        logging.info("Loading Whisper model %s on %s/%s", wcfg["model"], wcfg["device"], wcfg["compute_type"])
        model = WhisperModel(str(wcfg["model"]), device=str(wcfg["device"]), compute_type=str(wcfg["compute_type"]), download_root="/config/models")
    sig = config_signature(cfg, profanity_path)
    state_path = Path("/config/state.json")
    state = state_load(state_path)
    state.setdefault("files", {})
    stable_seen: dict[str, dict] = {}

    def handle_one(p: Path, force: bool = False) -> None:
        key = str(p)
        try:
            fp = fingerprint(p)
        except OSError:
            return
        old = state["files"].get(key, {})
        if force:
            clear_cancelled(p)
        elif cancelled_matches(p):
            logging.info("Skipping cancelled file until manually requeued or replaced: %s", p)
            return
        if not force and marker_matches(p, cfg):
            return
        if not force and old.get("fingerprint") == fp and old.get("config_signature") == sig and old.get("status") == "dry-run":
            return
        # Do not burn hours retrying a deterministic failure every scan. A new
        # Censorarr version or a manual/GUI reprocess will try it again.
        if (not force and old.get("fingerprint") == fp and old.get("config_signature") == sig
                and old.get("status") == "error" and old.get("version") == VERSION):
            return
        decision, rating, rating_reason = rating_decision(p, cfg)
        if decision == "wait":
            logging.info("Waiting for usable Plex rating: %s (%s)", p, rating_reason)
            state["files"][key] = {"fingerprint": fp, "config_signature": sig, "status": "waiting-rating",
                                   "media_type": media_type_for(p, cfg), "rating": rating, "time": time.time(), "reason": rating_reason}
            state_save(state_path, state)
            return
        if decision == "skip":
            logging.info("Skipping by content rating %s: %s", rating, p)
            marker_write(p, cfg, "skipped-rating", rating=rating)
            state["files"][key] = {"fingerprint":fp,"config_signature":sig,"status":"skipped-rating","media_type":media_type_for(p,cfg),"rating":rating,"time":time.time()}
            state_save(state_path,state)
            return
        probe = ffprobe(p)
        if find_clean_audio_streams(probe, str(cfg["clean_track"].get("title", "English - CLEAN"))):
            if not force and not cfg["clean_track"].get("reprocess_existing_clean", False):
                state["files"][key] = {"fingerprint": fp, "config_signature": sig, "status": "clean-exists", "media_type": media_type_for(p,cfg), "time": time.time(), "rating": rating}
                state_save(state_path, state)
                marker_write(p, cfg, "clean-exists", rating=rating)
                return
        if not force:
            sub_action, sub_info = subtitle_gate(p, probe, cfg, fp)
            if sub_action == "defer":
                QUEUE_ACTIVITY_FILE.touch()
                state["files"][key] = {"fingerprint": fp, "config_signature": sig, "status": "waiting-subtitle",
                                       "media_type": media_type_for(p,cfg), "rating": rating, "time": time.time(), "subtitle_wait": sub_info}
                state_save(state_path, state)
                update_heartbeat("waiting-subtitle", key, **{"subtitle_wait": sub_info})
                return
        QUEUE_ACTIVITY_FILE.touch()
        update_heartbeat("processing", key)
        started = time.time()
        try:
            result = process_file(p, cfg, model, matcher)
            newfp = fingerprint(p) if p.exists() else fp
            elapsed = max(0.0, time.time() - started)
            state["files"][key] = {
                "fingerprint": newfp, "config_signature": sig, "status": result.get("status"),
                "media_type": media_type_for(p,cfg), "time": time.time(), "report": result.get("report"), "rating": rating,
                "processing_seconds": elapsed, "detections": result.get("detections"),
            }
            state_save(state_path, state)
            if result.get("status") in {"applied", "no-detections", "skipped-clean-exists"}:
                marker_write(p, cfg, str(result.get("status")), rating=rating, report=result.get("report"))
                after_success(p, cfg, str(result.get("status")), rating, result.get("report"))
        except Exception as exc:
            logging.exception("FAILED processing %s: %s", p, exc)
            state["files"][key] = {
                "fingerprint": fp, "config_signature": sig, "status": "error", "time": time.time(),
                "version": VERSION, "error": str(exc), "media_type": media_type_for(p,cfg), "rating": rating,
                "processing_seconds": max(0.0, time.time() - started),
            }
            state_save(state_path, state)
            integ.notify("failed", f"Censorarr failed: {p.name}: {exc}", cfg, {"path": str(p), "error": str(exc)})
        finally:
            update_heartbeat("idle")

    def handle_review_apply(job: dict) -> None:
        p = Path(str(job.get("path", "")))
        key = str(p)
        if not p.exists():
            logging.warning("Review apply file no longer exists: %s", p); return
        old = state["files"].get(key, {})
        report = str(job.get("report") or old.get("report") or "")
        rating = old.get("rating")
        started = time.time()
        try:
            result = apply_report_to_file(p, report, cfg, list(job.get("excluded_indices") or []))
            state["files"][key] = {**old, "fingerprint": fingerprint(p), "config_signature": sig,
                                   "status": result.get("status"), "time": time.time(), "report": result.get("report"),
                                   "processing_seconds": max(0.0, time.time()-started), "review_applied": True}
            state_save(state_path, state)
            if result.get("status") in {"applied", "no-detections"}:
                marker_write(p, cfg, str(result.get("status")), rating=rating, report=result.get("report"))
                after_success(p, cfg, str(result.get("status")), rating, result.get("report"))
        except Exception as exc:
            logging.exception("FAILED review apply %s: %s", p, exc)
            state["files"][key] = {**old, "status": "error", "error": str(exc), "time": time.time(), "version": VERSION}
            state_save(state_path, state)
            integ.notify("failed", f"Censorarr review apply failed: {p.name}: {exc}", cfg)
        finally:
            update_heartbeat("idle")

    if args.file:
        handle_one(Path(args.file), force=True)
        return

    stable_seconds = int(cfg.get("stable_seconds", 300))
    interval = int(cfg.get("scan_interval_seconds", 120))
    first_scan = True
    while not STOP:
        # Manual jobs have priority and can run even while automatic processing is paused.
        job = pop_manual_job()
        if job:
            jp = Path(str(job.get("path", "")))
            if jp.exists():
                mode = str(job.get("mode", "process"))
                logging.info("Manual job requested (%s): %s", mode, jp)
                if mode == "apply-report": handle_review_apply(job)
                else: handle_one(jp, force=True)
            else:
                logging.warning("Manual job file no longer exists: %s", jp)
            remove_manual_job(str(job.get("id", "")))
            continue
        if PAUSED_FLAG.exists():
            update_heartbeat("paused")
            time.sleep(1)
            continue
        allowed, gate_reason, gate_extra = integ.processing_gate(cfg)
        if not allowed:
            update_heartbeat("blocked", None, gate=gate_reason, **gate_extra)
            time.sleep(5)
            continue
        if SCAN_NOW_FLAG.exists():
            try: SCAN_NOW_FLAG.unlink()
            except OSError: pass
        update_heartbeat("scanning")
        now = time.time()
        found = 0
        processing_blocked = False
        for p in media_files(cfg):
            found += 1
            try:
                st = p.stat()
            except OSError:
                continue
            key = str(p)
            current = (st.st_size, st.st_mtime_ns)
            rec = stable_seen.get(key)
            if rec is None or rec.get("stat") != current:
                stable_seen[key] = {"stat": current, "since": now}
                # Existing files that have not changed for stable_seconds can be processed immediately on startup.
                if first_scan and cfg.get("process_existing", True) and now - st.st_mtime >= stable_seconds:
                    stable_seen[key]["since"] = now - stable_seconds - 1
                    rec = stable_seen[key]
                else:
                    continue
            if now - float(rec["since"]) < stable_seconds:
                continue
            # Re-check schedule/Plex activity BETWEEN movies. A Plex stream that starts while a long
            # transcription is running should prevent the next automatic movie from starting.
            if processing_blocked:
                continue
            allowed_now, gate_reason_now, gate_extra_now = integ.processing_gate(cfg)
            if not allowed_now:
                processing_blocked = True
                update_heartbeat("blocked", None, gate=gate_reason_now, **gate_extra_now)
                continue
            handle_one(p)
        inv_movie = 0; inv_episode = 0
        for path_key in stable_seen.keys():
            try:
                if media_type_for(Path(path_key), cfg) == "episode": inv_episode += 1
                else: inv_movie += 1
            except Exception:
                pass
        _write_json(INVENTORY_FILE, {"total": found, "movies": inv_movie, "episodes": inv_episode, "timestamp": time.time()})
        pending_manual = bool(_read_json(MANUAL_QUEUE, []))
        pending_subs = bool(subtitle_wait_records())
        pending_state = any(v.get("status") in {"waiting-rating", "waiting-subtitle", "awaiting-review"} for v in state.get("files", {}).values())
        if QUEUE_ACTIVITY_FILE.exists() and not (pending_manual or pending_subs or pending_state):
            integ.notify("queue-finished", "Censorarr queue is finished.", cfg, {"media_seen": found})
            try: QUEUE_ACTIVITY_FILE.unlink()
            except OSError: pass
        logging.info("Scan complete: %d media files seen", found)
        first_scan = False
        update_heartbeat("idle")
        if args.once:
            break
        wait_recs = subtitle_wait_records()
        subtitle_check = int(cfg.get("subtitle_assist", {}).get("bazarr", {}).get("check_interval_seconds", 30))
        effective_interval = min(interval, max(10, subtitle_check)) if wait_recs else interval
        for _ in range(max(1, effective_interval)):
            if STOP:
                break
            time.sleep(1)
            if SCAN_NOW_FLAG.exists() or PAUSED_FLAG.exists():
                break
            if _ % 30 == 0:
                update_heartbeat("idle")


def signal_handler(_sig, _frame):
    global STOP
    STOP = True
    logging.info("Shutdown requested")


def main() -> int:
    parser = argparse.ArgumentParser(description="Censorarr - automated clean-audio media manager")
    parser.add_argument("--once", action="store_true", help="Scan once and exit")
    parser.add_argument("--file", help="Process one file path inside the container immediately")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()
    if args.version:
        print(VERSION)
        return 0
    config_path = Path(os.environ.get("CENSORARR_CONFIG", "/config/config.yaml"))
    cfg = load_config(config_path)
    setup_logging(cfg)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    logging.info("Censorarr %s worker starting; dry_run=%s", VERSION, cfg.get("dry_run"))
    Path("/work").mkdir(parents=True, exist_ok=True)
    for orphan in Path("/work").glob("censorarr-*"):
        if orphan.is_dir(): shutil.rmtree(orphan, ignore_errors=True)
    update_heartbeat("starting")
    try:
        daemon(cfg, args)
        return 0
    except Exception:
        logging.exception("Fatal error")
        update_heartbeat("fatal")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
