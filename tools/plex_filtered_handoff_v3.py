#!/usr/bin/env python3
"""Third Shield Direct Play -> filtered Plex transcode handoff proof.

Fixes two gaps in v2:

* The Shield's first /library/parts/.../file.mkv request can arrive before its
  first /:/timeline update.  For a freshly cached eligible decision, v3 starts
  the filtered stream at 0 seconds instead of passing the original file through.
* Timeline positions are exact movie times, not source-file byte probes.  They
  now bypass the byte-range edge-probe logic entirely and are sent directly to
  Plex universal start.mkv.

File correlation first uses the Plex session id and then safely falls back to the
newest eligible client-IP + part-id decision.  This accommodates Shield requests
that omit or alter a session header while preserving media eligibility gating.

The Plex transcode request keeps directPlay=0, directStream=1,
directStreamAudio=0, copyts=1, protocol=* so compatible video remains COPY while
audio passes through the Censorarr transcoder shim.
"""
from __future__ import annotations

import argparse
import secrets
import socket
import ssl
import time
from urllib.parse import urlsplit

import plex_policy_proxy as policy
import plex_filtered_handoff as base
import plex_filtered_handoff_v2 as v2

DEFAULT_STARTUP_GRACE_SECONDS = 12.0


class V3State(v2.TimelineHandoffState):
    def __init__(self, args: argparse.Namespace):
        super().__init__(args)
        self.startup_grace_seconds = max(0.0, float(args.startup_grace_seconds))
        self.handoff_attempts_v3: dict[tuple[str, str], float] = {}

    def lookup_file_fallback(self, client_ip: str, headers: dict[str, str], part_id: str) -> tuple[dict | None, str]:
        entry = self.lookup_file(client_ip, headers, part_id)
        if entry is not None:
            return entry, "session"

        now = time.monotonic()
        best: dict | None = None
        best_created = -1.0
        with self.lock:
            for (cached_ip, _session_id), row in list(self.sessions.items()):
                if cached_ip != client_ip:
                    continue
                created = float(row.get("created") or 0)
                if now - created > base.CACHE_TTL_SECONDS:
                    continue
                if not row.get("eligible") or str(row.get("part_id")) != str(part_id):
                    continue
                if created > best_created:
                    best = dict(row)
                    best_created = created
        return best, "client-part" if best is not None else "none"

    def claim_handoff_v3(self, client_ip: str, part_id: str) -> bool:
        attempt_key = (client_ip, str(part_id))
        now = time.monotonic()
        with self.lock:
            prior = float(self.handoff_attempts_v3.get(attempt_key) or 0)
            if prior and now - prior < self.handoff_cooldown_seconds:
                return False
            self.handoff_attempts_v3[attempt_key] = now
        return True

    def startup_offset_seconds(self, entry: dict) -> float | None:
        created = float(entry.get("created") or 0)
        if created <= 0:
            return None
        if time.monotonic() - created <= self.startup_grace_seconds:
            return 0.0
        return None

    def filtered_start_target_v3(self, entry: dict, offset_seconds: float) -> str:
        target = self.filtered_start_target(entry, offset_seconds)
        return base._replace_query(target, {"session": secrets.token_hex(12)})


class V3Handler(base.HandoffHandler):
    def _filtered_exact_offset(
        self,
        state: V3State,
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
            out_headers: list[bytes] = []
            for key, value in headers.items():
                lower = key.casefold()
                if lower in {"host", "connection", "proxy-connection", "range", "accept-encoding", "content-length"}:
                    continue
                out_headers.append(f"{key}: {value}".encode("iso-8859-1", "replace"))
            out_headers.extend(
                [
                    f"Host: {state.plex_host}:{state.plex_port}".encode("ascii"),
                    b"Accept-Encoding: identity",
                    b"Connection: close",
                ]
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
                "FILE_FILTERED client=%s media=%s source=%s correlation=%s offset=%.3f mode=video-copy-audio-transcode"
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

    def handle(self) -> None:
        state: V3State = self.server.state  # type: ignore[attr-defined]
        raw_client = self.request
        raw_client.settimeout(60.0)
        client = raw_client
        transport = "http"
        path = ""
        try:
            try:
                first_byte = raw_client.recv(1, socket.MSG_PEEK)
            except OSError:
                first_byte = b""
            if first_byte == b"\x16":
                client = state.tls_context.wrap_socket(raw_client, server_side=True)
                client.settimeout(60.0)
                transport = "https"

            head, rest = policy._read_request(client)
            if not head:
                return
            lines = head.split(b"\r\n")
            request_line = lines[0].decode("iso-8859-1", "replace")
            try:
                method, target, version = request_line.split(" ", 2)
            except ValueError:
                return
            headers = policy._headers_dict(lines[1:])
            path = urlsplit(target).path
            upgrade = policy._header_value(headers, "Upgrade").casefold() == "websocket"

            content_length = 0
            raw_length = policy._header_value(headers, "Content-Length")
            if raw_length:
                try:
                    content_length = max(0, int(raw_length))
                except ValueError:
                    content_length = 0
            body = bytearray(rest)
            while len(body) < content_length:
                chunk = client.recv(min(65536, content_length - len(body)))
                if not chunk:
                    break
                body.extend(chunk)

            if policy._is_decision_path(path):
                state.remember_decision(self.client_address[0], target, headers)
            elif path.casefold() == v2.TIMELINE_PATH.casefold():
                state.remember_timeline(self.client_address[0], target, headers)

            match = base.FILE_RE.match(path)
            if method.upper() == "GET" and match:
                part_id = match.group(1)
                entry, correlation = state.lookup_file_fallback(self.client_address[0], headers, part_id)
                range_header = policy._header_value(headers, "Range")
                range_start = base._range_start(range_header)

                if entry is None:
                    state.log(
                        "FILE_BYPASS client=%s part=%s range=%s reason=no-eligible-session"
                        % (self.client_address[0], part_id, range_header or "none")
                    )
                elif range_start is not None:
                    # Keep the original byte-range proof behavior for explicit
                    # mid-file requests. Edge probes still pass through.
                    if state.claim_handoff_v3(self.client_address[0], part_id):
                        if self._filtered_file(state, client, entry, headers, range_start):
                            return
                    else:
                        state.log(
                            "FILE_BYPASS client=%s media=%s range=%s reason=cooldown"
                            % (self.client_address[0], entry.get("basename") or "-", range_header)
                        )
                else:
                    offset_seconds = state.timeline_offset_seconds(entry)
                    source = "timeline"
                    if offset_seconds is None:
                        offset_seconds = state.startup_offset_seconds(entry)
                        source = "startup"

                    if offset_seconds is None:
                        state.log(
                            "FILE_BYPASS client=%s media=%s range=none correlation=%s reason=no-fresh-timeline"
                            % (self.client_address[0], entry.get("basename") or "-", correlation)
                        )
                    elif not state.claim_handoff_v3(self.client_address[0], part_id):
                        state.log(
                            "FILE_BYPASS client=%s media=%s range=none source=%s offset=%.3f reason=cooldown"
                            % (self.client_address[0], entry.get("basename") or "-", source, offset_seconds)
                        )
                    else:
                        state.log(
                            "FILE_EXACT client=%s media=%s source=%s correlation=%s offset=%.3f"
                            % (
                                self.client_address[0],
                                entry.get("basename") or "-",
                                source,
                                correlation,
                                offset_seconds,
                            )
                        )
                        if self._filtered_exact_offset(
                            state,
                            client,
                            entry,
                            headers,
                            offset_seconds,
                            source,
                            correlation,
                        ):
                            return

            state.log(
                "PASS transport=%s client=%s method=%s path=%s"
                % (transport, self.client_address[0], method, path)
            )
            self._forward_normal(state, client, method, target, version, lines, bytes(body), upgrade)
        except (BrokenPipeError, ConnectionResetError):
            return
        except ssl.SSLEOFError:
            return
        except ssl.SSLError as exc:
            state.log(f"ERROR client={self.client_address[0]} TLS {exc}")
        except Exception as exc:
            state.log(f"ERROR client={self.client_address[0]} path={path or '-'} {type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Censorarr startup/timeline-aware Plex filtered handoff proof")
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
    parser.add_argument("--startup-grace-seconds", type=float, default=DEFAULT_STARTUP_GRACE_SECONDS)
    parser.add_argument("--plex-appdata")
    parser.add_argument("--log", default="/volume1/docker/censorarr-test/work/plex-filtered-handoff.log")
    args = parser.parse_args()

    try:
        state = V3State(args)
    except Exception as exc:
        print(f"ERROR: handoff preflight failed: {exc}", file=sys.stderr)
        return 2

    try:
        server = base.ThreadingHandoffProxy((args.listen_host, args.listen_port), V3Handler)
    except OSError as exc:
        print(f"ERROR: could not listen on {args.listen_host}:{args.listen_port}: {exc}", file=sys.stderr)
        return 3
    server.state = state  # type: ignore[attr-defined]
    state.log(
        "START_V3 listen=%s:%s policy=%s:%s plex=%s:%s tls=plex:%s allowlist=%s timeline_ttl=%.1fs cooldown=%.1fs startup_grace=%.1fs"
        % (
            args.listen_host,
            args.listen_port,
            args.policy_host,
            args.policy_port,
            args.plex_host,
            args.plex_port,
            state.tls_p12.name,
            args.allowlist,
            state.timeline_ttl_seconds,
            state.handoff_cooldown_seconds,
            state.startup_grace_seconds,
        )
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        state.log("STOP_V3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
