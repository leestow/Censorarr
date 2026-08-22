#!/usr/bin/env python3
"""Experimental Shield Direct Play -> filtered Plex transcode handoff.

This proxy sits in front of plex_policy_proxy.py during development. It terminates
Plex HTTPS using the same Plex certificate helper, forwards ordinary requests to
the policy proxy, and watches filtered playback decisions so it can correlate a
later Direct Play /library/parts/.../file.mkv request with the selected media.

For an allowlisted mid-file byte-range request, it converts the source-file byte
offset to an approximate movie offset and substitutes Plex universal start.mkv
with:

  directPlay=0
  directStream=1
  directStreamAudio=0
  copyts=1
  protocol=*

That produces video COPY + audio TRANSCODE on compatible media, allowing the
Censorarr Plex Transcoder shim to inject audio mute filters without re-encoding
video.

Important: byte-range -> time conversion is intentionally an experimental proof.
Small beginning/end range probes are passed through unchanged. Any lookup or
handoff failure is fail-open to the normal policy proxy.
"""
from __future__ import annotations

import argparse
import os
import re
import socket
import socketserver
import ssl
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import plex_policy_proxy as policy

FILE_RE = re.compile(r"^/library/parts/(\d+)/[^/]+/file(?:\.[^/?]+)?$", re.I)
DEFAULT_ALLOWLIST = "/volume1/docker/censorarr-test/config/stream-filter-allowlist.txt"
CACHE_TTL_SECONDS = 15 * 60


def _query_value(target: str, name: str) -> str:
    wanted = name.casefold()
    for key, value in parse_qsl(urlsplit(target).query, keep_blank_values=True):
        if key.casefold() == wanted:
            return str(value)
    return ""


def _replace_query(target: str, values: dict[str, str]) -> str:
    parts = urlsplit(target)
    rows = [(str(k), str(v)) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    indexes = {k.casefold(): i for i, (k, _v) in enumerate(rows)}
    for key, value in values.items():
        idx = indexes.get(key.casefold())
        if idx is None:
            rows.append((key, str(value)))
            indexes[key.casefold()] = len(rows) - 1
        else:
            old_key, _old_value = rows[idx]
            rows[idx] = (old_key, str(value))
    return urlunsplit(("", "", parts.path, urlencode(rows, doseq=True), ""))


def _range_start(value: str) -> int | None:
    match = re.match(r"^bytes=(\d+)-", str(value or "").strip(), re.I)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _allowlist_names(path: Path) -> set[str]:
    try:
        rows = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return set()
    return {
        os.path.basename(row.strip()).casefold()
        for row in rows
        if row.strip() and not row.lstrip().startswith("#")
    }


def _selected(parent: ET.Element, tag: str) -> ET.Element | None:
    rows = parent.findall(f".//{tag}")
    for row in rows:
        if row.attrib.get("selected") == "1":
            return row
    return rows[0] if rows else None


def _int_attr(*pairs: tuple[ET.Element | None, str]) -> int:
    for elem, name in pairs:
        if elem is None:
            continue
        try:
            value = int(elem.attrib.get(name) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def _read_response_head(sock: socket.socket) -> tuple[bytes, bytes]:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(65536)
        if not chunk:
            return bytes(data), b""
        data.extend(chunk)
        if len(data) > policy.MAX_HEADER:
            raise RuntimeError("response headers too large")
    head, rest = bytes(data).split(b"\r\n\r\n", 1)
    return head, rest


class HandoffState:
    def __init__(self, args: argparse.Namespace):
        self.policy_host = args.policy_host
        self.policy_port = int(args.policy_port)
        self.plex_host = args.plex_host
        self.plex_port = int(args.plex_port)
        self.allowlist = Path(args.allowlist)
        self.probe_edge_bytes = max(0, int(args.probe_edge_bytes))
        self.log_path = Path(args.log) if args.log else None
        self.lock = threading.RLock()
        self.sessions: dict[tuple[str, str], dict] = {}

        appdata = policy._find_plex_appdata(args.plex_appdata)
        self.tls_context, self.tls_p12 = policy._build_plex_tls_context(appdata)

    def log(self, message: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"{stamp} {message}\n"
        with self.lock:
            sys.stdout.write(line)
            sys.stdout.flush()
            if self.log_path is not None:
                try:
                    self.log_path.parent.mkdir(parents=True, exist_ok=True)
                    with self.log_path.open("a", encoding="utf-8") as fh:
                        fh.write(line)
                except OSError:
                    pass

    def _key(self, client_ip: str, headers: dict[str, str]) -> tuple[str, str] | None:
        session_id = policy._header_value(headers, "X-Plex-Session-Id").strip()
        if not session_id:
            return None
        return client_ip, session_id

    def remember_decision(self, client_ip: str, target: str, headers: dict[str, str]) -> None:
        key = self._key(client_ip, headers)
        if key is None:
            return
        metadata_path = _query_value(target, "path").strip()
        token = policy._token_from_request(target, headers).strip()
        if not metadata_path.startswith("/library/metadata/") or not token:
            return

        try:
            separator = "&" if "?" in metadata_path else "?"
            url = (
                f"http://{self.plex_host}:{self.plex_port}{metadata_path}"
                f"{separator}{urlencode({'X-Plex-Token': token})}"
            )
            req = Request(url, headers={"Accept": "application/xml", "Accept-Encoding": "identity"})
            raw = urlopen(req, timeout=8).read()
            root = ET.fromstring(raw)
            video = root.find(".//Video")
            media = _selected(root, "Media")
            part = _selected(media if media is not None else root, "Part")
            if part is None:
                raise RuntimeError("metadata has no Part")

            part_id = str(part.attrib.get("id") or "").strip()
            file_path = str(part.attrib.get("file") or "").strip()
            basename = os.path.basename(file_path)
            size = _int_attr((part, "size"))
            if size <= 0 and file_path:
                try:
                    size = os.path.getsize(file_path)
                except OSError:
                    pass
            duration_ms = _int_attr(
                (part, "duration"),
                (media, "duration"),
                (video, "duration"),
            )
            eligible = bool(
                part_id
                and basename
                and size > 0
                and duration_ms > 0
                and basename.casefold() in _allowlist_names(self.allowlist)
            )
            entry = {
                "created": time.monotonic(),
                "decision_target": target,
                "part_id": part_id,
                "file": file_path,
                "basename": basename,
                "size": size,
                "duration_ms": duration_ms,
                "eligible": eligible,
            }
            with self.lock:
                self.sessions[key] = entry
            self.log(
                "DECISION_CACHE client=%s session=%s part=%s media=%s size=%s duration_ms=%s eligible=%s"
                % (client_ip, key[1], part_id or "-", basename or "-", size or "-", duration_ms or "-", "yes" if eligible else "no")
            )
        except Exception as exc:
            self.log(f"DECISION_CACHE_FAIL client={client_ip} {type(exc).__name__}: {exc}")

    def lookup_file(self, client_ip: str, headers: dict[str, str], part_id: str) -> dict | None:
        key = self._key(client_ip, headers)
        if key is None:
            return None
        with self.lock:
            entry = self.sessions.get(key)
            if entry and time.monotonic() - float(entry.get("created") or 0) > CACHE_TTL_SECONDS:
                self.sessions.pop(key, None)
                entry = None
            if not entry or not entry.get("eligible") or str(entry.get("part_id")) != str(part_id):
                return None
            return dict(entry)

    def filtered_start_target(self, entry: dict, offset_seconds: float) -> str:
        original = str(entry["decision_target"])
        parts = urlsplit(original)
        start_path = policy.UNIVERSAL_PREFIX + "start.mkv"
        base = urlunsplit(("", "", start_path, parts.query, ""))
        return _replace_query(
            base,
            {
                "directPlay": "0",
                "directStream": "1",
                "directStreamAudio": "0",
                "copyts": "1",
                "protocol": "*",
                "offset": f"{max(0.0, offset_seconds):.3f}",
            },
        )


class HandoffHandler(socketserver.BaseRequestHandler):
    def _forward_normal(
        self,
        state: HandoffState,
        client: socket.socket,
        method: str,
        target: str,
        version: str,
        lines: list[bytes],
        body: bytes,
        upgrade: bool,
    ) -> None:
        upstream = socket.create_connection((state.policy_host, state.policy_port), timeout=15.0)
        upstream.settimeout(60.0)
        try:
            out_headers: list[bytes] = []
            saw_host = False
            saw_connection = False
            for raw in lines[1:]:
                text = raw.decode("iso-8859-1", "replace")
                if ":" not in text:
                    continue
                key, _value = text.split(":", 1)
                lower = key.strip().casefold()
                if lower == "proxy-connection":
                    continue
                if lower == "host":
                    out_headers.append(f"Host: {state.policy_host}:{state.policy_port}".encode("iso-8859-1"))
                    saw_host = True
                    continue
                if lower == "connection" and not upgrade:
                    out_headers.append(b"Connection: close")
                    saw_connection = True
                    continue
                out_headers.append(raw)
            if not saw_host:
                out_headers.append(f"Host: {state.policy_host}:{state.policy_port}".encode("iso-8859-1"))
            if not upgrade and not saw_connection:
                out_headers.append(b"Connection: close")

            first = f"{method} {target} {version}\r\n".encode("iso-8859-1")
            upstream.sendall(first + b"\r\n".join(out_headers) + b"\r\n\r\n" + body)
            if upgrade:
                policy._tunnel(client, upstream)
            else:
                while True:
                    chunk = upstream.recv(65536)
                    if not chunk:
                        break
                    client.sendall(chunk)
        finally:
            try:
                upstream.close()
            except OSError:
                pass

    def _filtered_file(
        self,
        state: HandoffState,
        client: socket.socket,
        entry: dict,
        headers: dict[str, str],
        range_start: int,
    ) -> bool:
        size = int(entry["size"])
        duration_ms = int(entry["duration_ms"])
        if range_start < state.probe_edge_bytes or range_start > max(0, size - state.probe_edge_bytes):
            state.log(
                "FILE_PROBE client=%s media=%s range_start=%s size=%s action=passthru"
                % (self.client_address[0], entry.get("basename") or "-", range_start, size)
            )
            return False

        offset_seconds = (float(range_start) / float(size)) * (float(duration_ms) / 1000.0)
        target = state.filtered_start_target(entry, offset_seconds)
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

            response_head, response_rest = _read_response_head(upstream)
            status_line = response_head.split(b"\r\n", 1)[0].decode("iso-8859-1", "replace") if response_head else ""
            if " 200 " not in f" {status_line} ":
                state.log(
                    "FILE_HANDOFF_FAIL client=%s media=%s offset=%.3f status=%r action=passthru"
                    % (self.client_address[0], entry.get("basename") or "-", offset_seconds, status_line)
                )
                return False

            state.log(
                "FILE_FILTERED client=%s media=%s range_start=%s size=%s offset=%.3f mode=video-copy-audio-transcode"
                % (self.client_address[0], entry.get("basename") or "-", range_start, size, offset_seconds)
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
        state: HandoffState = self.server.state  # type: ignore[attr-defined]
        raw_client = self.request
        raw_client.settimeout(60.0)
        client = raw_client
        transport = "http"
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

            match = FILE_RE.match(path)
            if method.upper() == "GET" and match:
                entry = state.lookup_file(self.client_address[0], headers, match.group(1))
                start = _range_start(policy._header_value(headers, "Range"))
                if entry is not None and start is not None:
                    if self._filtered_file(state, client, entry, headers, start):
                        return

            state.log(
                "PASS transport=%s client=%s method=%s path=%s"
                % (transport, self.client_address[0], method, path)
            )
            self._forward_normal(state, client, method, target, version, lines, bytes(body), upgrade)
        except ssl.SSLError as exc:
            state.log(f"ERROR client={self.client_address[0]} TLS {exc}")
        except Exception as exc:
            state.log(f"ERROR client={self.client_address[0]} {type(exc).__name__}: {exc}")


class ThreadingHandoffProxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser(description="Censorarr experimental Plex filtered file handoff")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=32403)
    parser.add_argument("--policy-host", default="127.0.0.1")
    parser.add_argument("--policy-port", type=int, default=32402)
    parser.add_argument("--plex-host", default="127.0.0.1")
    parser.add_argument("--plex-port", type=int, default=32400)
    parser.add_argument("--allowlist", default=DEFAULT_ALLOWLIST)
    parser.add_argument("--probe-edge-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--plex-appdata")
    parser.add_argument("--log", default="/volume1/docker/censorarr-test/work/plex-filtered-handoff.log")
    args = parser.parse_args()

    try:
        state = HandoffState(args)
    except Exception as exc:
        print(f"ERROR: handoff preflight failed: {exc}", file=sys.stderr)
        return 2

    try:
        server = ThreadingHandoffProxy((args.listen_host, args.listen_port), HandoffHandler)
    except OSError as exc:
        print(f"ERROR: could not listen on {args.listen_host}:{args.listen_port}: {exc}", file=sys.stderr)
        return 3
    server.state = state  # type: ignore[attr-defined]
    state.log(
        "START listen=%s:%s policy=%s:%s plex=%s:%s tls=plex:%s allowlist=%s probe_edge_bytes=%s"
        % (
            args.listen_host,
            args.listen_port,
            args.policy_host,
            args.policy_port,
            args.plex_host,
            args.plex_port,
            state.tls_p12.name,
            args.allowlist,
            state.probe_edge_bytes,
        )
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        state.log("STOP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
