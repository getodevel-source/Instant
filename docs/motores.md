# Motores de reconocimiento: Parakeet o Qwen3-ASR

Decisión medida sobre el corpus de [`dictado/tests/corpus/`](../dictado/tests/corpus/README.md),
no sobre impresiones. Reproducible con:

```bash
python dictado/tests/corpus/generate_corpus.py
python dictado/tests/corpus/evaluate_models.py --engines parakeet,qwen,qwen-sin-hotwords
```

## Resultado

34 frases, 360 palabras de referencia, mismo audio para los tres escenarios:

| Motor | WER | Frases exactas | s/frase | Signos puestos |
|---|---:|---:|---:|---:|
| **Parakeet v3** | **0,056** | **24/34** | **0,21** | 39/43 (91 %) |
| Qwen3-ASR + hotwords | 0,069 | 24/34 | 0,74 | 35/43 (81 %) |
| Qwen3-ASR sin hotwords | 0,086 | 20/34 | 0,70 | 36/43 (84 %) |

WER por categoría (y frases exactas entre paréntesis):

| Categoría | Parakeet | Qwen + hotwords | Qwen sin hotwords |
|---|---:|---:|---:|
| Español puro | 0,011 (7/8) | 0,011 (7/8) | 0,023 (6/8) |
| **Términos ingleses** | **0,041 (8/12)** | 0,096 (8/12) | 0,103 (7/12) |
| Preguntas | 0,016 (7/8) | 0,016 (7/8) | 0,047 (5/8) |
| Nombres propios | 0,194 (2/6) | **0,145 (2/6)** | 0,177 (2/6) |

## Decisión

**Parakeet sigue siendo el motor de dictado.** Qwen queda para la comparación A/B.

Parakeet gana en WER global, en español puro, en preguntas y —lo que más
importa— en el caso real del usuario: **español con términos técnicos en inglés**
(0,041 contra 0,096, más del doble de errores en Qwen). Además transcribe en
0,21 s por frase contra 0,74 s: **3,5 veces más rápido**.

El único terreno donde Qwen gana es en nombres propios, y por poco (0,145 contra
0,194). No alcanza para cambiar el motor por defecto.

## Hallazgos que corrigen la sesión anterior

1. **La hipótesis "Qwen es multilingüe, debería ganar en code-switching" es
   falsa en este equipo.** Qwen no falla traduciendo: falla *inventando palabras
   en español* cuando escucha un término inglés. `staging` → «hasta», «haz
   tachin»; `rollback` → «loulbac»; `commit` → «kemite». Parakeet también se
   equivoca, pero se queda cerca del sonido («Stashing», «Lowlback»), y eso es
   mucho menos dañino: un usuario reconoce el error, mientras que una palabra
   española real y bien formada pasa desapercibida en el texto.

2. **Los hotwords de Qwen sirven, pero son frágiles.** Con la lista de términos
   del perfil, Qwen baja de 0,086 a 0,069 de WER y recupera 4 frases exactas.
   Pero la mejora depende de la cobertura exacta: al ampliar la lista se
   arreglaron `staging`, `Python`, `workflow` y `frontend`, y **`commit` siguió
   mal aunque estuviera en la lista**. No es una palanca confiable.

3. **Ninguno de los dos pone bien los signos de apertura.** Parakeet acertó el
   `¿` en 4 de 8 preguntas; Qwen, en 0 de 8 con hotwords. Los dos puntúan y
   acentúan bastante bien (81–91 % de los signos), pero el `¿`/`¡` de apertura
   queda como trabajo del pulido LLM. Esto confirma que esa función tiene un
   propósito concreto y medido.

4. **Los nombres propios son el punto débil de los dos.** `getodevel-source` y
   `Instant` salen deformados en ambos motores. Es exactamente lo que el perfil
   de vocabulario corrige después del reconocimiento, sin tocar el audio.

## Límites de esta medición

- **El audio es voz sintética** (voces neuronales `es-AR` y `es-ES`). Compara
  motores entre sí, pero los valores absolutos son optimistas: no hay ruido de
  micrófono, ni vacilaciones, ni prosodia real.
- 34 frases y 360 palabras: suficiente para ver una diferencia de 2 puntos de
  WER, no para afirmar una tasa de error del producto.
- Los términos ingleses los pronuncia una voz española, con fonética española.
  Es el escenario que se quería medir, pero no es lo mismo que un hablante
  bilingüe alternando idiomas.

Para cerrar la decisión con evidencia humana hace falta grabar las mismas 34
frases (o una parte) y poner los WAV en `dictado/tests/corpus/audio/` con el
mismo `id` del manifiesto: el arnés los usa sin cambiar nada.
