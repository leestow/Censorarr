#!/usr/bin/env python3
"""Stable Censorarr Plex playback-policy proxy entry point.

Filtered universal playback disables Direct Play, preserves Direct Stream/video
copy, disables audio Direct Stream so audio reaches the Censorarr transcoder
shim, and preserves timestamps for mute-range alignment.
"""
from __future__ import annotations

import plex_policy_proxy as proxy

proxy.FILTER_VALUES.update(
    {
        "directPlay": "0",
        "directStream": "1",
        "directStreamAudio": "0",
        "copyts": "1",
    }
)

if __name__ == "__main__":
    raise SystemExit(proxy.main())
