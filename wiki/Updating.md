# Updating Censorarr

## Native Windows

Download the newer `Censorarr-Setup-X.Y.Z.exe` from GitHub Releases and run it over the existing installation.

Application files under `C:\Program Files\Censorarr` are replaced. Persistent data under `C:\ProgramData\Censorarr` is preserved.

## Native Linux `.deb`

Download the newer package and install it over the current version:

```bash
sudo apt install ./Censorarr-X.Y.Z-linux-amd64.deb
```

The package replaces `/opt/censorarr` while preserving:

```text
/var/lib/censorarr
/etc/default/censorarr
```

Then check:

```bash
sudo systemctl status censorarr
journalctl -u censorarr --since "5 minutes ago"
```

## Normal source / Docker install

From the Censorarr project folder:

```bash
git pull
docker compose up -d --build
```

This updates source and recreates/rebuilds the container as needed.

## Synology Container Manager

After replacing/pulling source:

1. Open the Censorarr project.
2. Rebuild/recreate the project when Dockerfile, entrypoint, compose, or dependency behavior changed.
3. A simple restart is sufficient only for changes that are already bind-mounted into the running container and do not affect the image/entrypoint.

When in doubt after an application version update, rebuild.

## GPU Worker update

```bash
cd Censorarr/gpu-worker
git pull
docker compose down
docker compose up -d --build
```

If you use a separate clone on the GPU host, update that clone independently.

## Preserve these directories

Do not delete persistent runtime data unless you intentionally want a reset.

Docker/source:

```text
config/
work/
gpu-worker/models/
```

Native Linux:

```text
/var/lib/censorarr
```

Native Windows:

```text
C:\ProgramData\Censorarr
```

## Before upgrading

Recommended:

- back up your persistent Censorarr configuration
- note any service/compose environment values
- confirm your worker token if using remote GPU
- keep a copy of custom profanity/exception files

## After upgrading

For Docker/source, check:

```bash
docker compose logs --tail=100
```

and run:

```bash
docker exec -it censorarr python /app/selftest.py
```

For native Linux, use:

```bash
sudo systemctl status censorarr
journalctl -u censorarr --since "5 minutes ago"
```

If the GPU Worker was also updated, test:

```bash
curl -H 'X-Censorarr-Token: YOUR_TOKEN' http://GPU-IP:9000/health
```
