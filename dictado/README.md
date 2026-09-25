# Instant

Hold-to-talk offline en español. Mantén la tecla, habla 60-120s, suelta y pega.

Pipeline: mic 16kHz → Silero VAD (frases) → Parakeet TDT v3 int8 offline
(`sherpa-onnx`, CPU) → portapapeles + Ctrl+V. Sin nube, sin GPU.
Idioma: Español (único). Sin selector: el setup muestra
"Español (único)" y guarda `lang: "es"` en la config para futuro;
el engine transcribe igual que siempre.

Errores conocidos del modelo (no son bugs de la app): nombres propios
raros pueden salir deformados (p.ej. "Instant" → "instante"); siglas y
anglicismos se transcriben por fonética. El pulido LLM opcional ayuda
con tildes y puntuación, no con estos casos.

## Instalar

```bash
pip install -e .
```

### Windows

Sin dependencias del sistema. Si la tecla no responde en apps elevadas,
corre la terminal como administrador.

### Linux (X11)

```bash
sudo apt install libportaudio2 xclip xdotool
pip install -e .
```

Wayland: el pegado con `xdotool` no funciona; usa sesión X11 o
`wtype` manual. El hotkey con `pynput` requiere X.

### macOS

```bash
brew install portaudio
pip install -e .
```

Autoriza micrófono y accesibilidad (pegado por teclado) en
Ajustes del Sistema. Teclas F: usa Fn+F9 si tu teclado las mapea a multimedia.

## Uso

```bash
instant setup   # TUI simple: modelos juntos, mic con medidor, tecla, test final
instant run     # daemon: mantén la tecla, suelta para transcribir
instant check   # boot rapido: tecla + mic probe + warmup (<5s)
```

El setup interactivo hace, en orden:

1. **Modelos juntos**: baja Parakeet (~670MB) + VAD (~1MB) en un solo
   paso con progreso `[1/2]` y `[2/2]`. Sin modos parciales.
2. **Micrófono**: lista entradas reales, eliges por número, medidor de
   nivel de 3s (habla y mira las barras) y probe final. Guarda `mic_index`.
3. **Idioma**: Español (único), sin selector.
4. **Tecla**: modo captura — "Presiona la tecla para dictar...
   (Enter = F9)". Valida contra las teclas válidas y repite si no es válida.
5. **Test final**: probe del mic + warmup de modelos y mensaje
   "Listo. Mantén F9 y dicta".

No interactivo (no pregunta nada, conserva tu mic y tu tecla):

```bash
instant setup --yes --no-probe
instant setup --yes --mic 3 --key f9 --threads 4 --no-sound
```

Flags avanzados (solo flags, el interactivo no los pregunta):
`--threads` (default 4), `--sound`/`--no-sound` (default off),
`--llm-url` (default vacío = off), `--mic`, `--key`, `--no-meter`,
`--no-probe`, `--yes`, `--check-deps`, `--fix-deps`.

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
| Python >= 3.10 | `sys.version` | no (instalalo vos) | python.org / tienda |
| pip | `import pip` | sí (`ensurepip`) | `python -m ensurepip` |
| numpy, sounddevice, sherpa-onnx, pyperclip, huggingface_hub | `importlib` | sí (`pip install`) | `pip install <paquete>` |
| keyboard (win) / pynput (linux/mac) | `importlib` | sí (`pip install`) | `pip install <paquete>` |
| portaudio linux (`libportaudio2`) | lib/ldconfig/dpkg | sí (`apt`) solo con sudo sin password o root | `sudo apt install libportaudio2` |
| xclip/xsel linux | PATH | sí (`apt`) solo con sudo sin password o root | `sudo apt install xclip` |
| xdotool linux (X11) | PATH | sí (`apt`) solo con sudo sin password o root | `sudo apt install xdotool` |
| portaudio mac | `brew --prefix portaudio` | sí (`brew`) solo si tenés brew | `brew install portaudio` |
| Windows: nada del sistema | — | — | no hace falta nada |

Wayland: `xdotool` no anda (sale `[FALTA]`, no es auto, usa sesión X11
o `wtype` manual). Sin red no se instala nada: queda `[FALTA]` con
el hint, sin traceback. `install.bat`/`install.sh` las pueden llamar
así (no se tocan en este cambio): `instant setup --check-deps` para
mostrar, `instant setup --fix-deps` para autoinstalar lo permitido.

## De dónde saca los modelos (DICTADO_DATA)

Precedencia efectiva:

1. `DICTADO_DATA` gana siempre (aunque no exista, se respeta tal cual).
2. `./models` con `parakeet-v3-int8/encoder.int8.onnx` gana al dir de usuario.
3. `./models` sin ese marcador se ignora y cae al dir de usuario.
4. Si no hay nada, va al dir de usuario (`%LOCALAPPDATA%/instant/models`
   en win, `~/.local/share/instant/models` en linux,
   `~/Library/Application Support/instant/models` en mac).

Sin modelos o sin mic, `setup` avisa y sigue (no crashea); `run` sin
modelos pide correr `setup` con red primero.

Teclas: Windows `f9 f10 f20 scroll pause`, Linux/macOS `f9 f10 f11 f12`.
Config en `%APPDATA%/instant` (win), `~/.config/instant` (linux),
`~/Library/Application Support/instant` (mac). Env `DICTADO_*` pisa config
(`DICTADO_MIC`, `DICTADO_KEY`, `DICTADO_THREADS`, `DICTADO_SOUND`,
`DICTADO_MAX_SEG`, `DICTADO_LLM_URL`).

## Pulido LLM (opcional, off por defecto)

Si tienes `llama-server` local corriendo, pasa `--llm-url` al setup
(o env `DICTADO_LLM_URL=http://127.0.0.1:8080`) para corregir tildes y
puntuación. Sin servidor, el pipeline funciona idéntico sin él.
Nunca requiere red ni nube: solo ese endpoint local opt-in.

## Binarios por SO

Pendiente: builds PyInstaller por release en GitHub (win/linux/mac).
Hoy se distribuye como paquete Python.
