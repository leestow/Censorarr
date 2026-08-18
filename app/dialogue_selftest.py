#!/usr/bin/env python3
"""Small dependency-free self-test for the experimental Dialogue Enhancement layer."""
from __future__ import annotations

from types import SimpleNamespace

import dialogue_enhancement as de


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_filters() -> None:
    stereo = de._dialogue_filter({"channels": 2, "channel_layout": "stereo"}, "medium")
    check("pan=stereo" not in stereo, "Stereo input should keep native stereo before speech processing")
    check("equalizer=f=2500" in stereo, "Speech presence EQ missing")
    check("acompressor=" in stereo, "Dialogue compression missing")
    check("alimiter=" in stereo, "Peak limiter missing")

    five_one = de._dialogue_filter({"channels": 6, "channel_layout": "5.1(side)"}, "medium")
    check("pan=stereo" in five_one, "5.1 source should use explicit dialogue-focused downmix")
    check("*FC" in five_one and "*SL" in five_one and "*SR" in five_one, "5.1(side) channel mix is incomplete")

    seven_one = de._dialogue_filter({"channels": 8, "channel_layout": "7.1"}, "strong")
    check("*FC" in seven_one, "7.1 source must emphasize center dialogue")
    check("*BL" in seven_one and "*BR" in seven_one and "*SL" in seven_one and "*SR" in seven_one,
          "7.1 source should retain a small amount of surround ambience")


def test_title_detection() -> None:
    probe = {
        "streams": [
            {"codec_type": "video", "index": 0},
            {"codec_type": "audio", "index": 1, "tags": {"title": "English - CLEAN"}},
            {"codec_type": "audio", "index": 2, "tags": {"handler_name": "English - DIALOGUE ENHANCED"}},
        ]
    }
    found = de._find_named_audio(probe, "English - DIALOGUE ENHANCED")
    check(len(found) == 1 and found[0][1] == 1, "Dialogue title/handler_name matching failed")


def _fake_pc():
    pc = SimpleNamespace()
    pc.DEFAULT_CONFIG = {}
    pc.remux_with_clean_track = lambda *args, **kwargs: None
    pc.validate_output = lambda *args, **kwargs: None
    pc.duration_of = lambda probe: float((probe.get("format") or {}).get("duration", 0) or 0)

    def find_clean(probe, title):
        rows = []
        rel = 0
        wanted = str(title).lower()
        for stream in probe.get("streams", []):
            if stream.get("codec_type") != "audio":
                continue
            tags = stream.get("tags") or {}
            label = str(tags.get("title") or tags.get("handler_name") or "").lower()
            if label == wanted:
                rows.append((stream, rel))
            rel += 1
        return rows

    pc.find_clean_audio_streams = find_clean
    return pc


def _source_probe():
    return {
        "format": {"duration": 100.0},
        "streams": [
            {"codec_type": "video", "index": 0, "codec_name": "h264"},
            {"codec_type": "audio", "index": 1, "codec_name": "aac", "disposition": {"default": True}, "tags": {"language": "eng"}},
        ],
    }


def _output_probe(*, dialogue_default: bool, clean_default: bool):
    return {
        "format": {"duration": 100.0},
        "streams": [
            {"codec_type": "video", "index": 0, "codec_name": "h264"},
            {"codec_type": "audio", "index": 1, "codec_name": "aac", "disposition": {"default": clean_default},
             "tags": {"title": "English - CLEAN", "language": "eng"}},
            {"codec_type": "audio", "index": 2, "codec_name": "aac", "disposition": {"default": False},
             "tags": {"title": "English", "language": "eng"}},
            {"codec_type": "audio", "index": 3, "codec_name": "aac", "disposition": {"default": dialogue_default},
             "tags": {"title": "English - DIALOGUE ENHANCED", "language": "eng"}},
        ],
    }


def test_default_validation() -> None:
    pc = _fake_pc()
    de.install(pc)

    base_cfg = {
        "clean_track": {"title": "English - CLEAN", "place_clean_first": True, "make_default": True},
        "dialogue_enhancement": {
            **de.DEFAULTS,
            "enabled": True,
            "title": "English - DIALOGUE ENHANCED",
        },
        "safety": {"duration_tolerance_seconds": 2.0},
    }

    # Normal mode: CLEAN remains the default.
    cfg = {**base_cfg, "dialogue_enhancement": {**base_cfg["dialogue_enhancement"], "make_default": False}}
    pc.validate_output(_source_probe(), _output_probe(dialogue_default=False, clean_default=True), cfg)

    # User override: Dialogue Enhanced becomes the sole default and CLEAN may lose default disposition.
    cfg = {**base_cfg, "dialogue_enhancement": {**base_cfg["dialogue_enhancement"], "make_default": True}}
    pc.validate_output(_source_probe(), _output_probe(dialogue_default=True, clean_default=False), cfg)


def main() -> int:
    test_filters()
    test_title_detection()
    test_default_validation()
    print("Dialogue Enhancement self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
