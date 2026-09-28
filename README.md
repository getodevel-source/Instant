# Instant

Hold-to-talk offline en español. Mantén la tecla, habla, suelta y el texto se pega donde esté el cursor.

Pipeline: mic 16 kHz → Silero VAD (segmenta frases) → Parakeet TDT v3 int8
(`sherpa-onnx`, CPU) → portapapeles + Ctrl+V. Sin nube, sin GPU.
Paquete Python en `dictado/` (nombre `instant`, entry point `instant`).

## Estado actual verificado (esta vuelta, daemon VIVO ajeno)

- Proceso: `instant.exe` VIVO (verificado al ejecutar `instant-status.bat` ->
  `instant.exe vivo: SI`). NO lo levanto ni lo toco: es de otro worker.
- Log (`%APPDATA%/instant/instant.log`, tail de 15 lineas tal cual): a las
  13:23 decodifico 66.2 s en 5 segmentos (`decode 5 segs en 1.97s`,
  `RTF=0.03x`); de 13:23:47 a 13:28:47 repite `vivo, esperando F9...`
  cada minuto. Sin tracebacks.
- Config (`%APPDATA%/instant/config.json`, leida tal cual):
  `mic_index: 3`, `key: f9`, `threads: 4`, `sound: false`, `llm_url: ""`.
- CLI (exe por ruta absoluta, NO esta en PATH): `instant.exe --help` lista
  `setup,run,check`; `setup --help` muestra `-y/--yes ... --no-probe`;
  `check --help` sale 0. (Los tres ejecutados esta vuelta.)
- En mi shell `DICTADO_DATA` vacia y el default
  `%LOCALAPPDATA%/instant/models` VACIO (lo dice el propio status);
  el daemon ajeno sigue vivo igual. No lo toco.
- Modelos YA descargados en `models/` (no se versionan, no se empaquetan):
  `parakeet-v3-int8/` ~640 MB + `silero-vad/silero_vad.onnx` ~1 MB.
  Diagnostico sin levantar nada: `instant-status.bat`.

## Instalación en un comando

Clona el repo y corre el instalador de tu SO. Los dos instaladores hacen lo
mismo: instalan el paquete `instant` y corren `instant setup --yes`, que
descarga TODO JUNTO (Parakeet v3 int8 ~670 MB + Silero VAD ~1 MB, español
único) en un solo paso (fuente: `install.bat`, `install.sh`,
`dictado/src/instant_app/models.py` → `download_models()`; flag `--yes`
verificado en `instant.exe setup --help` y `dictado/src/instant_app/setup.py`).

### Windows (sin dependencias del sistema, solo Python 3.11+ en PATH)

```bat
git clone https://github.com/getodevel-source/Instant.git && cd Instant && install.bat
```

Pasos: 1/2 `pip install -e dictado`, 2/2 `instant setup --yes`
(con fallback a `python -m instant_app setup --yes` si `instant` aún no está
en PATH en esa terminal — mismo fallback que `instant-setup.bat`).

### Linux (X11)

```bash
git clone https://github.com/getodevel-source/Instant.git && cd Instant && ./install.sh
```

Pasos: 1/3 `sudo apt-get install libportaudio2 xclip xdotool`, 2/3
`pip install -e dictado`, 3/3 `instant setup --yes`.
Wayland: el pegado con `xdotool` no funciona; usa sesión X11.
El hotkey con `pynput` requiere X. (Fuente: `dictado/README.md`.)

### macOS

```bash
git clone https://github.com/getodevel-source/Instant.git && cd Instant && ./install.sh
```

(`install.sh` detecta el SO con `uname -s`: en macOS corre
`brew install portaudio` en vez del `apt-get`.) Autoriza micrófono y
accesibilidad (pegado por teclado) en Ajustes del Sistema. Teclas F: usa
Fn+F9 si tu teclado las mapea a multimedia. (Fuente: `dictado/README.md`.)

Verificado esta vuelta: `bash -n install.sh` → exit 0; rama Linux con stubs
(`sudo`/`pip`/`instant` falsos) → instala `libportaudio2 xclip xdotool` +
`setup --yes`, exit 0; rama macOS con stubs (`brew`/`pip`/`instant` falsos)
→ `brew install portaudio` + `setup --yes`, exit 0. `install.bat`: la línea
`pip install -e dictado` se ejecutó tal cual (requirements ya satisfechos,
exit 0); el `setup --yes` completo NO se ejecuta aquí (pesa/red y el daemon
ajeno está vivo). `pyinstaller` ausente (exit 127): sin build local.

Qué se te pide: nada en modo un-comando (`--yes` no pregunta). Solo se te
pedirá micrófono y tecla si corres `instant setup` interactivo después;
el idioma es fijo: español.

## Uso manual (tras instalar)

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
del repo (fijan `DICTADO_DATA` al repo; `setup`/`status` van al exe o
`python -m instant_app`, y `run` sin args arranca oculto con pythonw):

```bat
instant-setup.bat       :: = instant setup (con DICTADO_DATA al repo)
instant-run.bat         :: sin args = daemon OCULTO (pythonw, sin ventana); con args = passthrough en consola
instant-status.bat      :: diagnostico: vivo SI/NO (PID + tasklist), DICTADO_DATA, log, config
instant-stop.bat        :: frena solo la instancia instant (por PID); sale 0
install-autostart.bat   :: crea acceso en Startup -> instant-run.bat (listo, NO activado)
uninstall-autostart.bat :: quita el acceso de Startup
REM Linux/macOS: instant-run.sh / instant-status.sh / instant-stop.sh (bash, +x; mismo rol que sus primos .bat)
```

El daemon `run` NUNCA muestra ventana: `instant-run.bat` lo lanza con
`pythonw.exe -m instant_app run` (primo del `python.exe` que tiene el
paquete, fallback `C:\Python314\pythonw.exe`, luego `python.exe` oculto
vía `Start-Process -WindowStyle Hidden`). Sin duplicados: si ya hay
instancia viva avisa y no lanza otra. PID en
`%APPDATA%/instant/instant.pid` (se limpia al salir o si queda stale).
Autostart por acceso en la carpeta Startup del usuario (reversible con
`uninstall-autostart.bat`); no se activó en esta vuelta.

## Arranque con el sistema

Forma recomendada: la casilla de arranque en `instant setup` (TUI, paso 4b):
muestra el estado real del SO y pregunta `activar arranque con el sistema? s/n`
(default = estado actual). NoInteractivo:

```bash
instant setup --autostart     # activa sin preguntar
instant setup --no-autostart  # desactiva sin preguntar
```

Detalles verificados en `dictado/src/instant_app/setup.py` (`_parse_args`,
paso 4b) y `__main__.py` (forward de flags): con `--yes` solo se conserva el
estado actual salvo que pases `--autostart`/`--no-autostart`; si se pasan los
dos juntos gana `--no-autostart`; la preferencia queda en `config.json`
(`autostart: true/false`) pero el estado real lo manda el SO.
Arranque manual por SO (equivale a lo que hace la casilla):

### Windows

```bat
install-autostart.bat     :: crea acceso en Startup -> instant-run.bat (daemon oculto en el proximo login)
uninstall-autostart.bat   :: quita el acceso (no toca el daemon en curso; usa instant-stop.bat para frenarlo)
```

### Linux (manual: lo mismo que hace la casilla)

Crea `~/.config/autostart/instant.desktop` apuntando al launcher de este repo:

```ini
[Desktop Entry]
Type=Application
Name=Instant Dictado
Comment=Instant hold-to-talk (daemon oculto)
Exec=/ruta/al/repo/instant-run.sh
Path=/ruta/al/repo
Terminal=false
X-GNOME-Autostart-enabled=true
```

Para desactivar: borra el `.desktop` (o `X-GNOME-Autostart-enabled=false`).

### macOS (manual: lo mismo que hace la casilla)

Crea `~/Library/LaunchAgents/com.instant.dictado.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
  <key>Label</key><string>com.instant.dictado</string>
  <key>ProgramArguments</key>
  <array><string>/ruta/al/repo/instant-run.sh</string></array>
  <key>WorkingDirectory</key><string>/ruta/al/repo</string>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
```

Activa con `launchctl load ~/Library/LaunchAgents/com.instant.dictado.plist`;
desactiva con `launchctl unload` + borrar el plist.

### Verificar y frenar (los 3 SO)

```bash
./instant-status.sh  # Linux/macOS: vivo SI/NO + DICTADO_DATA + log tail + config (no levanta nada)
./instant-stop.sh    # frena solo la instancia instant por PID; nunca killall
```
```bat
instant-status.bat   :: Windows: lo mismo (PID + tasklist, modelos, log, config)
instant-stop.bat     :: Windows: frena solo la instancia por PID
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
