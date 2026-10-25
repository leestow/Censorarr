"""No-Plex-server regression tests for experimental fast-start changes."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import plex_filtered_handoff as handoff  # noqa: E402
import plex_transcoder_shim as shim  # noqa: E402


class ReportLookupTests(unittest.TestCase):
    def test_does_not_parse_unrelated_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for n in range(1000):
                (root / f"Other-Movie-{n:04d}-{'a' * 10}.json").write_text(
                    '{"file":"/other/Other Movie.mkv","mute_ranges":[]}', encoding="utf-8"
                )
            matched = root / "Target_Movie-1234567890.json"
            matched.write_text(json.dumps({
                "file": "/media/Target Movie.mkv",
                "mute_ranges": [{"start": 23.1, "end": 23.5}],
            }), encoding="utf-8")
            reads: list[Path] = []
            original = shim._read_json

            def count_reads(path: Path):
                reads.append(path)
                return original(path)

            with patch.object(shim, "REPORT_DIR", root), patch.object(shim, "_read_json", count_reads):
                report, ranges = shim._report_for_media(Path("/synology/Target Movie.mkv"))
            self.assertEqual(report, matched)
            self.assertEqual(ranges, [(23.1, 23.5)])
            self.assertEqual(reads, [matched], "Only the target report should be opened")

    def test_case_insensitive_legacy_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            match = root / "a_movie-abcdef1234.json"
            match.write_text(json.dumps({
                "file": "/container/a_movie.MKV",
                "mute_ranges": [{"start": 12, "end": 13}],
            }), encoding="utf-8")
            with patch.object(shim, "REPORT_DIR", root):
                report, ranges = shim._report_for_media(Path("/nas/A_MOVIE.MKV"))
            self.assertEqual(report, match)
            self.assertEqual(ranges, [(12.0, 13.0)])

    def test_duplicate_basenames_do_not_choose_wrong_movie(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, folder in enumerate(["A", "B"]):
                (root / f"Same_Movie-{index:010x}.json").write_text(json.dumps({
                    "file": f"/archive/{folder}/Same Movie.mkv",
                    "mute_ranges": [{"start": 20 + index, "end": 22 + index}],
                }), encoding="utf-8")
            with patch.object(shim, "REPORT_DIR", root):
                report, ranges = shim._report_for_media(Path("/plex/Same Movie.mkv"))
                exact, exact_ranges = shim._report_for_media(Path("/archive/B/Same Movie.mkv"))
            self.assertIsNone(report)
            self.assertEqual(ranges, [])
            self.assertEqual(exact, root / "Same_Movie-0000000001.json")
            self.assertEqual(exact_ranges, [(21.0, 23.0)])


class DecisionLatencyTests(unittest.TestCase):
    def make_state(self, root: Path) -> handoff.HandoffState:
        state = handoff.HandoffState.__new__(handoff.HandoffState)
        state.sessions = {}
        state.pending_decisions = {}
        state.lock = threading.RLock()
        state.plex_host = "127.0.0.1"
        state.plex_port = 32400
        state.allowlist = root / "allowlist.txt"
        state.allowlist.write_text("Target Movie.mkv\n", encoding="utf-8")
        state.log = lambda message: None
        return state

    def test_decision_returns_before_slow_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state = self.make_state(Path(temp))
            begin = threading.Event()
            release = threading.Event()
            calls = []
            xml = (
                b'<MediaContainer><Video duration="7200000">'
                b'<Media duration="7200000"><Part id="42" size="8000000000" '
                b'file="/movies/Target Movie.mkv" /></Media></Video></MediaContainer>'
            )

            def slow_lookup(request, timeout):
                calls.append(request)
                begin.set()
                self.assertTrue(release.wait(2), "test background lookup must be released")
                return type("Reply", (), {"read": lambda self: xml})()

            target = ("/video/:/transcode/universal/decision?"
                      "path=%2Flibrary%2Fmetadata%2F123&X-Plex-Token=dummy")
            headers = {"x-plex-session-id": "session-1"}
            with patch.object(handoff, "urlopen", slow_lookup):
                t0 = time.monotonic()
                state.remember_decision("192.0.2.10", target, headers)
                duration = time.monotonic() - t0
                self.assertLess(duration, 0.2, "playback decision should never await metadata")
                self.assertTrue(begin.wait(1))
                release.set()
                found = state.lookup_file("192.0.2.10", headers, "42")
                self.assertIsNotNone(found)
                self.assertTrue(found["eligible"])
                self.assertEqual(len(calls), 1)
                # Repeated Plex decisions must reuse an already-resolved cache.
                state.remember_decision("192.0.2.10", target, headers)
                self.assertEqual(len(calls), 1)

    def test_file_lookup_wait_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state = self.make_state(Path(temp))
            blocker = threading.Event()
            key = ("192.0.2.10", "session-2")
            state.pending_decisions[key] = blocker
            t0 = time.monotonic()
            row = state.lookup_file(key[0], {"x-plex-session-id": key[1]}, "42")
            elapsed = time.monotonic() - t0
            self.assertIsNone(row)
            self.assertGreaterEqual(elapsed, 0.5)
            self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
