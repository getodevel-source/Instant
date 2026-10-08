# Instant

Hold-to-talk offline en español. Mantén la tecla, habla 60-120s, suelta y pega.

Pipeline: mic 16kHz → Silero VAD (frases) → Parakeet TDT v3 int8 offline
(`sherpa-onnx`, CPU) → portapapeles + Ctrl+V. Sin nube, sin GPU.
Idioma: Español (único). Sin selector: el setup muestra
"Español (único)" y guarda `lang: "es"` en la config para futuro;
el engine transcribe igual que siempre.

Errores conocidos del modelo (no son bugs de la app): nombres propios
raros pueden salir deformados (p.ej. "Instant" → "instante"); siglas y
anglicismos se transcriben por fonética. Un perfil de vocabulario permite
corregir variantes reconocidas explícitamente; el pulido LLM por sí solo
ayuda con tildes y puntuación, pero no reemplaza el reconocimiento de audio.

## Instalación

En Windows, la vía recomendada es el instalador de la [última release](https://github.com/getodevel-source/Instant/releases/latest) (`Instant-Setup.exe`): por usuario, sin admin, con desinstalador y actualización in-place. El `Instant.exe` portable y los binarios de Linux/macOS viven en la misma release.

Desde la raíz del repositorio, `install.bat` (Windows) o `./install.sh` (Linux/macOS) crea `.venv`, instala Instant y abre el asistente de configuración. `INSTANT_UNATTENDED=1` conserva el modo sin preguntas.

Para desarrollar el paquete desde `dictado/`:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -e .
```

Los ejemplos de CLI siguientes suponen ese entorno virtual activo. Los instaladores del repositorio usan el `.venv` de la raíz automáticamente.

### Windows

Sin dependencias del sistema. Si la tecla no responde en apps elevadas,
corre la terminal como administrador.

En Windows, las entradas WASAPI se abren en modo compartido con conversión
automática a 16 kHz cuando el dispositivo usa otra frecuencia (por ejemplo,
48 kHz), requerida por VAD y Parakeet. En micrófonos estéreo se capturan
hasta dos canales y se usa el de mayor energía.
El selector de configuración consolida alias repetidos entre host APIs y
prioriza WASAPI; si un backend ofrece varias entradas con el mismo nombre,
las conserva y las distingue por índice.
Al iniciar cada dictado se vuelve a resolver el micrófono guardado. Si el
inicio por callback falla, Instant intenta aliases del mismo nombre y deja
constancia del backend usado o del error en el log; el diagnóstico abre también
una captura por callback para comprobar ese mismo modo.

Al cerrar la ventana, la interfaz se cierra para liberar sus recursos; el
dictado sigue activo en la bandeja. Abrir Instant desde el icono enfoca una
ventana existente o abre una nueva, sin duplicar ventanas. Clic derecho ofrece
«Abrir ventana de Instant», «Configurar micrófono y tecla», «Diagnóstico» y
«Salir de Instant» (que detiene el dictado).
Windows puede ubicar el icono bajo la flecha de iconos ocultos; su visibilidad
fija se configura en la barra de tareas.

### Linux (X11)

```bash
sudo apt install python3-venv libportaudio2 xclip xdotool libxcb-cursor0 libegl1 libgl1 libxkbcommon0
```

El panel Qt necesita las libs xcb/GL (el wheel de PySide6 no las trae);
`install.sh` las intenta instalar solo. Wayland: el pegado con `xdotool` no
funciona; usa sesión X11 o `wtype` manual. El hotkey con `pynput` requiere X.

### macOS

```bash
brew install portaudio
```

El panel Qt abre sin dependencias extra. Autoriza micrófono y accesibilidad
(pegado por teclado) en Ajustes del Sistema. Teclas F: usa Fn+F9 si tu teclado
las mapea a multimedia.

## Uso

Con el entorno virtual activado:
```bash
instant setup   # panel de configuración (los tres sistemas)
instant run     # daemon: mantén la tecla, suelta para transcribir
instant stop    # frena el daemon (lo usa también el desinstalador)
instant check   # boot rapido: tecla + mic probe + warmup (<5s)
```

`instant setup` abre el centro gráfico PySide6 en los tres sistemas: una sola
página con scroll y cuatro bloques. Arriba, la portada con el estado del
dictado, la tecla y los botones de iniciar/detener; después, micrófono con
selector y prueba de nivel (3 s), tarjeta General con tecla y arranque con el
sistema, y **Vocabulario**: tabla por perfil con término, variantes
(`a | b | c`), pill de sonido (`≈`) y botón de quitar (`✕`). «Añadir término»
agrega una fila en blanco lista para escribir. El panel indica los cambios
pendientes de guardar y, después de guardar, avisa si hace falta reiniciar
Instant. El diagnóstico muestra el informe en una ventana independiente. La
ventana puede cerrarse sin detener el daemon; en Windows queda el icono de
bandeja, y en Linux/macOS el daemon sigue vivo hasta `instant-stop.sh`.

Sin ventana (servidores, SSH, scripts): `instant setup --tui` mantiene el
asistente de terminal; cualquier flag de CLI también lo usa.

`instant` sin argumentos abre el panel y se asegura de un solo daemon activo.
Si ya hay una ventana abierta, una segunda apertura le pasa el pedido y sale
(Windows: mutex + `FindWindow`; Linux/macOS: canal `QLocalServer`).

El overlay es Qt Quick en los tres sistemas, con dos estilos (`overlay_style`
en la config): `orbital` (orbe con anillos que respiran con la voz, por
defecto) y `classic` (pastilla con barras y tecla visible). Ambos comparten la
paleta con la ventana. Si Qt no puede abrir (X11 sin GL, instalación vieja sin
PySide6 usable), el daemon cae solo al respaldo Tk y lo deja en el log.

Para retocar la interfaz, los colores están en
[`branding.py`](dictado/src/instant_app/branding.py) (`PALETTE`, única fuente de
verdad) y las medidas, la tipografía y los tiempos de animación en
[`theme.py`](dictado/src/instant_app/theme.py), que arma la hoja de estilo. Los
overlays repiten la paleta a mano en
[`qml/overlay.qml`](dictado/src/instant_app/qml/overlay.qml) y
[`qml/overlay_orbital.qml`](dictado/src/instant_app/qml/overlay_orbital.qml)
porque se cargan sin motor de plantillas;
`tests/test_overlay_palette.py` falla si se despegan. El tamaño del orbe se
ajusta con `compositionScale` y su posición con `_OVERLAY_BOTTOM_GAP` en
`overlay.py`.

El asistente de terminal (`instant setup --tui`, o con cualquier flag de CLI)
hace, en orden:

1. **Modelos**: descarga Parakeet (~670 MB) y VAD (~1 MB) si faltan.
2. **Micrófono**: muestra nombre, backend y canales; permite medir nivel. Guarda nombre e índice como fallback si cambia el orden de dispositivos.
3. **Idioma**: español fijo.
4. **Tecla**: captura una tecla individual (Enter conserva la actual).
5. **Arranque con el sistema**: muestra el estado real y permite activarlo o desactivarlo.
6. **Prueba final**: abre el micrófono y calienta los modelos.

Modo no interactivo (conserva el micrófono y la tecla actuales):

```bash
instant setup --yes --key f9 --threads 4 --no-sound
```
`--mic` recibe el índice PortAudio mostrado junto al dispositivo; el setup guarda también el nombre para recuperarse si Windows cambia los índices.

Flags avanzados (solo flags, el interactivo no los pregunta):
`--threads` (default 4), `--sound`/`--no-sound` (default off),
`--llm-url` (default vacío = off), `--context-profile`,
`--context-term "grafía=variante1|variante2"`,
`--context-remove-term "grafía"`, `--context-delete-profile`,
`--mic`, `--key`, `--no-meter`, `--no-probe`, `--yes`,
`--check-deps`, `--fix-deps`.
Arranque sin preguntar: `--autostart` lo prende, `--no-autostart` lo apaga;
con `--yes` pelado no se toca nada (se conserva lo que ya tenés).

## Dependencias

`instant setup` chequea las dependencias y te muestra `[OK]`/`[FALTA]`
en criollo. Con `--yes` solo avisa (nunca frena la config).
Con `--check-deps` muestra la tabla igual; con `--fix-deps` instala
lo que el SO deja y vuelve a chequear.

```bash
instant setup --check-deps
instant setup --fix-deps
```

| Qué | Cómo se detecta | Auto | Manual si falta |
|---|---|---|---|
| Python >= 3.12 | `sys.version` | no (instalalo vos) | python.org / tienda |
| pip | `import pip` | sí (`ensurepip`) | `python -m ensurepip` |
| numpy, sounddevice, sherpa-onnx, pyperclip | `importlib` | sí (`pip install`) | `pip install <paquete>` |
| PySide6 (panel, los tres sistemas) | `importlib` | sí (`pip install`) | `pip install PySide6` |
| Pillow (icono de ventana) | `importlib` | sí (`pip install`) | `pip install Pillow` |
| keyboard (win) / pynput (linux/mac) | `importlib` | sí (`pip install`) | `pip install <paquete>` |
| pystray (Windows) | icono de bandeja | sí (`pip install`) | `pip install pystray` |
| portaudio linux (`libportaudio2`) | lib/ldconfig/dpkg | sí (`apt`) solo con sudo sin password o root | `sudo apt install libportaudio2` |
| libs Qt linux (`libxcb-cursor0`, GL) | — (la pista la da el panel) | `install.sh` intenta `apt` | `sudo apt install libxcb-cursor0 libegl1 libgl1 libxkbcommon0` |
| xclip/xsel linux | PATH | sí (`apt`) solo con sudo sin password o root | `sudo apt install xclip` |
| xdotool linux (X11) | PATH | sí (`apt`) solo con sudo sin password o root | `sudo apt install xdotool` |
| portaudio mac | `brew --prefix portaudio` | sí (`brew`) solo si tenés brew | `brew install portaudio` |
| Windows: nada del sistema | — | — | no hace falta nada |

Wayland: `xdotool` no anda (usa sesión X11 o `wtype` manual). Sin red no se instalan paquetes ni modelos; el setup informa qué falta. Para evitar preguntas en instalaciones automatizadas, define `INSTANT_UNATTENDED=1` antes de correr el instalador del repositorio.

## De dónde saca los modelos (DICTADO_DATA)

Precedencia efectiva:

1. `DICTADO_DATA` gana siempre (aunque no exista, se respeta tal cual).
2. `./models` con `parakeet-v3-int8/encoder.int8.onnx` gana al dir de usuario.
3. Con el ejecutable congelado, `../models` respecto de su carpeta se usa si
   contiene el marcador; así el panel y el daemon comparten los modelos del
   checkout.
4. `./models` sin ese marcador se ignora.
5. Si no hay nada, va al dir de usuario (`%LOCALAPPDATA%/instant/models`
   en win, `~/.local/share/instant/models` en linux,
   `~/Library/Application Support/instant/models` en mac).

Sin modelos o sin mic, `setup` avisa y sigue (no crashea); `run` sin
modelos pide correr `setup` con red primero.

Teclas: Windows `f9 f10 f20 scroll pause`, Linux/macOS `f9 f10 f11 f12`.
Config en `%APPDATA%/instant` (win), `~/.config/instant` (linux),
`~/Library/Application Support/instant` (mac). Env `DICTADO_*` pisa config
(`DICTADO_MIC`, `DICTADO_KEY`, `DICTADO_THREADS`, `DICTADO_SOUND`,
`DICTADO_MAX_SEG`, `DICTADO_LLM_URL`, `DICTADO_AUTOSTART=1/0`).

PID file: `run` escribe `instant.pid` junto a la config al arrancar y lo
borra al salir limpio; los lanzadores `.bat` lo usan para stop/status
sin tocar procesos ajenos.

## Arranque con el sistema

En Windows, la casilla «Iniciar con Windows» está en el panel gráfico.
En Linux/macOS, el asistente terminal pregunta s/n después de la tecla,
muestra el estado real y qué va a crear; el default conserva el estado actual.
Si lo prendés, el daemon arranca solo y oculto en el próximo login; si lo apagás, no arranca más.

```bash
instant setup                       # interactivo: pregunta s/n
instant setup --yes --no-probe      # no toca nada, conserva lo que hay
instant setup --autostart           # lo prende sin preguntar
instant setup --no-autostart        # lo apaga sin preguntar
```

Qué crea en cada sistema (solo eso, nada más):

- Windows: acceso `Instant Dictado.lnk` en
  `%APPDATA%/Microsoft/Windows/Start Menu/Programs/Startup`, que apunta
  a `instant-run.bat` del repo si lo encuentra (modo dev), y si no a
  `instant.exe run` por PATH o `pythonw -m instant_app run`. Se crea con
  el powershell que ya trae Windows, sin instalar nada nuevo.
- Linux: archivo `~/.config/autostart/instant.desktop` (estándar
  freedesktop) que lanza `instant run` oculto con `nohup`.
- macOS: `~/Library/LaunchAgents/com.instant.dictado.plist` que lanza
  `instant run` al iniciar sesión.

Para sacarlo alcanza con correr el setup y decir que no, o con
`instant setup --no-autostart`. Si lo borrás a mano de esas rutas vale
igual: el setup lo detecta apagado. Lo que vale de verdad es lo que hay
en el sistema, no la casilla guardada (`autostart` en la config es solo
un recordatorio; si no coinciden, el setup te avisa y deja lo del sistema).

## Contexto y vocabulario

En Windows, Preferencias permite crear perfiles y definir variantes exactas
que el reconocedor suele transcribir con otra grafía. Cada línea tiene la
grafía final, un tabulador y una o más variantes separadas por `|`:

```text
Instant	instante | in stand
Parakeet	para kit
```

Solo se reemplazan esas variantes completas; no se fuerza una palabra del
glosario si el texto no contiene una variante.

### Emparejamiento por sonido (`~`)

Listar cada grafía que el motor inventa no escala: una marca como `Qwen` salió
«Quen», «Cuentres», «Quemet» y «cuen» en el mismo log. Un `~` delante de la
grafía activa el emparejamiento por sonido para ese término, y cubre esas
variantes sin enumerarlas:

```text
~Qwen	cuentres | quemet
~GitHub	hit hub
~Parakeet	para kit
```

Con `~`, `Quen`, `cuen` y `Cuen` se corrigen solos, igual que las palabras que
el motor parte o pega (`O en Pi` → `OpenAI`, `Git Hub` → `GitHub`).

La sustitución por sonido es conservadora a propósito, porque una corrección
falsa hace más daño que el error que arregla. Solo actúa cuando la palabra:

- tiene cuatro letras o más (las cortas del español son casi todas corrientes);
- no es una palabra corriente protegida (`quien`, `buen`, `ven`, `para`,
  `might`, `that`…), así «a quien quieras» y «buen resultados» quedan intactos;
- no es ya la propia grafía preferida;
- si son varias palabras, la primera suena como el principio del término y el
  resto como el final, con solo espacios en medio: la «y» de «Qwen y GitHub»
  nunca se pierde.

Dejá `~` apagado en términos cuyas variantes sean palabras reales: ahí conviene
listarlas a mano (`commit`, `staging`). Para ver qué cambiaría sin aplicar
nada, el perfil se puede probar desde Python con `context.correct_aliases`.

En el pipeline actual estas correcciones se aplican al texto **después** del
reconocimiento; no son pistas acústicas para Parakeet. Se probó el sesgo
contextual (hotwords) y **no funciona** con este modelo: sherpa-onnx lo
tokeniza con un `bpe.vocab` de sentencepiece que el paquete de Parakeet v3 no
trae. Ver [`docs/motores.md`](../docs/motores.md).

Los perfiles y el vocabulario se guardan localmente en la configuración de
Instant. En Linux/macOS también se pueden gestionar desde setup:

```bash
instant setup --yes --no-probe --context-profile Trabajo \
  --context-term "Instant=instante|in stand"
```

Con `~` delante de la grafía se activa el sonido para ese término:

```bash
instant setup --yes --no-probe --context-profile Trabajo \
  --context-term "~Qwen=cuentres|quemet"
```

Para quitar un término o un perfil en Linux/macOS:

```bash
instant setup --yes --no-probe --context-profile Trabajo \
  --context-remove-term Instant
instant setup --yes --no-probe --context-profile Trabajo \
  --context-delete-profile
```

El perfil activo se puede elegir mediante `DICTADO_CONTEXT`. El vocabulario
explícito funciona sin LLM ni internet. Para pulido adicional, el LLM local
recibe el glosario activo; el audio nunca se envía a la nube.

## Pulido LLM (opcional, off por defecto)

Si tienes `llama-server` local corriendo, en Windows configura su URL en
Preferencias; en Linux/macOS usa `--llm-url` al setup (o
`DICTADO_LLM_URL=http://127.0.0.1:8080`). El LLM recibe la transcripción y el
glosario activo —no el audio— y corrige ortografía, tildes, puntuación y los
signos de apertura `¿`/`¡`. No puede aprovechar la entonación del audio ni
sustituir palabras: se rechaza toda salida que cambie la secuencia de palabras
(comparando el texto normalizado, sin tildes ni mayúsculas). Si el servidor
falla, se conserva la transcripción con las sustituciones exactas del
glosario; Instant nunca manda audio a la nube.

## Binarios por SO

Los binarios PyInstaller todavía requieren verificación antes de publicarse como distribución oficial.
