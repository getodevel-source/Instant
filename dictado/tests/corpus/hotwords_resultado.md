"""Resultado negativo: los hotwords NO funcionan con este Parakeet v3.

Se probo el sesgo contextual (hotwords) para marcas y terminos tecnicos, que es
el problema real del usuario («Qwen» -> «cuen»). No aporta nada.

Medido sobre el corpus, con 17 hotwords (Qwen, Parakeet, Instant, GitHub,
commit, deploy, staging, rollback, workflow, frontend, backend, Python,
machine learning, plugin, benchmark, driver, getodevel):

| config           | pasada A            | pasada B            |
|------------------|---------------------|---------------------|
| greedy (actual)  | 20 err, 0,056, 0,21s| 30 err, 0,083, 0,24s|
| beam sin hotwords| 19 err, 0,053, 0,23s| 30 err, 0,083, 0,25s|
| beam + hotwords  | 20 err, 0,056, 0,24s| 30 err, 0,083, 0,25s|

Por que no funciona:
1. sherpa-onnx exige `modified_beam_search` para hotwords, y eso se cumple.
2. Exige `modeling_unit=bpe` + un `bpe.vocab` de sentencepiece para tokenizar
   los hotwords. **El paquete de Parakeet v3 no trae `bpe.vocab`**: solo
   `tokens.txt`. Usar `tokens.txt` como bpe_vocab NO alcanza: el tokenizador no
   encuentra la secuencia de tokens de la marca, asi que la palabra nunca se
   refuerza. Prueba directa: «Qwen» sigue saliendo «O en» / «Wen» con el hotword
   en la lista.
3. `greedy_search` directamente rechaza hotwords con un ValueError.

Ademas, `modified_beam_search` tampoco mejora por si solo: la ventaja de 1 error
en la pasada A desaparece en la B (identico). Es ruido, no una mejora.

Conclusion: no insistir con hotwords. Lo que si puede atacar las marcas es la
sustitucion fonetica en el perfil de vocabulario (texto, no audio), porque
`cuen`, `wen`, `quen` y `Qwen` son la misma palabra para un oido espanol.

Queda el script para reproducirlo: `hotwords_probe.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
