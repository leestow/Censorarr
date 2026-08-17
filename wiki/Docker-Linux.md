# Docker / Linux Installation

Use this guide for a normal Linux Docker host, VM, or server.

## Requirements

- Docker Engine
- Docker Compose v2 (`docker compose`)
- Read access to your media
- Write access to media if Apply mode will be used
- Enough CPU/RAM for local Whisper, or a reachable GPU Worker

## Install

```bash
git clone https://github.com/leestow/Censorarr.git
cd Censorarr
```

Edit `docker-compose.yml`.

### Set identity

```yaml
PUID: "1000"
PGID: "1000"
UMASK: "002"
```

Use the UID/GID of the host account that should access the media.

Check with:

```bash
id
```

### Map media

Example:

```yaml
- /mnt/media/Movies:/media:rw
- /mnt/media/TV:/tv:rw
```

The container-side paths should remain `/media` and `/tv` unless you deliberately change the Censorarr configuration too.

### Start

```bash
docker compose up -d --build
```

### Check status

```bash
docker compose ps
docker compose logs --tail=100
```

### Open the UI

The shipped port mapping is:

```yaml
- "8087:8787"
```

so open:

```text
http://SERVER-IP:8087
```

## Persistent data

Keep these project directories persistent:

```text
./config
./work
```

Censorarr runtime data includes:

- config
- secrets
- logs
- state
- reports
- Whisper models
- cached transcription/rescue audio

## Upgrade

```bash
git pull
docker compose up -d --build
```

See [Updating](Updating.md) for more detail.
