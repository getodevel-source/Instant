# Bake-off de UI del overlay (Qt Quick vs Web)

Comparación con evidencia de las dos rutas candidatas para el overlay del
dictado: el MISMO diseño objetivo implementado dos veces — QML (ShaderEffect
compilado con qsb) y canvas2d dentro de QtWebEngine — alimentadas por el mismo
replay de voz y medidas con el mismo método. Resultados y conclusiones:
[`docs/bakeoff-ui.md`](../../docs/bakeoff-ui.md).

## Piezas

| Archivo | Rol |
|---|---|
| `record_frames.py` → `frames.jsonl` | Graba el replay con la matemática real del daemon (`_LevelTracker`) sobre una pista silábica sintética determinística. |
| `qml/overlay_v2.qml` + `qml/overlay_v2.frag(.qsb)` | Prototipo QML: ventana transparente 224×224, todo el orbe en un fragment shader. |
| `web/overlay.html` + `web/host.qml` + `web/qwebchannel.js` | Prototipo web: canvas2d en QtWebEngine, puente QWebChannel bidireccional por señales. |
| `run_qml.py` / `run_web.py` | Runners: misma ventana, mismas flags, mismo reloj de replay, mismas métricas (fps, p95, shots). |
| `measure.py` | Arranque, FPS, CPU y working set del árbol de procesos (Windows, ctypes; incluye subprocesos de Chromium). |
| `make_compare.py` | Grilla side-by-side (`out/compare_grid.png`). |
| `probe_*.py` | Sondas que documentan los hallazgos de plataforma (dialecto de shaders, glow en ventana transparente, canal QWebChannel). |
| `../web_overlay_smoke.py` / `../web_panel_smoke.py` | Smokes de las UIs web de producción (secuencia sintética + captura); no tocan config ni autostart reales. |

`out/` guarda solo la evidencia: las tres grillas comparativas, los
`measure_*.json` y las capturas de los smokes. Los PNG intermedios de cada
corrida se regeneran con los runners.

## Reproducir

```bat
cd dictado\bench\bakeoff
python record_frames.py
python run_qml.py --shots 2500,7600,9200
python run_web.py --shots 2500,7600,9200
python measure.py --runner both --runs 3
python make_compare.py
```

### Ronda 2 (techo visual, variante v3)

Mismo replay y mismas métricas; diseño más ambicioso (blob fluido con fbm,
anillo deformado por las bandas, embers deterministas, sweep con eco) y stack
llevado a su techo por lado: shader RHI en QML, **WebGL2 en la web** (mismo
cuerpo GLSL, solo cambia el preludio).

```bat
python run_qml.py   --variant v3 --label qml3 --shots 2500,7600,9200
python run_web.py   --variant v3 --label web3 --shots 2500,7600,9200
python measure.py   --runner both --variant v3 --runs 3
python make_compare.py --tags qml3,web3 --out out/compare_grid_v3.png
```

Nota: la captura de la web v3 usa `preserveDrawingBuffer` para que
`toDataURL()` no devuelva un buffer vacío; el ``web3_grab_*.png`` (grab de Qt)
sirve de control cruzado.

### Ronda 3 (motor 3D + post-proceso propio, variante v4)

- QML: escena QtQuick3D (orbe PBR con luces, anillo de 48 esferas ondulado,
  embers 3D) capturada con `ShaderEffectSource` y post-procesada con cadena
  propia (`bloom_h` + `bloom_v`, alfa correcto). El glow del motor
  (`ExtendedSceneEnvironment`) NO compone sobre ventana transparente
  (verificado con `probe_q3d.py`: el spill aparece solo con fondo opaco).
- Web: misma tecnica sobre FBOs WebGL2 (umbral+blur H a media resolucion →
  blur V + composicion con tonemap y dithering, `preserveDrawingBuffer` solo
  para capturas).

```bat
python run_qml.py   --variant v4 --label qml4 --shots 2500,7600,9200
python run_web.py   --variant v4 --label web4 --shots 2500,7600,9200
python measure.py   --runner both --variant v4 --runs 3
python make_compare.py --tags qml4,web4 --out out/compare_grid_v4.png
```

Gotcha documentado: en un `ShaderEffect`, el **nombre del uniform sampler debe
coincidir con el nombre de la propiedad QML** (`src`, `scene`, `bloom`); si no,
la textura no se ata y el shader muestrea ceros en silencio (fue la causa de
los frames vacios de la cadena v4 hasta corregirlo).

### Piezas de sonda

- `probe_shader.py` / `probe2.py` / `probe3.py`: dialecto de shaders de Qt 6,
  MultiEffect y Qt5Compat.
- `probe_q3d.py`: View3D + `ExtendedSceneEnvironment` (glow) en ventana
  transparente vs opaca.
- `probe_chain.py`: cadena ShaderEffectSource → bloom por etapas.
- `probe_channel.py`: QWebChannel (tipo QML `WebChannel`, registro del bridge).

**Regenerar los shaders tras tocar un `.frag` (obligatorio):**

```bat
qsb.exe --qt6 -o qml/overlay_v2.frag.qsb qml/overlay_v2.frag
qsb.exe --qt6 -o qml/overlay_v3.frag.qsb qml/overlay_v3.frag
qsb.exe --qt6 -o qml/bloom_h.frag.qsb qml/bloom_h.frag
qsb.exe --qt6 -o qml/bloom_v.frag.qsb qml/bloom_v.frag
qsb.exe --qt6 -o qml/debug_pass.frag.qsb qml/debug_pass.frag
```

(`qsb.exe` viene en el wheel de PySide6; ver hallazgos en el informe: en Qt 6
los shaders de ShaderEffect son archivos `.qsb`, las cadenas inline se ignoran
en silencio.)

## Spec compartida (idéntica en ambas implementaciones)

La spec de la ronda 1 está abajo; las constantes de la ronda 2 (v3) viven
comentadas en `qml/overlay_v3.frag`/`qml/overlay_v3.qml` y replicadas en
`web/overlay_v3.html` (mismo cuerpo GLSL).

- Ventana 224×224 transparente, siempre encima, sin foco; composición de 200 px centrada.
- Núcleo: radio `24 + 8*level` en listening, halo `nucR + 22 + 22*level`, color `mix(accent, working, pitch)`.
- Anillo principal r=56, trazo `2*(1.5 + 2.5*level)` px.
- Espectro: 9 arcos r=78, ranura 40°, trazo 7 px con puntas redondas, largo `0.12 + 0.88*banda`, rotación `(0.15 + 0.35*level)` rad/s.
- Processing: barrido de 70° a `2π/1.1 s`, r=78, trazo 12 px.
- Notice: pulso ámbar a `2π/0.45 s` + pastilla «Listo».
- Suavizado de `level` a 90 ms y `pitch` a 140 ms (Behavior OutCubic en QML, exponencial equivalente en canvas).
- Métricas: FrameAnimation (QML) / rAF (web), mismo cálculo de p95 por ventana de 1 s.
