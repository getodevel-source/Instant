#!/usr/bin/env bash
# instant-stop.sh: frena SOLO la instancia instant por PID file, nunca procesos ajenos.
# Limpia el instant.pid. Sale 0 con mensaje claro.
set -euo pipefail

config_dir() {
  case "$(uname -s)" in
    Darwin) printf '%s' "$HOME/Library/Application Support/instant" ;;
    *) printf '%s' "${XDG_CONFIG_HOME:-$HOME/.config}/instant" ;;
  esac
}
PIDFILE="$(config_dir)/instant.pid"

matches_instant() { # matches_instant <pid> -> 0 si su cmdline es instant
  local p="$1" cmd=""
  if [ -r "/proc/$p/cmdline" ]; then
    cmd="$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null)"
  elif command -v ps >/dev/null 2>&1; then
    cmd="$(ps -p "$p" -o args= 2>/dev/null)"
  else
    return 0 # sin forma de verificar: el PID file lo escribio el propio daemon
  fi
  case "$cmd" in
    *instant*) return 0 ;;
    *) return 1 ;;
  esac
}

if [ ! -f "$PIDFILE" ]; then
  if command -v pgrep >/dev/null 2>&1 && pgrep -f "instant_app run|instant run" >/dev/null 2>&1; then
    echo "Hay proceso instant vivo pero sin PID file, lanzado con version vieja."
    echo "Frena solo ese PID (pgrep -af 'instant.*run'); nunca uses killall."
    exit 2
  fi
  echo "No estaba corriendo."
  exit 0
fi

LEPID="$(tr -d '[:space:]' < "$PIDFILE")"
if [ -z "${LEPID:-}" ]; then
  rm -f "$PIDFILE"
  echo "PID file vacio; se limpio. No habia instancia conocida."
  exit 0
fi

if ! kill -0 "$LEPID" 2>/dev/null || ! matches_instant "$LEPID"; then
  rm -f "$PIDFILE"
  echo "No estaba corriendo PID $LEPID stale, proceso muerto; PID file limpio."
  exit 0
fi

kill "$LEPID" 2>/dev/null || {
  echo "ERROR: no se pudo frenar el PID $LEPID. Revisa permisos."
  exit 1
}
for _ in {1..50}; do
  kill -0 "$LEPID" 2>/dev/null || break
  sleep 0.1
done
if kill -0 "$LEPID" 2>/dev/null; then
  kill -9 "$LEPID" 2>/dev/null || true
  sleep 0.5
fi
if kill -0 "$LEPID" 2>/dev/null; then
  echo "ERROR: no se pudo frenar el PID $LEPID. Revisa permisos."
  exit 1
fi
rm -f "$PIDFILE"
echo "Daemon frenado PID $LEPID."
exit 0
