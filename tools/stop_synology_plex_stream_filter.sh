#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ -n "${CENSORARR_ROOT:-}" ]; then
  ROOT="$CENSORARR_ROOT"
elif [ -d "$SCRIPT_DIR/work" ]; then
  ROOT="$SCRIPT_DIR"
elif [ -d "$SCRIPT_DIR/../work" ]; then
  ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
else
  ROOT="$SCRIPT_DIR"
fi
WORK="${CENSORARR_WORK_DIR:-$ROOT/work}"
CLIENT_STATE="$WORK/plex-stream-client-ip"
CLIENT_IP="${CENSORARR_PLEX_CLIENT_IP:-${1:-}}"
if [ -z "$CLIENT_IP" ] && [ -f "$CLIENT_STATE" ]; then
  CLIENT_IP="$(cat "$CLIENT_STATE" 2>/dev/null || true)"
fi
POLICY_PORT="${CENSORARR_POLICY_PORT:-32402}"
GATEWAY_PORT="${CENSORARR_GATEWAY_PORT:-32403}"
PLEX_PORT="${CENSORARR_PLEX_PORT:-32400}"

if [ "$(id -u)" != "0" ]; then
  echo "ERROR: run as root"
  exit 1
fi

kill_pidfile() {
  file="$1"
  if [ -f "$file" ]; then
    pid="$(cat "$file" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$file"
  fi
}

kill_pidfile "$WORK/plex-stream-gateway.pid"
kill_pidfile "$WORK/plex-stream-policy.pid"
pkill -f '[p]lex_stream_filter_gateway\.py' 2>/dev/null || true
pkill -f '[p]lex_stream_filter_policy_proxy\.py' 2>/dev/null || true
pkill -f '[p]lex_filtered_handoff_v[1-5]\.py' 2>/dev/null || true
pkill -f '[p]lex_policy_proxy_directstream\.py' 2>/dev/null || true
pkill -f '[p]lex_policy_proxy\.py.*--listen-port' 2>/dev/null || true

if [ -n "$CLIENT_IP" ]; then
  while iptables -t nat -C PREROUTING -s "$CLIENT_IP" -p tcp --dport "$PLEX_PORT" -j REDIRECT --to-ports "$GATEWAY_PORT" 2>/dev/null; do
    iptables -t nat -D PREROUTING -s "$CLIENT_IP" -p tcp --dport "$PLEX_PORT" -j REDIRECT --to-ports "$GATEWAY_PORT"
  done
  while iptables -t nat -C PREROUTING -s "$CLIENT_IP" -p tcp --dport "$PLEX_PORT" -j REDIRECT --to-ports "$POLICY_PORT" 2>/dev/null; do
    iptables -t nat -D PREROUTING -s "$CLIENT_IP" -p tcp --dport "$PLEX_PORT" -j REDIRECT --to-ports "$POLICY_PORT"
  done
fi
rm -f "$CLIENT_STATE"

echo "Censorarr Plex stream filter stopped.${CLIENT_IP:+ Redirect removed for $CLIENT_IP.}"
