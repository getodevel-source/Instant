# Instant

Hold-to-talk offline en español. Mantén la tecla, habla, suelta y el texto se pega donde esté el cursor.

Pipeline: mic 16 kHz → Silero VAD (segmenta frases) → Parakeet TDT v3 int8
(`sherpa-onnx`, CPU) → portapapeles + Ctrl+V. Sin nube, sin GPU.
Paquete Python en `dictado/` (nombre `instant`, entry point `instant`).

## Estado actual verificado (2026-09-25 ~06:16, daemon VIVO del otro worker)

- Proceso: `instant.exe` VIVO pid 12648 (verificado con
  `Get-Process instant` y `instant-status.bat` → `instant.exe vivo: SI`).
  NO lo levanto ni lo toco: es del otro worker.
- Log (`%APPDATA%/instant/instant.log`, leído tal cual): el bug de las
  06:13:23 quedó registrado — `instant run` sin `DICTADO_DATA` buscó
  `C:\Users\juans\AppData\Local\instant\models\parakeet-v3-int8\encoder.int8.onnx`
  (vacío, ese dir ni existe) y murió con `modelo parakeet incompleto...
  -> corre instant setup primero`. Con `DICTADO_DATA` apuntando al repo,
  06:13:47: `modelo listo en 1.7s`, `warmup ok`,
  `listo. Manten F9 para dictar (60-120s), suelta para transcribir`,
  y `vivo, esperando F9...` 06:14:47 y 06:15:47. Sin traceback tras el fix.
- `instant-run.bat check` (con el fix) → exit 0: `tecla: f9 OK`,
  `mic probe: OK` (`[3] Microphone (DGM20 USB Microphon…`),
  `boot mic+warmup: 2.4s (OK <5s)`.
- Bench anterior en el mismo log (2026-09-25 05:45):
  `14.7s audio -> 0.64s, RTF=0.04x` (2 segmentos, decode 0.58 s).
- Config activa (`%APPDATA%/instant/config.json`, leído tal cual):
  `mic_index: 3`, `key: f9`, `threads: 4`, `sound: false`, `llm_url: ""`.
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
del repo (fijan `DICTADO_DATA` al repo, llaman al exe por ruta absoluta,
con fallback a `python -m instant_app` que hereda el env igual):

```bat
instant-setup.bat   :: = instant setup (con DICTADO_DATA al repo)
instant-run.bat     :: = instant run (con DICTADO_DATA al repo)
instant-status.bat  :: diagnostico: proceso, DICTADO_DATA, log, config
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

## DICTADO_DATA (dónde busca los modelos)

(Fuente: `dictado/src/instant_app/paths.py`, `resolve_data_dir()`:
`DICTADO_DATA` > `./models` (solo si el cwd tiene `parakeet-v3-int8/`) >
dir de usuario por SO. Verificado en log 06:13:23: sin la var, el exe cayó
al default y murió `modelo parakeet incompleto... encoder.int8.onnx
(corre instant setup)`.)

| SO      | Default sin `DICTADO_DATA`                                          |
|---------|---------------------------------------------------------------------|
| Windows | `%LOCALAPPDATA%/instant/models` (vacío aquí: ese dir ni existe)     |
| Linux   | `~/.local/share/instant/models` (o `$XDG_DATA_HOME/instant/models`) |
| macOS   | `~/Library/Application Support/instant/models`                      |

Los modelos de este repo viven en `C:/PROYECTOS/Instant/models`, así que
`instant-run.bat` e `instant-setup.bat` fijan
`set DICTADO_DATA=C:/PROYECTOS/Instant/models` — solo si la var no viene
ya definida (`if not defined DICTADO_DATA`), para respetar un override
externo. `instant-status.bat` muestra `DICTADO_DATA=%DICTADO_DATA%` y
si está vacía avisa que el default está VACÍO.

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
- `modelo parakeet incompleto... encoder.int8.onnx` → el exe buscó en el
  default `%LOCALAPPDATA%/instant/models` (vacío) porque `DICTADO_DATA` no
  estaba definida (visto en log 06:13:23). Usa `instant-run.bat` /
  `instant-setup.bat` (la fijan a `C:/PROYECTOS/Instant/models`) o define
  `DICTADO_DATA` a mano. Solo si el error persiste, corre `instant setup`.
