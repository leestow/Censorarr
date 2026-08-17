# Native Linux Installation

Censorarr can run natively on **Debian/Ubuntu-family x86_64 Linux** without Docker.

This is separate from the Docker/Linux installation. If you prefer containers, use [Docker / Linux Installation](Docker-Linux.md).

## Download

Open the Censorarr **Releases** page and download:

```text
Censorarr-X.Y.Z-linux-amd64.deb
```

Latest release:

```text
https://github.com/leestow/Censorarr/releases/latest
```

The package is built from the same Censorarr source as Windows, Docker, and Synology. GitHub Actions builds the native executable, creates the `.deb`, installs the package on a clean Ubuntu runner, and verifies that Censorarr's web API starts before the package is published.

## Supported package target

The first native Linux package targets:

- Debian/Ubuntu-family distributions
- x86_64 / `amd64`
- systemd-based installations

Docker remains available for other Linux distributions.

## Install

From the folder containing the downloaded package:

```bash
sudo apt install ./Censorarr-X.Y.Z-linux-amd64.deb
```

The package declares FFmpeg and the required Linux runtime libraries as dependencies, so `apt` can install them if needed.

## Installed locations

| Item | Location |
|---|---|
| Application | `/opt/censorarr` |
| Configuration/state | `/var/lib/censorarr/config` |
| Work files | `/var/lib/censorarr/work` |
| Whisper model cache | `/var/lib/censorarr/config/models` |
| Launcher/runtime logs | `/var/lib/censorarr/logs` |
| Service settings | `/etc/default/censorarr` |
| systemd service | `censorarr.service` |
| Default web UI | `http://127.0.0.1:8087` |

## Service commands

Check status:

```bash
sudo systemctl status censorarr
```

Restart:

```bash
sudo systemctl restart censorarr
```

Follow the systemd log:

```bash
journalctl -u censorarr -f
```

Censorarr's own configured log is stored under its persistent data directory.

## First-run Setup Wizard

By default the native Linux web UI is local-only:

```text
http://127.0.0.1:8087
```

Open it on the Linux machine and complete the Setup Wizard.

For Movies and TV folders, use real Linux paths such as:

```text
/mnt/media/Movies
/mnt/media/TV
/srv/media/Movies
/home/user/Videos
```

The **Browse...** button starts at the Linux filesystem root during first-run setup. After setup completes, browsing and manual processing are constrained to the configured media roots.

Start with **Dry Run** enabled and test a small media set before switching to Apply mode.

## Media permissions

The package creates a dedicated system account:

```text
censorarr
```

That account must be able to read your source media and, in Apply mode, write to the media location.

The cleanest approach is usually to add `censorarr` to the group that already owns your media.

Example:

```bash
sudo usermod -aG media censorarr
sudo systemctl restart censorarr
```

Replace `media` with your real media group.

To inspect permissions:

```bash
namei -l /mnt/media/Movies
id censorarr
```

Avoid making your whole media library world-writable just to satisfy the service.

## Headless server / LAN access

The package intentionally binds to localhost by default.

To make Censorarr available to other devices on your LAN:

```bash
sudo nano /etc/default/censorarr
```

Change:

```text
CENSORARR_HOST=127.0.0.1
```

to:

```text
CENSORARR_HOST=0.0.0.0
```

Before exposing it on the network, also set a web password:

```text
WEB_USERNAME=admin
WEB_PASSWORD=choose-a-strong-password
```

Restart:

```bash
sudo systemctl restart censorarr
```

Then open:

```text
http://SERVER-IP:8087
```

If a firewall is enabled, allow TCP port `8087` only from networks/devices that should reach Censorarr.

## Local CPU and remote GPU

The native Linux package supports:

- local CPU faster-whisper transcription
- remote NVIDIA transcription through the optional Censorarr GPU Worker
- Auto mode with local fallback when configured

Local Whisper models are stored under:

```text
/var/lib/censorarr/config/models
```

## Updating

Download the new package and install it over the existing version:

```bash
sudo apt install ./Censorarr-X.Y.Z-linux-amd64.deb
```

The application under `/opt/censorarr` is replaced. Persistent configuration/state under `/var/lib/censorarr` and service settings under `/etc/default/censorarr` are preserved.

After updating:

```bash
sudo systemctl status censorarr
journalctl -u censorarr --since "5 minutes ago"
```

## Uninstalling

Remove the package:

```bash
sudo apt remove censorarr
```

Runtime data under `/var/lib/censorarr` is intentionally preserved to prevent accidental loss.

If you truly want a clean reset, back up anything needed and remove the persistent directory manually after uninstalling.
