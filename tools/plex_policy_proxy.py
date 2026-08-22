#!/usr/bin/env python3
"""Development TCP/HTTP reverse proxy for proving Censorarr Plex playback policy.

The proxy listens on a separate local port and forwards requests to Plex Media
Server. For selected universal transcode decision/start requests it rewrites:

  directPlay=0
  directStream=1
  directStreamAudio=0
  copyts=1

This forces playback through Plex's transcoder path while still allowing Plex to
copy/remux video when possible. The existing Censorarr Plex Transcoder shim then
injects profanity mute ranges into the audio graph.

For the first proof use --force-all and redirect only one test client's traffic to
this port. The proxy never prints raw Plex tokens. WebSocket upgrade requests are
passed through untouched as a raw tunnel.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import select
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UNIVERSAL_PREFIX = "/video/:/transcode/universal/"
FILTER_VALUES = {
    "directPlay": "0",
    "directStream": "1",
    "directStreamAudio": "0",
    "copyts": "1",
}
MAX_HEADER = 1024 * 1024


def _token_sha256(token: str) -> str:
    value = str(token or "").strip()
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def _policy_hashes(path: str | None) -> set[str]:
    if not path:
        return set()
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return set()
    rows = payload.get("filtered_token_sha256") if isinstance(payload, dict) else []
    return {str(x).strip().casefold() for x in (rows or []) if str(x).strip()}


def _is_playback_path(path: str) -> bool:
    if not str(path).startswith(UNIVERSAL_PREFIX):
        return False
    leaf = str(path)[len(UNIVERSAL_PREFIX):].casefold()
    return leaf == "decision" or leaf.startswith("start")


def _headers_dict(lines: list[bytes]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in lines:
        try:
            text = raw.decode("iso-8859-1")
        except Exception:
            continue
        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        out[key.strip()] = value.strip()
    return out


def _token_from_request(target: str, headers: dict[str, str]) -> str:
    parts = urlsplit(target)
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.casefold() == "x-plex-token" and str(value).strip():
            return str(value).strip()
    for key, value in headers.items():
        if key.casefold() == "x-plex-token" and str(value).strip():
            return str(value).strip()
    return ""


def _rewrite_target(target: str) -> tuple[str, dict[str, str]]:
    parts = urlsplit(target)
    if not _is_playback_path(parts.path):
        return target, {}
    rows = [(str(k), str(v)) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    indexes = {k.casefold(): i for i, (k, _v) in enumerate(rows)}
    changed: dict[str, str] = {}
    for key, value in FILTER_VALUES.items():
        idx = indexes.get(key.casefold())
        if idx is None:
            rows.append((key, value))
            indexes[key.casefold()] = len(rows) - 1
            changed[key] = value
        else:
            old_key, old_value = rows[idx]
            if old_value != value:
                rows[idx] = (old_key, value)
                changed[old_key] = value
    query = urlencode(rows, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment)), changed


def _redact_target(target: str) -> str:
    parts = urlsplit(target)
    rows = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        rows.append((key, "<redacted>" if key.casefold() == "x-plex-token" else value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(rows, doseq=True), parts.fragment))


class ProxyState:
    def __init__(self, args: argparse.Namespace):
        self.upstream_host = args.upstream_host
        self.upstream_port = int(args.upstream_port)
        self.force_all = bool(args.force_all)
        self.policy_file = args.policy
        self.log_path = Path(args.log) if args.log else None
        self.lock = threading.Lock()

    def should_filter(self, target: str, headers: dict[str, str]) -> bool:
        if not _is_playback_path(urlsplit(target).path):
            return False
        if self.force_all:
            return True
        token = _token_from_request(target, headers)
        digest = _token_sha256(token)
        return bool(digest and digest.casefold() in _policy_hashes(self.policy_file))

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
                except Exception:
                    pass


def _read_request(sock: socket.socket) -> tuple[bytes, bytes]:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(65536)
        if not chunk:
            return bytes(data), b""
        data.extend(chunk)
        if len(data) > MAX_HEADER:
            raise RuntimeError("request headers too large")
    head, rest = bytes(data).split(b"\r\n\r\n", 1)
    return head, rest


def _tunnel(a: socket.socket, b: socket.socket) -> None:
    sockets = [a, b]
    while sockets:
        readable, _, _ = select.select(sockets, [], [], 60.0)
        if not readable:
            continue
        for src in list(readable):
            dst = b if src is a else a
            try:
                chunk = src.recv(65536)
            except OSError:
                return
            if not chunk:
                return
            try:
                dst.sendall(chunk)
            except OSError:
                return


class PlexProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        state: ProxyState = self.server.state  # type: ignore[attr-defined]
        client = self.request
        client.settimeout(60.0)
        try:
            head, rest = _read_request(client)
            if not head:
                return
            lines = head.split(b"\r\n")
            request_line = lines[0].decode("iso-8859-1", "replace")
            try:
                method, target, version = request_line.split(" ", 2)
            except ValueError:
                return
            headers = _headers_dict(lines[1:])
            filtered = state.should_filter(target, headers)
            rewritten_target, changed = _rewrite_target(target) if filtered else (target, {})
            upgrade = str(headers.get("Upgrade") or headers.get("upgrade") or "").casefold() == "websocket"

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
                    out_headers.append(f"Host: {state.upstream_host}:{state.upstream_port}".encode("iso-8859-1"))
                    saw_host = True
                    continue
                if lower == "connection" and not upgrade:
                    out_headers.append(b"Connection: close")
                    saw_connection = True
                    continue
                out_headers.append(raw)
            if not saw_host:
                out_headers.append(f"Host: {state.upstream_host}:{state.upstream_port}".encode("iso-8859-1"))
            if not upgrade and not saw_connection:
                out_headers.append(b"Connection: close")

            content_length = 0
            for key, value in headers.items():
                if key.casefold() == "content-length":
                    try:
                        content_length = max(0, int(value))
                    except ValueError:
                        content_length = 0
                    break
            body = bytearray(rest)
            while len(body) < content_length:
                chunk = client.recv(min(65536, content_length - len(body)))
                if not chunk:
                    break
                body.extend(chunk)

            upstream = socket.create_connection((state.upstream_host, state.upstream_port), timeout=15.0)
            upstream.settimeout(60.0)
            try:
                first = f"{method} {rewritten_target} {version}\r\n".encode("iso-8859-1")
                upstream.sendall(first + b"\r\n".join(out_headers) + b"\r\n\r\n" + bytes(body))
                if filtered:
                    state.log(
                        "FILTERED client=%s method=%s target=%s set=%s"
                        % (self.client_address[0], method, _redact_target(rewritten_target), json.dumps(changed, sort_keys=True))
                    )
                elif _is_playback_path(urlsplit(target).path):
                    state.log(
                        "PASSTHRU client=%s method=%s target=%s"
                        % (self.client_address[0], method, _redact_target(target))
                    )
                if upgrade:
                    _tunnel(client, upstream)
                else:
                    while True:
                        chunk = upstream.recv(65536)
                        if not chunk:
                            break
                        client.sendall(chunk)
            finally:
                try:
                    upstream.close()
                except Exception:
                    pass
        except Exception as exc:
            state.log(f"ERROR client={self.client_address[0]} {type(exc).__name__}: {exc}")


class ThreadingProxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser(description="Censorarr Plex request-policy proxy proof")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=32401)
    parser.add_argument("--upstream-host", default="127.0.0.1")
    parser.add_argument("--upstream-port", type=int, default=32400)
    parser.add_argument("--force-all", action="store_true", help="Filter every universal decision/start request through this proxy")
    parser.add_argument("--policy", help="JSON policy containing filtered_token_sha256 entries")
    parser.add_argument("--log", default="/volume1/docker/censorarr-test/work/plex-policy-proxy.log")
    args = parser.parse_args()

    if not args.force_all and not args.policy:
        parser.error("use --force-all for the development proof or provide --policy")

    state = ProxyState(args)
    server = ThreadingProxy((args.listen_host, args.listen_port), PlexProxyHandler)
    server.state = state  # type: ignore[attr-defined]
    state.log(
        f"START listen={args.listen_host}:{args.listen_port} upstream={args.upstream_host}:{args.upstream_port} "
        f"mode={'force-all' if args.force_all else 'token-policy'}"
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
