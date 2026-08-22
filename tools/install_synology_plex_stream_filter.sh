#!/bin/sh
set -eu

PLEX_DIR="/volume1/@appstore/PlexMediaServer"
PLEX_BIN="$PLEX_DIR/Plex Transcoder"
PLEX_REAL="$PLEX_DIR/Plex Transcoder.censorarr-real"
CENSORARR_ROOT="/volume1/docker/censorarr-test"
SHIM_SOURCE="$CENSORARR_ROOT/plex_transcoder_shim.py"
ALLOWLIST="$CENSORARR_ROOT/config/stream-filter-allowlist.txt"
LOG="$CENSORARR_ROOT/work/plex-transcoder-shim.log"
TARGET_MEDIA="Beverly.Hills.Cop.II.1987.REMASTERED.BluRay.10Bit.1080p.DD.5.1.H265-d3g.mkv"

if [ "$(id -u)" != "0" ]; then
  echo "ERROR: run as root"
  exit 1
fi

PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "ERROR: python3 was not found on the Synology host. Nothing was changed."
  exit 2
fi

if [ ! -f "$PLEX_BIN" ] && [ ! -f "$PLEX_REAL" ]; then
  echo "ERROR: Plex Transcoder was not found at: $PLEX_BIN"
  exit 3
fi

if [ ! -f "$SHIM_SOURCE" ]; then
  echo "ERROR: shim source missing: $SHIM_SOURCE"
  echo "Download tools/plex_transcoder_shim.py there first."
  exit 4
fi

# Verify the bundled Plex Transcoder exposes the standard FFmpeg volume filter
# before modifying anything. If a prior install already exists, probe the backup.
PROBE="$PLEX_BIN"
if [ -f "$PLEX_REAL" ]; then
  PROBE="$PLEX_REAL"
fi
if ! "$PROBE" -hide_banner -filters 2>&1 | grep -Eq '(^|[[:space:]])volume([[:space:]]|$)'; then
  echo "ERROR: Plex Transcoder does not advertise the FFmpeg volume filter. Nothing was changed."
  exit 5
fi

mkdir -p "$CENSORARR_ROOT/config" "$CENSORARR_ROOT/work"
printf '%s\n' "$TARGET_MEDIA" > "$ALLOWLIST"
chmod 644 "$ALLOWLIST" 2>/dev/null || true

# Plex runs as PlexMediaServer, not root. The Censorarr test root may be mode 700
# on Synology, which blocks Plex from traversing into config/reports even when the
# files themselves are readable. Grant traverse-only access at the root; do not
# grant directory listing/read access there. The config/report directories remain
# read/traverse so Plex can open only the explicitly named files the shim needs.
chmod o+x "$CENSORARR_ROOT" 2>/dev/null || true
chmod o+rx "$CENSORARR_ROOT/config" 2>/dev/null || true
chmod o+rx "$CENSORARR_ROOT/config/reports" 2>/dev/null || true

# Pre-create a writable diagnostic log so a missing log actually means the shim
# was not invoked rather than a simple permissions failure.
chmod 755 "$CENSORARR_ROOT/work" 2>/dev/null || true
touch "$LOG"
chmod 666 "$LOG" 2>/dev/null || true

# Embed the discovered Python interpreter in the shebang so the Plex service does
# not depend on PATH when it spawns the shim.
TMP="$CENSORARR_ROOT/work/Plex Transcoder.censorarr-shim.tmp"
{
  printf '#!%s\n' "$PYTHON"
  tail -n +2 "$SHIM_SOURCE"
} > "$TMP"
chmod 755 "$TMP"

if command -v synopkg >/dev/null 2>&1; then
  echo "Stopping PlexMediaServer..."
  synopkg stop PlexMediaServer >/dev/null 2>&1 || true
  sleep 2
fi

if [ ! -f "$PLEX_REAL" ]; then
  echo "Backing up original Plex Transcoder..."
  mv "$PLEX_BIN" "$PLEX_REAL"
fi

cp "$TMP" "$PLEX_BIN"
chmod 755 "$PLEX_BIN"

if command -v synopkg >/dev/null 2>&1; then
  echo "Starting PlexMediaServer..."
  synopkg start PlexMediaServer >/dev/null 2>&1 || true
fi

echo
echo "Censorarr Plex stream-filter shim installed."
echo "Original: $PLEX_REAL"
echo "Shim:     $PLEX_BIN"
echo "Allowlist:$ALLOWLIST"
echo "Log:      $LOG"
echo
echo "Only this file is currently filtered:"
echo "  $TARGET_MEDIA"
echo
echo "Rollback command:"
echo "  sh $CENSORARR_ROOT/uninstall_synology_plex_stream_filter.sh"
