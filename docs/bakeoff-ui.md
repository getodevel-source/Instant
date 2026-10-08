# Bake-off de UI: Qt Quick vs Web para el overlay del dictado

Fecha: 2026-10-08 · Entorno: Windows 11 (26100), Python 3.14.2, PySide6 6.11.2,
scenegraph Direct3D11, monitor de 200 Hz.

Pregunta: ¿conviene migrar la UI/anímación del overlay a la web (canvas/WebGL)
o llevar Qt Quick a su techo? Método: **el mismo diseño objetivo implementado
dos veces y medido con el mismo método**, no dos demos distintas.

## Método

- **Mismo replay**: `bench/bakeoff/frames.jsonl` (182 frames, 10.6 s, idle →
  starting → listening → processing → notice) grabado con la matemática REAL
  del daemon (`_LevelTracker`: 9 bandas log 80 Hz–7.5 kHz, gate de silencio,
  pitch por autocorrelación) sobre una pista silábica sintética determinística.
- **Misma ventana**: 224×224, `Qt.Tool | FramelessWindowHint |
  WindowStaysOnTopHint | WindowDoesNotAcceptFocus`, fondo transparente, abajo
  al centro.
- **Misma spec visual**: constantes detalladas en
  [`bench/bakeoff/README.md`](../dictado/bench/bakeoff/README.md).
- **Mismas métricas**: frames presentados (FrameAnimation vs rAF), p95 de
  intervalos por ventana de 1 s, arranque a primer frame, CPU y working set del
  árbol de procesos completo (`measure.py`, ctypes; incluye los subprocesos de
  Chromium), 3 corridas por lado, medianas.

## Resultados (medianas de 3 corridas)

| Métrica | QML (Qt Quick) | Web (QtWebEngine) |
|---|---|---|
| Arranque → primer frame | **158 ms** | 192 ms |
| FPS presentados | **200.5** | 60.0 |
| p95 de intervalo entre frames | **6.0 ms** | 16.8 ms |
| CPU (1 core = 100 %) | **0.8 %** | 0.9 % |
| RAM (working set del árbol) | **80.1 MB** | 231.8 MB |
| Frames en 11.75 s | 2325 | 705 |
| IPC overlay↔datos | ninguno (props Qt) | QWebChannel por señal (incluido en las métricas) |
| Peso de empaquetado añadido | **0** | ≈ 296 MB (DLL 194 MB + recursos 101 MB) |

Artefactos crudos: `bench/bakeoff/out/measure_v2.json`, `measure_v3.json` y
`measure_v4.json` (3 corridas por lado y ronda; las corridas individuales
tienen varianza — p. ej. un pico de CPU ajeno en una corrida web — por eso se
reporta la mediana).

Grilla visual (mismos instantes): `bench/bakeoff/out/compare_grid.png`.
Paridad de diseño lograda en ambos; diferencias menores esperables (curva del
halo, feather del barrido, tipografía del aviso).

## Hallazgos de plataforma (documentados con sondas en `bench/bakeoff/`)

1. **En Qt 6 los shaders de `ShaderEffect` son archivos, no cadenas**: Vulkan
   GLSL (`#version 440`, bloque std140 con `qt_Matrix`/`qt_Opacity` primero) →
   `qsb --qt6` → `.qsb` referenciado por URL. Las cadenas inline **no pintan
   nada y no avisan** (docs Qt 6.11 + sonda `probe_shader.py`/`probe3.py`).
   `MultiEffect` y `Qt5Compat.GraphicalEffects` sí renderizan (usan shaders
   precompilados).
2. **`RadialGradient` no existe en QtQuick core** (solo en el módulo de
   compatibilidad deprecado): los gradientes radiales propios van por shader.
3. **Precisión float32**: usar epoch (`Date.now()/1000`) como tiempo del shader
   rompe `mod`/`sin` sobre argumentos gigantes — los arcos del espectro
   desaparecían. Solución: tiempo relativo acumulado.
4. **WebEngine en QML**: la propiedad `webChannel` del `WebEngineView` es
   `QQmlWebChannel` (sin binding en PySide) → el canal se crea en QML (tipo
   `WebChannel`) y el bridge Python se registra por una función QML.
   `runJavaScript` del view QML exige un callback `QJSValue` imposible de
   construir desde Python → el canal **bidireccional por señales**
   (`frame`/`command` + slot `event`) es el camino viable.
5. **Transparencia per-pixel: funciona** con `WebEngineView` +
   `backgroundColor: "transparent"` en ventana transparente (esquinas con
   alpha 0 en `grabWindow`, píxel central idéntico al canvas).
6. **Chromium tope 60 fps** en este entorno (p95 16.8 ms) aunque el monitor es
   de 200 Hz; QML presenta al refresh completo (200 fps, p95 6 ms).
7. Trampa menor reproducida: `QUrl.fromLocalFile` con ruta relativa produce una
   URL inválida (`file://dictado/...`) — causó un falso negativo de carga.

## Ergonomía de iteración (lo que costó llegar al diseño final)

| | QML | Web |
|---|---|---|
| Ciclos de edición→corrida hasta el diseño final | 9 | 8 |
| Dónde se fue el tiempo | shaders: dialecto qsb (2), precisión de tiempo (1), geometría 200→224 (1), pulido de trazo (2) | puente Qt: marshalling de callbacks (1), import/orden del canal (3); canvas portado casi directo |
| LOC del visual | shader 119 + QML 130 | canvas 200 |
| LOC de integración (runner/host) | 126 | 190 + host 37 |

El canvas2d es un target natural para el LLM (port de la spec casi directo);
la **fricción de la ruta web no está en el dibujo sino en el puente Qt**
(QWebChannel). Del lado QML, la fricción está en el dialecto de shaders y en
la cabeza de build (`qsb`), pero el resto es declarativo.

## Ronda 2: techo visual (v3)

Mismo replay, misma ventana, mismas métricas; diseño mucho más ambicioso
(blob fluido con fbm + domain warp, anillo deformado por las 9 bandas,
18 embers deterministas por hash, sweep con eco) y cada stack en su techo:
shader RHI en QML, **WebGL2** en la web (el cuerpo GLSL es el mismo; solo
cambia el preludio: bloque std140 vs uniforms sueltos).

| Métrica (mediana de 3) | QML v3 | Web v3 (WebGL2) |
|---|---|---|
| Arranque → primer frame | 187 ms | 186 ms |
| FPS presentados | **200.6** | 60.2 |
| p95 de intervalo | **6.0 ms** | 16.8 ms |
| CPU (1 core) | **0.6 %** | 1.2 % |
| RAM (working tree) | **80.0 MB** | 225.5 MB |
| Frames en 11.75 s | **2318** | 707 |

Grilla: `bench/bakeoff/out/compare_grid_v3.png` (paridad alta: el blob, el
anillo ondulado y los embers son casi idénticos entre stacks, como lo predice
compartir el GLSL; el barrido de processing queda en fases distintas por los
relojes independientes, cosmético).

Lectura:

- **Ninguno de los dos se quedó sin resto.** QML sostiene fbm + 18 partículas a
  200 fps (p95 6 ms, CPU 0.6 %); WebGL2 rinde lo mismo en Chromium a 60 fps
  con CPU 1.2 %. El techo visual de este diseño no discrimina.
- **La ronda 2 movió el arranque**: el shader más pesado encarece el pipeline
  RHI de Qt (≈158 → 187 ms en las medianas de cada ronda); el lado web quedó
  igual (~192 → 186 ms). Empatan.
- **El resto del cuadro no cambió**: tope de 60 fps de Chromium, ~3× RAM,
  CPU igual o hasta 2× según la ronda, y los ~296 MB de empaquetado siguen
  del lado web.
- **Iteración**: el flujo `.frag → qsb` ya estaba aceitado: el v3 QML salió
  bien al primer corrido (0 ciclos de diseño). En web, 2 ciclos — y ninguno
  fue del shader: fueron de plomería de captura (`preserveDrawingBuffer`;
  sin él `toDataURL()` devuelve un buffer vacío aunque la pantalla se vea bien).
- Para subir más: del lado QML quedan QtQuick3D, partículas con física y
  capas; del lado web, post-proceso estilo DOF y assets de diseñador (Rive).
  La restricción práctica web sigue siendo el tope de 60 fps y el peso.

## Ronda 3: motor 3D + post-proceso propio (v4)

Qué se subió, por lado:

- **QML**: escena QtQuick3D real — orbe PBR con dos luces direccionales y
  MSAA, anillo de onda de 48 esferas (`Repeater3D`), embers 3D con la misma
  matemática de hash que los shaders y sweep de processing con eco. El
  post-proceso es **propio**: la escena se captura con `ShaderEffectSource`
  (`hideSource`) y pasa por `bloom_h` (umbral + gaussiana horizontal a media
  resolución) y `bloom_v` (gaussiana vertical + composición + tonemap +
  dithering), ambos `.frag → qsb`.
- **Web**: el shader de la ronda 2 + cadena FBO WebGL2 equivalente
  (umbral+blurH → blurV+compose, tonemap exponencial, dithering, alfa
  correcto de punta a punta).

| Métrica (mediana de 3) | QML v4 (3D + bloom propio) | Web v4 (FBO bloom) |
|---|---|---|
| Arranque → primer frame | 267 ms | 220 ms |
| FPS presentados | **200.3** | 60.2 |
| p95 de intervalo | **6.0 ms** | 16.8 ms |
| CPU (1 core) | 1.7 % | 0.9 % |
| RAM (working set) | **110.1 MB** | 229.4 MB |
| Frames en 11.75 s | **2305** | 707 |

Grilla: `bench/bakeoff/out/compare_grid_v4.png`. Artefacto:
`bench/bakeoff/out/measure_v4.json`.

Hallazgos de la ronda:

1. **El glow del motor Quick3D no compone sobre ventana transparente**
   (`ExtendedSceneEnvironment` con fondo transparente deja el halo en alfa 0;
   con fondo opaco el spill aparece — sonda `probe_q3d.py`). Para un overlay
   transparente el post-proceso tiene que ser propio y alfa-consciente:
   exactamente la cadena que se terminó usando en ambos lados.
2. **En un `ShaderEffect` el uniform sampler debe llamarse igual que la
   propiedad QML** (`src`, `scene`, `bloom`). Si no, la textura no se ata y el
   shader muestrea ceros **en silencio**, sin warnings — causó los frames
   vacíos de la cadena v4 hasta corregirlo (`probe_chain.py` lo aisló por
   etapas: directo / captura / bloom).
3. `ShaderEffectSource` **sí** captura un `View3D` (con `hideSource`): el
   fallo previo era el punto 2, no la captura.
4. Web: `preserveDrawingBuffer` es necesario para que `toDataURL()` no
   devuelva un buffer vacío; y el uv de un pass a media resolución debe
   normalizarse contra **su** viewport (un cuadrante si se mezclan tamaños).
5. Rive no se pudo evaluar sin assets de diseñador: queda como requisito real
   de la ruta web si se quiere ese ecosistema.

Lectura: a 224 px el motor 3D no lee mejor que el shader vectorial (v3) para
este diseño — un orbe de ~34 px no gana tanto con PBR — y Quick3D exige
maquinaria extra (pipeline 3D + captura offscreen + post propio): el arranque
pasó de 187 a 267 ms y la RAM de 80 a 110 MB, pagando por un payoff visual
modesto **en esta escala**. Sigue sosteniendo 200 fps (p95 6 ms). El lado web
no cambió: mismo tope de 60 fps y ~230 MB.

## Veredicto (tras las tres rondas)

- **El techo visual no discrimina**: con v2 (vectorial), v3 (blob fluido +
  WebGL2) y v4 (motor 3D + post propio) ambos stacks llegaron al diseño y
  ninguno se quedó sin resto. Elegir stack por "hasta dónde llega el dibujo"
  no tiene sentido aquí; la decisión es de costos y ecosistema.
- **Para el overlay del dictado, Qt Quick gana con evidencia**: ~3× menos RAM
  (80-110 vs 220-234 MB), 200 fps vs tope de 60 de Chromium, cero IPC y cero
  MB de empaquetado extra. Con el motor 3D (v4) el arranque sube a 267 ms y la
  CPU a ~1.7 %, un costo que no se justifica a 224 px: el diseño vectorial
  (v2/v3) lee igual o mejor.
- **La ruta web es viable** (transparencia per-pixel validada, paridad visual
  lograda, mismo GLSL) y tiene sentido si algún día se unifica el panel de
  ajustes y el overlay en un stack web, o si se priorizan assets de diseñador
  (Rive — requiere assets, no evaluado). Paga los costos de las tablas.
- **Recomendación**: llevar el overlay v2/v3 (QML) a producción como evolución
  del overlay actual y reservar la migración web para una decisión explícita
  sobre el panel completo. El v4 queda como demostración de techo y como base
  si algún día el diseño pide 3D de verdad.

## Decisión e implementación

Con las tres rondas sobre la mesa, la decisión fue **migrar la UI a web**. Se
ejecuta por fases:

1. **Overlay (hecho).** El renderer del daemon es
   [`overlay_web.py`](../dictado/src/instant_app/overlay_web.py): ventana
   transparente/sin foco de siempre con la página
   [`web/overlay.html`](../dictado/src/instant_app/web/overlay.html) en
   QtWebEngine, canal QWebChannel (`frame` Python→JS, `event` JS→Python) y los
   dos estilos (`classic`, `orbital`). Si QtWebEngine no abre, cae a Qt Quick y
   después a Tk. Empaquetado actualizado (hidden imports + `--add-data` +
   módulos QML `QtWebChannel`/`QtWebEngine` en el hook de PyInstaller;
   dependencias de WebEngine en `install.sh`).
2. **Panel (hecho).** `gui.py` ahora es `PanelLogic` (sin Qt) + ventana host
   web (`qml/panel_web_host.qml` + `web/panel.html`): un solo dialecto de
   estilos para overlay y panel, con los mismos contratos (canal de
   instancia única, mensajes de la bandeja, toasts, diagnóstico, captura de
   tecla, vocabulario y guardado). El renderer Qt Quick del overlay y el
   panel QtWidgets quedaron retirados.

Los costos aceptados (medidos arriba): tope ~60 fps, ~150 MB más de RAM del
daemon, ~296 MB más de instalador.

## Reproducir

```bat
cd dictado\bench\bakeoff
python record_frames.py
python run_qml.py --shots 2500,7600,9200
python run_web.py --shots 2500,7600,9200
python measure.py --runner both --runs 3
python make_compare.py

rem ronda 2
python run_qml.py   --variant v3 --label qml3 --shots 2500,7600,9200
python run_web.py   --variant v3 --label web3 --shots 2500,7600,9200
python measure.py   --runner both --variant v3 --runs 3
python make_compare.py --tags qml3,web3 --out out/compare_grid_v3.png

rem ronda 3
python run_qml.py   --variant v4 --label qml4 --shots 2500,7600,9200
python run_web.py   --variant v4 --label web4 --shots 2500,7600,9200
python measure.py   --runner both --variant v4 --runs 3
python make_compare.py --tags qml4,web4 --out out/compare_grid_v4.png
```
