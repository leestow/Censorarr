#!/usr/bin/env python3
"""Stable Censorarr Plex playback-policy proxy entry point.

Filtered universal playback disables Direct Play, preserves Direct Stream/video
copy, disables audio Direct Stream so audio reaches the Censorarr transcoder
shim, and preserves timestamps for mute-range alignment.

For Plex Android TV text subtitles, the client may request subtitles=burn even
though the HLS/Matroska target can carry compatible text subtitles. Burning an
SRT forces video encoding. For that specific text-subtitle case Censorarr
changes the request to subtitles=embedded so Plex can mux the selected text
subtitle into the HLS Matroska segments while leaving advanced/image subtitle
behavior untouched.
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


def _rewrite_target(target: str) -> tuple[str, dict[str, str]]:
    rewritten, changed = _original_rewrite_target(target)
    parts = urlsplit(rewritten)
    rows = [(str(k), str(v)) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    values = {k.casefold(): v for k, v in rows}

    if (
        values.get("advancedsubtitles", "").casefold() == "text"
        and values.get("subtitles", "").casefold() == "burn"
    ):
        out: list[tuple[str, str]] = []
        for key, value in rows:
            if key.casefold() == "subtitles":
                out.append((key, "embedded"))
            else:
                out.append((key, value))

        rewritten = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(out, doseq=True), parts.fragment)
        )
        changed = dict(changed)
        changed["subtitles"] = "embedded"

    return rewritten, changed


proxy._rewrite_target = _rewrite_target


if __name__ == "__main__":
    raise SystemExit(proxy.main())
