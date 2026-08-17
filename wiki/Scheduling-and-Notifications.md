# Scheduling & Notifications

## Processing schedule

Automatic jobs can be limited to selected times.

Example:

```yaml
processing_schedule:
  enabled: true
  start: "23:00"
  end: "06:00"
  days: [0, 1, 2, 3, 4, 5, 6]
```

Day numbering:

```text
Monday = 0
...
Sunday = 6
```

Manual Process/Reprocess actions can still run outside the automatic schedule.

## Plex playback gating

If Plex is configured:

```yaml
plex_activity:
  pause_when_streaming: true
```

Censorarr avoids starting a **new automatic** job during active Plex video playback.

It does not kill an already-running job.

## Notifications

Example event list:

```yaml
notifications:
  enabled: true
  events: [completed, failed, queue-finished]
```

Supported configuration areas include:

- webhook / Discord
- Pushover
- email/SMTP

### Discord/generic webhook

```yaml
webhook:
  enabled: true
  type: discord
  url: ""
```

### Pushover

Store the app token and user key through the GUI when possible.

### Email

Configure:

- host
- port
- username
- from
- to
- TLS/SSL behavior

Store the SMTP password through the GUI when possible.

## Keep notification secrets out of Git

See [Security & Secrets](Security-and-Secrets.md).
