"""CLI proof for timestamp-driven server-side profanity filtering.

This intentionally bypasses Plex/player timing.  It reads Censorarr's existing
report and creates a short media sample where video is stream-copied and only the
audio is decoded, silenced at saved profanity timestamps, and re-encoded.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import stream_filter


def _fmt(seconds: float) -> str:
    total_ms = int(round(max(0.0, seconds) * 1000))
    ms = total_ms % 1000
    total = total_ms // 1000
    sec = total % 60
    minute = (total // 60) % 60
    hour = total // 3600
    return f"{hour}:{minute:02d}:{sec:02d}.{ms:03d}" if hour else f"{minute}:{sec:02d}.{ms:03d}"


def main() -> int:
    p = argparse.ArgumentParser(description="Create a short Censorarr timestamp-filtered proof sample")
    p.add_argument("--media", required=True, help="Local media path as seen inside the Censorarr container")
    p.add_argument("--output", default="/work/stream-filter-proof.mkv")
    p.add_argument("--start", type=float, default=None, help="Sample start in seconds; defaults to 4 seconds before first mute")
    p.add_argument("--duration", type=float, default=12.0)
    p.add_argument("--audio-stream", type=int, default=0, help="Audio stream ordinal (0 = first audio stream)")
    p.add_argument("--lead-ms", type=int, default=35)
    p.add_argument("--tail-ms", type=int, default=35)
    p.add_argument("--join-gap-ms", type=int, default=20)
    p.add_argument("--report-dir", default="/config/reports")
    args = p.parse_args()

    media = Path(args.media)
    if not media.is_file():
        raise SystemExit(f"Media not found: {media}")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg was not found in PATH")

    report, raw_ranges = stream_filter.report_for_media(media, Path(args.report_dir))
    if not report.is_file():
        raise SystemExit(f"No Censorarr report found for: {media.name}\nExpected/last checked: {report}")
    if not raw_ranges:
        raise SystemExit(f"Report contains no mute ranges: {report}")

    ranges = stream_filter.merge_ranges(
        raw_ranges,
        lead_ms=args.lead_ms,
        tail_ms=args.tail_ms,
        join_gap_ms=args.join_gap_ms,
    )
    first_start, first_end = ranges[0]
    start = max(0.0, first_start - 4.0) if args.start is None else max(0.0, args.start)
    duration = max(1.0, args.duration)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    local = stream_filter.ranges_for_window(ranges, window_start=start, window_duration=duration)
    print(f"MEDIA: {media}")
    print(f"REPORT: {report}")
    print(f"RAW MUTE RANGES: {len(raw_ranges)}")
    print(f"FILTERED/MERGED RANGES: {len(ranges)}")
    print(f"FIRST FILTER WINDOW: {_fmt(first_start)} -> {_fmt(first_end)}")
    print(f"PROOF SAMPLE: {_fmt(start)} -> {_fmt(start + duration)}")
    print(f"WINDOW MUTE RANGES: {len(local)}")
    for idx, (a, b) in enumerate(local[:10]):
        print(f"  {idx}: +{a:.3f}s -> +{b:.3f}s")
    if len(local) > 10:
        print(f"  ... {len(local) - 10} more")
    print(f"AUDIO FILTER: {stream_filter.volume_filter(local)}")
    print(f"OUTPUT: {output}")
    print()

    cmd = stream_filter.sample_command(
        ffmpeg=ffmpeg,
        media=media,
        output=output,
        absolute_ranges=ranges,
        start=start,
        duration=duration,
        audio_stream=args.audio_stream,
    )
    print("Running FFmpeg server-side proof transcode...")
    proc = subprocess.run(cmd, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg failed with exit code {proc.returncode}")

    size = output.stat().st_size if output.is_file() else 0
    print(f"SUCCESS: {output} ({size:,} bytes)")
    print("Video was copied; only the selected audio stream was re-encoded with timestamp-based silence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
