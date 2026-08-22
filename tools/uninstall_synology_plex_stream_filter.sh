#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PLEX_DIR="${CENSORARR_PLEX_DIR:-/volume1/@appstore/PlexMediaServer}"
PLEX_BIN="$PLEX_DIR/Plex Transcoder"
PLEX_REAL="$PLEX_DIR/Plex Transcoder.censorarr-real"
RUNTIME_CONFIG="$PLEX_DIR/Censorarr Stream Filter.json"
STOP_RUNTIME="$SCRIPT_DIR/stop_synology_plex_stream_filter.sh"

if [ "$(id -u)" != "0" ]; then
  echo "ERROR: run as root"
  exit 1
fi

# Stop the playback gateway/policy proxy and remove its remembered client
# redirect before restoring Plex's original transcoder.
if [ -f "$STOP_RUNTIME" ]; then
  sh "$STOP_RUNTIME" >/dev/null 2>&1 || true
fi

if [ ! -f "$PLEX_REAL" ]; then
  rm -f "$RUNTIME_CONFIG"
  echo "No Censorarr Plex Transcoder backup was found. Nothing to restore."
  exit 0
fi

if command -v synopkg >/dev/null 2>&1; then
  echo "Stopping PlexMediaServer..."
  synopkg stop PlexMediaServer >/dev/null 2>&1 || true
  sleep 2
fi

rm -f "$PLEX_BIN"
mv "$PLEX_REAL" "$PLEX_BIN"
chmod 755 "$PLEX_BIN"
rm -f "$RUNTIME_CONFIG"

if command -v synopkg >/dev/null 2>&1; then
  echo "Starting PlexMediaServer..."
  synopkg start PlexMediaServer >/dev/null 2>&1 || true
fi

echo "Original Plex Transcoder restored and Censorarr Plex stream-filter runtime stopped."
