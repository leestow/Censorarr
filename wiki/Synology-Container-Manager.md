# Synology Container Manager Installation

This is the recommended installation path for Synology DSM / Container Manager.

## Recommended folder layout

Example:

```text
/volume1/docker/censorarr/
├── app/
├── config/
├── work/
├── docker-compose.yml
├── Dockerfile
├── config.example.yaml
└── ...
```

The repository contains `.gitkeep` files so `config/` and `work/` exist after cloning/extracting.

## 1. Put the source on the NAS

Download or clone the repository into a folder such as:

```text
/volume1/docker/censorarr
```

Do not put runtime secrets into GitHub.

## 2. Edit the compose file before creating the project

The important section is:

```yaml
ports:
  - "8087:8787"

environment:
  TZ: Etc/UTC
  PUID: "1000"
  PGID: "1000"
  UMASK: "002"
  CENSORARR_SYNOLOGY_COMPAT_MODE: "auto"

volumes:
  - ./app:/app
  - ./en.json:/app/en.json:ro
  - ./config.example.yaml:/app/config.example.yaml:ro
  - ./config:/config
  - ./work:/work
  - /volume1/Movies:/media:rw
  - /volume1/TV Shows:/tv:rw
```

### Browser port

Change only the left side if needed:

```yaml
- "8088:8787"
```

would make the UI:

```text
http://NAS-IP:8088
```

### Movies and TV paths

Change only the left side of the media mounts:

```yaml
- /volume1/Your Movies Share:/media:rw
- /volume1/Your TV Share:/tv:rw
```

Inside Censorarr, the paths remain `/media` and `/tv`.

## 3. Find PUID and PGID

From SSH on the Synology:

```bash
id YOUR_USERNAME
```

Use the numeric UID and GID:

```yaml
PUID: "1026"
PGID: "100"
```

## 4. Leave Synology compatibility mode on `auto`

```yaml
CENSORARR_SYNOLOGY_COMPAT_MODE: "auto"
```

DSM ACLs can be mixed below the share root. A share may appear accessible while individual movie folders/files are blocked for the configured PUID/PGID.

In 1.6.5, `auto` checks nested media paths/files before dropping privileges. If the configured identity cannot fully access the media tree but container root can, Censorarr automatically uses container root for compatibility.

Modes:

| Value | Behavior |
|---|---|
| `auto` | Recommended. Use PUID/PGID when possible; fall back to root only when DSM ACLs require it |
| `false` | Never fall back to root |
| `true` | Always run the application as container root |

Censorarr never recursively `chown`s your Movies or TV shares.

## 5. Create the project in Container Manager

In DSM:

1. Open **Container Manager**.
2. Go to **Project**.
3. Create a new project.
4. Choose the Censorarr project folder.
5. Use the included `docker-compose.yml`.
6. Build/start the project.

You can also do the equivalent through SSH:

```bash
cd /volume1/docker/censorarr
sudo docker compose up -d --build
```

## 6. Open Censorarr

Using the shipped mapping:

```text
http://NAS-IP:8087
```

Complete the Setup Wizard.

## 7. Start in Dry Run

For a clean first test, use:

- `/media`
- `/tv` if applicable
- local CPU
- Dry Run
- no optional integrations

After the core works, add Plex/Radarr/Sonarr/Bazarr/GPU.

## Permission troubleshooting

If logs show:

```text
Permission denied
```

see [Media Folders & Permissions](Media-Folders-and-Permissions.md).

Do **not** assume a visible folder means the configured PUID can read the actual media files. DSM ACLs can differ by folder/file.

## Rebuild after entrypoint/compose changes

When `docker-entrypoint.sh`, Dockerfile, or compose behavior changes, recreate/rebuild the project rather than only restarting the container.
