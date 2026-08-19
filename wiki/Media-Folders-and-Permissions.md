# Media Folders & Permissions

Most first-install problems are path or permission problems.

## Container paths vs host paths

This:

```yaml
- /volume1/Movies:/media:rw
```

means:

```text
Host/NAS path:   /volume1/Movies
Censorarr path:  /media
```

The Setup Wizard should normally use the **container path** `/media`, not the NAS path.

Likewise:

```yaml
- /volume1/TV Shows:/tv:rw
```

becomes `/tv` inside Censorarr.

## Read and write requirements

Censorarr requires read/traverse access so it can inspect media with `ffprobe`, extract audio, and transcribe dialogue.

It also requires write/replace access to the media location so it can create, validate, and install the processed media file containing the CLEAN audio track.

## PUID / PGID

Censorarr normally runs using:

```yaml
PUID: "..."
PGID: "..."
UMASK: "002"
```

Use IDs for an account that can access the media.

## Synology DSM ACL behavior

DSM can allow container root to read a share while the same numeric PUID/GID cannot.

Censorarr 1.6.5 supports:

```yaml
CENSORARR_SYNOLOGY_COMPAT_MODE: "auto"
```

`auto` checks nested Movies/TV folders and media files. If PUID/PGID is blocked but root can access the tree, Censorarr falls back to container root.

## Useful tests inside the container

Open a terminal in the container.

### See the configured identity

```bash
echo "PUID=$PUID PGID=$PGID"
```

### Test as configured PUID/GID

```bash
gosu "$PUID:$PGID" id
```

### Test a specific file

```bash
gosu "$PUID:$PGID" head -c 1 "/media/Movie Folder/Movie.mkv" >/dev/null && echo READ_OK || echo READ_FAILED
```

### Test as container root

```bash
head -c 1 "/media/Movie Folder/Movie.mkv" >/dev/null && echo ROOT_READ_OK || echo ROOT_READ_FAILED
```

If PUID/GID fails but root succeeds on Synology, `CENSORARR_SYNOLOGY_COMPAT_MODE=auto` should detect the mixed ACL condition on startup.

## ffprobe permission errors

A message such as:

```text
SKIPPED media file because Censorarr does not have read permission
```

is a per-file failure, not a fatal daemon failure.

In 1.6.5 permission failures are marked retryable. They can retry when the runtime identity changes or when the file becomes readable.

## Do not blindly chmod/chown your entire library

Especially on Synology, ACLs may be intentional. Diagnose the container identity and mount behavior first.

## Config/work permissions

Censorarr must also be able to write:

```text
/config
/work
```

The entrypoint creates/adjusts these project-local runtime directories for the configured identity.