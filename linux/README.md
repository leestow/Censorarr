# Censorarr native Linux package

Censorarr can run directly on **Debian/Ubuntu-family x86_64 Linux** without Docker.

## Download

Download the latest `.deb` from GitHub Releases:

```text
https://github.com/leestow/Censorarr/releases/latest
```

The package is named:

```text
Censorarr-X.Y.Z-linux-amd64.deb
```

Install it with:

```bash
sudo apt install ./Censorarr-X.Y.Z-linux-amd64.deb
```

## Installed locations

- Application: `/opt/censorarr`
- Persistent configuration/state: `/var/lib/censorarr`
- Service settings: `/etc/default/censorarr`
- systemd unit: `censorarr.service`
- Default web UI: `http://127.0.0.1:8087`

The package depends on the distribution's FFmpeg package and installs a native, self-contained Censorarr executable built with PyInstaller.

## Service

```bash
sudo systemctl status censorarr
sudo systemctl restart censorarr
journalctl -u censorarr -f
```

## Media permissions

The service runs as the dedicated `censorarr` user.

Give that user access to the group that owns your media. Example:

```bash
sudo usermod -aG media censorarr
sudo systemctl restart censorarr
```

Replace `media` with the actual group that can read/write your Movies and TV folders.

## LAN access

For safety, the native Linux package binds to localhost by default.

For a headless server, edit:

```bash
sudo nano /etc/default/censorarr
```

Set:

```text
CENSORARR_HOST=0.0.0.0
WEB_PASSWORD=choose-a-password
```

Then:

```bash
sudo systemctl restart censorarr
```

Open:

```text
http://SERVER-IP:8087
```

## Updating

Download the newer `.deb` and install it over the existing package:

```bash
sudo apt install ./Censorarr-X.Y.Z-linux-amd64.deb
```

Persistent configuration, models, work state, and logs under `/var/lib/censorarr` are preserved.
