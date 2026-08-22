#!/usr/bin/env python3
"""Run the Censorarr Plex policy proxy with Direct Stream enabled.

This development wrapper keeps Direct Play disabled and audio Direct Stream
disabled, but allows container/video Direct Stream. For compatible Shield media
that means Plex can COPY the video while transcoding audio through the Censorarr
Plex Transcoder shim.
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
