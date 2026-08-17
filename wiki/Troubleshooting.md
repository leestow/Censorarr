# Troubleshooting

## Failure Center

The **Activity > Failures** page collects items that need attention and provides Retry and Details actions.

![Censorarr Failure Center](https://raw.githubusercontent.com/leestow/Censorarr/main/docs/screenshots/failures.jpg)

## Logs

Main Docker/Synology log:

```text
/config/censorarr.log
```

Native Windows launcher log:

```text
C:\ProgramData\Censorarr\logs\windows-launcher.log
```

Docker logs:

```bash
docker logs --tail 200 censorarr
```

Follow live:

```bash
docker logs -f censorarr
```

## `Permission denied` on a movie

Symptoms:

```text
ffprobe ... Permission denied
```

or:

```text
SKIPPED media file because Censorarr does not have read permission
```

Check:

```bash
echo "PUID=$PUID PGID=$PGID"
gosu "$PUID:$PGID" id
```

Then test a real file:

```bash
gosu "$PUID:$PGID" head -c 1 "/media/Movie/Movie.mkv" >/dev/null && echo READ_OK || echo READ_FAILED
```

On Synology, also test as root:

```bash
head -c 1 "/media/Movie/Movie.mkv" >/dev/null && echo ROOT_READ_OK || echo ROOT_READ_FAILED
```

If PUID/GID fails but root succeeds, use:

```yaml
CENSORARR_SYNOLOGY_COMPAT_MODE: "auto"
```

Censorarr 1.6.5 checks nested ACLs and can fall back automatically.

## Windows folder or network share is unavailable

If a folder works in File Explorer but not in Censorarr:

1. Confirm Censorarr is running under the same signed-in Windows account.
2. Try a UNC path such as `\\SERVER\Share\Movies` if a mapped drive is not visible.
3. Confirm the account has read permission, plus write permission when Apply mode will modify media.
4. Restart Censorarr after changing credentials or drive mappings.

See [Windows Installation](Windows-Installation.md).

## GPU Worker says `Invalid worker token`

Current protocol uses:

```text
X-Censorarr-Token
```

Check that:

1. main Censorarr and worker use the same literal token
2. the worker is current and not an old pre-rename build expecting the legacy protocol
3. no GUI-saved token is overriding the environment value

Test the worker directly:

```bash
curl -H 'X-Censorarr-Token: YOUR_TOKEN' http://GPU-IP:9000/health
```

## Token looks correct but still fails

Censorarr secret precedence is:

```text
GUI-saved secret
then environment variable
then legacy config value
```

So a stale GUI token can override `ASR_WORKER_TOKEN`.

See [Security & Secrets](Security-and-Secrets.md).

## GPU Worker cannot be reached

Check:

```bash
docker ps
docker logs --tail 100 censorarr-gpu-worker
```

Verify:

```text
TCP 9000
correct worker IP
9000:9000 port mapping
firewall/routing
```

## Worker says no CUDA device

This is normally a Docker/NVIDIA passthrough issue.

Verify the host sees the GPU and that NVIDIA Container Toolkit is configured before troubleshooting Censorarr.

## Container keeps restarting

Check Docker logs first.

Censorarr 1.6.5 handles per-file ffprobe/read failures without terminating the whole daemon, so a restart loop usually points to a startup/configuration problem rather than one bad movie.

## `/config` or `/work` bind mount fails on Synology

Make sure the project contains:

```text
config/
work/
```

The public repository preserves them with `.gitkeep`.

Use relative mounts:

```yaml
- ./config:/config
- ./work:/work
```

rather than hard-coded `/volume1/docker/censorarr/...` project-internal paths.

## Censorarr sees no media

Inside the container:

```bash
ls -la /media
ls -la /tv
```

If empty, verify the **left side** of the compose volume mapping points to the correct host/NAS folder.

## Radarr/Sonarr connects but media does not match

Check path mappings.

Example:

```text
Radarr reports: /movies/...
Censorarr sees: /media/...
```

Mapping:

```yaml
- from: /movies
  to: /media
```

## Bazarr connects but subtitles do not associate

Check both movie and TV path mappings.

## Browser cannot open Censorarr

Docker/Synology: check compose:

```yaml
ports:
  - "8087:8787"
```

Then use:

```text
http://SERVER-IP:8087
```

Native Windows normally uses:

```text
http://127.0.0.1:8087
```

## Self-test

```bash
docker exec -it censorarr python /app/selftest.py
```

This is useful after upgrades and before reporting a reproducible application bug.
