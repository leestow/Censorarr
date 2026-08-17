# Radarr & Sonarr Integration

Radarr and Sonarr are optional metadata integrations.

They are **not** required for media scanning, profanity detection, or CLEAN audio creation.

## What they add

### Radarr

- movie posters
- richer movie metadata
- association between Censorarr files and Radarr movie entries

### Sonarr

- series/season/episode metadata
- richer TV Shows page

Without them, Censorarr falls back to the mounted folders.

## Radarr example

```yaml
arr_integrations:
  radarr:
    enabled: true
    url: http://RADARR-SERVER-IP:7878
    path_mappings:
      - from: /movies
        to: /media
```

Save the Radarr API key in Censorarr Settings.

## Sonarr example

```yaml
arr_integrations:
  sonarr:
    enabled: true
    url: http://SONARR-SERVER-IP:8989
    path_mappings:
      - from: /tv
        to: /tv
```

Save the Sonarr API key in Censorarr Settings.

## Path mapping rule

The mapping is:

```text
from = path the *arr application reports
to   = equivalent path inside Censorarr
```

Example:

Radarr reports:

```text
/movies/Alien (1979)/Alien.mkv
```

Censorarr sees:

```text
/media/Alien (1979)/Alien.mkv
```

Use:

```yaml
- from: /movies
  to: /media
```

## Common mistake

Do not assume the NAS path must match between containers.

Container paths are allowed to differ as long as the mapping accurately translates them.

## Testing

Use the integration test button in Censorarr Settings after entering:

- URL
- API key
- path mapping

If the connection test passes but media associations are wrong, the path mapping is the next thing to check.
