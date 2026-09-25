#!/usr/bin/env bash
# Instalador de Instant en un comando (Linux y macOS, todo en español).
# Descarga TODO JUNTO (Parakeet v3 int8 ~670 MB + Silero VAD ~1 MB, español único)
# vía el `instant setup --yes` existente. No interactivo: no pide nada.
# Uso:  ./install.sh   (o:  bash install.sh)
set -euo pipefail

OS="$(uname -s)"

if [ "$OS" = "Linux" ]; then
  echo "[Instant] 1/3 Dependencias del sistema (Linux)..."
  sudo apt-get update && sudo apt-get install -y libportaudio2 xclip xdotool
elif [ "$OS" = "Darwin" ]; then
  echo "[Instant] 1/3 Dependencias del sistema (macOS)..."
  brew install portaudio
else
  echo "[Instant] SO no reconocido ($OS). Solo Linux y macOS." >&2
  exit 1
fi

echo "[Instant] 2/3 Instalando el paquete instant..."
pip install -e "$(dirname "$0")/dictado"

echo "[Instant] 3/3 Descargando modelos en español (~670 MB, una sola vez)..."
instant setup --yes

echo ""
echo "[Instant] Listo. Usa:  instant setup  (para microfono/tecla)  |  instant run  |  instant check"
echo "Solo se te pedira microfono y tecla si corres 'instant setup' interactivo;"
echo "el idioma es fijo: español."
