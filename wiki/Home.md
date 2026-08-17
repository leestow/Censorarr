# Censorarr Wiki

**Applies to Censorarr 1.6.5**

Censorarr is a self-hosted clean-audio manager for movies and TV shows. It scans mounted media, transcribes dialogue, detects configured profanity, and can add a separate **English - CLEAN** audio track while preserving the original audio streams.

## What you actually need

Only two things are required:

1. A Movies and/or TV Shows folder mounted into the Censorarr container.
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

Censorarr works without Plex, Radarr, Sonarr, or Bazarr. Without Radarr/Sonarr, the Media pages fall back to the mounted folders.

## Recommended reading order

1. [Quick Start](Quick-Start.md)
2. [Synology Container Manager](Synology-Container-Manager.md) **or** [Docker / Linux Installation](Docker-Linux.md)
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

- a small test folder,
- **Dry Run** enabled,
- local CPU first if you want to validate the main install before adding the GPU Worker,
- optional integrations disabled until the core scan works.

Once Censorarr can see and analyze your test files correctly, add integrations one at a time.

## Important safety note

No speech-recognition or subtitle system can guarantee 100% profanity recall. Censorarr writes temporary output, validates it, and only then replaces the original pathname, but you should still keep backups of important media and test your settings before using Apply mode across a full library.
