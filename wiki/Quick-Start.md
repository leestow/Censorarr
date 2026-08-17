# Quick Start

This is the shortest path from zero to a working Censorarr 1.6.5 install.

## Windows 11 x64

The fastest Windows path is the native installer:

1. Open the Censorarr Releases page.
2. Download `Censorarr-Setup-X.Y.Z.exe`.
3. Run the installer.
4. Leave **Open Censorarr** checked when Setup finishes.
5. Complete the Setup Wizard at `http://127.0.0.1:8087`.
6. Use **Browse...** to select your Movies and TV folders.
7. Start with **Dry Run** enabled.

Latest Windows installer:

```text
https://github.com/leestow/Censorarr/releases/latest
```

See [Windows Installation](Windows-Installation.md) for mapped drives, UNC paths, updates, and troubleshooting.

## Native Linux - Debian/Ubuntu x86_64

Download the latest package from GitHub Releases:

```text
Censorarr-X.Y.Z-linux-amd64.deb
```

Install it:

```bash
sudo apt install ./Censorarr-X.Y.Z-linux-amd64.deb
```

The package creates the `censorarr` service and dedicated `censorarr` system user.

Check it:

```bash
sudo systemctl status censorarr
```

By default the web UI is local-only:

```text
http://127.0.0.1:8087
```

Use **Browse...** in the Setup Wizard to select real Linux folders such as `/mnt/media/Movies` and `/mnt/media/TV`.

If your media is group-owned, add the service account to that group and restart:

```bash
sudo usermod -aG media censorarr
sudo systemctl restart censorarr
```

Replace `media` with your actual media group.

For a headless server, see [Native Linux Installation](Linux-Installation.md) for secure LAN access through `/etc/default/censorarr`.

## Docker / Synology

### 1. Download or clone Censorarr

```bash
git clone https://github.com/leestow/Censorarr.git
cd Censorarr
```

On Synology, you can instead download/extract the repository into a Container Manager project folder such as:

```text
/volume1/docker/censorarr
```

### 2. Edit `docker-compose.yml`

At minimum change:

- `TZ`
- `PUID`
- `PGID`
- the **left side** of the Movies volume
- the **left side** of the TV Shows volume, if used

Example:

```yaml
environment:
  TZ: America/Chicago
  PUID: "1026"
  PGID: "100"
  UMASK: "002"
  CENSORARR_SYNOLOGY_COMPAT_MODE: "auto"

volumes:
  - /volume1/Movies:/media:rw
  - /volume1/TV Shows:/tv:rw
```

The shipped application/config/work mounts are relative to the project folder and normally should not be changed:

```yaml
- ./app:/app
- ./config:/config
- ./work:/work
```

### 3. Start Censorarr

```bash
docker compose up -d --build
```

The shipped browser mapping is:

```text
8087:8787
```

so the UI is normally:

```text
http://SERVER-IP:8087
```

### 4. Complete the Setup Wizard

A fresh install stays idle until the wizard is completed.

Recommended first-pass choices:

- Movies folder: `/media`
- TV folder: `/tv` if used
- Dry Run: **On**
- Transcription: local CPU
- Plex: Skip
- Radarr/Sonarr: Skip
- Bazarr: Skip

This validates the standalone core before adding integrations.

### 5. Watch the logs

```bash
docker compose logs -f
```

or:

```bash
docker logs -f censorarr
```

You should see the media preflight pass before Whisper loads.

### 6. Test a small media set

Dry Run still needs to **read** the source media, but it does not perform the final media replacement.

Once detection looks correct, enable Apply mode.

### 7. Optional: add the GPU Worker

See [Transcription & GPU Worker](Transcription-and-GPU-Worker.md).

### 8. Run the self-test

```bash
docker exec -it censorarr python /app/selftest.py
```

A healthy 1.6.5 install should end with:

```text
Censorarr v1.6.5 self-test: ALL PASS
```
