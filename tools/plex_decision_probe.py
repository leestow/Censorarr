#!/usr/bin/env python3
"""Read a real Plex universal decision request from PMS logs and compare policies.

Development probe only. It does not proxy traffic or modify Plex configuration.
It locates the newest universal-transcode decision request in Plex Media Server.log,
replays it locally against PMS with the original client's X-Plex headers, then
replays a Censorarr-filtered variant:

    directPlay=0
    directStream=1
    directStreamAudio=0
    copyts=1

The probe never prints Plex tokens. If the PMS log redacts the client token, it uses
PlexOnlineToken from Preferences.xml for the local decision requests.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

FILTERED_VALUES = {
    "directPlay": "0",
    "directStream": "1",
    "directStreamAudio": "0",
    "copyts": "1",
}

LOG_CANDIDATES = (
    "/volume1/PlexMediaServer/AppData/Plex Media Server/Logs/Plex Media Server.log",
    "/var/packages/PlexMediaServer/shares/PlexMediaServer/AppData/Plex Media Server/Logs/Plex Media Server.log",
    "/volume1/@appdata/PlexMediaServer/Plex Media Server/Logs/Plex Media Server.log",
)
PREF_CANDIDATES = (
    "/volume1/PlexMediaServer/AppData/Plex Media Server/Preferences.xml",
    "/var/packages/PlexMediaServer/shares/PlexMediaServer/AppData/Plex Media Server/Preferences.xml",
    "/volume1/@appdata/PlexMediaServer/Plex Media Server/Preferences.xml",
)
DECISION_RE = re.compile(r"(/video/:/transcode/universal/decision\?[^\s\"']+)")
TOKEN_RE = re.compile(r"([?&]X-Plex-Token=)[^&]+", re.IGNORECASE)
HEADER_PAIR_RE = re.compile(r"\s/\s([^/=]+?)\s*=>\s*(.*?)(?=\s/\s[^/=]+?\s*=>|$)")


def _first_file(candidates: tuple[str, ...], explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    for raw in candidates:
        p = Path(raw)
        if p.is_file():
            return p
    roots = [Path("/volume1/PlexMediaServer"), Path("/var/packages/PlexMediaServer"), Path("/volume1/@appdata/PlexMediaServer")]
    wanted = Path(candidates[0]).name
    for root in roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob(wanted):
                if p.is_file():
                    return p
        except (OSError, PermissionError):
            pass
    return None


def _tail_text(path: Path, max_bytes: int = 8 * 1024 * 1024) -> str:
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > max_bytes:
            fh.seek(size - max_bytes)
        raw = fh.read()
    return raw.decode("utf-8", "replace")


def newest_decision_request(log_path: Path) -> tuple[str, dict[str, str], str]:
    lines = _tail_text(log_path).splitlines()
    for line in reversed(lines):
        match = DECISION_RE.search(line)
        if not match:
            continue
        path = match.group(1).replace("&amp;", "&")
        headers: dict[str, str] = {}
        for hmatch in HEADER_PAIR_RE.finditer(line):
            key = hmatch.group(1).strip()
            value = hmatch.group(2).strip()
            if not key or not value:
                continue
            # Let urllib generate transport headers for the local replay. Preserve the
            # Plex capability headers that actually influence the decision engine.
            if key.casefold() in {"host", "connection", "accept-encoding", "content-length"}:
                continue
            if key.casefold() == "x-plex-token":
                continue
            if key.casefold().startswith("x-plex-") or key.casefold() in {"accept", "accept-language", "user-agent"}:
                headers[key] = value
        return path, headers, line
    raise RuntimeError("No Plex universal decision request was found in the recent server log")


def plex_online_token(pref_path: Path | None) -> str:
    if pref_path is None:
        return ""
    try:
        root = ET.parse(pref_path).getroot()
    except Exception:
        return ""
    return str(root.attrib.get("PlexOnlineToken") or "").strip()


def _token_looks_redacted(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return True
    lower = raw.casefold()
    return raw.startswith("<") or "redact" in lower or lower in {"token", "xxxxxxxx", "xxxxx"}


def localize_request(path_or_url: str, server_token: str = "") -> str:
    parts = urlsplit(path_or_url)
    path = parts.path or path_or_url.split("?", 1)[0]
    query = parts.query if parts.query else (path_or_url.split("?", 1)[1] if "?" in path_or_url else "")
    rows = parse_qsl(query, keep_blank_values=True)
    token_idx = None
    for idx, (key, value) in enumerate(rows):
        if key.casefold() == "x-plex-token":
            token_idx = idx
            if server_token and _token_looks_redacted(value):
                rows[idx] = (key, server_token)
            break
    if token_idx is None and server_token:
        rows.append(("X-Plex-Token", server_token))
    return urlunsplit(("http", "127.0.0.1:32400", path, urlencode(rows, doseq=True), ""))


def filtered_url(url: str) -> str:
    parts = urlsplit(url)
    rows = parse_qsl(parts.query, keep_blank_values=True)
    indexes = {k.casefold(): i for i, (k, _v) in enumerate(rows)}
    for key, value in FILTERED_VALUES.items():
        idx = indexes.get(key.casefold())
        if idx is None:
            rows.append((key, value))
            indexes[key.casefold()] = len(rows) - 1
        else:
            old_key, _old_value = rows[idx]
            rows[idx] = (old_key, value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(rows, doseq=True), parts.fragment))


def redact_url(url: str) -> str:
    return TOKEN_RE.sub(r"\1<redacted>", url)


def redacted_headers(headers: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        if key.casefold() == "x-plex-token":
            out[key] = "<redacted>"
        elif key.casefold() == "x-plex-client-profile-extra" and len(value) > 240:
            out[key] = value[:240] + f"... ({len(value)} chars)"
        else:
            out[key] = value
    return out


def fetch(url: str, headers: dict[str, str] | None = None, timeout: float = 20.0) -> tuple[int, bytes, str]:
    request_headers = dict(headers or {})
    request_headers.setdefault("Accept", "application/xml")
    request_headers.setdefault("User-Agent", "Censorarr-Decision-Probe/2")
    req = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read(), str(resp.headers.get("Content-Type") or "")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(), str(exc.headers.get("Content-Type") or "")


def summarize_xml(raw: bytes) -> dict:
    try:
        root = ET.fromstring(raw)
    except Exception as exc:
        text = raw.decode("utf-8", "replace")[:1000]
        return {"parse_error": str(exc), "body_preview": text}

    root_keys = (
        "generalDecisionCode", "generalDecisionText", "transcodeDecisionCode", "transcodeDecisionText",
        "directPlayDecisionCode", "directPlayDecisionText", "directStreamDecisionCode", "directStreamDecisionText",
    )
    out: dict = {"root": {k: root.attrib[k] for k in root_keys if k in root.attrib}, "streams": []}
    interesting = {
        "videoDecision", "audioDecision", "subtitleDecision", "protocol", "container", "transcodeContainer",
        "videoCodec", "audioCodec", "decision", "selected", "streamType", "codec", "id", "index",
    }
    for elem in root.iter():
        attrs = {k: v for k, v in elem.attrib.items() if k in interesting}
        if any(k in attrs for k in ("videoDecision", "audioDecision", "subtitleDecision", "decision")):
            out["streams"].append({"tag": elem.tag, **attrs})
    return out


def current_sessions(server_token: str) -> list[dict]:
    if not server_token:
        return []
    url = "http://127.0.0.1:32400/status/sessions?" + urlencode({"X-Plex-Token": server_token})
    status, raw, _content_type = fetch(url, {"Accept": "application/xml"})
    if status != 200:
        return []
    try:
        root = ET.fromstring(raw)
    except Exception:
        return []
    out: list[dict] = []
    for video in root.findall(".//Video"):
        row = {
            "title": video.attrib.get("title"),
            "type": video.attrib.get("type"),
            "viewOffset": video.attrib.get("viewOffset"),
            "session": None,
            "player": {},
            "transcode": None,
        }
        session = video.find("Session")
        if session is not None:
            row["session"] = session.attrib.get("id")
        player = video.find("Player")
        if player is not None:
            row["player"] = {k: player.attrib.get(k) for k in ("title", "platform", "product", "machineIdentifier", "local") if player.attrib.get(k) is not None}
        transcode = video.find("TranscodeSession")
        if transcode is not None:
            row["transcode"] = {k: transcode.attrib.get(k) for k in ("protocol", "container", "videoDecision", "audioDecision", "subtitleDecision", "transcodeHwRequested", "transcodeHwFullPipeline") if transcode.attrib.get(k) is not None}
        out.append(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare a real Plex playback decision with Censorarr forced-audio policy")
    parser.add_argument("--log", help="Explicit Plex Media Server.log path")
    parser.add_argument("--preferences", help="Explicit Plex Preferences.xml path")
    parser.add_argument("--url", help="Use this captured universal decision URL/path instead of reading the log")
    parser.add_argument("--save-dir", default="/tmp", help="Directory for raw original/filtered XML responses")
    args = parser.parse_args()

    log_path = None if args.url else _first_file(LOG_CANDIDATES, args.log)
    if not args.url and log_path is None:
        print("ERROR: could not locate Plex Media Server.log; pass --log", file=sys.stderr)
        return 2
    pref_path = _first_file(PREF_CANDIDATES, args.preferences)
    token = plex_online_token(pref_path)

    captured_headers: dict[str, str] = {}
    if args.url:
        captured = args.url
    else:
        captured, captured_headers, _line = newest_decision_request(log_path)
    original = localize_request(captured, token)
    forced = filtered_url(original)

    print(f"Plex log: {log_path or '(URL supplied)'}")
    print(f"Preferences: {pref_path or '(not found)'}")
    print("Captured:", redact_url(original))
    print("Filtered:", redact_url(forced))
    print("Captured client headers:")
    print(json.dumps(redacted_headers(captured_headers), indent=2))
    sessions = current_sessions(token)
    print("Current sessions:")
    print(json.dumps(sessions, indent=2))

    save = Path(args.save_dir)
    save.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, url in (("original", original), ("filtered", forced)):
        status, body, content_type = fetch(url, captured_headers)
        (save / f"censorarr-plex-decision-{name}.xml").write_bytes(body)
        decision = summarize_xml(body)
        if status != 200:
            decision["body_preview"] = body.decode("utf-8", "replace")[:1000]
        results[name] = {
            "http_status": status,
            "content_type": content_type,
            "decision": decision,
        }

    print(json.dumps(results, indent=2))
    print(f"Raw responses: {save}/censorarr-plex-decision-original.xml and {save}/censorarr-plex-decision-filtered.xml")
    return 0 if all(x["http_status"] == 200 for x in results.values()) else 3


if __name__ == "__main__":
    raise SystemExit(main())
