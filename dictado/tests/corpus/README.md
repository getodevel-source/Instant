# Corpus etiquetado para comparar motores

Banco de frases en español con la etiqueta de referencia, para medir Parakeet y
Qwen3-ASR sobre **el mismo audio** en lugar de opinar. Existe porque la decisión
«¿Parakeet o Qwen?» de la sesión anterior se apoyaba en un solo clip de 12
palabras, que no alcanza para afirmar nada.

## Contenido

| Archivo | Qué es |
|---|---|
| `manifest.json` | Las frases con `id`, `category` y `text` (la etiqueta). Es lo único versionado del corpus. |
| `generate_corpus.py` | Genera el audio: voz neuronal con `edge-tts` y conversión a 16 kHz mono con `ffmpeg`. |
| `evaluate_models.py` | Corre los motores, calcula WER, frases exactas, signos de apertura y tiempos. |
| `robustness.py` | Repite la medición sobre dos pasadas de audio y dice si el ranking se sostiene. |
| `audio/`, `audio_b/` | WAV generados. **No se versionan**: se regeneran con el script. |

## Categorías

| Categoría | Qué mide |
|---|---|
| `espanol_puro` | Piso de calidad: español sin términos raros. |
| `terminos_ingleses` | El caso real del usuario: inglés técnico dentro de una frase en español (`commit`, `deploy`, `workflow`). |
| `preguntas` | Si el motor pone `¿` de apertura, que es lo que el pulido LLM intenta compensar. |
| `nombres_propios` | `Instant`, `Parakeet`, `Qwen`, `GitHub` y nombres de personas. |

## Uso

```bash
# 1. Generar el audio (una vez; necesita red y ffmpeg en PATH)
python dictado/tests/corpus/generate_corpus.py

# 2. Evaluar
python dictado/tests/corpus/evaluate_models.py
python dictado/tests/corpus/evaluate_models.py --engines parakeet
python dictado/tests/corpus/evaluate_models.py --engines qwen,qwen-sin-hotwords --save results.json

# 3. Robustez: segunda pasada con otras voces y otro ritmo
python dictado/tests/corpus/generate_corpus.py --out dictado/tests/corpus/audio_b \
    --voice-set voices_pass_b --rate=-12%
python dictado/tests/corpus/robustness.py
```

`--hotwords terminos` (por defecto) le pasa a Qwen la lista de términos técnicos
del manifiesto, que es lo que un usuario escribiría en su perfil de vocabulario.
Comparar contra `--hotwords ninguno` responde si esa función aporta algo.

La segunda pasada existe porque una sola generación de audio no alcanza para
decidir: cambia las voces (`voices_pass_b` en el manifiesto) y el ritmo, y
`robustness.py` avisa si el ganador cambia entre pasadas. Con el corpus actual
**cambia**, así que la comparación de precisión no cierra la decisión por sí
sola.

## Cómo se mide

- **WER**: distancia de edición por palabra sobre texto normalizado (minúsculas,
  sin tildes ni signos). La ortografía no debería contar como error del motor.
- **Frase exacta**: coincidencia completa tras normalizar.
- **Signos**: si el texto trae `¿`/`¡` de apertura cuando la etiqueta los tiene.
- **Tiempo**: segundos de pared por frase, con el modelo ya cargado.

## Límite conocido

El audio es **voz sintética** (voces neuronales de `es-AR` y `es-ES`). Sirve
para comparar motores entre sí y para localizar en qué falla cada uno, pero no
reemplaza una grabación humana: la prosodia y el ruido de micrófono cambian el
resultado. Cuando haya grabaciones propias, se ponen en `audio/` con el mismo
`id` del manifiesto y el arnés las usa sin tocar nada más.
