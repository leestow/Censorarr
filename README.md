# Censorarr 1.6.3

Censorarr is a self-hosted clean-audio manager for movies and TV shows. It detects configured profanity, preserves the original media streams, and adds or replaces a separate **CLEAN** audio track.

## What is required?

Only two things are required:

1. A Movies and/or TV Shows folder mounted into Censorarr.
2. A transcription engine: local CPU transcription, or the optional **Censorarr GPU Worker**.

Everything else is optional:

- **Plex** — rating-based filtering, playback-aware start gating, and library refreshes.
- **Radarr** — richer movie metadata and posters. Without Radarr, Censorarr reads the Movies folder directly.
- **Sonarr** — richer TV metadata. Without Sonarr, Censorarr reads the TV Shows folder directly.
- **Bazarr** — can request missing text subtitles automatically. Local/embedded subtitle assistance works without Bazarr.
- **GPU Worker** — accelerates transcription on an NVIDIA GPU. Censorarr can use CPU transcription without it.

## Guided setup

Fresh installations open a guided Setup Wizard automatically and remain idle until setup is completed. The wizard can be reopened from **Settings → Setup Wizard**.

It walks through media folders, Dry Run/Apply mode, CPU vs GPU transcription, optional Plex, optional Radarr/Sonarr, subtitle assistance/Bazarr, and a final review.

> Start with **Dry Run** and test a small number of files before switching to Apply mode.

## Installation choices

| Goal | Install |
|---|---|
| Censorarr using CPU transcription | Main Censorarr project only |
| Censorarr with NVIDIA GPU acceleration | Main Censorarr + GPU Worker |
| GPU server for an existing Censorarr installation | `gpu-worker/` only |
| No Plex/Radarr/Sonarr/Bazarr | Main Censorarr standalone |

### Main Censorarr

See [`INSTALL-SOURCE.md`](INSTALL-SOURCE.md) and [`README-SYNOLOGY.md`](README-SYNOLOGY.md). The included `docker-compose.yml` is a starting point; change host-side media paths, PUID/PGID, timezone, and any optional integration credentials for your environment.

### GPU Worker only

The GPU worker is fully self-contained under [`gpu-worker/`](gpu-worker/).

```bash
git clone https://github.com/leestow/Censorarr.git
cd Censorarr/gpu-worker
# Edit docker-compose.yml and set ASR_WORKER_TOKEN
docker compose up -d --build
```

See [`gpu-worker/README.md`](gpu-worker/README.md).

## How CLEAN audio works

Censorarr preserves the original video/audio/subtitle streams and creates a separate profanity-muted audio track. Reprocessing replaces an existing CLEAN track instead of stacking additional copies.

Whisper performs the primary transcription. Censorarr can also use subtitle evidence and targeted rescue passes to improve recall. No speech-recognition system can guarantee 100% detection, so review/test important material before relying on automated processing.

## Security

Never commit runtime configuration or secrets. In particular, do not commit `config/`, `.env` files, `secrets.json`, API tokens, logs, reports, model caches, or backup snapshots containing configuration. The included `.gitignore` excludes common secret/runtime locations.

## Project status

Censorarr is under active development. Bug reports, compatibility reports, and contributions are welcome through GitHub Issues and Pull Requests.
