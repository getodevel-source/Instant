# Motores de reconocimiento: Parakeet o Qwen3-ASR

Decisión medida sobre el corpus de [`dictado/tests/corpus/`](../dictado/tests/corpus/README.md),
no sobre impresiones. Reproducible con:

```bash
python dictado/tests/corpus/generate_corpus.py
python dictado/tests/corpus/generate_corpus.py --out dictado/tests/corpus/audio_b \
    --voice-set voices_pass_b --rate=-12%
python dictado/tests/corpus/robustness.py
```

## Decisión

**Parakeet sigue siendo el motor de dictado.** Qwen queda para la comparación A/B.

La razón **no** es que Parakeet transcriba mejor: en precisión los dos están
empatados dentro del error de medición. La razón es lo que sí es concluyente y
no depende de la voz:

1. **Velocidad: Parakeet es 3× más rápido** (0,25 s por frase contra 0,76–0,81 s),
   en las dos pasadas. Para dictado en vivo eso se siente en cada frase.
2. **Signos de apertura: Parakeet pone el `¿` en 4 de 8 preguntas; Qwen, en 0
   de 8**, en las dos pasadas. Es la diferencia que el usuario nota en un
   WhatsApp o un correo, y es exactamente lo que el pulido LLM no siempre
   arregla.
3. Qwen no gana en precisión de forma estable, así que no hay motivo para pagar
   3× el tiempo.

## Precisión: empate, no victoria

Dos pasadas de audio, mismas 34 frases (360 palabras):

| Motor | WER pasada A | WER pasada B | Diferencia | Frases exactas A / B |
|---|---:|---:|---:|---:|
| Parakeet v3 | **0,056** | 0,092 | +0,036 | 24/34 · 16/34 |
| Qwen3-ASR + hotwords | 0,069 | **0,075** | +0,006 | 24/34 · 22/34 |
| Qwen3-ASR sin hotwords | 0,086 | 0,128 | +0,042 | 20/34 · 17/34 |

- **Pasada A**: voces `es-AR` y `es-ES`, ritmo normal (139 s de audio).
- **Pasada B**: voces `es-MX` y `es-CO`, 12 % más lento (153 s de audio).

**El ranking se invierte entre pasadas**: gana Parakeet en A y Qwen con hotwords
en B. Con este corpus no se puede afirmar que un motor reconozca mejor que el
otro; lo único sólido es que **Parakeet es más sensible a la voz y al ritmo**
(varía 0,036 de WER entre pasadas) y **Qwen con hotwords es más estable**
(varía 0,006). Esa estabilidad es un dato a favor de Qwen que conviene recordar
si algún día se cambia el motor.

### Por categoría (pasada A / pasada B)

| Categoría | Parakeet | Qwen + hotwords | Qwen sin hotwords |
|---|---:|---:|---:|
| Español puro | 0,011 / 0,023 | 0,011 / 0,011 | 0,023 / 0,023 |
| Términos ingleses | 0,041 / 0,082 | 0,096 / 0,055 | 0,103 / 0,158 |
| Preguntas | 0,016 / 0,078 | 0,016 / 0,047 | 0,047 / 0,078 |
| Nombres propios | 0,194 / 0,226 | 0,145 / 0,242 | 0,177 / 0,258 |

En términos ingleses la ventaja de Parakeet en A (0,041 contra 0,096) **se da
vuelta en B** (0,082 contra 0,055). La primera pasada hacía parecer que Parakeet
dominaba el code-switching; la segunda lo desmiente.

## Hallazgos que se sostienen en las dos pasadas

1. **Ninguno pone bien los signos de apertura.** Parakeet acierta el `¿` en 4 de
   8 preguntas en A y en 4 de 8 en B; Qwen, en 0 de 8 en ambas. Los dos puntúan
   y acentúan bastante bien (81–91 % de los signos), pero el `¿`/`¡` de apertura
   queda como trabajo del pulido LLM. Es la justificación medida de esa función.

2. **Los nombres propios son el punto débil de los dos** (WER 0,145–0,258).
   `getodevel-source`, `Instant` y `Parakeet` salen deformados en ambos motores.
   Es lo que el perfil de vocabulario corrige después del reconocimiento.

3. **Los hotwords de Qwen aportan y son lo que lo hace competitivo.** Sin ellos
   Qwen queda último en las dos pasadas (0,086 y 0,128). Con ellos empata arriba
   (0,069 y 0,075). Pero la mejora depende de la cobertura de la lista: al
   ampliarla se arreglaron `staging`, `Python`, `workflow` y `frontend`, y
   `commit` **siguió mal aunque estuviera en la lista**.

4. **Hay términos que ninguno de los dos acierta nunca**: `commit` sale «Quemet»,
   «camer», «kemite» o «comer»; `build` sale «Bill» o «bifallo». No es un
   problema de motor sino del vocabulario que traen; el perfil de vocabulario es
   la única corrección posible hoy.

## Límites de esta medición

- **El audio es voz sintética** (voces neuronales de cuatro países). Compara
  motores entre sí, pero no hay ruido de micrófono, ni vacilaciones, ni prosodia
  real. Los valores absolutos son optimistas.
- 34 frases y 360 palabras por pasada: alcanza para ver una diferencia de 2
  puntos de WER, no para afirmar una tasa de error del producto.
- Los términos ingleses los pronuncia una voz española, con fonética española.
  Es el escenario que se quería medir, pero no es lo mismo que un hablante
  bilingüe alternando idiomas.
- **La decisión sobre precisión sigue abierta** y depende de la voz real del
  usuario: es la única forma de desempatar. Para cerrarla hay que grabar las
  mismas 34 frases (o unas 10) y poner los WAV en
  `dictado/tests/corpus/audio/` con el mismo `id` del manifiesto; el arnés los
  usa sin cambiar nada. Mientras tanto, la decisión por defecto se apoya en
  velocidad y puntuación, que sí son concluyentes.
