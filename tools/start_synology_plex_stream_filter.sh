#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ -n "${CENSORARR_ROOT:-}" ]; then
  ROOT="$CENSORARR_ROOT"
elif [ -d "$SCRIPT_DIR/config" ]; then
  ROOT="$SCRIPT_DIR"
elif [ -d "$SCRIPT_DIR/../config" ]; then
  ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
else
  ROOT="$SCRIPT_DIR"
fi
CODE_DIR="${CENSORARR_CODE_DIR:-$SCRIPT_DIR}"
WORK="${CENSORARR_WORK_DIR:-$ROOT/work}"
ALLOWLIST="${CENSORARR_STREAM_FILTER_ALLOWLIST:-$ROOT/config/stream-filter-allowlist.txt}"
CLIENT_IP="${CENSORARR_PLEX_CLIENT_IP:-${1:-}}"
POLICY_PORT="${CENSORARR_POLICY_PORT:-32402}"
GATEWAY_PORT="${CENSORARR_GATEWAY_PORT:-32403}"
PLEX_PORT="${CENSORARR_PLEX_PORT:-32400}"
PYTHON="$(command -v python3 || true)"
POLICY="$CODE_DIR/plex_stream_filter_policy_proxy.py"
GATEWAY="$CODE_DIR/plex_stream_filter_gateway.py"
POLICY_PID="$WORK/plex-stream-policy.pid"
GATEWAY_PID="$WORK/plex-stream-gateway.pid"
POLICY_LOG="$WORK/plex-stream-policy.log"
GATEWAY_LOG="$WORK/plex-stream-gateway.log"
POLICY_CONSOLE="$WORK/plex-stream-policy-console.log"
GATEWAY_CONSOLE="$WORK/plex-stream-gateway-console.log"

if [ "$(id -u)" != "0" ]; then
  echo "ERROR: run as root"
  exit 1
fi
if [ -z "$PYTHON" ]; then
  echo "ERROR: python3 not found"
  exit 2
fi
for f in "$POLICY" "$GATEWAY" "$CODE_DIR/plex_policy_proxy.py" "$CODE_DIR/plex_filtered_handoff.py" "$CODE_DIR/plex_filtered_handoff_v2.py" "$CODE_DIR/plex_filtered_handoff_v3.py" "$CODE_DIR/plex_filtered_handoff_v4.py" "$CODE_DIR/plex_filtered_handoff_v5.py"; do
  if [ ! -f "$f" ]; then
    echo "ERROR: required runtime file missing: $f"
    exit 3
  fi
done
if [ ! -f "$ALLOWLIST" ]; then
  echo "ERROR: allowlist missing: $ALLOWLIST"
  exit 4
fi

mkdir -p "$WORK"

kill_pidfile() {
  file="$1"
  if [ -f "$file" ]; then
    pid="$(cat "$file" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
    fi
    rm -f "$file"
  fi
}

kill_pidfile "$GATEWAY_PID"
kill_pidfile "$POLICY_PID"
# Clean up development checkpoints so only the stable runtime owns the ports.
pkill -f '[p]lex_filtered_handoff_v[1-5]\.py' 2>/dev/null || true
pkill -f '[p]lex_stream_filter_gateway\.py' 2>/dev/null || true
pkill -f '[p]lex_policy_proxy_directstream\.py' 2>/dev/null || true
pkill -f '[p]lex_stream_filter_policy_proxy\.py' 2>/dev/null || true
pkill -f '[p]lex_policy_proxy\.py.*--listen-port' 2>/dev/null || true
sleep 1

rm -f "$POLICY_LOG" "$GATEWAY_LOG" "$POLICY_CONSOLE" "$GATEWAY_CONSOLE"

nohup "$PYTHON" "$POLICY" \
  --force-all \
  --listen-port "$POLICY_PORT" \
  --plex-tls-auto \
  --log "$POLICY_LOG" \
  >"$POLICY_CONSOLE" 2>&1 &
policy_pid=$!
printf '%s\n' "$policy_pid" > "$POLICY_PID"

nohup "$PYTHON" "$GATEWAY" \
  --listen-port "$GATEWAY_PORT" \
  --policy-port "$POLICY_PORT" \
  --plex-port "$PLEX_PORT" \
  --allowlist "$ALLOWLIST" \
  --log "$GATEWAY_LOG" \
  >"$GATEWAY_CONSOLE" 2>&1 &
gateway_pid=$!
printf '%s\n' "$gateway_pid" > "$GATEWAY_PID"

sleep 2
if ! kill -0 "$policy_pid" 2>/dev/null; then
  echo "ERROR: policy proxy failed to start"
  cat "$POLICY_CONSOLE" 2>/dev/null || true
  exit 5
fi
if ! kill -0 "$gateway_pid" 2>/dev/null; then
  echo "ERROR: stream gateway failed to start"
  cat "$GATEWAY_CONSOLE" 2>/dev/null || true
  exit 6
fi

if [ -n "$CLIENT_IP" ]; then
  while iptables -t nat -C PREROUTING -s "$CLIENT_IP" -p tcp --dport "$PLEX_PORT" -j REDIRECT --to-ports "$POLICY_PORT" 2>/dev/null; do
    iptables -t nat -D PREROUTING -s "$CLIENT_IP" -p tcp --dport "$PLEX_PORT" -j REDIRECT --to-ports "$POLICY_PORT"
  done
  while iptables -t nat -C PREROUTING -s "$CLIENT_IP" -p tcp --dport "$PLEX_PORT" -j REDIRECT --to-ports "$GATEWAY_PORT" 2>/dev/null; do
    iptables -t nat -D PREROUTING -s "$CLIENT_IP" -p tcp --dport "$PLEX_PORT" -j REDIRECT --to-ports "$GATEWAY_PORT"
  done
  iptables -t nat -I PREROUTING 1 -s "$CLIENT_IP" -p tcp --dport "$PLEX_PORT" -j REDIRECT --to-ports "$GATEWAY_PORT"
else
  echo "WARNING: no client IP supplied; gateway is running but no iptables redirect was added."
  echo "Set CENSORARR_PLEX_CLIENT_IP or pass the client IP as argument 1."
fi

echo "Censorarr Plex stream filter running."
echo "  policy:  pid=$policy_pid port=$POLICY_PORT log=$POLICY_LOG"
echo "  gateway: pid=$gateway_pid port=$GATEWAY_PORT log=$GATEWAY_LOG"
echo "  client:  ${CLIENT_IP:-not redirected}"
echo "  mode:    Direct Play reject -> native HLS; video copy + audio transcode"
