#!/usr/bin/env python3
"""Fourth Shield Direct Play -> filtered Plex transcode handoff proof.

V4 keeps the working v3 startup/timeline correlation, but changes the internal
Plex universal start.mkv request to match the successful manual proof more
closely.  In particular, it does not forward Android TV client/profile headers
from the original /library/parts/... request into the internal transcode start.

The URL still carries the original Plex client parameters and token, while the
internal HTTP request uses only minimal transport/auth headers.  This avoids
X-Plex-Client-Profile-Extra and related request headers causing Plex to choose a
full HEVC -> H264 video transcode when the decision itself supports HEVC COPY +
audio TRANSCODE.
"""
from __future__ import annotations

import argparse
import socket
import ssl

import plex_policy_proxy as policy
import plex_filtered_handoff as base
import plex_filtered_handoff_v2 as v2
import plex_filtered_handoff_v3 as v3


class V4Handler(v3.V3Handler):
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
        target = state.filtered_start_target_v3(entry, offset_seconds)
        upstream = socket.create_connection((state.plex_host, state.plex_port), timeout=15.0)
        upstream.settimeout(60.0)
        try:
            # Match the successful manual proof: do not forward the Shield's
            # client-profile/request headers into Plex's internal start.mkv call.
            # The original decision query already contains Plex client metadata.
            token = policy._token_from_request(str(entry.get("decision_target") or ""), headers).strip()
            out_headers = [
                f"Host: {state.plex_host}:{state.plex_port}".encode("ascii"),
                b"Accept: */*",
                b"Accept-Encoding: identity",
                b"Connection: close",
            ]
            if token and "x-plex-token=" not in target.casefold():
                out_headers.append(f"X-Plex-Token: {token}".encode("iso-8859-1", "replace"))

            state.log(
                "START_MINIMAL client=%s media=%s source=%s correlation=%s offset=%.3f headers=minimal"
                % (
                    self.client_address[0],
                    entry.get("basename") or "-",
                    source,
                    correlation,
                    offset_seconds,
                )
            )

            first = f"GET {target} HTTP/1.1\r\n".encode("iso-8859-1")
            upstream.sendall(first + b"\r\n".join(out_headers) + b"\r\n\r\n")

            response_head, response_rest = base._read_response_head(upstream)
            status_line = response_head.split(b"\r\n", 1)[0].decode("iso-8859-1", "replace") if response_head else ""
            if " 200 " not in f" {status_line} ":
                state.log(
                    "FILE_HANDOFF_FAIL client=%s media=%s source=%s offset=%.3f status=%r action=passthru"
                    % (self.client_address[0], entry.get("basename") or "-", source, offset_seconds, status_line)
                )
                return False

            state.log(
                "FILE_FILTERED client=%s media=%s source=%s correlation=%s offset=%.3f mode=video-copy-audio-transcode headers=minimal"
                % (
                    self.client_address[0],
                    entry.get("basename") or "-",
                    source,
                    correlation,
                    offset_seconds,
                )
            )
            client.sendall(response_head + b"\r\n\r\n" + response_rest)
            while True:
                chunk = upstream.recv(65536)
                if not chunk:
                    break
                client.sendall(chunk)
            return True
        except (BrokenPipeError, ConnectionResetError):
            return True
        finally:
            try:
                upstream.close()
            except OSError:
                pass


class ThreadingV4Proxy(base.ThreadingHandoffProxy):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Censorarr minimal-header Plex filtered handoff proof")
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
    parser.add_argument("--log", default="/volume1/docker/censorarr-test/work/plex-filtered-handoff.log")
    args = parser.parse_args()

    try:
        state = v3.V3State(args)
    except Exception as exc:
        print(f"ERROR: handoff preflight failed: {exc}")
        return 2

    try:
        server = ThreadingV4Proxy((args.listen_host, args.listen_port), V4Handler)
    except OSError as exc:
        print(f"ERROR: could not listen on {args.listen_host}:{args.listen_port}: {exc}")
        return 3
    server.state = state  # type: ignore[attr-defined]
    state.log(
        "START_V4 listen=%s:%s policy=%s:%s plex=%s:%s tls=plex:%s allowlist=%s headers=minimal"
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
        state.log("STOP_V4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
