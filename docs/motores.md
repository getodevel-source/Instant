# Motores de reconocimiento: Parakeet o Qwen3-ASR

Registro histórico de una decisión ya tomada: **Parakeet es el motor de dictado
y Qwen3-ASR se retiró del proyecto** (el modelo, la comparación A/B del panel y
el arnés de medición). Este documento queda para no repetir el trabajo.

La decisión se midió sobre un corpus etiquetado de 34 frases en español con
términos ingleses, preguntas y nombres propios, con dos pasadas de audio (voces
`es-AR`/`es-ES` a ritmo normal, y `es-MX`/`es-CO` un 12 % más lento). El corpus
y los scripts se eliminaron con Qwen; los números que importan quedan abajo.

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
  usuario: es la única forma de desempatar. Mientras tanto, la decisión por
  defecto se apoya en velocidad y puntuación, que sí son concluyentes.

## Vías descartadas, para no repetirlas

**1. Hotwords (sesgo contextual) en Parakeet: no funcionan.** Es lo que la
documentación de sherpa-onnx recomienda para marcas y términos técnicos, y se
probó con 17 hotwords (`Qwen`, `Parakeet`, `Instant`, `GitHub`, `commit`,
`deploy`, `staging`, `rollback`, `workflow`, `frontend`, `backend`, `Python`,
`machine learning`, `plugin`, `benchmark`, `driver`, `getodevel`):

| config            | pasada A             | pasada B             |
|-------------------|----------------------|----------------------|
| greedy (actual)   | 20 err, 0,056, 0,21s | 30 err, 0,083, 0,24s |
| beam sin hotwords | 19 err, 0,053, 0,23s | 30 err, 0,083, 0,25s |
| beam + hotwords   | 20 err, 0,056, 0,24s | 30 err, 0,083, 0,25s |

Causa: sherpa-onnx tokeniza los hotwords con un `bpe.vocab` de sentencepiece y
el paquete de Parakeet v3 no lo trae (solo `tokens.txt`). Usar `tokens.txt` como
bpe_vocab no alcanza: «Qwen» siguió saliendo «O en» / «Wen» con el hotword en la
lista. `greedy_search` además rechaza hotwords con `ValueError`.

**2. `modified_beam_search`: no mejora por sí solo.** La ventaja de 1 error en
la pasada A desaparece en la B (idéntico). Era ruido.

**3. Modelo de puntuación en español: no existe** en sherpa-onnx (solo inglés y
chino). El `¿` de apertura queda para el pulido LLM local.

**4. HomophoneReplacer: solo caracteres chinos.** La documentación lo repite tres
veces. No sirve para español.

**5. Parakeet v2 / unified: solo inglés.** No sirven para dictado en español.

**6. Fusión de los dos motores (estilo ROVER): no vale el costo.** Alineando las
dos hipótesis por palabra y votando, la fusión con desempate por Parakeet bajó a
48 errores sobre 720 palabras, contra 53 de Parakeet solo y 52 de Qwen solo. Pero
en la pasada B perdía contra Qwen solo (30 contra 27), la mejora total era de 5
errores en 720 palabras (dentro del ruido) y correr los dos motores triplica el
tiempo por frase (0,25 s → ~1,0 s). Además descarta la puntuación, que es donde
Parakeet es claramente mejor.

**7. Clave fonética sola para marcas: insuficiente.** Se probó normalizar por
sonido (`Qwen`→`quen`, `cuen`→`kuen`) y no alcanza: `Bill`→`bi` contra
`build`→`build`. Sirve como sugerencia a confirmar por el usuario, nunca como
sustitución automática.

## Qué queda para mejorar la precisión

Lo único que ataca las marcas y los términos técnicos sin tocar el motor ni
perder velocidad es el **perfil de vocabulario** (sustitución de variantes
exactas, en texto, después del reconocimiento), y el **pulido LLM local** para
los signos de apertura. Al retirar Qwen, el perfil de vocabulario quedó vacío en
este equipo: cargarlo es el siguiente paso pendiente.

