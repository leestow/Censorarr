# First-Run Setup Wizard

Fresh installations stay idle until the Setup Wizard is completed.

You can reopen it later from **Settings → Setup Wizard**.

## Setup Wizard interface

The first-run wizard walks through required media/transcription settings and optional integrations step by step.

![Censorarr Setup Wizard](https://raw.githubusercontent.com/leestow/Censorarr/main/docs/screenshots/setup-wizard.jpg)

## Step 1 — Media folders

Typical container paths:

```text
Movies: /media
TV:     /tv
```

On native Windows, use real Windows paths such as `D:\Movies`, `E:\TV Shows`, a mapped drive, or a reachable UNC path.

For a new installation, start with a small test folder or a small media set so you can verify permissions, transcription, CLEAN-track creation, and playback before expanding to the full library.

## Step 2 — Transcription backend

Choose one:

### Local CPU

Best for initial validation or systems without an NVIDIA worker.

Default configuration uses CPU/int8.

### Remote GPU

Use the Censorarr GPU Worker only.

You need:

- worker URL, e.g. `http://GPU-IP:9000`
- matching worker token
- reachable TCP 9000

### Auto

Uses the GPU Worker with local CPU fallback when configured.

See [Transcription & GPU Worker](Transcription-and-GPU-Worker.md).

## Step 3 — Plex (optional)

Skip this if you do not need Plex-specific features.

Plex can add:

- rating filters
- playback-aware start gating
- library refresh after processing

See [Plex Integration](Plex-Integration.md).

## Step 4 — Radarr and Sonarr (optional)

These are metadata integrations. They are **not required** for scanning or processing media.

- Radarr enriches Movies
- Sonarr enriches TV Shows

See [Radarr & Sonarr](Radarr-and-Sonarr.md).

## Step 5 — Subtitle Assist / Bazarr

Subtitle Assist can use:

- external subtitle files
- embedded English text subtitles
- optional Bazarr downloads

Bazarr is not required.

See [Bazarr & Subtitle Assist](Bazarr-and-Subtitles.md).

## Step 6 — Review

Verify:

- correct media roots
- backend selection
- optional integrations you actually want
- that your test media is backed up if it is important

Finish setup only after the media permission checks pass.

## Recommended first-run sequence

For troubleshooting, do not enable everything at once.

1. Core + local CPU + small test media set
2. Verify file discovery
3. Verify transcription/detection and CLEAN-track output
4. Add GPU Worker
5. Add Plex
6. Add Radarr/Sonarr
7. Add Bazarr
8. Expand to the full library after the test files behave as expected