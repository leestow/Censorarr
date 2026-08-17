# Bazarr & Subtitle Assist

Subtitle Assist is built into Censorarr. Bazarr is optional.

## What Subtitle Assist can use

- external text subtitle files
- embedded English text subtitles
- optionally, subtitles requested through Bazarr

Subtitle evidence augments Whisper. It does not replace Whisper and does not suppress profanity Whisper already detected.

## Default Subtitle Assist behavior

The example configuration enables:

```yaml
subtitle_assist:
  enabled: true
  use_embedded: true
  use_external: true
  ignore_forced_only: true
  accept_untagged_english: true
  use_dialogue_as_rescue_prompt: true
  whisper_overrides_omissions: true
  global_text_alignment: true
```

Global alignment helps when subtitle timing is shifted or drifts.

## Enable Bazarr

Example:

```yaml
subtitle_assist:
  bazarr:
    enabled: true
    url: http://BAZARR-SERVER-IP:6767
```

Save the Bazarr API key through Censorarr Settings.

## Movie path mapping

If Bazarr/Radarr reports:

```text
/movies/Movie Name/Movie.mkv
```

and Censorarr sees:

```text
/media/Movie Name/Movie.mkv
```

use:

```yaml
path_mappings:
  - from: /movies
    to: /media
```

## TV path mapping

Example:

```yaml
tv_path_mappings:
  - from: /tv
    to: /tv
```

The left and right can be identical if both containers use the same internal path.

## Waiting behavior

The example configuration includes:

```yaml
wait_for_download: true
timeout_minutes: 30
check_interval_seconds: 30
retry_seconds: 300
max_attempts: 3
```

This lets Censorarr defer a job while it waits for subtitle acquisition rather than immediately abandoning subtitle assistance.

## Bazarr is not required

If you do not use Bazarr, leave it disabled. Censorarr can still use existing external/embedded subtitles and Whisper rescue logic.
