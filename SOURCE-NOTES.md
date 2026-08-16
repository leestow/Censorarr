# Censorarr 1.6.3 source notes

- `app/censorarr.py` — Movies/TV watcher, rating gates, Whisper/fuzzy rescue, subtitle-assisted rescue, review apply, safe remux/validation, markers/state, and effective profanity dictionary.
- `app/webapp.py` — FastAPI web manager and REST endpoints.
- `app/integrations.py` — Plex/Radarr/Sonarr/Bazarr integration helpers.
- `app/remote_asr.py` — main-server client for the optional Censorarr GPU Worker.
- `app/subtitle_assist.py` — subtitle parsing/alignment/rescue support.
- `app/static/index.html` — browser UI and Setup Wizard.
- `gpu-worker/app/worker.py` — optional NVIDIA Faster-Whisper worker with bounded long-audio chunking.
