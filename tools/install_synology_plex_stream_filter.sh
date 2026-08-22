#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PLEX_DIR="${CENSORARR_PLEX_DIR:-/volume1/@appstore/PlexMediaServer}"
PLEX_BIN="$PLEX_DIR/Plex Transcoder"
PLEX_REAL="$PLEX_DIR/Plex Transcoder.censorarr-real"
PLEX_USER="${CENSORARR_PLEX_USER:-PlexMediaServer}"
CENSORARR_ROOT="${CENSORARR_ROOT:-$SCRIPT_DIR}"
SHIM_SOURCE="${CENSORARR_SHIM_SOURCE:-$CENSORARR_ROOT/plex_transcoder_shim.py}"
REPORT_DIR="${CENSORARR_REPORT_DIR:-$CENSORARR_ROOT/config/reports}"
ALLOWLIST="${CENSORARR_STREAM_FILTER_ALLOWLIST:-$CENSORARR_ROOT/config/stream-filter-allowlist.txt}"
LOG="${CENSORARR_STREAM_FILTER_LOG:-$CENSORARR_ROOT/work/plex-transcoder-shim.log}"
RUNTIME_CONFIG="$PLEX_DIR/Censorarr Stream Filter.json"
TARGET_MEDIA="${CENSORARR_TARGET_MEDIA:-Beverly.Hills.Cop.II.1987.REMASTERED.BluRay.10Bit.1080p.DD.5.1.H265-d3g.mkv}"

if [ "$(id -u)" != "0" ]; then
  echo "ERROR: run as root"
  exit 1
fi

PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "ERROR: python3 was not found on the Synology host. Nothing was changed."
  exit 2
fi

if ! id "$PLEX_USER" >/dev/null 2>&1; then
  echo "ERROR: Plex service user '$PLEX_USER' was not found. Nothing was changed."
  exit 3
fi
PLEX_UID="$(id -u "$PLEX_USER")"
PLEX_GID="$(id -g "$PLEX_USER")"

if [ ! -f "$PLEX_BIN" ] && [ ! -f "$PLEX_REAL" ]; then
  echo "ERROR: Plex Transcoder was not found at: $PLEX_BIN"
  exit 4
fi

if [ ! -f "$SHIM_SOURCE" ]; then
  echo "ERROR: shim source missing: $SHIM_SOURCE"
  echo "Download tools/plex_transcoder_shim.py beside this installer first."
  exit 5
fi

# Verify Plex's bundled FFmpeg supports the filter before touching the binary.
PROBE="$PLEX_BIN"
if [ -f "$PLEX_REAL" ]; then
  PROBE="$PLEX_REAL"
fi
if ! "$PROBE" -hide_banner -filters 2>&1 | grep -Eq '(^|[[:space:]])volume([[:space:]]|$)'; then
  echo "ERROR: Plex Transcoder does not advertise the FFmpeg volume filter. Nothing was changed."
  exit 6
fi

mkdir -p "$CENSORARR_ROOT/config" "$CENSORARR_ROOT/work" "$REPORT_DIR"
printf '%s\n' "$TARGET_MEDIA" > "$ALLOWLIST"

# Plex runs under its own service UID. Synology installations frequently create
# Docker project roots as mode 700, so readable files below them are still
# unreachable. Grant only the path traversal/list/read needed by the shim.
chmod o+x "$CENSORARR_ROOT" 2>/dev/null || true
chmod o+x "$CENSORARR_ROOT/config" 2>/dev/null || true
chmod o+rx "$REPORT_DIR" 2>/dev/null || true
chmod o+r "$ALLOWLIST" 2>/dev/null || true
for report in "$REPORT_DIR"/*.json; do
  [ -f "$report" ] || continue
  chmod o+r "$report" 2>/dev/null || true
done

# The log itself is writable by Plex; the rest of /work only needs traversal.
chmod o+x "$CENSORARR_ROOT/work" 2>/dev/null || true
touch "$LOG"
chmod 666 "$LOG" 2>/dev/null || true

# Critical preflight: actually drop privileges to the Plex service UID/GID and
# prove that Plex can read the allowlist and find/parse the target report. This
# catches POSIX/DSM ACL problems before the Plex Transcoder is replaced.
echo "Preflight: testing Censorarr data access as $PLEX_USER (uid=$PLEX_UID)..."
"$PYTHON" - "$PLEX_UID" "$PLEX_GID" "$ALLOWLIST" "$REPORT_DIR" "$TARGET_MEDIA" <<'PY'
import json
import os
import sys
from pathlib import Path

uid = int(sys.argv[1])
gid = int(sys.argv[2])
allowlist = Path(sys.argv[3])
report_dir = Path(sys.argv[4])
target = sys.argv[5].casefold()

try:
    os.setgroups([])
except Exception:
    pass
os.setgid(gid)
os.setuid(uid)

try:
    allowed = [x.strip() for x in allowlist.read_text(encoding="utf-8").splitlines()
               if x.strip() and not x.lstrip().startswith("#")]
except Exception as exc:
    raise SystemExit(f"ERROR: Plex cannot read allowlist: {exc}")
if target and target not in {x.casefold() for x in allowed}:
    raise SystemExit("ERROR: target media is not present in the Plex filter allowlist")

try:
    candidates = list(report_dir.glob("*.json"))
except Exception as exc:
    raise SystemExit(f"ERROR: Plex cannot list Censorarr reports: {exc}")

match = None
ranges = []
for candidate in candidates:
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8")) or {}
    except Exception:
        continue
    recorded = str(payload.get("file") or "").strip()
    if recorded and Path(recorded).name.casefold() == target:
        match = candidate
        ranges = payload.get("mute_ranges") or []
        break
if match is None:
    raise SystemExit(f"ERROR: Plex could not read a matching Censorarr report for {sys.argv[5]}")
if not ranges:
    raise SystemExit(f"ERROR: matching report has no mute ranges: {match}")
print(f"Preflight OK: allowlist readable; report={match.name}; mute_ranges={len(ranges)}")
PY

# Store actual install paths beside Plex so the shim is portable across Synology
# volumes and Docker directory names rather than depending on Lee's test paths.
"$PYTHON" - "$RUNTIME_CONFIG" "$PLEX_REAL" "$REPORT_DIR" "$ALLOWLIST" "$LOG" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
payload = {
    "schema": 1,
    "plex_real": sys.argv[2],
    "report_dir": sys.argv[3],
    "allowlist": sys.argv[4],
    "log": sys.argv[5],
    "lead_ms": 35,
    "tail_ms": 35,
    "join_gap_ms": 20,
}
out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
chmod 644 "$RUNTIME_CONFIG" 2>/dev/null || true

# Embed the discovered Python interpreter in the shebang so Plex does not depend
# on PATH when it spawns the shim.
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
  if ! synopkg start PlexMediaServer >/dev/null 2>&1; then
    echo "ERROR: Plex failed to start after shim install. Restoring original transcoder..."
    rm -f "$PLEX_BIN"
    if [ -f "$PLEX_REAL" ]; then
      mv "$PLEX_REAL" "$PLEX_BIN"
      chmod 755 "$PLEX_BIN"
    fi
    rm -f "$RUNTIME_CONFIG"
    synopkg start PlexMediaServer >/dev/null 2>&1 || true
    exit 7
  fi
fi

echo
echo "Censorarr Plex stream-filter shim installed."
echo "Original: $PLEX_REAL"
echo "Shim:     $PLEX_BIN"
echo "Config:   $RUNTIME_CONFIG"
echo "Allowlist:$ALLOWLIST"
echo "Reports:  $REPORT_DIR"
echo "Log:      $LOG"
echo
echo "Currently allowlisted:"
echo "  $TARGET_MEDIA"
echo
echo "Rollback command:"
echo "  sh $CENSORARR_ROOT/uninstall_synology_plex_stream_filter.sh"
