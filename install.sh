#!/usr/bin/env bash
# Instala Instant en un entorno virtual del repositorio y abre el asistente.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OS="$(uname -s)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[Instant] Falta Python 3.10 o posterior." >&2
  exit 1
fi
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"; then
  echo "[Instant] Se requiere Python 3.10 o posterior." >&2
  exit 1
fi

case "$OS" in
  Linux)
    echo "[Instant] Instalando dependencias del sistema..."
    sudo apt-get update
    sudo apt-get install -y python3-venv libportaudio2 xclip xdotool
    ;;
  Darwin)
    echo "[Instant] Instalando PortAudio..."
    brew install portaudio
    ;;
  *)
    echo "[Instant] Sistema operativo no compatible: $OS" >&2
    exit 1
    ;;
esac

if [ -z "${DICTADO_DATA:-}" ]; then
  export DICTADO_DATA="$ROOT/models"
fi

PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "[Instant] Creando entorno virtual..."
  python3 -m venv "$ROOT/.venv"
fi

echo "[Instant] Instalando Instant y sus dependencias..."
"$PYTHON" -m pip install "$ROOT/dictado"

SETUP_ARGS=()
if [ -n "${INSTANT_UNATTENDED:-}" ]; then
  SETUP_ARGS+=(--yes)
fi
if [ "${INSTANT_AUTOSTART:-0}" = "1" ]; then
  SETUP_ARGS+=(--autostart)
fi

echo "[Instant] Configurando modelos, micrófono y tecla..."
cd "$ROOT"
"$PYTHON" -m instant_app setup "${SETUP_ARGS[@]}"

echo
echo "[Instant] Instalación completa. Arranca con ./instant-run.sh."
