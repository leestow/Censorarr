#!/usr/bin/env python3
"""Censorarr Plex stream-filter gateway.

Stable entry point for the validated Shield playback path. The gateway
terminates Plex HTTPS, correlates a Plex playback decision with allowlisted
media, rejects Direct Play file requests immediately with HTTP 415, and lets the
Plex client fall back to its native universal HLS path.

The companion policy proxy forces filtered universal playback to:

  directPlay=0
  directStream=1
  directStreamAudio=0
  copyts=1

That keeps compatible video on COPY while routing audio through the Censorarr
Plex Transcoder shim for profanity muting. The v1-v5 modules remain in the
repository as development checkpoints; this file is the stable runtime entry
point.
"""
from __future__ import annotations

import argparse
import sys

import plex_filtered_handoff as base
import plex_filtered_handoff_v2 as v2
import plex_filtered_handoff_v3 as v3
import plex_filtered_handoff_v5 as validated


def main() -> int:
    parser = argparse.ArgumentParser(description="Censorarr Plex stream-filter gateway")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=32403)
    parser.add_argument("--policy-host", default="127.0.0.1")
    parser.add_argument("--policy-port", type=int, default=32402)
    parser.add_argument("--plex-host", default="127.0.0.1")
    parser.add_argument("--plex-port", type=int, default=32400)
    parser.add_argument("--allowlist", default=base.DEFAULT_ALLOWLIST)
    parser.add_argument("--probe-edge-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--timeline-ttl-seconds", type=float, default=v2.DEFAULT_TIMELINE_TTL_SECONDS)
    parser.add_argument("--handoff-cooldown-seconds", type=float, default=v2.DEFAULT_HANDOFF_COOLDOWN_SECONDS)
    parser.add_argument("--startup-grace-seconds", type=float, default=v3.DEFAULT_STARTUP_GRACE_SECONDS)
    parser.add_argument("--plex-appdata")
    parser.add_argument("--log", default="/volume1/docker/censorarr-test/work/plex-stream-gateway.log")
    args = parser.parse_args()

    try:
        state = v3.V3State(args)
    except Exception as exc:
        print(f"ERROR: gateway preflight failed: {exc}", file=sys.stderr)
        return 2

    try:
        server = base.ThreadingHandoffProxy((args.listen_host, args.listen_port), validated.V5Handler)
    except OSError as exc:
        print(f"ERROR: could not listen on {args.listen_host}:{args.listen_port}: {exc}", file=sys.stderr)
        return 3

    server.state = state  # type: ignore[attr-defined]
    state.log(
        "START_GATEWAY listen=%s:%s policy=%s:%s plex=%s:%s tls=plex:%s allowlist=%s "
        "directplay=reject-415 native_hls=yes video=copy audio=transcode"
        % (
            args.listen_host,
            args.listen_port,
            args.policy_host,
            args.policy_port,
            args.plex_host,
            args.plex_port,
            state.tls_p12.name,
            args.allowlist,
        )
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        state.log("STOP_GATEWAY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
