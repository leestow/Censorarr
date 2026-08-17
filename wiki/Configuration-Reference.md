# Configuration Reference

The full example is in `config.example.yaml`.

The Setup Wizard and Settings UI manage most common values. This page explains the main groups.

## Core

| Setting | Example | Purpose |
|---|---|---|
| `media_roots` | `[/media]` | Movie roots |
| `extensions` | `.mkv, .mp4, .m4v` | Media extensions |
| `scan_interval_seconds` | `120` | Automatic scan interval |
| `stable_seconds` | `300` | Wait for new files to stop changing |
| `process_existing` | `true` | Include existing library |
| `dry_run` | `true` | Analyze without final media replacement |

## Setup

```yaml
setup:
  completed: false
  wizard_version: 1
```

Fresh installs remain idle until setup is completed.

## TV

```yaml
tv:
  enabled: true
  media_roots:
    - /tv
```

## Whisper

```yaml
whisper:
  backend: local
  model: small
  device: cpu
  compute_type: int8
  language: en
  beam_size: 5
  vad_filter: false
  condition_on_previous_text: false
```

Backend:

- `local`
- `remote`
- `auto`

Remote worker:

```yaml
remote:
  url: http://GPU-WORKER-IP:9000
  model: small.en
  timeout_seconds: 1800
  fallback_to_local: true
```

## Audio cache

```yaml
audio_cache:
  enabled: true
  directory: /work/audio-cache
  keep_after_success: false
```

Failed/cancelled work can reuse extracted transcription/rescue audio.

## Profanity

```yaml
profanity:
  file: /config/en.json
  min_severity: 3
  padding_before_ms: 120
  padding_after_ms: 160
  max_word_window: 4
```

## Precision alignment

```yaml
precision_alignment:
  enabled: true
  padding_before_ms: 25
  padding_after_ms: 40
  edge_search_ms: 120
  neighbor_guard_ms: 12
  energy_threshold_ratio: 0.22
  frame_ms: 5
```

## Rescue

Key defaults:

```yaml
rescue:
  enabled: true
  confidence_trigger: 0.18
  fuzzy_confidence_ceiling: 0.70
  fuzzy_similarity: 0.72
  prefer_center_channel: true
```

## Subtitle Assist

Key defaults:

```yaml
subtitle_assist:
  enabled: true
  use_embedded: true
  use_external: true
  global_text_alignment: true
```

Bazarr is nested under `subtitle_assist.bazarr`.

## *arr integrations

```yaml
arr_integrations:
  radarr:
    enabled: false
  sonarr:
    enabled: false
```

## Review mode

```yaml
review_mode:
  enabled: false
```

## CLEAN track

```yaml
clean_track:
  title: English - CLEAN
  language: eng
  place_clean_first: true
  make_default: true
  replace_existing_clean: true
  reprocess_existing_clean: false
  codec: auto
```

## Schedule

```yaml
processing_schedule:
  enabled: false
  start: "00:00"
  end: "23:59"
  days: [0, 1, 2, 3, 4, 5, 6]
```

## Worker concurrency

```yaml
worker:
  max_concurrent_jobs: 1
```

Censorarr deliberately serializes media modification for NAS safety.

## Safety

```yaml
safety:
  validate_output: true
  duration_tolerance_seconds: 2.0
  preserve_owner_mode: true
  backup_original: false
```

## Reports

```yaml
reports:
  directory: /config/reports
  keep_transcript_json: true
  keep_rescue_details: true
```

## Logging

```yaml
logging:
  level: INFO
  file: /config/censorarr.log
```

# Docker environment variables

Common environment variables in the shipped compose:

| Variable | Purpose |
|---|---|
| `TZ` | Container timezone |
| `CENSORARR_CONFIG` | Config path |
| `PUID` | Runtime user ID |
| `PGID` | Runtime group ID |
| `UMASK` | New-file permissions mask |
| `CENSORARR_SYNOLOGY_COMPAT_MODE` | `auto`, `true`, or `false` |
| `PLEX_TOKEN` | Optional Plex token fallback |
| `BAZARR_API_KEY` | Optional Bazarr API-key fallback |
| `ASR_WORKER_TOKEN` | Remote GPU worker token fallback |
| `WEB_USERNAME` | Optional web login username |
| `WEB_PASSWORD` | Optional web login password |
| `PUSHOVER_APP_TOKEN` | Optional notification secret |
| `PUSHOVER_USER_KEY` | Optional notification secret |
| `SMTP_PASSWORD` | Optional email secret |

# GPU Worker environment variables

| Variable | Shipped value/purpose |
|---|---|
| `ASR_MODEL` | `small.en` |
| `ASR_COMPUTE_TYPE` | `int8_float32` |
| `ASR_WORKER_TOKEN` | Must match main Censorarr |
| `ASR_MODEL_DIR` | `/models` |
| `ASR_CHUNK_SECONDS` | `600` |
| `ASR_CHUNK_OVERLAP_SECONDS` | `2` |
