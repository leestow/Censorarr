#!/usr/bin/env python3
"""Experimental Censorarr gateway: use MKV handoff for selected text subtitles.

Normal filtered playback keeps the validated v5 behavior: fail Direct Play fast
and let Plex Android TV fall back to native HLS, with video COPY and audio
TRANSCODE through the Censorarr shim.

When the cached playback decision has a selected text subtitle, this proof keeps
the older validated start.mkv handoff instead. The start.mkv request forces
subtitles=embedded while preserving directPlay=0, directStream=1,
directStreamAudio=0, and copyts=1. The goal is a single Matroska stream with
video COPY + filtered audio + an embedded SRT track for the Shield to render.
"""
from __future__ import annotations

import argparse
import socket
import sys
from urllib.parse import parse_qsl, urlsplit

import plex_policy_proxy as policy
import plex_filtered_handoff as base
import plex_filtered_handoff_v2 as v2
import plex_filtered_handoff_v3 as v3
import plex_filtered_handoff_v4 as v4
import plex_filtered_handoff_v5 as v5


def _query_values(target: str) -> dict[str, str]:
    return {
        str(key).casefold(): str(value)
        for key, value in parse_qsl(urlsplit(str(target or "")).query, keep_blank_values=True)
    }


def _text_subtitles(entry: dict) -> bool:
    values = _query_values(str(entry.get("decision_target") or ""))
    advanced = values.get("advancedsubtitles", "").casefold()
    subtitles = values.get("subtitles", "").casefold()
    return advanced == "text" and subtitles not in {"", "none", "0", "false", "off"}


class MkvSubtitleState(v3.V3State):
    def filtered_start_target_v3(self, entry: dict, offset_seconds: float) -> str:
        target = super().filtered_start_target_v3(entry, offset_seconds)
        if _text_subtitles(entry):
            target = base._replace_query(
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
        return target


class MkvSubtitleHandler(v5.V5Handler):
    def _filtered_exact_offset(
        self,
        state: MkvSubtitleState,
        client: socket.socket,
        entry: dict,
        headers: dict[str, str],
        offset_seconds: float,
        source: str,
        correlation: str,
    ) -> bool:
        if _text_subtitles(entry):
            state.log(
                "TEXT_SUBTITLE_MKV_HANDOFF client=%s media=%s source=%s correlation=%s offset=%.3f subtitles=embedded"
                % (
                    self.client_address[0],
                    entry.get("basename") or "-",
                    source,
                    correlation,
                    offset_seconds,
                )
            )
            return v4.V4Handler._filtered_exact_offset(
                self,
                state,
                client,
                entry,
                headers,
                offset_seconds,
                source,
                correlation,
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

    def _filtered_file(
        self,
        state: MkvSubtitleState,
        client: socket.socket,
        entry: dict,
        headers: dict[str, str],
        range_start: int,
    ) -> bool:
        if _text_subtitles(entry):
            try:
                size = max(1, int(entry.get("size") or 1))
                duration_ms = max(1, int(entry.get("duration_ms") or 1))
                offset_seconds = (float(range_start) / float(size)) * (float(duration_ms) / 1000.0)
            except (TypeError, ValueError, ZeroDivisionError):
                offset_seconds = 0.0
            return self._filtered_exact_offset(
                state,
                client,
                entry,
                headers,
                max(0.0, offset_seconds),
                "byte-range-mkv",
                "session-or-client-part",
            )
        return super()._filtered_file(state, client, entry, headers, range_start)

    def _forward_normal(
        self,
        state: MkvSubtitleState,
        client: socket.socket,
        method: str,
        target: str,
        version: str,
        lines: list[bytes],
        body: bytes,
        upgrade: bool,
    ) -> None:
        # V5 normally catches a late/stale Direct Play file request here and
        # rejects it with 415. For text subtitles, prefer the MKV handoff even
        # when the timeline was not fresh enough for V3's first pass.
        path = urlsplit(target).path
        match = base.FILE_RE.match(path)
        if method.upper() == "GET" and match:
            headers = policy._headers_dict(lines[1:])
            entry, correlation = state.lookup_file_fallback(
                self.client_address[0], headers, match.group(1)
            )
            if entry is not None and _text_subtitles(entry):
                offset = state.timeline_offset_seconds(entry)
                source = "timeline-late"
                if offset is None:
                    offset = state.startup_offset_seconds(entry)
                    source = "startup-late"
                if offset is None:
                    offset = 0.0
                    source = "fallback-zero"
                if self._filtered_exact_offset(
                    state,
                    client,
                    entry,
                    headers,
                    max(0.0, float(offset)),
                    source,
                    correlation,
                ):
                    return

        super()._forward_normal(
            state, client, method, target, version, lines, body, upgrade
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Censorarr MKV embedded-text-subtitle gateway proof"
    )
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
        state = MkvSubtitleState(args)
    except Exception as exc:
        print(f"ERROR: gateway preflight failed: {exc}", file=sys.stderr)
        return 2

    try:
        server = base.ThreadingHandoffProxy(
            (args.listen_host, args.listen_port), MkvSubtitleHandler
        )
    except OSError as exc:
        print(f"ERROR: could not listen on {args.listen_host}:{args.listen_port}: {exc}", file=sys.stderr)
        return 3

    server.state = state  # type: ignore[attr-defined]
    state.log(
        "START_GATEWAY_MKV_SUBS listen=%s:%s policy=%s:%s plex=%s:%s tls=plex:%s allowlist=%s normal=native-hls text_subtitles=start-mkv-embedded video=copy audio=transcode"
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
        state.log("STOP_GATEWAY_MKV_SUBS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
