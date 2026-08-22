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
Plex Transcoder shim for profanity muting.

For selected text subtitles, Plex Android TV may request burn-in even though
Plex creates temp-0.srt. The policy proxy prevents the burn. This gateway then
adds a WebVTT subtitle rendition to the HLS master playlist and serves segmented
WebVTT converted on demand from Plex's active temp-0.srt. The subtitle media
playlist mirrors Plex's video HLS segment cadence and EXT-X-START offset so the
Shield/ExoPlayer timeline stays aligned. Image/advanced subtitles are left
alone.
"""
from __future__ import annotations

import argparse
import http.client
import math
import re
import socket
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlsplit

import plex_policy_proxy as policy
import plex_filtered_handoff as base
import plex_filtered_handoff_v2 as v2
import plex_filtered_handoff_v3 as v3
import plex_filtered_handoff_v5 as validated


_SUBTITLE_PATH_RE = re.compile(
    r"^/censorarr/subtitles/([^/]+)/(index\.m3u8|segment-(\d+)\.vtt)$", re.I
)
_SRT_TIME_RE = re.compile(
    r"^(\d{1,3}:\d{2}:\d{2}),(\d{3})\s+-->\s+"
    r"(\d{1,3}:\d{2}:\d{2}),(\d{3})(.*)$"
)
_SUBTITLE_SEGMENT_SECONDS = 10.0
_START_OFFSET_RE = re.compile(r"TIME-OFFSET=(-?\d+(?:\.\d+)?)", re.I)


def _query_values(target: str) -> dict[str, str]:
    return {
        str(key).casefold(): str(value)
        for key, value in parse_qsl(urlsplit(target).query, keep_blank_values=True)
    }


def _is_text_subtitle_master(target: str) -> bool:
    parts = urlsplit(target)
    if parts.path.casefold() != (policy.UNIVERSAL_PREFIX + "start.m3u8").casefold():
        return False
    values = _query_values(target)
    return (
        values.get("advancedsubtitles", "").casefold() == "text"
        and values.get("subtitles", "").casefold() == "burn"
        and bool(values.get("session", "").strip())
    )


def _send_response(
    client: socket.socket,
    status: int,
    reason: str,
    headers: list[tuple[str, str]],
    payload: bytes,
) -> None:
    rows = [f"HTTP/1.1 {status} {reason}".encode("iso-8859-1", "replace")]
    blocked = {
        "content-length",
        "transfer-encoding",
        "connection",
        "content-encoding",
    }
    saw_type = False
    for key, value in headers:
        lower = str(key).casefold()
        if lower in blocked:
            continue
        if lower == "content-type":
            saw_type = True
        rows.append(f"{key}: {value}".encode("iso-8859-1", "replace"))
    if not saw_type:
        rows.append(b"Content-Type: application/octet-stream")
    rows.append(f"Content-Length: {len(payload)}".encode("ascii"))
    rows.append(b"Connection: close")
    client.sendall(b"\r\n".join(rows) + b"\r\n\r\n" + payload)


def _send_simple(
    client: socket.socket,
    status: int,
    reason: str,
    content_type: str,
    payload: bytes,
) -> None:
    _send_response(
        client,
        status,
        reason,
        [
            ("Content-Type", content_type),
            ("Cache-Control", "no-store"),
        ],
        payload,
    )


def _active_srt(state: v3.V3State, client_id: str) -> Path | None:
    root = getattr(state, "subtitle_sessions_root", None)
    if not isinstance(root, Path) or not root.is_dir():
        return None
    prefix = f"plex-transcode-{client_id}-"
    found: list[tuple[float, Path]] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return None
    for child in children:
        if not child.is_dir() or not child.name.startswith(prefix):
            continue
        srt = child / "temp-0.srt"
        try:
            if srt.is_file() and srt.stat().st_size > 0:
                stat = srt.stat()
                found.append((stat.st_mtime, srt))
        except OSError:
            continue
    if not found:
        return None
    found.sort(key=lambda row: row[0], reverse=True)
    return found[0][1]


def _hms_seconds(value: str, millis: str) -> float:
    hours, minutes, seconds = [int(piece) for piece in value.split(":", 2)]
    return hours * 3600.0 + minutes * 60.0 + seconds + int(millis) / 1000.0


def _parse_srt(raw: str) -> tuple[list[tuple[float, float, str]], float]:
    text = str(raw or "").lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[tuple[float, float, str]] = []
    max_end = 1.0

    for block in re.split(r"\n{2,}", text.strip()):
        lines = block.splitlines()
        timing_index = -1
        timing_match = None
        for idx, line in enumerate(lines):
            match = _SRT_TIME_RE.match(line.strip())
            if match:
                timing_index = idx
                timing_match = match
                break
        if timing_match is None:
            continue

        try:
            start = _hms_seconds(timing_match.group(1), timing_match.group(2))
            end = _hms_seconds(timing_match.group(3), timing_match.group(4))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue

        lines[timing_index] = (
            f"{timing_match.group(1)}.{timing_match.group(2)} --> "
            f"{timing_match.group(3)}.{timing_match.group(4)}{timing_match.group(5)}"
        )
        cue = "\n".join(lines).strip()
        cues.append((start, end, cue))
        max_end = max(max_end, end)

    return cues, max_end


def _video_playlist_timing(
    state: v3.V3State,
    client_id: str,
) -> tuple[float | None, int, float]:
    token = str(getattr(state, "plex_token", "") or "").strip()
    if not token:
        return None, 0, _SUBTITLE_SEGMENT_SECONDS

    target = (
        f"/video/:/transcode/universal/session/{quote(client_id, safe='')}/base/index.m3u8"
        f"?X-Plex-Token={quote(token, safe='')}"
    )
    conn = http.client.HTTPConnection(state.plex_host, state.plex_port, timeout=5.0)
    try:
        conn.request(
            "GET",
            target,
            headers={
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        resp = conn.getresponse()
        payload = resp.read()
        if int(resp.status) != 200:
            return None, 0, _SUBTITLE_SEGMENT_SECONDS
    except Exception:
        return None, 0, _SUBTITLE_SEGMENT_SECONDS
    finally:
        conn.close()

    text = payload.decode("utf-8", "replace")
    start_offset: float | None = None
    media_sequence = 0
    segment_seconds = _SUBTITLE_SEGMENT_SECONDS

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXT-X-START:"):
            match = _START_OFFSET_RE.search(line)
            if match:
                try:
                    start_offset = float(match.group(1))
                except ValueError:
                    pass
        elif line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                media_sequence = max(0, int(line.split(":", 1)[1].strip()))
            except (IndexError, ValueError):
                pass
        elif line.startswith("#EXTINF:"):
            try:
                value = line.split(":", 1)[1].split(",", 1)[0].strip()
                parsed = float(value)
                if parsed > 0:
                    segment_seconds = parsed
                    break
            except (IndexError, ValueError):
                pass

    return start_offset, media_sequence, segment_seconds


def _subtitle_playlist(
    duration: float,
    start_offset: float | None,
    media_sequence: int,
    segment_seconds: float,
) -> bytes:
    length = max(1.0, float(duration))
    segment = max(0.001, float(segment_seconds or _SUBTITLE_SEGMENT_SECONDS))
    count = max(1, int(math.ceil(length / segment)))
    first = min(max(0, int(media_sequence)), count - 1)
    rows = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        f"#EXT-X-TARGETDURATION:{int(math.ceil(segment))}",
    ]
    if start_offset is not None:
        rows.append(f"#EXT-X-START:TIME-OFFSET={float(start_offset):.6f}")
    rows.extend(
        [
            "#EXT-X-ALLOW-CACHE:NO",
            f"#EXT-X-MEDIA-SEQUENCE:{first}",
            "#EXT-X-PLAYLIST-TYPE:VOD",
        ]
    )
    for index in range(first, count):
        start = index * segment
        seg_length = min(segment, max(0.001, length - start))
        rows.append(f"#EXTINF:{seg_length:.3f},")
        rows.append(f"segment-{index:05d}.vtt")
    rows.append("#EXT-X-ENDLIST")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _subtitle_segment(
    cues: list[tuple[float, float, str]],
    index: int,
    segment_seconds: float,
) -> bytes:
    segment = max(0.001, float(segment_seconds or _SUBTITLE_SEGMENT_SECONDS))
    start = max(0.0, float(index) * segment)
    end = start + segment
    selected = [cue for cue_start, cue_end, cue in cues if cue_start < end and cue_end > start]
    rows = [
        "WEBVTT",
        "X-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0",
        "",
    ]
    if selected:
        rows.append("\n\n".join(selected))
        rows.append("")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _inject_subtitle_master(payload: bytes, client_id: str) -> tuple[bytes, bool]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload, False
    if not text.startswith("#EXTM3U"):
        return payload, False
    if "#EXT-X-MEDIA:TYPE=SUBTITLES" in text:
        return payload, False

    group = "censorarr-text"
    uri = f"/censorarr/subtitles/{quote(client_id, safe='')}/index.m3u8"
    media = (
        '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="%s",NAME="English",'
        'LANGUAGE="en",AUTOSELECT=YES,DEFAULT=YES,FORCED=NO,URI="%s"'
        % (group, uri)
    )

    rows = text.splitlines()
    out: list[str] = []
    inserted_media = False
    changed_variant = False
    for row in rows:
        out.append(row)
        if not inserted_media and row.strip() == "#EXTM3U":
            out.append(media)
            inserted_media = True
            continue
        if row.startswith("#EXT-X-STREAM-INF:") and "SUBTITLES=" not in row:
            out[-1] = row + f',SUBTITLES="{group}"'
            changed_variant = True

    if not inserted_media or not changed_variant:
        return payload, False
    return ("\n".join(out) + "\n").encode("utf-8"), True


class GatewayHandler(validated.V5Handler):
    def _serve_subtitle_path(
        self,
        state: v3.V3State,
        client: socket.socket,
        path: str,
    ) -> bool:
        match = _SUBTITLE_PATH_RE.match(path)
        if not match:
            return False

        client_id = unquote(match.group(1)).strip()
        leaf = match.group(2).casefold()
        segment_index = match.group(3)
        srt = _active_srt(state, client_id)
        if srt is None:
            state.log(
                "SUBTITLE_MISS client=%s session=%s path=%s status=404"
                % (self.client_address[0], client_id or "-", leaf)
            )
            _send_simple(client, 404, "Not Found", "text/plain; charset=utf-8", b"")
            return True

        try:
            raw = srt.read_text(encoding="utf-8", errors="replace")
            cues, duration = _parse_srt(raw)
        except OSError as exc:
            state.log(
                "SUBTITLE_READ_FAIL client=%s session=%s error=%s"
                % (self.client_address[0], client_id or "-", exc)
            )
            _send_simple(
                client,
                500,
                "Internal Server Error",
                "text/plain; charset=utf-8",
                b"",
            )
            return True

        if leaf == "index.m3u8":
            start_offset, media_sequence, segment_seconds = _video_playlist_timing(
                state,
                client_id,
            )
            with state.lock:
                state.subtitle_timing[client_id] = (
                    start_offset,
                    media_sequence,
                    segment_seconds,
                )
            payload = _subtitle_playlist(
                duration,
                start_offset,
                media_sequence,
                segment_seconds,
            )
            state.log(
                "SUBTITLE_PLAYLIST client=%s session=%s source=%s cues=%s bytes=%s start=%s media_sequence=%s segment=%.3f"
                % (
                    self.client_address[0],
                    client_id,
                    srt.name,
                    len(cues),
                    len(payload),
                    "-" if start_offset is None else f"{start_offset:.3f}",
                    media_sequence,
                    segment_seconds,
                )
            )
            _send_simple(
                client,
                200,
                "OK",
                "application/vnd.apple.mpegurl",
                payload,
            )
            return True

        try:
            index = int(segment_index or "-1")
        except ValueError:
            index = -1
        if index < 0:
            _send_simple(client, 404, "Not Found", "text/plain; charset=utf-8", b"")
            return True

        with state.lock:
            timing = state.subtitle_timing.get(client_id)
        segment_seconds = (
            float(timing[2])
            if timing is not None and len(timing) >= 3
            else _SUBTITLE_SEGMENT_SECONDS
        )
        payload = _subtitle_segment(cues, index, segment_seconds)
        state.log(
            "SUBTITLE_SEGMENT client=%s session=%s index=%s source=%s bytes=%s segment=%.3f"
            % (
                self.client_address[0],
                client_id,
                index,
                srt.name,
                len(payload),
                segment_seconds,
            )
        )
        _send_simple(
            client,
            200,
            "OK",
            "text/vtt; charset=utf-8",
            payload,
        )
        return True

    def _forward_text_subtitle_master(
        self,
        state: v3.V3State,
        client: socket.socket,
        method: str,
        target: str,
        lines: list[bytes],
        body: bytes,
    ) -> None:
        headers = policy._headers_dict(lines[1:])
        out: dict[str, str] = {}
        for key, value in headers.items():
            lower = key.casefold()
            if lower in {
                "host",
                "connection",
                "proxy-connection",
                "accept-encoding",
                "content-length",
            }:
                continue
            out[key] = value
        out["Host"] = f"{state.policy_host}:{state.policy_port}"
        out["Accept-Encoding"] = "identity"
        out["Connection"] = "close"

        conn = http.client.HTTPConnection(
            state.policy_host,
            state.policy_port,
            timeout=60.0,
        )
        try:
            conn.request(method, target, body=body or None, headers=out)
            resp = conn.getresponse()
            payload = resp.read()
            response_headers = [(str(k), str(v)) for k, v in resp.getheaders()]
            reason = str(resp.reason or "OK")
            status = int(resp.status)

            values = _query_values(target)
            client_id = values.get("session", "").strip()
            changed = False
            if status == 200 and client_id:
                payload, changed = _inject_subtitle_master(payload, client_id)
            if changed:
                state.log(
                    "SUBTITLE_MASTER_INJECT client=%s session=%s mode=webvtt-segmented-aligned"
                    % (self.client_address[0], client_id)
                )
            else:
                state.log(
                    "SUBTITLE_MASTER_PASS client=%s session=%s status=%s"
                    % (self.client_address[0], client_id or "-", status)
                )
            _send_response(client, status, reason, response_headers, payload)
        finally:
            conn.close()

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
        path = urlsplit(target).path
        if method.upper() == "GET" and self._serve_subtitle_path(state, client, path):
            return
        if (
            method.upper() == "GET"
            and not upgrade
            and _is_text_subtitle_master(target)
        ):
            self._forward_text_subtitle_master(
                state,
                client,
                method,
                target,
                lines,
                body,
            )
            return
        super()._forward_normal(
            state,
            client,
            method,
            target,
            version,
            lines,
            body,
            upgrade,
        )


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
        appdata = policy._find_plex_appdata(args.plex_appdata)
        state.subtitle_sessions_root = appdata / "Cache" / "Transcode" / "Sessions"
        state.subtitle_timing = {}
        try:
            root = ET.parse(str(appdata / "Preferences.xml")).getroot()
            state.plex_token = str(root.attrib.get("PlexOnlineToken") or "").strip()
        except Exception:
            state.plex_token = ""
    except Exception as exc:
        print(f"ERROR: gateway preflight failed: {exc}", file=sys.stderr)
        return 2

    try:
        server = base.ThreadingHandoffProxy((args.listen_host, args.listen_port), GatewayHandler)
    except OSError as exc:
        print(f"ERROR: could not listen on {args.listen_host}:{args.listen_port}: {exc}", file=sys.stderr)
        return 3

    server.state = state  # type: ignore[attr-defined]
    state.log(
        "START_GATEWAY listen=%s:%s policy=%s:%s plex=%s:%s tls=plex:%s allowlist=%s "
        "directplay=reject-415 native_hls=yes video=copy audio=transcode text_subtitles=webvtt-aligned"
        % (
            args.listen_host,
            args.listen_port,
            args.policy_host,
            args.policy_port,
            state.plex_host,
            state.plex_port,
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