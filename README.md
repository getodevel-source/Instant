# Instant

Hold-to-talk offline en español. Mantén la tecla, habla, suelta y el texto se pega donde esté el cursor.

Pipeline: mic 16 kHz → Silero VAD (segmenta frases) → Parakeet TDT v3 int8
(`sherpa-onnx`, CPU) → portapapeles + Ctrl+V. Sin nube, sin GPU.
Paquete Python en `dictado/` (nombre `instant`, entry point `instant`).

## Estado actual verificado (2026-09-25 ~06:11, sin levantar daemon)

- Proceso: `tasklist /FI "IMAGENAME eq instant.exe"` → sin coincidencias
  (`instant.exe vivo: NO` según `instant-status.bat`); ningún `python.exe`
  con `instant` en su command line. Daemon MUERTO, no se levanta
  (convive con tests de otro worker).
- `instant.exe check` → exit 0: `tecla: f9 OK`, `mic probe: OK`
  (`[3] Microphone (DGM20 USB Microphon…`, fijado por config),
  `boot mic+warmup: 2.5s (OK <5s)` (líneas finales de
  `%APPDATA%/instant/instant.log`: `mic probe OK`, `modelo listo en 1.9s`,
  `warmup ok`).
- Bench anterior en el mismo log (2026-09-25 05:45):
  `14.7s audio -> 0.64s, RTF=0.04x` (2 segmentos, decode 0.58 s).
- Config activa (`%APPDATA%/instant/config.json`, leído tal cual):
  `mic_index: 3`, `key: f9`, `threads: 4`, `sound: false`.
- Modelos YA descargados en `models/` (no se versionan, no se empaquetan):
  `parakeet-v3-int8/` ~640 MB + `silero-vad/silero_vad.onnx` ~1 MB.
  Diagnóstico sin levantar nada: `instant-status.bat`.

## Instalación

### Windows

Sin dependencias del sistema.

```bat
pip install -e dictado
```

(`pip show instant` confirma install editable desde `dictado/`.)

### Linux (X11)

```bash
sudo apt install libportaudio2 xclip xdotool
pip install -e dictado
```

(Fuente: `dictado/README.md`. Wayland: el pegado con `xdotool` no funciona;
usa sesión X11. El hotkey con `pynput` requiere X.)

### macOS

```bash
brew install portaudio
pip install -e dictado
```

(Fuente: `dictado/README.md`.) Autoriza micrófono y accesibilidad (pegado por
teclado) en Ajustes del Sistema. Teclas F: usa Fn+F9 si tu teclado las mapea
a multimedia.

```bat
instant setup
instant run
instant check
```

(`setup`: TUI que descarga modelos ~670 MB si faltan y guarda mic/tecla/hilos.
`run`: daemon — mantén la tecla, suelta para transcribir. `check`: boot
rápido — tecla + mic probe + warmup (<5s). Verificado esta vuelta:
`instant.exe --help` (lista `setup,run,check`), `instant.exe check --help`
y `instant.exe check` salen 0.)

En Windows el `instant.exe` existe pero NO está en PATH; usa los lanzadores
del repo (llaman al exe por ruta absoluta, con fallback a `python -m instant_app`):

```bat
instant-setup.bat   :: = instant setup
instant-run.bat     :: = instant run
instant-status.bat  :: diagnostico (no levanta nada)
```

## Dónde vive la config

(Fuente: `dictado/src/instant_app/paths.py`, función `config_dir()`.)

| SO      | Config (`config.json`, `instant.log`)              |
|---------|----------------------------------------------------|
| Windows | `%APPDATA%/instant`                                |
| Linux   | `~/.config/instant`                                |
| macOS   | `~/Library/Application Support/instant`            |

Env `DICTADO_*` pisa config (fuente: `dictado/README.md`):
`DICTADO_MIC`, `DICTADO_KEY`, `DICTADO_THREADS`, `DICTADO_SOUND`,
`DICTADO_MAX_SEG`, `DICTADO_LLM_URL`.

Modelos en primer arranque: `instant setup` descarga lo que falte
(Parakeet v3 int8 ~670 MB desde HuggingFace + Silero VAD ~1 MB) al dir de datos
(fuente: `dictado/src/instant_app/models.py`, `download_models()`).
Nunca se empaquetan en git ni en los zips de release.

## Troubleshooting

- Tecla sin respuesta en apps elevadas → corre la terminal como administrador.
  (Fuente: `dictado/README.md`.)
- Wayland → usa sesión X11 (`xdotool` no pega en Wayland).
- `instant` no reconocido en terminal (no está en PATH) → ruta completa
  `C:\Users\juans\AppData\Roaming\Python\Python314\Scripts\instant.exe`
  (verificado con `ls`), o usa `instant-run.bat` / `instant-setup.bat`.
- `FileNotFoundError` al arrancar → corre `instant setup` primero
  (fuente: `dictado/src/instant_app/__main__.py`).
