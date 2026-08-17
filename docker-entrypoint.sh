#!/bin/sh
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
UMASK_VALUE="${UMASK:-002}"
COMPAT_MODE="${CENSORARR_SYNOLOGY_COMPAT_MODE:-auto}"

case "$PUID" in
  ''|*[!0-9]*) echo "ERROR: PUID must be a numeric user ID (got: $PUID)" >&2; exit 64 ;;
esac
case "$PGID" in
  ''|*[!0-9]*) echo "ERROR: PGID must be a numeric group ID (got: $PGID)" >&2; exit 64 ;;
esac
case "$UMASK_VALUE" in
  ''|*[!0-7]*) echo "ERROR: UMASK must contain only octal digits 0-7 (got: $UMASK_VALUE)" >&2; exit 64 ;;
esac

case "$(printf '%s' "$COMPAT_MODE" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on|root) COMPAT_MODE="true" ;;
  0|false|no|off|strict) COMPAT_MODE="false" ;;
  auto|'') COMPAT_MODE="auto" ;;
  *) echo "ERROR: CENSORARR_SYNOLOGY_COMPAT_MODE must be auto, true, or false (got: $COMPAT_MODE)" >&2; exit 64 ;;
esac

# Keep application-created files group-friendly by default.
umask "$UMASK_VALUE"
export HOME=/config

mkdir -p /config /work

# Never chown /media or /tv here. The media libraries retain their NAS ownership/ACLs.
# Keep config/work owned by the requested identity even if Synology compatibility mode
# ultimately needs to run the application as container root.
chown -R "$PUID:$PGID" /config /work
chmod 2775 /config /work 2>/dev/null || true

can_user_read_root() {
  gosu "$PUID:$PGID" sh -c '[ -r "$1" ] && [ -x "$1" ] && ls -A "$1" >/dev/null 2>&1' _ "$1"
}
can_root_read_root() {
  sh -c '[ -r "$1" ] && [ -x "$1" ] && ls -A "$1" >/dev/null 2>&1' _ "$1"
}

# DSM ACLs can be mixed below the share root: /media may be readable while a
# movie/series folder or the media file inside it is not. Scan the normal Movies/TV
# depth before dropping privileges so auto mode can choose the compatible identity.
can_user_read_tree() {
  gosu "$PUID:$PGID" sh -c '
    root="$1"
    find "$root" -mindepth 1 -maxdepth 4 -print >/dev/null 2>&1 || exit 1
    bad="$(find "$root" -maxdepth 4 -type f \( -iname "*.mkv" -o -iname "*.mp4" -o -iname "*.m4v" \) ! -readable -print -quit 2>/dev/null || true)"
    [ -z "$bad" ]
  ' _ "$1"
}
can_root_read_tree() {
  sh -c '
    root="$1"
    find "$root" -mindepth 1 -maxdepth 4 -print >/dev/null 2>&1 || exit 1
    bad="$(find "$root" -maxdepth 4 -type f \( -iname "*.mkv" -o -iname "*.mp4" -o -iname "*.m4v" \) ! -readable -print -quit 2>/dev/null || true)"
    [ -z "$bad" ]
  ' _ "$1"
}

NEEDS_ROOT=0
for MEDIA_ROOT in /media /tv; do
  if [ -d "$MEDIA_ROOT" ]; then
    if ! can_user_read_root "$MEDIA_ROOT" || ! can_user_read_tree "$MEDIA_ROOT"; then
      echo "WARNING: $MEDIA_ROOT contains paths/files not readable by PUID=$PUID PGID=$PGID." >&2
      if can_root_read_root "$MEDIA_ROOT" && can_root_read_tree "$MEDIA_ROOT"; then
        NEEDS_ROOT=1
      fi
    fi
  fi
done

EFFECTIVE_UID="$PUID"
EFFECTIVE_GID="$PGID"
ROOT_REASON=""
if [ "$COMPAT_MODE" = "true" ]; then
  EFFECTIVE_UID=0
  EFFECTIVE_GID=0
  ROOT_REASON="explicit Synology compatibility mode"
elif [ "$COMPAT_MODE" = "auto" ] && [ "$NEEDS_ROOT" -eq 1 ]; then
  EFFECTIVE_UID=0
  EFFECTIVE_GID=0
  ROOT_REASON="Synology ACL fallback: requested PUID/PGID cannot fully access the media tree but container root can"
fi

export CENSORARR_EFFECTIVE_UID="$EFFECTIVE_UID"
export CENSORARR_EFFECTIVE_GID="$EFFECTIVE_GID"
export CENSORARR_SYNOLOGY_COMPAT_MODE="$COMPAT_MODE"

if [ "$EFFECTIVE_UID" = "0" ]; then
  echo "WARNING: Censorarr is running as container root ($ROOT_REASON)." >&2
  echo "WARNING: This is intended for Synology ACL compatibility. Set CENSORARR_SYNOLOGY_COMPAT_MODE=false to forbid root fallback." >&2
else
  echo "Censorarr permissions: requested=$PUID:$PGID effective=$EFFECTIVE_UID:$EFFECTIVE_GID UMASK=$UMASK_VALUE SynologyCompat=$COMPAT_MODE"
fi

exec gosu "$EFFECTIVE_UID:$EFFECTIVE_GID" "$@"
