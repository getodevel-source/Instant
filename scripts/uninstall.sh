#!/usr/bin/env bash
# uninstall.sh: desinstala Instant en Linux/macOS.
# Por defecto conserva config (~/.config/instant o ~/Library/...) y modelos
# (igual que el desinstalador de Windows): borrar 670 MB y ajustes sin pedir
# sería destructivo. Con --purge se borra también todo lo del usuario.
#
# Uso: scripts/uninstall.sh [--purge] [--yes]
#   --purge  borra config, logs, pid y modelos del usuario tras frenar todo.
#   --yes    no pide confirmación (para CI).
set -euo pipefail

PURGE=0
YES=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    --yes) YES=1 ;;
    -h|--help)
      echo "Uso: $0 [--purge] [--yes]"
      echo "  Sin flags: frena daemon+panel y quita el autostart; conserva config y modelos."
      echo "  --purge: además borra la config y los modelos del usuario."
      exit 0 ;;
    *) echo "ERROR: flag desconocido: $arg (ver $0 --help)"; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OS="$(uname -s)"

config_dir() {
  case "$OS" in
    Darwin) printf '%s' "$HOME/Library/Application Support/instant" ;;
    *) printf '%s' "${XDG_CONFIG_HOME:-$HOME/.config}/instant" ;;
  esac
}
data_dir() {
  case "$OS" in
    Darwin) printf '%s' "$HOME/Library/Application Support/instant/models" ;;
    *) printf '%s' "${XDG_DATA_HOME:-$HOME/.local/share}/instant/models" ;;
  esac
}

CONFIG_DIR="$(config_dir)"
DATA_DIR="${DICTADO_DATA:-$(data_dir)}"
DESKTOP_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/instant.desktop"
PLIST="$HOME/Library/LaunchAgents/com.instant.dictado.plist"

echo "[1/3] Frenando daemon y panel..."
if [ -x "$SCRIPT_DIR/instant-stop.sh" ]; then
  "$SCRIPT_DIR/instant-stop.sh" || true
else
  echo "  (sin instant-stop.sh; intento por PID file)"
  PIDFILE="$CONFIG_DIR/instant.pid"
  if [ -f "$PIDFILE" ]; then
    LEPID="$(tr -d '[:space:]' < "$PIDFILE" 2>/dev/null || true)"
    if [ -n "${LEPID:-}" ]; then kill "$LEPID" 2>/dev/null || true; fi
  fi
fi
# El panel Qt no lo cubre el stop del daemon: se cierra por cmdline propia.
if command -v pkill >/dev/null 2>&1; then
  pkill -f "instant.*(panel|gui|setup)" 2>/dev/null || true
fi

echo "[2/3] Quitando arranque automático..."
case "$OS" in
  Darwin)
    if [ -f "$PLIST" ]; then
      if grep -q "com.instant.dictado" "$PLIST" 2>/dev/null; then
        if command -v launchctl >/dev/null 2>&1; then
          launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
        fi
        rm -f "$PLIST" && echo "  LaunchAgent eliminado."
      else
        echo "  $PLIST no es de Instant; no se toca."
      fi
    else
      echo "  Sin LaunchAgent."
    fi ;;
  *)
    if [ -f "$DESKTOP_FILE" ]; then
      if grep -q "instant-autostart-managed" "$DESKTOP_FILE" 2>/dev/null; then
        rm -f "$DESKTOP_FILE" && echo "  Autostart .desktop eliminado."
      else
        echo "  $DESKTOP_FILE no es de Instant; no se toca."
      fi
    else
      echo "  Sin autostart .desktop."
    fi ;;
esac

if [ "$PURGE" -eq 1 ]; then
  echo "[3/3] Purga de datos de usuario..."
  echo "  Se borrará: $CONFIG_DIR"
  echo "  Se borrará: $DATA_DIR"
  if [ "$YES" -ne 1 ]; then
    printf '  Confirmar purga total (config+modelos) [s/N]: '
    read -r answer
    case "$answer" in
      s|S|sí|si|y|Y|yes) ;;
      *) echo "  Purga cancelada; config y modelos conservados."; exit 0 ;;
    esac
  fi
  rm -rf -- "$CONFIG_DIR" && echo "  Config eliminada."
  rm -rf -- "$DATA_DIR" && echo "  Modelos eliminados."
else
  echo "[3/3] Datos conservados:"
  echo "  config: $CONFIG_DIR"
  echo "  modelos: $DATA_DIR"
  echo "  Para borrarlos también: $0 --purge"
fi
echo "Listo."
