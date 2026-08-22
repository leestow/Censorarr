"""Rewrite a Plex Transcoder argv to apply Censorarr mute ranges server-side.

This is the bridge between Plex's own transcoding pipeline and Censorarr's
media-timeline profanity ranges.  It does not poll a player or issue volume
commands.  Instead it injects a volume filter into Plex's existing audio
filter_complex graph so the outgoing audio bytes are already clean.

The first use is deliberately conservative: if a supported Plex audio graph or
Censorarr report cannot be identified, the argv is returned unchanged (fail
open) and a reason is reported.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path
from typing import Any

import stream_filter

_AUDIO_GRAPH_HINTS = ("aresample", "aformat", "pan=", "volume=")
_OUTPUT_LABEL_RE = re.compile(r"(\[[^\[\]]+\])\s*$")


def read_argv_file(path: Path) -> list[str]:
    data = path.read_bytes()
    if b"\0" in data:
        return [x.decode("utf-8", "surrogateescape") for x in data.split(b"\0") if x]
    return [line.rstrip("\r\n") for line in data.decode("utf-8", "surrogateescape").splitlines() if line.rstrip("\r\n")]


def _filter_complex_slots(argv: list[str]) -> list[int]:
    out: list[int] = []
    for i in range(len(argv) - 1):
        if argv[i] == "-filter_complex":
            out.append(i + 1)
    return out


def _audio_filter_slot(argv: list[str]) -> int | None:
    """Return the value index of Plex's audio filter_complex graph.

    Plex often emits separate -filter_complex arguments for video and audio.
    The captured Synology command has an aresample graph for audio, which is a
    strong and safe discriminator.  We intentionally do not guess when the
    graph shape is ambiguous.
    """
    candidates: list[int] = []
    for idx in _filter_complex_slots(argv):
        graph = argv[idx]
        low = graph.lower()
        if any(hint in low for hint in _AUDIO_GRAPH_HINTS) and _OUTPUT_LABEL_RE.search(graph):
            candidates.append(idx)
    if len(candidates) == 1:
        return candidates[0]
    # Prefer the single graph containing aresample when several audio-ish
    # graphs exist; this matches stock Plex transcode output on the current PMS.
    resample = [idx for idx in candidates if "aresample" in argv[idx].lower()]
    return resample[0] if len(resample) == 1 else None


def _inject_filter(graph: str, mute_filter: str) -> str | None:
    if "censorarr" in graph.lower():
        return graph
    match = _OUTPUT_LABEL_RE.search(graph)
    if not match:
        return None
    label = match.group(1)
    prefix = graph[: match.start()].rstrip()
    # The metadata filter is harmless to ffmpeg and gives captures/logs an
    # obvious marker that this graph passed through Censorarr.
    injected = f"{prefix},{mute_filter},ametadata=mode=add:key=censorarr:value=1{label}"
    return injected


def _timeline_ranges(argv: list[str], media_index: int, ranges: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], str, float]:
    seek = stream_filter.input_seek_seconds(argv, media_index)
    # Plex's captured command uses -copyts -start_at_zero. FFmpeg documents
    # that an input seek such as -ss 50 then retains a 50-second timestamp
    # origin, so Censorarr's absolute media timestamps are directly usable.
    if "-copyts" in argv and "-start_at_zero" in argv:
        # Ranges before the seek can never fire and only make the expression
        # longer. Keep a small margin for keyframe/accurate-seek preroll.
        keep_from = max(0.0, seek - 2.0)
        return [(a, b) for a, b in ranges if b >= keep_from], "absolute-copyts", seek

    # Fallback for non-copyts ffmpeg shapes: input -ss normally makes the
    # filtered timeline start near zero, so convert media times to seek-relative
    # times. This path remains conservative and clips intervals before zero.
    relative: list[tuple[float, float]] = []
    for a, b in ranges:
        if b <= seek:
            continue
        relative.append((max(0.0, a - seek), max(0.0, b - seek)))
    return relative, "seek-relative", seek


def rewrite_argv(
    argv: list[str],
    *,
    report_dir: Path = Path("/config/reports"),
    lead_ms: int = 35,
    tail_ms: int = 35,
    join_gap_ms: int = 20,
) -> tuple[list[str], dict[str, Any]]:
    original = list(argv)
    media_idx, media_raw = stream_filter.detect_media_argument(original)
    plan: dict[str, Any] = {
        "changed": False,
        "reason": "",
        "media": media_raw,
        "report": "",
        "seek_seconds": 0.0,
        "timeline_mode": "",
        "raw_ranges": 0,
        "merged_ranges": 0,
        "injected_ranges": 0,
        "audio_filter_index": None,
        "original_audio_filter": "",
        "rewritten_audio_filter": "",
    }
    if media_idx is None or not media_raw:
        plan["reason"] = "no-media-input"
        return original, plan

    report, raw_ranges = stream_filter.report_for_media(Path(media_raw), report_dir)
    plan["report"] = str(report)
    plan["raw_ranges"] = len(raw_ranges)
    if not report.is_file() or not raw_ranges:
        plan["reason"] = "no-censorarr-mute-ranges"
        return original, plan

    merged = stream_filter.merge_ranges(
        raw_ranges,
        lead_ms=lead_ms,
        tail_ms=tail_ms,
        join_gap_ms=join_gap_ms,
    )
    plan["merged_ranges"] = len(merged)
    timeline_ranges, mode, seek = _timeline_ranges(original, media_idx, merged)
    plan["timeline_mode"] = mode
    plan["seek_seconds"] = seek
    plan["injected_ranges"] = len(timeline_ranges)
    if not timeline_ranges:
        plan["reason"] = "no-ranges-after-current-seek"
        return original, plan

    slot = _audio_filter_slot(original)
    plan["audio_filter_index"] = slot
    if slot is None:
        plan["reason"] = "unsupported-or-ambiguous-audio-filter-graph"
        return original, plan

    mute_filter = stream_filter.volume_filter(timeline_ranges)
    rewritten_graph = _inject_filter(original[slot], mute_filter)
    if not rewritten_graph:
        plan["reason"] = "could-not-inject-audio-filter"
        return original, plan

    out = list(original)
    plan["original_audio_filter"] = original[slot]
    plan["rewritten_audio_filter"] = rewritten_graph
    out[slot] = rewritten_graph
    plan["changed"] = out != original
    plan["reason"] = "censorarr-filter-injected" if plan["changed"] else "already-filtered"
    return out, plan


def main() -> int:
    p = argparse.ArgumentParser(description="Rewrite captured Plex Transcoder argv with Censorarr audio mute ranges")
    p.add_argument("--args-file", required=True, help="Newline- or NUL-separated argv capture; executable may be first")
    p.add_argument("--report-dir", default="/config/reports")
    p.add_argument("--lead-ms", type=int, default=35)
    p.add_argument("--tail-ms", type=int, default=35)
    p.add_argument("--join-gap-ms", type=int, default=20)
    p.add_argument("--write-nul", default="", help="Optional path for rewritten NUL-separated argv")
    args = p.parse_args()

    argv = read_argv_file(Path(args.args_file))
    # /proc/<pid>/cmdline includes argv[0]. A real exec wrapper receives only
    # argv[1:], so strip a leading Plex Transcoder executable for analysis.
    if argv and Path(argv[0]).name == "Plex Transcoder":
        executable = argv.pop(0)
    else:
        executable = ""

    rewritten, plan = rewrite_argv(
        argv,
        report_dir=Path(args.report_dir),
        lead_ms=args.lead_ms,
        tail_ms=args.tail_ms,
        join_gap_ms=args.join_gap_ms,
    )

    print(json.dumps(plan, indent=2))
    print()
    if plan.get("changed"):
        print("REWRITTEN COMMAND PREVIEW:")
        preview = ([executable] if executable else ["Plex Transcoder"]) + rewritten
        print(shlex.join(preview))
    else:
        print("UNCHANGED: " + str(plan.get("reason") or "unknown"))

    if args.write_nul:
        output = ([executable] if executable else []) + rewritten
        Path(args.write_nul).write_bytes(b"\0".join(x.encode("utf-8", "surrogateescape") for x in output) + b"\0")
        print(f"WROTE: {args.write_nul}")

    return 0 if plan.get("changed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
