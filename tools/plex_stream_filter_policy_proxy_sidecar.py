#!/usr/bin/env python3
"""Experimental Censorarr Plex policy: native HLS + client-rendered text subtitles.

For filtered playback keep the proven low-CPU policy:
  directPlay=0
  directStream=1
  directStreamAudio=0
  copyts=1

For Android TV text subtitles, change subtitles=burn to subtitles=sidecar. On the
universal HLS start request also set skipSubtitles=1. Plex's own player code uses
skipSubtitles=1 for soft/client-rendered subtitles during HLS transcoding; this
keeps the subtitle out of the HLS A/V transcode so the client can render the
selected external SRT separately.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import plex_policy_proxy as proxy

proxy.FILTER_VALUES.update(
    {
        "directPlay": "0",
        "directStream": "1",
        "directStreamAudio": "0",
        "copyts": "1",
    }
)

_original_rewrite_target = proxy._rewrite_target


def _set_query(rows: list[tuple[str, str]], name: str, value: str) -> list[tuple[str, str]]:
    wanted = name.casefold()
    out: list[tuple[str, str]] = []
    found = False
    for key, old in rows:
        if key.casefold() == wanted:
            if not found:
                out.append((key, value))
                found = True
        else:
            out.append((key, old))
    if not found:
        out.append((name, value))
    return out


def _rewrite_target(target: str) -> tuple[str, dict[str, str]]:
    rewritten, changed = _original_rewrite_target(target)
    parts = urlsplit(rewritten)
    rows = [(str(k), str(v)) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    values = {k.casefold(): v for k, v in rows}

    is_text = values.get("advancedsubtitles", "").casefold() == "text"
    subtitle_mode = values.get("subtitles", "").casefold()

    if is_text and subtitle_mode == "burn":
        rows = _set_query(rows, "subtitles", "sidecar")
        changed = dict(changed)
        changed["subtitles"] = "sidecar"

    if is_text and parts.path.casefold().endswith("/start.m3u8"):
        rows = _set_query(rows, "skipSubtitles", "1")
        changed = dict(changed)
        changed["skipSubtitles"] = "1"

    rewritten = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(rows, doseq=True), parts.fragment)
    )
    return rewritten, changed


proxy._rewrite_target = _rewrite_target


if __name__ == "__main__":
    raise SystemExit(proxy.main())
