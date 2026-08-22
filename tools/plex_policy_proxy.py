#!/usr/bin/env python3
"""Development Plex request-policy proxy for proving Censorarr filtered playback.

The proxy listens on a separate port and forwards requests to Plex Media Server.
For selected universal transcode decision/start requests it rewrites:

  directPlay=0
  directStream=0
  directStreamAudio=0
  copyts=1

For the Shield proof, --plex-tls-auto loads the server's own plex.direct P12
certificate so HTTPS clients can be transparently redirected to this proxy. The
proxy accepts both TLS and plain HTTP on the same listen port.

The existing Censorarr Plex Transcoder shim then injects profanity mute ranges into
Plex's audio filter graph. Raw Plex tokens and certificate passwords are never
logged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import select
import shutil
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UNIVERSAL_PREFIX = "/video/:/transcode/universal/"
FILTER_VALUES = {
    "directPlay": "0",
    "directStream": "0",
    "directStreamAudio": "0",
    "copyts": "1",
}
MAX_HEADER = 1024 * 1024
MAX_DECISION_PROBE = 256 * 1024
PLEX_APPDATA_CANDIDATES = (
    "/volume1/PlexMediaServer/AppData/Plex Media Server",
    "/var/packages/PlexMediaServer/shares/PlexMediaServer/AppData/Plex Media Server",
    "/volume1/@appdata/PlexMediaServer/Plex Media Server",
)
P12_NAMES = ("cert-v2.p12", "certificate.p12")


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


def _find_plex_appdata(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if (p / "Preferences.xml").is_file():
            return p
        raise RuntimeError(f"Plex appdata does not contain Preferences.xml: {p}")
    for raw in PLEX_APPDATA_CANDIDATES:
        p = Path(raw)
        if (p / "Preferences.xml").is_file():
            return p
    raise RuntimeError("could not locate Plex appdata; pass --plex-appdata")


def _find_p12(appdata: Path) -> Path:
    cache = appdata / "Cache"
    for name in P12_NAMES:
        p = cache / name
        if p.is_file():
            return p
    try:
        for p in cache.iterdir():
            if p.is_file() and p.suffix.casefold() == ".p12":
                return p
    except OSError:
        pass
    raise RuntimeError(f"could not find Plex P12 certificate under {cache}")


def _plex_p12_password(appdata: Path) -> str:
    prefs = appdata / "Preferences.xml"
    try:
        root = ET.parse(str(prefs)).getroot()
    except Exception as exc:
        raise RuntimeError(f"could not read Plex Preferences.xml: {exc}") from exc
    processed = str(root.attrib.get("ProcessedMachineIdentifier") or "").strip()
    if not processed:
        raise RuntimeError("ProcessedMachineIdentifier missing from Plex Preferences.xml")
    return hashlib.sha512(("plex" + processed).encode("utf-8")).hexdigest()


def _extract_p12_to_pem(p12: Path, password: str) -> Path:
    openssl = shutil.which("openssl")
    if not openssl:
        raise RuntimeError("openssl was not found on the Synology host")
    fd, raw_path = tempfile.mkstemp(prefix="censorarr-plex-proxy-", suffix=".pem")
    os.close(fd)
    pem = Path(raw_path)
    try:
        os.chmod(str(pem), 0o600)
    except OSError:
        pass

    attempts = [
        [openssl, "pkcs12", "-in", str(p12), "-nodes", "-passin", f"pass:{password}", "-out", str(pem)],
        [openssl, "pkcs12", "-legacy", "-in", str(p12), "-nodes", "-passin", f"pass:{password}", "-out", str(pem)],
    ]
    errors: list[str] = []
    for cmd in attempts:
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        except Exception as exc:
            errors.append(str(exc))
            continue
        if proc.returncode == 0 and pem.is_file() and pem.stat().st_size > 0:
            return pem
        text = proc.stderr.decode("utf-8", "replace").strip()
        if text:
            errors.append(text[-600:])
    try:
        pem.unlink()
    except OSError:
        pass
    detail = " | ".join(errors[-2:]) if errors else "unknown openssl error"
    raise RuntimeError(f"could not extract Plex P12 certificate: {detail}")


def _build_plex_tls_context(appdata: Path) -> tuple[ssl.SSLContext, Path]:
    p12 = _find_p12(appdata)
    password = _plex_p12_password(appdata)
    pem = _extract_p12_to_pem(p12, password)
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(pem))
    finally:
        try:
            pem.unlink()
        except OSError:
            pass
    return context, p12


def _is_playback_path(path: str) -> bool:
    if not str(path).startswith(UNIVERSAL_PREFIX):
        return False
    leaf = str(path)[len(UNIVERSAL_PREFIX):].casefold()
    return leaf == "decision" or leaf.startswith("start")


def _is_decision_path(path: str) -> bool:
    return str(path).casefold() == (UNIVERSAL_PREFIX + "decision").casefold()


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


def _header_value(headers: dict[str, str], name: str) -> str:
    wanted = name.casefold()
    for key, value in headers.items():
        if key.casefold() == wanted:
            return str(value)
    return ""


def _token_from_request(target: str, headers: dict[str, str]) -> str:
    parts = urlsplit(target)
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.casefold() == "x-plex-token" and str(value).strip():
            return str(value).strip()
    return _header_value(headers, "X-Plex-Token").strip()


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


def _decision_response_summary(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace")
    first = text.split("\r\n", 1)[0].strip() or "unknown-status"
    def values(name: str) -> str:
        found = re.findall(rf'\b{re.escape(name)}="([^"]+)"', text, flags=re.I)
        unique: list[str] = []
        for item in found:
            if item not in unique:
                unique.append(item)
        return ",".join(unique[:8]) or "-"
    return (
        f"status={first!r} decision={values('decision')} "
        f"videoDecision={values('videoDecision')} audioDecision={values('audioDecision')} "
        f"protocol={values('protocol')} container={values('container')}"
    )


class ProxyState:
    def __init__(self, args: argparse.Namespace):
        self.upstream_host = args.upstream_host
        self.upstream_port = int(args.upstream_port)
        self.force_all = bool(args.force_all)
        self.policy_file = args.policy
        self.trace_paths = bool(args.trace_paths)
        self.log_path = Path(args.log) if args.log else None
        self.lock = threading.Lock()
        self.tls_context: ssl.SSLContext | None = None
        self.tls_p12: Path | None = None
        if args.plex_tls_auto:
            appdata = _find_plex_appdata(args.plex_appdata)
            self.tls_context, self.tls_p12 = _build_plex_tls_context(appdata)

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
                if state.tls_context is None:
                    state.log(f"ERROR client={self.client_address[0]} tls-request-without---plex-tls-auto")
                    return
                client = state.tls_context.wrap_socket(raw_client, server_side=True)
                client.settimeout(60.0)
                transport = "https"

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
            path = urlsplit(target).path
            if state.trace_paths:
                state.log(
                    "TRACE transport=%s client=%s method=%s path=%s"
                    % (transport, self.client_address[0], method, path)
                )
            filtered = state.should_filter(target, headers)
            rewritten_target, changed = _rewrite_target(target) if filtered else (target, {})
            upgrade = _header_value(headers, "Upgrade").casefold() == "websocket"

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
            raw_length = _header_value(headers, "Content-Length")
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

            upstream = socket.create_connection((state.upstream_host, state.upstream_port), timeout=15.0)
            upstream.settimeout(60.0)
            try:
                first = f"{method} {rewritten_target} {version}\r\n".encode("iso-8859-1")
                upstream.sendall(first + b"\r\n".join(out_headers) + b"\r\n\r\n" + bytes(body))
                if filtered:
                    state.log(
                        "FILTERED transport=%s client=%s method=%s target=%s set=%s"
                        % (transport, self.client_address[0], method, _redact_target(rewritten_target), json.dumps(changed, sort_keys=True))
                    )
                elif _is_playback_path(path):
                    state.log(
                        "PASSTHRU transport=%s client=%s method=%s target=%s"
                        % (transport, self.client_address[0], method, _redact_target(target))
                    )
                if upgrade:
                    _tunnel(client, upstream)
                else:
                    decision_probe = bytearray()
                    decision_logged = False
                    while True:
                        chunk = upstream.recv(65536)
                        if not chunk:
                            break
                        if filtered and _is_decision_path(path) and len(decision_probe) < MAX_DECISION_PROBE:
                            remaining = MAX_DECISION_PROBE - len(decision_probe)
                            decision_probe.extend(chunk[:remaining])
                            if not decision_logged and (b"</MediaContainer>" in decision_probe or len(decision_probe) >= 8192):
                                state.log(
                                    "DECISION_RESPONSE client=%s %s"
                                    % (self.client_address[0], _decision_response_summary(bytes(decision_probe)))
                                )
                                decision_logged = True
                        client.sendall(chunk)
                    if filtered and _is_decision_path(path) and decision_probe and not decision_logged:
                        state.log(
                            "DECISION_RESPONSE client=%s %s"
                            % (self.client_address[0], _decision_response_summary(bytes(decision_probe)))
                        )
            finally:
                try:
                    upstream.close()
                except Exception:
                    pass
        except ssl.SSLError as exc:
            state.log(f"ERROR client={self.client_address[0]} TLS {exc}")
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
    parser.add_argument("--plex-tls-auto", action="store_true", help="Terminate Plex HTTPS using the server's own plex.direct P12 certificate")
    parser.add_argument("--plex-appdata", help="Explicit Plex Media Server appdata directory")
    parser.add_argument("--trace-paths", action="store_true", help="Log request paths and summarized decision responses for debugging")
    parser.add_argument("--log", default="/volume1/docker/censorarr-test/work/plex-policy-proxy.log")
    args = parser.parse_args()

    if not args.force_all and not args.policy:
        parser.error("use --force-all for the development proof or provide --policy")

    try:
        state = ProxyState(args)
    except Exception as exc:
        print(f"ERROR: proxy preflight failed: {exc}", file=sys.stderr)
        return 2

    try:
        server = ThreadingProxy((args.listen_host, args.listen_port), PlexProxyHandler)
    except OSError as exc:
        print(f"ERROR: could not listen on {args.listen_host}:{args.listen_port}: {exc}", file=sys.stderr)
        return 3
    server.state = state  # type: ignore[attr-defined]
    tls_mode = f"plex:{state.tls_p12.name}" if state.tls_p12 is not None else "off"
    state.log(
        f"START listen={args.listen_host}:{args.listen_port} upstream={args.upstream_host}:{args.upstream_port} "
        f"mode={'force-all' if args.force_all else 'token-policy'} tls={tls_mode} trace_paths={'on' if state.trace_paths else 'off'}"
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
