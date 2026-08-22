#!/usr/bin/env python3
"""Timeline-aware Shield Direct Play -> filtered Plex transcode handoff proof.

This is the second experimental handoff layer.  It builds on
plex_filtered_handoff.py, but handles the NVIDIA Shield behavior where the player
reopens /library/parts/.../file.mkv without a Range header after a seek.

The proxy remembers the most recent /:/timeline movie position for the Plex
session.  When an allowlisted Direct Play file request arrives without a byte
range, that timeline position is converted to a synthetic source-file offset and
fed through the existing handoff logic.  Plex then starts universal start.mkv with:

  directPlay=0
  directStream=1
  directStreamAudio=0
  copyts=1
  protocol=*

On compatible media this keeps video on COPY while audio is transcoded through
the Censorarr Plex Transcoder shim.

This remains an experimental proof.  It is fail-open and rate-limits handoff
attempts so a client retry loop cannot rapidly spawn many transcoders.
"""
from __future__ import annotations

import argparse
import socket
import ssl
import time
from urllib.parse import parse_qsl, urlsplit

import plex_policy_proxy as policy
import plex_filtered_handoff as base

TIMELINE_PATH = "/:/timeline"
DEFAULT_TIMELINE_TTL_SECONDS = 30.0
DEFAULT_HANDOFF_COOLDOWN_SECONDS = 5.0


def _query_map(target: str) -> dict[str, str]:
    return {
        str(key).casefold(): str(value)
        for key, value in parse_qsl(urlsplit(target).query, keep_blank_values=True)
    }


class TimelineHandoffState(base.HandoffState):
    def __init__(self, args: argparse.Namespace):
        super().__init__(args)
        self.timeline_ttl_seconds = max(1.0, float(args.timeline_ttl_seconds))
        self.handoff_cooldown_seconds = max(0.0, float(args.handoff_cooldown_seconds))
        self.handoff_attempts: dict[tuple[str, str, str], float] = {}

    def remember_timeline(self, client_ip: str, target: str, headers: dict[str, str]) -> None:
        key = self._key(client_ip, headers)
        if key is None:
            return
        query = _query_map(target)
        raw_time = str(query.get("time") or "").strip()
        if not raw_time:
            return
        try:
            time_ms = max(0, int(float(raw_time)))
        except ValueError:
            return

        rating_key = str(query.get("ratingkey") or "").strip()
        playback_state = str(query.get("state") or "").strip().casefold()
        now = time.monotonic()
        updated = False
        media_name = "-"

        with self.lock:
            entry = self.sessions.get(key)
            if not entry:
                return
            if now - float(entry.get("created") or 0) > base.CACHE_TTL_SECONDS:
                self.sessions.pop(key, None)
                return

            decision_target = str(entry.get("decision_target") or "")
            metadata_path = base._query_value(decision_target, "path").strip()
            expected_rating = metadata_path.rstrip("/").rsplit("/", 1)[-1] if metadata_path else ""
            if rating_key and expected_rating and rating_key != expected_rating:
                return

            entry["timeline_ms"] = time_ms
            entry["timeline_seen"] = now
            entry["timeline_state"] = playback_state
            media_name = str(entry.get("basename") or "-")
            updated = True

        if updated:
            self.log(
                "TIMELINE_CACHE client=%s session=%s media=%s time_ms=%s state=%s"
                % (client_ip, key[1], media_name, time_ms, playback_state or "-")
            )

    def timeline_offset_seconds(self, entry: dict) -> float | None:
        try:
            seen = float(entry.get("timeline_seen") or 0)
            time_ms = int(entry.get("timeline_ms"))
        except (TypeError, ValueError):
            return None
        if seen <= 0 or time.monotonic() - seen > self.timeline_ttl_seconds:
            return None
        if time_ms < 0:
            return None
        duration_ms = int(entry.get("duration_ms") or 0)
        if duration_ms > 0:
            time_ms = min(time_ms, max(0, duration_ms - 1))
        return float(time_ms) / 1000.0

    def claim_handoff(self, client_ip: str, headers: dict[str, str], part_id: str) -> bool:
        key = self._key(client_ip, headers)
        if key is None:
            return False
        attempt_key = (key[0], key[1], str(part_id))
        now = time.monotonic()
        with self.lock:
            prior = float(self.handoff_attempts.get(attempt_key) or 0)
            if prior and now - prior < self.handoff_cooldown_seconds:
                return False
            self.handoff_attempts[attempt_key] = now
        return True


class TimelineHandoffHandler(base.HandoffHandler):
    def handle(self) -> None:
        state: TimelineHandoffState = self.server.state  # type: ignore[attr-defined]
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
            elif path.casefold() == TIMELINE_PATH.casefold():
                state.remember_timeline(self.client_address[0], target, headers)

            match = base.FILE_RE.match(path)
            if method.upper() == "GET" and match:
                part_id = match.group(1)
                entry = state.lookup_file(self.client_address[0], headers, part_id)
                range_header = policy._header_value(headers, "Range")
                range_start = base._range_start(range_header)

                if entry is None:
                    state.log(
                        "FILE_BYPASS client=%s part=%s range=%s reason=no-eligible-session"
                        % (self.client_address[0], part_id, range_header or "none")
                    )
                elif range_start is not None:
                    if state.claim_handoff(self.client_address[0], headers, part_id):
                        if self._filtered_file(state, client, entry, headers, range_start):
                            return
                    else:
                        state.log(
                            "FILE_BYPASS client=%s media=%s range=%s reason=cooldown"
                            % (self.client_address[0], entry.get("basename") or "-", range_header)
                        )
                else:
                    timeline_seconds = state.timeline_offset_seconds(entry)
                    if timeline_seconds is None:
                        state.log(
                            "FILE_BYPASS client=%s media=%s range=none reason=no-fresh-timeline"
                            % (self.client_address[0], entry.get("basename") or "-")
                        )
                    elif not state.claim_handoff(self.client_address[0], headers, part_id):
                        state.log(
                            "FILE_BYPASS client=%s media=%s range=none timeline=%.3f reason=cooldown"
                            % (self.client_address[0], entry.get("basename") or "-", timeline_seconds)
                        )
                    else:
                        size = int(entry.get("size") or 0)
                        duration_ms = int(entry.get("duration_ms") or 0)
                        synthetic_start = 0
                        if size > 0 and duration_ms > 0:
                            synthetic_start = int(
                                float(size) * min(1.0, max(0.0, timeline_seconds / (duration_ms / 1000.0)))
                            )
                        state.log(
                            "FILE_TIMELINE client=%s media=%s time=%.3f synthetic_range=%s"
                            % (
                                self.client_address[0],
                                entry.get("basename") or "-",
                                timeline_seconds,
                                synthetic_start,
                            )
                        )
                        if self._filtered_file(state, client, entry, headers, synthetic_start):
                            return

            state.log(
                "PASS transport=%s client=%s method=%s path=%s"
                % (transport, self.client_address[0], method, path)
            )
            self._forward_normal(state, client, method, target, version, lines, bytes(body), upgrade)
        except (BrokenPipeError, ConnectionResetError):
            # Android TV aggressively abandons probe/retry connections.  This is
            # expected during playback and is not a proxy failure by itself.
            return
        except ssl.SSLEOFError:
            return
        except ssl.SSLError as exc:
            state.log(f"ERROR client={self.client_address[0]} TLS {exc}")
        except Exception as exc:
            state.log(f"ERROR client={self.client_address[0]} path={path or '-'} {type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Censorarr timeline-aware Plex filtered file handoff proof")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=32403)
    parser.add_argument("--policy-host", default="127.0.0.1")
    parser.add_argument("--policy-port", type=int, default=32402)
    parser.add_argument("--plex-host", default="127.0.0.1")
    parser.add_argument("--plex-port", type=int, default=32400)
    parser.add_argument("--allowlist", default=base.DEFAULT_ALLOWLIST)
    parser.add_argument("--probe-edge-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--timeline-ttl-seconds", type=float, default=DEFAULT_TIMELINE_TTL_SECONDS)
    parser.add_argument("--handoff-cooldown-seconds", type=float, default=DEFAULT_HANDOFF_COOLDOWN_SECONDS)
    parser.add_argument("--plex-appdata")
    parser.add_argument("--log", default="/volume1/docker/censorarr-test/work/plex-filtered-handoff.log")
    args = parser.parse_args()

    try:
        state = TimelineHandoffState(args)
    except Exception as exc:
        print(f"ERROR: handoff preflight failed: {exc}", file=sys.stderr)
        return 2

    try:
        server = base.ThreadingHandoffProxy((args.listen_host, args.listen_port), TimelineHandoffHandler)
    except OSError as exc:
        print(f"ERROR: could not listen on {args.listen_host}:{args.listen_port}: {exc}", file=sys.stderr)
        return 3
    server.state = state  # type: ignore[attr-defined]
    state.log(
        "START_V2 listen=%s:%s policy=%s:%s plex=%s:%s tls=plex:%s allowlist=%s timeline_ttl=%.1fs cooldown=%.1fs"
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
        )
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        state.log("STOP_V2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
