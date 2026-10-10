#!/usr/bin/env bash
# instant-status.sh: diagnostico rapido, NO levanta el daemon, solo lo inspecciona.
# Modelos: <repo>/models (relativo al script). Solo default, respeta DICTADO_DATA previa.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
if [ -z "${DICTADO_DATA:-}" ]; then
  DICTADO_DATA="$ROOT/models"
  export DICTADO_DATA
fi

config_dir() {
  case "$(uname -s)" in
    Darwin) printf '%s' "$HOME/Library/Application Support/instant" ;;
    *) printf '%s' "${XDG_CONFIG_HOME:-$HOME/.config}/instant" ;;
  esac
}
CONFDIR="$(config_dir)"
PIDFILE="$CONFDIR/instant.pid"
LOGFILE="$CONFDIR/instant.log"
CONFFILE="$CONFDIR/config.json"

alive_pid() {
  kill -0 "$1" 2>/dev/null
}

matches_instant() {
  local p="$1" cmd=""
  if [ -r "/proc/$p/cmdline" ]; then
    cmd="$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null)"
  elif command -v ps >/dev/null 2>&1; then
    cmd="$(ps -p "$p" -o args= 2>/dev/null)"
  else
    return 0
  fi
  case "$cmd" in
    *instant*) return 0 ;;
    *) return 1 ;;
  esac
}

echo "== proceso =="
if [ -f "$PIDFILE" ]; then
  LEPID="$(tr -d '[:space:]' < "$PIDFILE")"
  if [ -z "${LEPID:-}" ]; then
    echo "PID file vacio; se limpia."
    rm -f "$PIDFILE"
  elif alive_pid "$LEPID" && matches_instant "$LEPID"; then
    echo "vivo: SI PID $LEPID"
  else
    echo "vivo: NO PID $LEPID stale; el proceso murio."
    rm -f "$PIDFILE"
    echo "PID file stale limpio."
  fi
elif command -v pgrep >/dev/null 2>&1 && pgrep -f "instant_app run|instant run" >/dev/null 2>&1; then
  echo "vivo: SI (pgrep) sin PID file, lanzado con version vieja."
else
  echo "vivo: NO"
fi

echo "== modelos =="
echo "DICTADO_DATA=$DICTADO_DATA"
if [ -f "$DICTADO_DATA/parakeet-v3-int8/encoder.int8.onnx" ]; then
  echo "dir DICTADO_DATA: OK encoder.int8.onnx presente."
else
  echo "dir DICTADO_DATA: VACIO o sin modelos, revisa la ruta."
fi

echo ""
echo "== log: ultimas 15 lineas de \$config/instant.log ($LOGFILE) =="
if [ -f "$LOGFILE" ]; then
  tail -n 15 "$LOGFILE"
else
  echo "(sin log todavia)"
fi

echo ""
echo "== config: config.json ($CONFFILE) =="
if [ -f "$CONFFILE" ]; then
  cat "$CONFFILE"
else
  echo "(sin config todavia: corre 'instant setup')"
fi
