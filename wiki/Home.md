# Censorarr Wiki

**Applies to Censorarr 1.6.9**

Censorarr is a self-hosted clean-audio manager for movies and TV shows. It scans media, transcribes dialogue, detects configured profanity, and can add a separate **English - CLEAN** audio track while preserving the original audio streams.

## Installation options

Choose the guide for your platform:

- **[Windows Installation](Windows-Installation.md)** — native Windows 11 x64 installer, no Docker required.
- **[Native Linux Installation](Linux-Installation.md)** — Debian/Ubuntu-family x86_64 `.deb`, no Docker required.
- **[Synology Container Manager](Synology-Container-Manager.md)** — recommended Synology deployment.
- **[Docker / Linux Installation](Docker-Linux.md)** — standard Docker deployment.

## What you actually need

Only two things are required:

1. A Movies and/or TV Shows folder available to Censorarr.
2. A transcription backend:
   - local CPU, or
   - the optional Censorarr GPU Worker on another NVIDIA-equipped host.

Everything else is optional.

| Integration | Required? | What it adds |
|---|---:|---|
| Plex | No | Rating filters, playback-aware start gating, library refresh |
| Radarr | No | Movie posters and richer movie metadata |
| Sonarr | No | TV/episode metadata |
| Bazarr | No | Automatic subtitle acquisition |
| GPU Worker | No | NVIDIA-accelerated Whisper transcription |

Censorarr works without Plex, Radarr, Sonarr, or Bazarr. Without Radarr/Sonarr, the Media pages fall back to the configured media folders.

## Interface tour

### Dashboard

The Dashboard shows current processing, queue status, GPU-worker progress, system information, and live logs.

![Censorarr dashboard](https://raw.githubusercontent.com/leestow/Censorarr/main/docs/screenshots/dashboard.jpg)

### Movies library

The Movies page shows posters, metadata, quality, and each movie's current Censorarr status.

![Censorarr Movies library](https://raw.githubusercontent.com/leestow/Censorarr/main/docs/screenshots/movies-library.jpg)

### Movie details

Open a movie for a detailed view of its file, metadata, CLEAN conversion status, and processing controls.

![Censorarr movie details](https://raw.githubusercontent.com/leestow/Censorarr/main/docs/screenshots/movie-details.jpg)

## Recommended reading order

1. [Quick Start](Quick-Start.md)
2. Pick your installation guide:
   - [Windows Installation](Windows-Installation.md)
   - [Native Linux Installation](Linux-Installation.md)
   - [Synology Container Manager](Synology-Container-Manager.md)
   - [Docker / Linux Installation](Docker-Linux.md)
3. [First-Run Setup Wizard](Setup-Wizard.md)
4. [Media Folders & Permissions](Media-Folders-and-Permissions.md)
5. [Transcription & GPU Worker](Transcription-and-GPU-Worker.md)
6. Optional integrations:
   - [Plex](Plex-Integration.md)
   - [Radarr & Sonarr](Radarr-and-Sonarr.md)
   - [Bazarr & Subtitle Assist](Bazarr-and-Subtitles.md)
7. [Profanity & Detection](Profanity-and-Detection.md)
8. [CLEAN Audio, Review & Safety](Clean-Audio-Review-and-Safety.md)
9. [Scheduling & Notifications](Scheduling-and-Notifications.md)
10. [Updating](Updating.md)
11. [Troubleshooting](Troubleshooting.md)
12. [Configuration Reference](Configuration-Reference.md)
13. [Security & Secrets](Security-and-Secrets.md)

## Strong recommendation for a new install

Start with:

- a small test folder or small media set,
- local CPU first if you want to validate the main install before adding the GPU Worker,
- optional integrations disabled until the core scan works.

Once Censorarr can see and process your test files correctly, add integrations one at a time.

## Important safety note

No speech-recognition or subtitle system can guarantee 100% profanity recall. Censorarr writes temporary output, validates it, and only then replaces the original pathname, but you should still keep backups of important media and test your settings on a small media set before using automated processing across a full library.