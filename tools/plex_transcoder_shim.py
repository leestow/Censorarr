#!/usr/bin/env python3
"""Standalone fail-open Plex Transcoder shim for Censorarr stream filtering.

This script is intended to temporarily replace Plex's `Plex Transcoder` binary on
Synology during development. The original binary must be renamed to
`Plex Transcoder.censorarr-real` in the same directory.

For explicitly allowlisted media only, the shim reads Censorarr report JSON files,
converts saved mute ranges into an FFmpeg `volume` timeline expression, injects it
into Plex's existing audio filter graph, and then `exec()`s the untouched original
Plex Transcoder. Any parsing/rewrite failure falls open to the original argv.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

PLEX_REAL = Path(os.environ.get(
    "CENSORARR_PLEX_REAL",
    "/volume1/@appstore/PlexMediaServer/Plex Transcoder.censorarr-real",
))
REPORT_DIR = Path(os.environ.get(
    "CENSORARR_REPORT_DIR",
    "/volume1/docker/censorarr-test/config/reports",
))
ALLOWLIST = Path(os.environ.get(
    "CENSORARR_STREAM_FILTER_ALLOWLIST",
    "/volume1/docker/censorarr-test/config/stream-filter-allowlist.txt",
))
LOG_PATH = Path(os.environ.get(
    "CENSORARR_STREAM_FILTER_LOG",
    "/volume1/docker/censorarr-test/work/plex-transcoder-shim.log",
))
FALLBACK_LOG_PATH = Path("/tmp/censorarr-plex-transcoder-shim.log")

LEAD_MS = int(os.environ.get("CENSORARR_STREAM_FILTER_LEAD_MS", "35") or 35)
TAIL_MS = int(os.environ.get("CENSORARR_STREAM_FILTER_TAIL_MS", "35") or 35)
JOIN_GAP_MS = int(os.environ.get("CENSORARR_STREAM_FILTER_JOIN_GAP_MS", "20") or 20)

MEDIA_EXTENSIONS = {
    ".mkv", ".mp4", ".m4v", ".mov", ".avi", ".ts", ".m2ts", ".mpg", ".mpeg", ".webm",
}
OUTPUT_LABEL_RE = re.compile(r"(\[[^\[\]]+\])\s*$")


def _write_log(path: Path, line: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        return True
    except Exception:
        return False


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} pid={os.getpid()} uid={os.geteuid()} {message}\n"
    if _write_log(LOG_PATH, line):
        return
    _write_log(FALLBACK_LOG_PATH, line)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _ranges(payload: dict[str, Any]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for row in payload.get("mute_ranges", []) or []:
        if not isinstance(row, dict):
            continue
        try:
            start = max(0.0, float(row.get("start")))
            end = max(0.0, float(row.get("end")))
        except (TypeError, ValueError):
            continue
        if end > start:
            out.append((start, end))
    out.sort()
    return out


def _merge_ranges(ranges: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    lead = max(0, LEAD_MS) / 1000.0
    tail = max(0, TAIL_MS) / 1000.0
    gap = max(0, JOIN_GAP_MS) / 1000.0
    padded = sorted((max(0.0, a - lead), b + tail) for a, b in ranges if b > a)
    merged: list[list[float]] = []
    for start, end in padded:
        if not merged or start > merged[-1][1] + gap:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(a, b) for a, b in merged]


def _allowlisted(media: Path) -> bool:
    if not ALLOWLIST.is_file():
        return False
    wanted = media.name.casefold()
    try:
        lines = ALLOWLIST.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False
    for raw in lines:
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        if item.casefold() == wanted:
            return True
    return False


def _report_for_media(media: Path) -> tuple[Path | None, list[tuple[float, float]]]:
    wanted = media.name.casefold()
    if not wanted or not REPORT_DIR.is_dir():
        return None, []
    try:
        candidates = sorted(REPORT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        candidates = list(REPORT_DIR.glob("*.json"))
    for candidate in candidates:
        payload = _read_json(candidate)
        if payload is None:
            continue
        recorded = str(payload.get("file") or "").strip()
        if recorded and Path(recorded).name.casefold() == wanted:
            return candidate, _ranges(payload)
    return None, []


def _detect_media(argv: list[str]) -> tuple[int | None, Path | None]:
    for idx, arg in enumerate(argv):
        if idx > 0 and argv[idx - 1] == "-i":
            p = Path(str(arg))
            if p.suffix.lower() in MEDIA_EXTENSIONS:
                return idx, p
    return None, None


def _parse_time(raw: str) -> float | None:
    value = str(raw or "").strip()
    try:
        return float(value)
    except ValueError:
        pass
    parts = value.split(":")
    if len(parts) not in {2, 3}:
        return None
    try:
        nums = [float(x) for x in parts]
    except ValueError:
        return None
    if len(nums) == 2:
        return nums[0] * 60.0 + nums[1]
    return nums[0] * 3600.0 + nums[1] * 60.0 + nums[2]


def _input_seek(argv: list[str], media_index: int) -> float:
    seek = 0.0
    for idx in range(0, max(0, media_index - 1)):
        if argv[idx] != "-ss":
            continue
        parsed = _parse_time(argv[idx + 1])
        if parsed is not None:
            seek = max(0.0, parsed)
    return seek


def _num(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".") or "0"


def _volume_filter(ranges: Iterable[tuple[float, float]]) -> str:
    rows = [(a, b) for a, b in ranges if b > a]
    enabled = "+".join(f"between(t,{_num(a)},{_num(b)})" for a, b in rows)
    return f"volume=volume=0:enable='{enabled}'"


def _audio_filter_slot(argv: list[str]) -> int | None:
    candidates: list[int] = []
    for idx in range(len(argv) - 1):
        if argv[idx] != "-filter_complex":
            continue
        graph_idx = idx + 1
        graph = argv[graph_idx]
        if "aresample" in graph.lower() and OUTPUT_LABEL_RE.search(graph):
            candidates.append(graph_idx)
    return candidates[0] if len(candidates) == 1 else None


def _rewrite(argv: list[str]) -> tuple[list[str], str]:
    media_index, media = _detect_media(argv)
    if media_index is None or media is None:
        return argv, "no-media-input"
    if not _allowlisted(media):
        return argv, f"not-allowlisted media={media.name}"

    report, raw = _report_for_media(media)
    if report is None or not raw:
        return argv, f"no-report media={media.name}"

    merged = _merge_ranges(raw)
    seek = _input_seek(argv, media_index)
    if "-copyts" in argv and "-start_at_zero" in argv:
        keep_from = max(0.0, seek - 2.0)
        filtered = [(a, b) for a, b in merged if b >= keep_from]
        timeline = "absolute-copyts"
    else:
        filtered = [(max(0.0, a - seek), max(0.0, b - seek)) for a, b in merged if b > seek]
        timeline = "seek-relative"

    if not filtered:
        return argv, f"no-future-ranges media={media.name} seek={seek:.3f}"

    slot = _audio_filter_slot(argv)
    if slot is None:
        return argv, f"unsupported-audio-graph media={media.name}"

    graph = argv[slot]
    match = OUTPUT_LABEL_RE.search(graph)
    if not match:
        return argv, f"missing-audio-output-label media={media.name}"

    label = match.group(1)
    prefix = graph[:match.start()].rstrip()
    out = list(argv)
    out[slot] = f"{prefix},{_volume_filter(filtered)}{label}"
    return out, (
        f"FILTERED media={media.name} report={report.name} raw={len(raw)} merged={len(merged)} "
        f"injected={len(filtered)} seek={seek:.3f} timeline={timeline}"
    )


def main() -> int:
    argv = sys.argv[1:]
    if not PLEX_REAL.is_file():
        log(f"FATAL original transcoder missing: {PLEX_REAL}")
        return 127

    rewritten = argv
    reason = "unchanged"
    try:
        rewritten, reason = _rewrite(argv)
    except Exception as exc:
        reason = f"FAIL-OPEN rewrite-error={type(exc).__name__}:{exc}"
        rewritten = argv

    log(reason)
    os.execv(str(PLEX_REAL), [str(PLEX_REAL), *rewritten])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
