# CLEAN Audio, Review & Safety

## CLEAN track behavior

Default configuration:

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

Censorarr preserves retained original media streams and creates a separate CLEAN audio track.

Reprocessing replaces the existing CLEAN track rather than stacking additional CLEAN tracks.

## Original audio

Censorarr does not intentionally destroy the retained original audio track when adding the CLEAN version.

## Dry Run

```yaml
dry_run: true
```

Use this for initial evaluation.

Dry Run still reads/transcribes media but does not perform the final media replacement.

## Review Mode

```yaml
review_mode:
  enabled: true
```

When enabled, analysis stops at the review screen.

Approving uses the existing analysis report, so the file does not need to be transcribed again.

## Safe replacement

Default safety settings:

```yaml
safety:
  validate_output: true
  duration_tolerance_seconds: 2.0
  preserve_owner_mode: true
  backup_original: false
```

Censorarr creates temporary output, validates it, and only then replaces the original pathname.

If you want an additional original-file backup, enable:

```yaml
backup_original: true
```

Understand the storage impact before enabling it across a large library.

## Completion markers

Default marker:

```text
.censorarr.done.json
```

It is stored in the media directory and includes a media fingerprint.

If the media file is replaced/changed, the fingerprint changes and the old completion state is no longer treated as current.

## Reports

Default:

```text
/config/reports
```

The example configuration keeps transcript JSON and rescue details.
