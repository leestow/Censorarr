#!/usr/bin/env python3
"""Fifth Shield filtered-playback proof: fail Direct Play fast, let Plex use HLS.

By v4/v5 testing we proved that Plex's native universal HLS path can run the
movie with HEVC video COPY + audio TRANSCODE when the policy proxy forces:

  directPlay=0
  directStream=1
  directStreamAudio=0
  copyts=1

The remaining long startup delay came from the Android TV player first opening
/library/parts/.../file.mkv and waiting tens of seconds before falling back to
that working HLS path.

V5 therefore stops substituting start.mkv.  For an allowlisted media part that
has already been correlated to a filtered playback decision, every Direct Play
file request is failed immediately with HTTP 415.  The Plex Android TV app can
then fall back to its own universal HLS request, preserving the native player
flow, native seek behavior, and the already-proven Censorarr transcoder shim.

Unmatched/non-allowlisted requests remain fail-open to the normal proxy chain.
"""
from __future__ import annotations

import argparse
import socket
from urllib.parse import urlsplit

import plex_policy_proxy as policy
import plex_filtered_handoff as base
import plex_filtered_handoff_v2 as v2
import plex_filtered_handoff_v3 as v3
import plex_filtered_handoff_v4 as v4


class V5Handler(v4.V4Handler):
    def _reject_direct_play(
        self,
        state: v3.V3State,
        client: socket.socket,
        entry: dict,
        reason: str,
        correlation: str,
    ) -> bool:
        state.log(
            "DIRECTPLAY_REJECT client=%s media=%s correlation=%s reason=%s status=415 action=force-native-hls-fallback"
            % (
                self.client_address[0],
                entry.get("basename") or "-",
                correlation,
                reason,
            )
        )
        payload = (
            b"HTTP/1.1 415 Unsupported Media Type\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Cache-Control: no-store\r\n"
            b"X-Censorarr-Direct-Play: rejected\r\n"
            b"\r\n"
        )
        try:
            client.sendall(payload)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        return True

    def _filtered_exact_offset(
        self,
        state: v3.V3State,
        client: socket.socket,
        entry: dict,
        headers: dict[str, str],
        offset_seconds: float,
        source: str,
        correlation: str,
    ) -> bool:
        # Do not synthesize start.mkv anymore.  Native Android TV HLS is the
        # proven fast/compatible path once Direct Play fails.
        return self._reject_direct_play(
            state,
            client,
            entry,
            reason="%s-offset-%.3f" % (source, offset_seconds),
            correlation=correlation,
        )

    def _filtered_file(
        self,
        state: v3.V3State,
        client: socket.socket,
        entry: dict,
        headers: dict[str, str],
        range_start: int,
    ) -> bool:
        return self._reject_direct_play(
            state,
            client,
            entry,
            reason="byte-range-%s" % range_start,
            correlation="session-or-client-part",
        )

    def _forward_normal(
        self,
        state: v3.V3State,
        client: socket.socket,
        method: str,
        target: str,
        version: str,
        lines: list[bytes],
        body: bytes,
        upgrade: bool,
    ) -> None:
        # Catch the exact case that caused the 30-40 second startup delay in v4:
        # v3 had decided to PASS a no-Range file request because its timeline was
        # stale.  Eligibility does not depend on a fresh timeline, so reject that
        # Direct Play request immediately too.
        path = urlsplit(target).path
        match = base.FILE_RE.match(path)
        if method.upper() == "GET" and match:
            headers = policy._headers_dict(lines[1:])
            entry, correlation = state.lookup_file_fallback(
                self.client_address[0], headers, match.group(1)
            )
            if entry is not None:
                self._reject_direct_play(
                    state,
                    client,
                    entry,
                    reason="passthru-file-request",
                    correlation=correlation,
                )
                return

        super()._forward_normal(
            state, client, method, target, version, lines, body, upgrade
        )


class ThreadingV5Proxy(base.ThreadingHandoffProxy):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Censorarr fail-fast Direct Play -> native Plex HLS proof"
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
        default="/volume1/docker/censorarr-test/work/plex-filtered-handoff.log",
    )
    args = parser.parse_args()

    try:
        state = v3.V3State(args)
    except Exception as exc:
        print(f"ERROR: handoff preflight failed: {exc}")
        return 2

    try:
        server = ThreadingV5Proxy((args.listen_host, args.listen_port), V5Handler)
    except OSError as exc:
        print(f"ERROR: could not listen on {args.listen_host}:{args.listen_port}: {exc}")
        return 3

    server.state = state  # type: ignore[attr-defined]
    state.log(
        "START_V5 listen=%s:%s policy=%s:%s plex=%s:%s tls=plex:%s allowlist=%s directplay=reject-415 native_hls=yes"
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
        state.log("STOP_V5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
