# Instant

Dictado por voz local en español: mantené F9, hablá y soltá. Instant transcribe y pega el texto en el campo enfocado. El reconocimiento corre en CPU; el audio no se envía a la nube.

![Ventana de Instant](docs/screenshots/ventana-ajustes.png)

*Una sola pantalla: estado, micrófono, ajustes y vocabulario. Los botones de cada término (sonido `≈`, quitar `✕`) se ven completos, sin recortes.*

## Instalación

Los instaladores preparan un entorno virtual dentro del checkout y abren el asistente de configuración. Python 3.12 o posterior es un requisito.

### Windows

```bat
git clone https://github.com/getodevel-source/Instant.git
cd Instant
install.bat
```

### Linux (X11)

```bash
git clone https://github.com/getodevel-source/Instant.git
cd Instant
./install.sh
```

### macOS

```bash
git clone https://github.com/getodevel-source/Instant.git
cd Instant
./install.sh
```

La primera configuración descarga Parakeet TDT v3 int8 (~670 MB) y Silero VAD (~1 MB). El asistente permite elegir micrófono y tecla. En Linux el pegado requiere X11; macOS puede pedir permisos de micrófono y accesibilidad.

Para instalaciones automatizadas, `INSTANT_UNATTENDED=1` ejecuta la configuración sin preguntas. `INSTANT_AUTOSTART=1` activa además el arranque con el sistema.

## Uso

En Windows:

```bat
instant-run.bat
instant-setup.bat
instant-status.bat
instant-stop.bat
```

Sin argumentos, `instant-setup.bat` abre la ventana de ajustes sin
dejar una consola abierta y **no** inicia el daemon: usa `dist/Instant.exe setup`
si el ejecutable está disponible, o `pythonw` en segundo plano. Los argumentos
explícitos conservan su salida de CLI en consola.

La ventana es una sola página con scroll: portada con estado y tecla,
micrófono con prueba de nivel, tarjeta General (tecla + arranque con
Windows) y **Vocabulario**, una tabla por perfil donde cada término lleva
sus variantes (`a | b | c`), el pill de sonido (`≈`, corrige también lo que
suena parecido) y el botón para quitarlo (`✕`).

![Tabla de vocabulario](docs/screenshots/vocab-tabla.png)

`dist/Instant.exe` sin argumentos abre el panel y se asegura de que haya un
solo daemon activo. `Instant.exe setup` es solo configuración. Cerrar la ventana
con X deja el icono y el servicio en la bandeja; «Salir de Instant» desde el
menú de la bandeja cierra ambos. «Abrir ventana» reutiliza la existente.

Antes de mantener F9, enfocá el prompt o campo editable de la CLI; Instant copia
el resultado y envía Ctrl+V al campo enfocado. En Windows, el overlay del daemon
usa Qt Quick, no muestra el contenido dictado y confirma «Copiado»; Linux/macOS
mantienen el fallback Tk. Windows puede ubicar el icono bajo la flecha de
iconos ocultos.

Mientras dictás, el orbe respira con tu voz (nivel y espectro reales del
micrófono); al soltar, un arco barre mientras transcribe y el tilde confirma.
Vive fijo abajo al centro del monitor donde trabajás:

![Orbe del overlay](docs/screenshots/overlay-orbital.png)

## Actualizaciones

Cada release de GitHub (`v*`) trae el ejecutable de cada sistema más su
`.sha256`. Sin hacerlo a mano:

```bat
instant update              :: dice si hay versión nueva
instant update --download DIR
instant-update.bat <archivo descargado>
```

o el botón «Buscar actualizaciones» de la ventana: consulta, descarga
verificada y, si aceptás, frena todo, respalda el exe anterior
(`Instant.exe.bak`) y arranca el daemon nuevo. Sin `.sha256` no instala.

La ventana consulta sola una vez por día y, si hay versión, el botón se
viste de primario («↓ Actualizar a vX»): sin modales ni apuros. El
instalador verifica el hash de nuevo, y si el daemon nuevo no levanta,
restaura el `.bak` automáticamente y reabre la ventana.

## Privacidad y datos

- El audio se procesa localmente con Silero VAD y Parakeet; no se sube a un servicio.
- Los modelos se descargan durante la configuración y se guardan en `models/`, que no se versiona.
- El pulido LLM es opcional y solo usa el servidor local configurado por el usuario.

## Desarrollo

El paquete está en `dictado/`; la guía detallada de configuración y CLI está en [`dictado/README.md`](dictado/README.md).

Toda la suite, desde `dictado/`:

```bash
python -m unittest discover -s tests
```

También se puede correr archivo por archivo. Los que usan Qt informan `SKIP` si PySide6 no está instalado:

```bash
python dictado/tests/test_regression.py     # overlay, setup, audio y modelos
python dictado/tests/test_context.py        # perfiles de vocabulario y pulido LLM
python dictado/tests/test_daemon_overlay.py # progreso por sesion y feedback
python dictado/tests/test_datadir.py        # precedencia de DICTADO_DATA
python dictado/tests/test_autostart.py
python dictado/tests/test_app_lifecycle.py  # daemon unico y arranque del panel
python dictado/tests/test_tray.py
python dictado/tests/test_gui_settings.py
python dictado/tests/test_gui_lifecycle.py
python dictado/tests/test_qml_success.py
```

La decisión de motor (por qué Parakeet y qué se descartó) está en
[`docs/motores.md`](docs/motores.md).

La interfaz de control de Windows usa PySide6/Qt Widgets; el icono de bandeja
y el overlay de Qt Quick del daemon son superficies independientes. El workflow
de tags `v*` configura PySide6 en el ejecutable Windows y mantiene binarios CLI
para Linux/macOS. Windows usa hooks selectivos de Qt, sin `--collect-all PySide6`:
el build local de PyInstaller 6.22.3 pasó de 303.651.236 a 96.099.689 bytes
(reducción del 68,4 %), ya con la bandeja, el overlay y el perfil de vocabulario.
El binario mantiene el tema oscuro y empaqueta el overlay QML.

Los cambios por versión están en [`CHANGELOG.md`](CHANGELOG.md), incluidas las
limitaciones conocidas.

## Desinstalar

1. Desactivá el arranque con el sistema: `instant-setup.bat` → Preferencias, o
   `instant setup --no-autostart` (en Linux/macOS, `./uninstall-autostart.bat`
   en Windows si lo instalaste con el script suelto).
2. Frená el dictado: `instant-stop.bat` (o `./instant-stop.sh`).
3. Borrá la carpeta del repositorio, que incluye `.venv` y `models/`.
4. Si querés borrar también tus datos y configuración:
   - Windows: `%APPDATA%\instant` (config y log) y `%LOCALAPPDATA%\instant` (modelos).
   - Linux: `~/.config/instant` y `~/.local/share/instant`.
   - macOS: `~/Library/Application Support/instant`.

Nada se escribe fuera de esas carpetas.

## Licencia

MIT. Ver [`LICENSE`](LICENSE).

Los ejecutables todavía no están firmados, así que Windows SmartScreen avisa la
primera vez que se abren. Es esperable hasta que haya un certificado de firma de
código; no es un indicio de que el binario esté alterado.
