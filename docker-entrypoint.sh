#!/bin/sh
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
UMASK_VALUE="${UMASK:-002}"

case "$PUID" in
  ''|*[!0-9]*) echo "ERROR: PUID must be a numeric user ID (got: $PUID)" >&2; exit 64 ;;
esac
case "$PGID" in
  ''|*[!0-9]*) echo "ERROR: PGID must be a numeric group ID (got: $PGID)" >&2; exit 64 ;;
esac
case "$UMASK_VALUE" in
  ''|*[!0-7]*) echo "ERROR: UMASK must contain only octal digits 0-7 (got: $UMASK_VALUE)" >&2; exit 64 ;;
esac

# Keep application-created files group-friendly by default.
umask "$UMASK_VALUE"
export HOME=/config

mkdir -p /config /work

# Never chown /media or /tv here. The media libraries should retain their Synology ownership.
# Running Censorarr as PUID:PGID gives the process the same filesystem permissions
# as the selected NAS account/group.
chown -R "$PUID:$PGID" /config /work

for MEDIA_ROOT in /media /tv; do
  if [ -d "$MEDIA_ROOT" ]; then
    if ! gosu "$PUID:$PGID" test -r "$MEDIA_ROOT"; then
      echo "WARNING: $MEDIA_ROOT is not readable by PUID=$PUID PGID=$PGID." >&2
    fi
    if ! gosu "$PUID:$PGID" test -w "$MEDIA_ROOT"; then
      echo "WARNING: $MEDIA_ROOT is not writable by PUID=$PUID PGID=$PGID. Censorarr needs write access to media folders to create temporary/remuxed files." >&2
    fi
  fi
done

echo "Censorarr permissions: PUID=$PUID PGID=$PGID UMASK=$UMASK_VALUE"
exec gosu "$PUID:$PGID" "$@"
