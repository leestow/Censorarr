# Censorarr 1.6.5 source notes

- `app/censorarr.py` — Movies/TV watcher, rating gates, Whisper/fuzzy rescue, subtitle-assisted rescue, review apply, safe remux/validation, markers/state, and effective profanity dictionary.
- `app/webapp.py` — FastAPI web manager and REST endpoints.
- `app/integrations.py` — Plex/Radarr/Sonarr/Bazarr integration helpers.
- `app/remote_asr.py` — main-server client for the optional Censorarr GPU Worker.
- `app/subtitle_assist.py` — subtitle parsing/alignment/rescue support.
- `app/static/index.html` — browser UI and Setup Wizard.
- `gpu-worker/app/worker.py` — optional NVIDIA Faster-Whisper worker with bounded long-audio chunking.


Synology permission compatibility (v1.6.5):
- CENSORARR_SYNOLOGY_COMPAT_MODE=auto is recommended for DSM Container Manager.
- auto uses PUID/PGID normally and falls back to container root only if DSM ACLs block that identity from a media mount while root can access it.
- false forbids root fallback; true always uses container root.
- Censorarr checks media access before loading Whisper and waits with a clear permission error instead of crash-looping.
