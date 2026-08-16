# Censorarr 1.6.3

Censorarr is a self-hosted clean-audio manager for movies and TV shows. It detects configured profanity, keeps the original media streams, and adds or replaces a separate **CLEAN** audio track.

## What is required?

Only two things are required:

1. A Movies and/or TV media folder mounted into Censorarr.
2. A transcription engine: the local CPU, or the optional **Censorarr GPU Worker**.

Everything else is optional:

- **Plex** — adds rating-based filtering, playback-aware start gating, and library refreshes.
- **Radarr** — adds richer movie posters and metadata. Without it, the Movies page reads the local Movies folder directly.
- **Sonarr** — adds richer TV/episode metadata. Without it, the TV Shows page reads the local TV folder directly.
- **Bazarr** — can request missing text subtitles automatically. Local and embedded subtitle assistance works without Bazarr.
- **GPU Worker** — accelerates Whisper transcription. Censorarr can run transcription locally on CPU instead.

## First-run Setup Wizard

Fresh installations open a guided Setup Wizard automatically and remain idle until setup is completed. The wizard can be reopened later from **Settings → Setup Wizard**.

It walks through:

1. Movies and TV folders, plus Dry Run / Apply mode.
2. Local CPU vs remote GPU transcription.
3. Optional Plex setup.
4. Optional Radarr and Sonarr setup.
5. Subtitle assistance and optional Bazarr setup.
6. A final review before automatic processing is enabled.

**Start with Dry Run and test a small number of files before switching to Apply mode.**

## Installation choices

| What you want | What to install |
|---|---|
| Censorarr using CPU transcription | Main Censorarr project only |
| Censorarr with NVIDIA GPU acceleration | Main Censorarr + GPU Worker |
| GPU server for an existing Censorarr install | `gpu-worker/` only |
| No Plex / Radarr / Sonarr / Bazarr | Main Censorarr standalone |

### Main Censorarr

See [`INSTALL-FIRST.txt`](INSTALL-FIRST.txt), [`INSTALL-SOURCE.md`](INSTALL-SOURCE.md), and [`README-SYNOLOGY.md`](README-SYNOLOGY.md).

The included `docker-compose.yml` is a starting point. Change the host-side media paths, PUID/PGID, and any optional integration settings for your environment.

### GPU Worker only

The GPU worker is a self-contained Docker project inside [`gpu-worker/`](gpu-worker/).

```bash
git clone https://github.com/leestow/Censorarr.git
cd Censorarr/gpu-worker
# Edit docker-compose.yml and set ASR_WORKER_TOKEN
docker compose up -d --build
```

See [`gpu-worker/README.md`](gpu-worker/README.md) for the full GPU-worker setup.

## How CLEAN audio works

Censorarr preserves the original media streams and creates a separate profanity-muted audio track. Reprocessing replaces the existing CLEAN track instead of stacking additional CLEAN tracks.

Whisper performs the primary transcription. Censorarr can also use subtitle evidence and targeted rescue passes to improve recall. No speech-recognition system can guarantee 100% detection, so review/test important material before relying on automated processing.

## Safety

Censorarr writes a temporary output, validates it, and only then replaces the original pathname. Keep backups of important media and begin with **Dry Run** when evaluating a new installation.

## Credentials

Never commit runtime configuration or secrets. In particular, do not commit:

- `config/`
- `secrets.json`
- `.env` files
- API tokens
- logs/reports
- Whisper models
- backup snapshots containing configuration

The repository `.gitignore` excludes common runtime and secret locations, but you should still review changes before pushing them publicly.

## Acknowledgements

Censorarr's transcription engine is built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper), created by [Guillaume Klein](https://github.com/guillaumekln) and maintained with contributions from the faster-whisper community. Its CTranslate2-based implementation of Whisper provides the fast, memory-efficient speech-to-text foundation that makes Censorarr's detection pipeline possible.

A sincere thank-you to Guillaume Klein and everyone who has contributed to faster-whisper for making their work available to the open-source community.

faster-whisper itself is based on OpenAI's [Whisper](https://github.com/openai/whisper) speech-recognition model, so Censorarr also gratefully acknowledges the original Whisper project and its contributors.

## Project status

Censorarr is under active development. Bug reports, compatibility reports, and contributions are welcome through GitHub Issues and Pull Requests.
