from __future__ import annotations

import sys
import types

# Import the established Windows launcher first. Its module-level setup configures
# ProgramData, CENSORARR_CONFIG, model-cache variables, and bundled FFmpeg before
# the Censorarr web modules are imported.
import windows_launcher as launcher

import webapp
import webapp_core as core


# Censorarr 1.6.5 split the web entrypoint into webapp.py + webapp_core.py.
# The native Windows launcher predates that split and intentionally patches
# webapp module globals to map /config, /work, and /app to native Windows paths.
# Proxy those assignments into webapp_core so the tested launcher remains
# compatible with the current main branch without changing Docker behavior.
_CORE_PROXY_NAMES = {
    "Path",
    "CONFIG",
    "LOG",
    "HEARTBEAT",
    "STATE",
    "QUEUE",
    "CANCELLED",
    "PAUSED",
    "SCAN_NOW",
    "RESTART_AFTER_CURRENT",
    "SUBTITLE_WAIT",
    "INVENTORY",
    "CUSTOM_PROFANITY",
    "PROFANITY_OVERRIDES",
    "USER_EXCEPTIONS",
    "STATIC",
    "FIRST_RUN",
    "_allowed_media_mounts",
    "safe_media_path",
}

for _name in _CORE_PROXY_NAMES:
    if hasattr(core, _name):
        setattr(webapp, _name, getattr(core, _name))

# The Windows launcher replaces WorkerSupervisor.start so the worker is another
# background copy of the installed Censorarr.exe.
webapp.WorkerSupervisor = core.WorkerSupervisor


class _WebappProxy(types.ModuleType):
    def __setattr__(self, name, value):
        if name in _CORE_PROXY_NAMES:
            setattr(core, name, value)
        super().__setattr__(name, value)


sys.modules["webapp"].__class__ = _WebappProxy


if __name__ == "__main__":
    raise SystemExit(launcher.main())
