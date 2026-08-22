"""Timestamp-driven audio filtering for experimental Family Safe streaming.

This module deliberately does not know anything about the current player clock.
It converts Censorarr's saved mute ranges into an FFmpeg audio filter tied to the
media timeline itself.  That makes the filtering suitable for server-side
transcoding/proxying where audio is changed before it reaches the client buffer.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

import censorarr as pc


REPORT_DIR_DEFAULT = Path("/config/reports")
MEDIA_EXTENSIONS = {
    ".mkv", ".mp4", ".m4v", ".mov", ".avi", ".ts", ".m2ts", ".mpg", ".mpeg", ".webm",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _seconds_ranges(payload: dict[str, Any]) -> list[tuple[float, float]]:
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


def report_for_media(media: Path, report_dir: Path = REPORT_DIR_DEFAULT) -> tuple[Path, list[tuple[float, float]]]:
    """Return the best Censorarr report and its mute ranges for *media*.

    The normal report name contains a hash of the full media path.  Old Censorarr
    installs may have reports created under a previous mount path, so we retain the
    same filename fallback used by Live Mute.
    """
    media = Path(media)
    exact = report_dir / f"{pc.report_name(media)}.json"
    payload = _read_json(exact) if exact.is_file() else None
    if payload is not None:
        return exact, _seconds_ranges(payload)

    wanted = media.name.casefold()
    if not wanted or not report_dir.is_dir():
        return exact, []

    try:
        candidates = sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        candidates = list(report_dir.glob("*.json"))

    for candidate in candidates:
        if candidate == exact:
            continue
        payload = _read_json(candidate)
        if payload is None:
            continue
        recorded = str(payload.get("file") or "").strip()
        if not recorded or Path(recorded).name.casefold() != wanted:
            continue
        return candidate, _seconds_ranges(payload)
    return exact, []


def merge_ranges(
    ranges: Iterable[tuple[float, float]],
    *,
    lead_ms: int = 0,
    tail_ms: int = 0,
    join_gap_ms: int = 20,
) -> list[tuple[float, float]]:
    """Pad and merge ranges into stable server-side mute windows."""
    lead = max(0, int(lead_ms)) / 1000.0
    tail = max(0, int(tail_ms)) / 1000.0
    join_gap = max(0, int(join_gap_ms)) / 1000.0
    padded = sorted((max(0.0, float(a) - lead), max(0.0, float(b) + tail)) for a, b in ranges if b > a)
    merged: list[list[float]] = []
    for start, end in padded:
        if not merged or start > merged[-1][1] + join_gap:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(a, b) for a, b in merged]


def ranges_for_window(
    ranges: Iterable[tuple[float, float]],
    *,
    window_start: float,
    window_duration: float,
) -> list[tuple[float, float]]:
    """Clip absolute media ranges to a window and make them window-relative."""
    start = max(0.0, float(window_start))
    end = start + max(0.0, float(window_duration))
    out: list[tuple[float, float]] = []
    for a, b in ranges:
        if b <= start or a >= end:
            continue
        out.append((max(a, start) - start, min(b, end) - start))
    return out


def _num(value: float) -> str:
    # Millisecond precision is enough for FFmpeg's audio timeline and keeps filter
    # expressions compact even when a feature film contains hundreds of ranges.
    return f"{float(value):.3f}".rstrip("0").rstrip(".") or "0"


def volume_filter(ranges: Iterable[tuple[float, float]]) -> str:
    """Build an FFmpeg timeline filter that replaces configured intervals with silence."""
    rows = [(float(a), float(b)) for a, b in ranges if b > a]
    if not rows:
        return "anull"
    enabled = "+".join(f"between(t,{_num(a)},{_num(b)})" for a, b in rows)
    return f"volume=volume=0:enable='{enabled}'"


def sample_command(
    *,
    ffmpeg: str,
    media: Path,
    output: Path,
    absolute_ranges: Iterable[tuple[float, float]],
    start: float,
    duration: float,
    audio_stream: int = 0,
) -> list[str]:
    """Build a short proof transcode: copy video, filter/re-encode only audio.

    ``asetpts=PTS-STARTPTS`` makes the filter clock explicitly relative to the
    requested proof window, eliminating any ambiguity around input seek timestamps.
    """
    start = max(0.0, float(start))
    duration = max(0.25, float(duration))
    local_ranges = ranges_for_window(absolute_ranges, window_start=start, window_duration=duration)
    af = f"asetpts=PTS-STARTPTS,{volume_filter(local_ranges)}"
    return [
        ffmpeg,
        "-hide_banner", "-loglevel", "warning", "-y",
        "-ss", _num(start),
        "-i", str(media),
        "-t", _num(duration),
        "-map", "0:v:0?",
        "-map", f"0:a:{max(0, int(audio_stream))}",
        "-map_metadata", "0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "384k",
        "-af", af,
        "-avoid_negative_ts", "make_zero",
        str(output),
    ]


def detect_media_argument(argv: list[str]) -> tuple[int | None, str]:
    """Best-effort source-media discovery in a Plex/FFmpeg-style argv list."""
    for idx, arg in enumerate(argv):
        if idx > 0 and argv[idx - 1] == "-i":
            value = str(arg)
            if Path(value).suffix.lower() in MEDIA_EXTENSIONS:
                return idx, value
    for idx, arg in enumerate(argv):
        value = str(arg)
        if value.startswith("-"):
            continue
        if Path(value).suffix.lower() in MEDIA_EXTENSIONS and (value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value)):
            return idx, value
    return None, ""


def parse_time_seconds(raw: str) -> float | None:
    value = str(raw or "").strip()
    if not value:
        return None
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


def input_seek_seconds(argv: list[str], media_arg_index: int | None = None) -> float:
    """Return the last ``-ss`` that applies at/before the media input, if present."""
    limit = len(argv) if media_arg_index is None else max(0, int(media_arg_index))
    found = 0.0
    for idx in range(0, max(0, limit - 1)):
        if argv[idx] != "-ss":
            continue
        parsed = parse_time_seconds(argv[idx + 1])
        if parsed is not None:
            found = max(0.0, parsed)
    return found
