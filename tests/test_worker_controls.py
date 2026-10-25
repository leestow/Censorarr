"""Dependency-free regression tests for shared process-control and log-clear code.

The production module has heavyweight media dependencies. Extract only the
functions under test via AST so these safety tests can run on every PR without
Whisper, FFmpeg, a media share, or a GPU.
"""
from __future__ import annotations

import ast
import json
import os
import signal
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "app" / "webapp_core.py"


def extract(*names, variables=None):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    selected = [
        node for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names
    ]
    if len(selected) != len(names):
        raise AssertionError(f"Missing definitions: {set(names) - {n.name for n in selected}}")
    for node in selected:
        node.decorator_list = []
    namespace = {
        "os": os, "signal": signal, "subprocess": subprocess,
        "threading": threading, "time": time, "Path": Path,
        "Depends": lambda *args, **kwargs: None,
        "auth": lambda: True,
    }
    namespace.update(variables or {})
    compiled = compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])),
                       str(SOURCE), "exec", flags=__import__("__future__").annotations.compiler_flag)
    exec(compiled, namespace)
    return namespace


class StopCurrentTests(unittest.TestCase):
    def test_stop_removes_active_manual_job_but_keeps_next_job(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            movie = root / "movie.mp4"
            other = root / "other.mp4"
            movie.write_bytes(b"sample")
            files = {
                "HEARTBEAT": root / "heartbeat.json",
                "QUEUE": root / "queue.json",
                "CANCELLED": root / "cancelled.json",
                "STATE": root / "state.json",
                "CONFIG": root / "config.yaml",
                "VERSION": "test",
            }

            def read_json(path, default):
                return json.loads(path.read_text()) if path.exists() else default

            def write_json(path, data):
                path.write_text(json.dumps(data))

            files.update({
                "read_json": read_json,
                "write_json": write_json,
                "pc": SimpleNamespace(
                    load_config=lambda _: {}, fingerprint=lambda _: "fingerprint"
                ),
                "remote_asr": SimpleNamespace(enabled=lambda _: False),
            })
            write_json(files["HEARTBEAT"], {
                "current": str(movie), "status": "transcribing"
            })
            write_json(files["QUEUE"], [
                {"id": "active", "path": str(movie)},
                {"id": "next", "path": str(other)},
            ])
            worker_class = extract("WorkerSupervisor", variables=files)["WorkerSupervisor"]
            worker = worker_class()
            calls = []
            worker.stop_process = lambda graceful_seconds: calls.append("stop")
            worker.start = lambda: calls.append("start")
            result = worker.stop_current()

            self.assertTrue(result["ok"])
            self.assertEqual(calls, ["stop", "start"])
            self.assertEqual(read_json(files["QUEUE"], []),
                             [{"id": "next", "path": str(other)}])
            self.assertEqual(read_json(files["STATE"], {})["files"][str(movie)]["status"],
                             "cancelled")
            self.assertIn(str(movie), read_json(files["CANCELLED"], {}))
            self.assertIsNone(read_json(files["HEARTBEAT"], {})["current"])

    def test_stop_with_no_active_job_does_not_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            heartbeat = Path(folder) / "hb.json"
            heartbeat.write_text('{"status":"idle","current":null}')
            ns = extract("WorkerSupervisor", variables={
                "HEARTBEAT": heartbeat,
                "read_json": lambda p, d: json.loads(p.read_text()),
            })
            worker = ns["WorkerSupervisor"]()
            worker.stop_process = lambda **kwargs: self.fail("No process should stop")
            worker.start = lambda: self.fail("No process should restart")
            self.assertFalse(worker.stop_current()["ok"])


class LogClearTests(unittest.TestCase):
    def test_clear_does_not_truncate_an_open_worker_log_handle(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "censorarr.log"
            path.write_text("previous run\n")
            marker = "=== CENSORARR USER LOG CLEAR BOUNDARY ==="
            ns = extract("visible_log_text", "log_clear", variables={
                "LOG": path, "LOG_CLEAR_MARKER": marker,
            })
            with path.open("a", encoding="utf-8") as active_writer:
                ns["log_clear"]()
                active_writer.write("new processing message\n")
                active_writer.flush()
            self.assertEqual(ns["visible_log_text"](), "new processing message\n")
            # The original log remains on disk for the worker; the UI shows only
            # entries after the marker, avoiding a writer-handle race.
            self.assertIn("previous run", path.read_text())
            self.assertIn(marker, path.read_text())


class WindowsMediaRootTests(unittest.TestCase):
    def test_authenticated_new_root_is_separate_from_browse_restrictions(self):
        """A new folder is configurable, but browsing remains constrained to old roots."""
        windows_source = SOURCE.parents[1] / "windows" / "windows_launcher.py"
        tree = ast.parse(windows_source.read_text(encoding="utf-8"))
        nodes = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name in {
                "safe_media_path_windows", "validate_new_media_root_windows"
            }
        ]
        self.assertEqual(len(nodes), 2)

        class FakeHTTPException(Exception):
            def __init__(self, code, detail):
                self.status_code = code
                self.detail = detail

        namespace = {
            "_RealPath": Path,
            "webapp": SimpleNamespace(HTTPException=FakeHTTPException),
        }
        for node in nodes:
            node.decorator_list = []
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                     str(windows_source), "exec"), namespace)

        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder) / "existing"
            new = Path(folder) / "new"
            old.mkdir()
            new.mkdir()
            namespace["configured_media_roots"] = lambda: ([old.resolve()], True)
            namespace["allowed_media_mounts_windows"] = lambda: [old.resolve()]
            browse = namespace["safe_media_path_windows"]
            adopt = namespace["validate_new_media_root_windows"]

            self.assertEqual(adopt(str(new)), new.resolve())
            self.assertEqual(browse(str(old)), old.resolve())
            with self.assertRaises(FakeHTTPException) as result:
                browse(str(new))
            self.assertEqual(result.exception.status_code, 403)
            with self.assertRaises(FakeHTTPException):
                adopt("relative-folder")

if __name__ == "__main__":
    unittest.main()
