# Plex Integration

Plex is optional.

Censorarr can process mounted media without Plex.

## What Plex adds

- content-rating filtering
- playback-aware start gating
- optional library refresh after processing

## Basic settings

Typical values:

```text
Plex URL:        http://PLEX-SERVER-IP:32400
Movies library: Movies
TV library:     TV Shows
```

The Plex token is best saved through the Censorarr UI. Environment-variable fallback is also supported.

## Rating filters

Movies default example:

```yaml
rating_filter:
  enabled: false
  source: plex
  minimum: PG-13
  include_unrated: false
```

TV default example:

```yaml
tv:
  rating_filter:
    minimum: TV-14
```

Enable rating filtering only if Plex metadata is reliable enough for your library.

## Path mappings

Plex may report host/NAS paths that differ from paths inside Censorarr.

Example:

```yaml
plex_path_mappings:
  - from: /volume1/Movies
    to: /media
```

TV:

```yaml
plex_path_mappings:
  - from: /volume1/TV Shows
    to: /tv
```

`from` is the path Plex reports.

`to` is the path Censorarr uses inside its container.

## Playback-aware gating

```yaml
plex_activity:
  pause_when_streaming: true
```

This prevents a **new automatic job** from starting while Plex has active video playback.

It does not terminate a movie that is already being transcribed.

## Refresh after processing

```yaml
plex_activity:
  refresh_after_processing: true
```

Use this if you want Plex to refresh after Censorarr changes a media file.

## If Plex is disabled

Leave Plex-specific features disabled. Censorarr still scans and processes the mounted files normally.
