# Diagnóstico: precisión variable del dictado (Parakeet TDT v3 + Silero VAD)

Fecha: 2026-10-03. Fuente: código en `dictado/src/instant_app/` + `%APPDATA%\instant\instant.log` real (231 audios).
Restricción de la sesión: no se modificó lógica de audio/motor; solo diagnóstico.

## Conclusión en una línea

El audio graba bien (pico mínimo 0.0076, muy por encima del gate de silencio 0.005) y aun así
el modelo devuelve vacío o recorta inicios: **el input que ve el modelo nunca es el mismo
entre tomas**, por segmentación VAD + decodificación aislada por segmento + colapso greedy a blank.

## Números medidos

- Audios que llegaron a segmentar: 231. Dur media 12.8 s (min 0.9, max 66.6).
- Pico media 0.0513, p10 0.0281, p50 0.0451. **0/231 bajo el gate 0.005.**
- Gates previos (no son el modelo): `silencio` 6, `muy corto (<0.4 s)` 9.
- Vacíos de modelo: 6 pérdidas totales (`1/1` vacío con pico bueno) + 8 pérdidas parciales
  (multi-segmento con 1-2 `seg` vacíos) = **14 sesiones (~6 %)**.
- Distribución `(n_segs, n_vacíos): conteo`:
  `(1,0):149, (1,1):6, (2,0):47, (2,1):2, (3,0):16, (3,1):2, (3,2):2, (4,0):3, (4,1):2, (5,0):2`.
- 76/231 dictados (33 %) se parten en >1 segmento: cada corte es una apuesta sin contexto cruzado.

## Casos testigo (todos con pico bueno)

- Sesión 56 (10:53): `audio 9.3 s pico=0.0412 → 3 segmentos → seg 2/3 y 3/3 vacíos`.
  Cola de 9 s de voz perdida en silencio.
- `audio 2.9 s pico=0.0386 → seg 1/1 vacío → "vacio tras 2.9 s"`, y gemelo de 3.4 s.
  Decode vacío en 0.05-0.10 s = path greedy colapsado a blank, no timeout.
  (Un caso tardó 2.45 s e igual colapsó: no es falta de cómputo.)
- Sesiones 53/55: textos que arrancan con "en..."/"de..." — onset recortado.

## Causas por etapa

1. **Hotkey** (`hotkey.py:WindowsPolling`, polling 10 ms): barato, no es fuente de variabilidad.
2. **Stream** (`daemon.py:_record` → `resolve_mic` + `open_input_stream` *después* del `on_press`):
   latencia no logueada durante la cual el usuario ya habla. Mitad del inicio recortado.
3. **VAD** (`engine.py:segment`, Silero threshold 0.5, `min_speech_duration` 0.25 s,
   `min_silence` 0.5 s, `window_size` 512, `pad` 0.2 s): exige 0.25 s de voz para arrancar,
   recorta ataques suaves; pausas de 0.4 vs 0.6 s cambian el corte entre tomas.
4. **Segmentación + decode** (`merge_short_bounds` 1.0 s/1.0 s + `ThreadPoolExecutor`
   concurrente sobre un único recognizer compartido, `greedy_search`, int8, `provider=cpu`,
   sin beam ni hotwords — ver `docs/motores.md` por qué los hotwords no aplican):
   cada segmento se decodifica aislado; el transducer sin contexto izquierdo colapsa a blank
   en chunks cortos o cortados a mitad de palabra. Sin normalización de nivel/AGC, hablar
   bajito o fuerte cambia la hipótesis aunque suene igual.
5. **Post** (`join_texts` + `context.correct_aliases` solo variantes exactas + LLM apagado
   por defecto): la variabilidad llega cruda al pegado. Nombres propios y code-switch son
   lo más inestable (WER 0.14-0.25 medido en `docs/motores.md`).

Contexto de diseño: `docs/motores.md` ya midió que Parakeet varía +0.036 WER entre pasadas
solo cambiando voz/ritmo (Qwen+hotwords variaba 0.006). La sensibilidad es del motor, no de tu mic.

## Cómo clasificar el próximo fallo (10 s, solo log)

1. `silencio (pico...)` o `muy corto` → gate previo, no es el modelo.
2. `vacio tras` con `seg 1/1:` vacío y pico >0.01 → colapso greedy con buen audio.
3. `N segmentos` con algún `seg i/N:` vacío → chunk indecodificable aislado.
4. Texto que empieza con "en/de/y..." → onset recortado (stream + VAD + sin contexto izquierdo).

## Propuestas ordenadas (para la sesión que toque motor)

1. **Log de bounds** en `segment()`: `bounds=[(t0,t1),...]` + dur/pico por segmento. Inocuo;
   distingue onset recortado de colapso.
2. **Log de latencia de apertura** en `_record()`: `t_resolve + t_open`. Cuantifica lo perdido
   antes del primer bloque.
3. **Fallback todo-junto**: si algún seg da vacío con pico alto, re-decodificar el wav completo.
4. **Decode secuencial A/B** (flag): descarta race del recognizer compartido.
5. **Pad izquierdo / merge**: `vad_pad 0.2→0.35`, `min_speech 0.25→0.15`, `merge 1.0→1.5`.
6. **Pre-roll** (ring buffer 0.3-0.5 s o stream persistente): elimina la latencia de apertura.

## Fixes aplicados (2026-10-03)

En `dictado/src/instant_app/engine.py` y `daemon.py`, cubiertos por
`dictado/tests/test_transcribe_fallback.py` (suite de regresión verde):

- `_decode_lock`: la inferencia sobre el recognizer compartido se serializa.
- `_recover_empties`: reintento secuencial de cada segmento vacío con audio
  fuerte (pico ≥ 0.005, dur ≥ 0.3 s) con ±1 s de contexto; si todo sigue vacío,
  último intento con el wav completo (tope 120 s).
- `merge_short_bounds(min_len=1.5)`: los arranques de 1-1.5 s ya no se
  decodifican sin contexto.
- VAD `min_speech_duration` 0.25→0.20 s, `vad_pad` default 0.2→0.3 s
  (override por config `vad_pad`, sin cambio de esquema).
- Log: cortes por sesión (`0.00-3.10, 3.60-9.30`), pico/duración por segmento,
  reintentos y latencia de apertura del mic (`mic listo en X.XXs`).

La captura persistente con pre-roll se implementó en la tercera oleada de abajo.
Pendiente: medir latencia de inicio con voces y micrófonos reales.

## Segunda oleada (2026-10-03)

Caso testigo: sesión 65, `3.3 s → 2 segmentos → seg 2/2 vacío` ("Eh más cosas
[puedas mejorar o no]" perdido con pico bueno). La sesión siguiente repitió la
cola y salió en un solo segmento: es el patrón de pérdida parcial ya medido.

- Flush de cola en `daemon.py:_record`: hasta 0.3 s drenando tras soltar antes
  de `stream.stop()`. La sesión 65 traía solo 0.1 s menos de audio que de tecla,
  así que su causa fue decode vacío (cubierto por el fallback), pero sin flush
  la cola en buffers se pierde igual.
- `_fit_level` en `engine.py`: normalización RMS boost-only por chunk
  (RMS < 0.03 → 0.06, tope 8x, silencio y takes fuertes intactos, `g=` en el log).
- Tests: 5 checks nuevos en `test_transcribe_fallback.py` (silencio/fuerte
  intactos, boost exacto 6x en 0.01, rescate de take bajito en 1 decode).

## Tercera oleada (2026-10-03)

- Captura continua (`StreamKeeper` en `daemon.py`): un InputStream abierto toda
  la vida del daemon + deque de pre-roll 0.45 s. `_record` deriva a
  `_record_continuous` (prefijo + `_pump` común + `_LevelTracker` extraído) y
  cae a `_record_oneshot` si el stream murió. El onset ya no depende de la
  latencia de apertura.
- El borde entre el historial pre-roll y la cola viva comparte el mismo lock
  que el callback de audio: así un bloque concurrente no puede entrar por los
  dos caminos y repetirse al principio de la sesión.
- Guardado opt-in de fallos (`DICTADO_SAVE_WAVS`, tope 50): wav 16-bit + .txt
  con duración/pico/cortes, solo cuando el texto final queda vacío.
- El corrector de vocabulario solo deja un evento de debug sin contenido; el
  log de sesión informa duración y longitud de la transcripción, no el texto.
- Tests: `dictado/tests/test_capture.py` (14 checks: keeper, tracker, pump,
  propagación de stream muerto, dump de fallo). Suite verde.

## Ronda autónoma de números (2026-10-03, `dictado/bench/bench_numbers.py`)

Medido con Parakeet + Silero reales en este equipo, señal silábica sintética
(tonos armónicos con envolvente; NO es voz: sirve para estabilidad y bordes,
no para afirmar WER):

- **Determinismo 6/6**: mismo wav, 6 transcripciones idénticas. El lock de
  inferencia cumple.
- **VAD 6/6**: mismos bounds en 6 pasadas.
- **RTF 0.19x** @2 threads en 6.5 s sintético (en vivo ~0.05x @4 threads).
- **Threshold**: 0.3 colapsa todo a 1 segmento; 0.5→3 segs, 0.7→4 segs (techo
  5 por un gap de 0.4 s < min_silence). **Se mantiene 0.5**: 0.7 parte mejor
  los gaps sintéticos pero desensibiliza los onsets reales, que es justo lo
  que se está arreglando. Sin voz real no se cambia.
- **Sin cold-start del VAD**: ráfaga aislada detectada en t=0.000, 0.436
  (con 0.5 s previo) y 1.428 (con 1.5 s previo). No hace falta warmup del VAD.
- **A/B fallback en 12 cortes abultados: 12/12 vs 12/12 no concluyente** y
  barrido de amplitud casi todo blank: los tonos puros caen fuera de lo que
  el modelo considera voz, así que lo sintético no valida recuperación.
- **Hallazgo útil**: el merge cambia la hipótesis (chunk fusionado 3.9 s →
  blank, partes → 'Mm.'): confirma con caso reproducible que la segmentación
  manda, y que el fallback con otros bordes es el camino (ya implementado).
- **save_wavs e2e verificado**: el vacío deja .wav + .txt en disco.
- Decisión: ningún cambio de motor en esta ronda. Lo que desbloquea la
  próxima mejora real es corpus de voz con `DICTADO_SAVE_WAVS`.
