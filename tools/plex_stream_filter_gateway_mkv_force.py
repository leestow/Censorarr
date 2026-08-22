#!/usr/bin/env python3
"""Forced MKV + embedded subtitle proof for Shield.

This deliberately removes subtitle-detection logic from the experiment. Every
allowlisted/eligible playback uses the previously proven V4 start.mkv handoff,
with video direct-stream/copy, audio transcode through the Censorarr shim, and
subtitles=embedded.

It is a proof tool only. The production gateway should remain conditional.
"""
from __future__ import annotations

import argparse
import sys

import plex_filtered_handoff as base
import plex_filtered_handoff_v2 as v2
import plex_filtered_handoff_v3 as v3
import plex_filtered_handoff_v4 as v4


class ForceMkvState(v3.V3State):
    def filtered_start_target_v3(self, entry: dict, offset_seconds: float) -> str:
        target = super().filtered_start_target_v3(entry, offset_seconds)
        return base._replace_query(
            target,
            {
                "directPlay": "0",
                "directStream": "1",
                "directStreamAudio": "0",
                "copyts": "1",
                "protocol": "*",
                "subtitles": "embedded",
            },
        )


class ForceMkvHandler(v4.V4Handler):
    def _filtered_exact_offset(
        self,
        state: ForceMkvState,
        client,
        entry: dict,
        headers: dict[str, str],
        offset_seconds: float,
        source: str,
        correlation: str,
    ) -> bool:
        state.log(
            "FORCE_MKV_EMBEDDED client=%s media=%s source=%s correlation=%s offset=%.3f"
            % (
                self.client_address[0],
                entry.get("basename") or "-",
                source,
                correlation,
                offset_seconds,
            )
        )
        return super()._filtered_exact_offset(
            state,
            client,
            entry,
            headers,
            offset_seconds,
            source,
            correlation,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Censorarr forced MKV embedded-subtitle proof"
    )
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=32403)
    parser.add_argument("--policy-host", default="127.0.0.1")
    parser.add_argument("--policy-port", type=int, default=32402)
    parser.add_argument("--plex-host", default="127.0.0.1")
    parser.add_argument("--plex-port", type=int, default=32400)
    parser.add_argument("--allowlist", default=base.DEFAULT_ALLOWLIST)
    parser.add_argument("--probe-edge-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument(
        "--timeline-ttl-seconds",
        type=float,
        default=v2.DEFAULT_TIMELINE_TTL_SECONDS,
    )
    parser.add_argument(
        "--handoff-cooldown-seconds",
        type=float,
        default=v2.DEFAULT_HANDOFF_COOLDOWN_SECONDS,
    )
    parser.add_argument(
        "--startup-grace-seconds",
        type=float,
        default=v3.DEFAULT_STARTUP_GRACE_SECONDS,
    )
    parser.add_argument("--plex-appdata")
    parser.add_argument(
        "--log",
        default="/volume1/docker/censorarr-test/work/plex-stream-gateway.log",
    )
    args = parser.parse_args()

    try:
        state = ForceMkvState(args)
    except Exception as exc:
        print(f"ERROR: gateway preflight failed: {exc}", file=sys.stderr)
        return 2

    try:
        server = base.ThreadingHandoffProxy(
            (args.listen_host, args.listen_port), ForceMkvHandler
        )
    except OSError as exc:
        print(
            f"ERROR: could not listen on {args.listen_host}:{args.listen_port}: {exc}",
            file=sys.stderr,
        )
        return 3

    server.state = state  # type: ignore[attr-defined]
    state.log(
        "START_GATEWAY_FORCE_MKV listen=%s:%s policy=%s:%s plex=%s:%s tls=plex:%s allowlist=%s subtitles=embedded video=copy audio=transcode"
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
        state.log("STOP_GATEWAY_FORCE_MKV")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
