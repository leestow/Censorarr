# Censorarr 1.6.4 — Synology Installation

Censorarr can run standalone against mounted Movies and TV Shows folders. Plex, Radarr, Sonarr, Bazarr, and the remote GPU Worker are optional integrations.

## What the optional integrations add

- **Plex** — rating filters, playback-aware start gating, and library refreshes.
- **Radarr** — movie metadata/posters for the Movies page.
- **Sonarr** — TV metadata for the TV Shows page.
- **Bazarr** — automatic requests for missing text subtitles.
- **Censorarr GPU Worker** — NVIDIA-accelerated Whisper transcription on another server.

Without Radarr/Sonarr, the Media pages fall back to the mounted folders. Without Plex, rating/Plex-specific features can be disabled. Without Bazarr, Censorarr can still use local/embedded subtitles and Whisper. Without a GPU Worker, transcription runs locally on CPU.

## Recommended Synology layout

A common project location is:

```text
/volume1/docker/censorarr/
```

Typical mounts are:

- `/volume1/Movies` → `/media`
- `/volume1/TV Shows` → `/tv`
- `/volume1/docker/censorarr/config` → `/config`
- `/volume1/docker/censorarr/work` → `/work`

Change the **left side** of the media mounts in `docker-compose.yml` to match your Synology shares.

## Install

1. Copy or clone the source into `/volume1/docker/censorarr` (or another project folder).
2. Edit `docker-compose.yml`.
3. Set the host-side Movies/TV paths.
4. Set `PUID`, `PGID`, `UMASK`, and `TZ` for your environment.
5. Add credentials only for integrations you intend to use.
6. In DSM Container Manager, create/start the project from the Censorarr folder, or from SSH run:

```bash
cd /volume1/docker/censorarr
sudo docker compose up -d --build
```

7. Browse to the host port from `docker-compose.yml` (the shipped example is `8087:8787`).
8. Complete the guided Setup Wizard.
9. Start in **Dry Run** and test a small number of files before enabling Apply mode.

## Permissions

Censorarr normally runs as the configured numeric `PUID`/`PGID` and intentionally does not recursively change ownership on `/media` or `/tv`. With the shipped `CENSORARR_SYNOLOGY_COMPAT_MODE=auto`, Censorarr first tests that identity against the mounted media folders. If DSM ACLs block it but container root can access the same mount, Censorarr falls back to root for compatibility and logs the reason. Set the mode to `false` to forbid that fallback, or `true` to always run as container root.

Find the IDs for a Synology user that can read/write both media shares:

```bash
id YOUR_USERNAME
```

Example:

```yaml
environment:
  PUID: "1026"
  PGID: "100"
  UMASK: "002"
```

## Persistent files

Runtime data normally lives under `/config` and `/work`, including:

- `/config/config.yaml`
- `/config/censorarr.log`
- `/config/state.json`
- `/config/reports/`
- `/config/models/`
- `/config/custom_profanity.json`
- `/config/profanity_overrides.json`
- `/config/user_exceptions.json`

Each completed media directory uses `.censorarr.done.json` as the default durable completion marker.

## CLEAN audio behavior

Censorarr preserves retained original streams and adds one `English - CLEAN` audio track by default. Reprocessing replaces the previous CLEAN track instead of stacking duplicates.

Censorarr writes a temporary output, validates it, and only then replaces the original pathname.

## Subtitle assistance

Censorarr can use external text subtitles and embedded English text subtitles. Bazarr is optional and only adds automatic subtitle acquisition. Subtitle evidence is additive to Whisper rather than replacing it.

## GPU Worker

For NVIDIA acceleration on another host, install only the `gpu-worker/` project and use the same `ASR_WORKER_TOKEN` on both machines. See [`gpu-worker/README.md`](gpu-worker/README.md).

The shipped worker defaults to `small.en`, `int8_float32`, 600-second chunks, and 2-second overlap.

## Self-test

Inside the running main container:

```bash
docker exec -it censorarr python /app/selftest.py
```

The v1.6.4 self-test covers dictionary/fuzzy matching, large mute lists, subtitle alignment, progress mapping, MP4 metadata/default-track handling, precision mute behavior, schedules, TV/rating logic, and Sonarr episode path mapping.

## Limits

No ASR/subtitle system guarantees 100% profanity recall. Test your configuration and use Review Mode where accuracy is especially important.
