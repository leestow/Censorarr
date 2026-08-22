#!/usr/bin/env python3
"""Policy helpers for routing Censorarr-filtered Plex playback through transcoding.

This module does not proxy traffic by itself. It is the deliberately small policy
layer that a future Plex middleware/reverse-proxy will call for universal transcode
`decision` and `start` requests.

For a session selected for filtering, the first policy is:

* directPlay=0       -> do not let the client bypass Plex Transcoder
* directStream=1     -> allow Plex to copy/remux video when the client supports it
* directStreamAudio=0 -> require audio processing so the Censorarr shim can mute it
* copyts=1           -> preserve media timestamps used by Censorarr mute ranges

The proxy will identify filtered accounts by Plex token. Raw tokens should not be
stored in policy files; this module stores/compares SHA-256 token fingerprints.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UNIVERSAL_PREFIX = "/video/:/transcode/universal/"
FILTERED_QUERY_VALUES = {
    "directPlay": "0",
    "directStream": "1",
    "directStreamAudio": "0",
    "copyts": "1",
}


def token_sha256(token: str) -> str:
    value = str(token or "").strip()
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def token_from_request(query_items: Iterable[tuple[str, str]], headers: Mapping[str, str] | None = None) -> str:
    for key, value in query_items:
        if key.casefold() == "x-plex-token" and str(value).strip():
            return str(value).strip()
    for key, value in (headers or {}).items():
        if str(key).casefold() == "x-plex-token" and str(value).strip():
            return str(value).strip()
    return ""


def is_universal_playback_path(path: str) -> bool:
    raw = str(path or "")
    if not raw.startswith(UNIVERSAL_PREFIX):
        return False
    leaf = raw[len(UNIVERSAL_PREFIX):].casefold()
    return leaf == "decision" or leaf.startswith("start")


def load_policy(path: str | Path) -> dict:
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return {"schema": 1, "filtered_token_sha256": []}
    if not isinstance(payload, dict):
        return {"schema": 1, "filtered_token_sha256": []}
    rows = payload.get("filtered_token_sha256") or []
    payload["filtered_token_sha256"] = [str(x).strip().casefold() for x in rows if str(x).strip()]
    return payload


def token_is_filtered(token: str, policy: Mapping) -> bool:
    digest = token_sha256(token)
    if not digest:
        return False
    wanted = {str(x).strip().casefold() for x in (policy.get("filtered_token_sha256") or []) if str(x).strip()}
    return digest.casefold() in wanted


def rewrite_query_items(query_items: Iterable[tuple[str, str]], filtered: bool) -> tuple[list[tuple[str, str]], dict[str, str]]:
    rows = [(str(k), str(v)) for k, v in query_items]
    if not filtered:
        return rows, {}

    lower_to_index: dict[str, int] = {}
    for idx, (key, _value) in enumerate(rows):
        lower_to_index[key.casefold()] = idx

    changed: dict[str, str] = {}
    for key, value in FILTERED_QUERY_VALUES.items():
        idx = lower_to_index.get(key.casefold())
        if idx is None:
            rows.append((key, value))
            lower_to_index[key.casefold()] = len(rows) - 1
            changed[key] = value
            continue
        existing_key, existing_value = rows[idx]
        if existing_value != value:
            rows[idx] = (existing_key, value)
            changed[existing_key] = value
    return rows, changed


def rewrite_url(url: str, filtered: bool) -> tuple[str, dict]:
    parts = urlsplit(str(url))
    items = parse_qsl(parts.query, keep_blank_values=True)
    if not is_universal_playback_path(parts.path):
        return str(url), {"changed": False, "reason": "not-universal-playback"}
    rewritten, values = rewrite_query_items(items, filtered=filtered)
    if not filtered:
        return str(url), {"changed": False, "reason": "policy-unfiltered"}
    out = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(rewritten, doseq=True), parts.fragment))
    return out, {
        "changed": out != str(url),
        "reason": "filtered-playback-policy",
        "set": values,
    }


def _self_test() -> None:
    original = (
        "http://plex:32400/video/:/transcode/universal/decision?"
        "path=%2Flibrary%2Fmetadata%2F123&directPlay=1&directStream=1&"
        "directStreamAudio=1&copyts=0&X-Plex-Token=secret"
    )
    rewritten, result = rewrite_url(original, filtered=True)
    parsed = dict(parse_qsl(urlsplit(rewritten).query, keep_blank_values=True))
    assert result["changed"] is True
    assert parsed["directPlay"] == "0"
    assert parsed["directStream"] == "1"
    assert parsed["directStreamAudio"] == "0"
    assert parsed["copyts"] == "1"
    assert parsed["X-Plex-Token"] == "secret"
    assert token_from_request(parse_qsl(urlsplit(rewritten).query)) == "secret"
    assert not is_universal_playback_path("/library/metadata/123")
    policy = {"filtered_token_sha256": [token_sha256("secret")]}
    assert token_is_filtered("secret", policy)
    assert not token_is_filtered("adult-token", policy)
    print("plex_stream_policy self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview Censorarr Plex playback policy rewrites")
    parser.add_argument("--url", help="Plex universal decision/start URL to rewrite")
    parser.add_argument("--filtered", action="store_true", help="Apply filtered-playback policy")
    parser.add_argument("--self-test", action="store_true", help="Run built-in policy tests")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
        return 0
    if not args.url:
        parser.error("--url or --self-test is required")
    rewritten, result = rewrite_url(args.url, filtered=bool(args.filtered))
    print(json.dumps({"result": result, "url": rewritten}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
