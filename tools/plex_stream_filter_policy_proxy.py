#!/usr/bin/env python3
"""Stable Censorarr Plex playback-policy proxy entry point.

Filtered universal playback disables Direct Play, preserves Direct Stream/video
copy, disables audio Direct Stream so audio reaches the Censorarr transcoder
shim, and preserves timestamps for mute-range alignment.

For Plex Android TV text subtitles, the client may request subtitles=burn even
though it can render timed text. Burning an SRT forces video encoding. For that
specific text-subtitle case Censorarr changes the request to subtitles=auto and
adds an HLS WebVTT subtitle transcode target. Plex can then convert text
subtitles for the HLS player without burning them into the copied video.
Advanced/image subtitle behavior is otherwise left untouched.
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
_HLS_WEBVTT_TARGET = (
    "add-transcode-target(type=subtitleProfile&context=streaming&protocol=hls&"
    "container=webvtt&subtitleCodec=webvtt&replace=true)"
)


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
        saw_profile = False
        profile_changed = False

        for key, value in rows:
            lower = key.casefold()
            if lower == "subtitles":
                out.append((key, "auto"))
                continue
            if lower == "x-plex-client-profile-extra":
                saw_profile = True
                profile = value
                if "protocol=hls&container=webvtt&subtitlecodec=webvtt" not in profile.casefold():
                    profile = (profile + "+" if profile else "") + _HLS_WEBVTT_TARGET
                    profile_changed = True
                out.append((key, profile))
                continue
            out.append((key, value))

        if not saw_profile:
            out.append(("X-Plex-Client-Profile-Extra", _HLS_WEBVTT_TARGET))
            profile_changed = True

        rewritten = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(out, doseq=True), parts.fragment)
        )
        changed = dict(changed)
        changed["subtitles"] = "auto"
        if profile_changed:
            changed["X-Plex-Client-Profile-Extra"] = "append-hls-webvtt"

    return rewritten, changed


proxy._rewrite_target = _rewrite_target


if __name__ == "__main__":
    raise SystemExit(proxy.main())
