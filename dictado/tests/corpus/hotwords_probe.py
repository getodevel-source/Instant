"""Prueba experimental: hotwords en Parakeet para nombres propios y marcas.

Objetivo: ver si el sesgo contextual (hotwords) mejora el reconocimiento de
marcas y terminos tecnicos, que es donde Parakeet falla hoy («Qwen» -> «cuen»).

Contexto del experimento: la doc de sherpa-onnx exige `modified_beam_search`,
`modeling_unit=bpe` y un `bpe.vocab` de sentencepiece. El paquete de Parakeet v3
NO trae bpe.vocab, solo `tokens.txt`. Aca se prueba si `tokens.txt` sirve.

Se miden cuatro configuraciones sobre el mismo audio del corpus:
  1. greedy            - lo que usa Instant hoy
  2. greedy + hotwords - deberia fallar (greedy no soporta hotwords)
  3. beam              - modified_beam_search sin hotwords (aisla su costo)
  4. beam + hotwords   - la configuracion que se quiere evaluar

Uso (desde la raiz del repo):
    python dictado/tests/corpus/hotwords_probe.py
    python dictado/tests/corpus/hotwords_probe.py --audio dictado/tests/corpus/audio_b
"""
import argparse
import io
import json
import os
import sys
import time
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(REPO, "dictado", "src"))
sys.path.insert(0, HERE)

from evaluate_models import edit_distance, normalize  # noqa: E402

MANIFEST = os.path.join(HERE, "manifest.json")
AUDIO_DIR = os.path.join(HERE, "audio")
SAMPLE_RATE = 16000

# Marcas y terminos que el usuario reporta como mal reconocidos.
HOTWORDS = ["Qwen", "Parakeet", "Instant", "GitHub", "commit", "deploy",
            "staging", "rollback", "workflow", "frontend", "backend",
            "Python", "machine learning", "plugin", "benchmark", "driver",
            "getodevel"]


def load_audio(path):
    with wave.open(path, "rb") as handle:
        frames, rate = handle.getnframes(), handle.getframerate()
        raw = handle.readframes(frames)
    if rate != SAMPLE_RATE:
        raise SystemExit(f"{path}: se esperaba {SAMPLE_RATE} Hz")
    return np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0


def build(decoding, hotwords_file="", bpe_vocab=""):
    import sherpa_onnx

    from instant_app.paths import model_paths

    paths = model_paths()
    kwargs = dict(
        encoder=paths["encoder"], decoder=paths["decoder"], joiner=paths["joiner"],
        tokens=paths["tokens"], num_threads=4, decoding_method=decoding,
        model_type="nemo_transducer", provider="cpu")
    if hotwords_file:
        kwargs.update(hotwords_file=hotwords_file, hotwords_score=2.0,
                      modeling_unit="bpe", bpe_vocab=bpe_vocab)
    started = time.perf_counter()
    recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(**kwargs)
    return recognizer, time.perf_counter() - started


def run(recognizer, wav):
    stream = recognizer.create_stream()
    stream.accept_waveform(SAMPLE_RATE, np.ascontiguousarray(wav, dtype=np.float32))
    recognizer.decode_stream(stream)
    return (stream.result.text or "").strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prueba hotwords con Parakeet.")
    parser.add_argument("--manifest", default=MANIFEST)
    parser.add_argument("--audio", default=AUDIO_DIR)
    parser.add_argument("--hotwords-file", default="",
                        help="archivo de hotwords; si se omite, se genera del corpus")
    parser.add_argument("--only", default="",
                        help="ids separados por coma (default: todas)")
    args = parser.parse_args(argv)

    with io.open(args.manifest, encoding="utf-8") as handle:
        manifest = json.load(handle)
    phrases = manifest["phrases"]
    if args.only:
        wanted = {value.strip() for value in args.only.split(",") if value.strip()}
        phrases = [item for item in phrases if item["id"] in wanted]

    hotwords_path = args.hotwords_file
    if not hotwords_path:
        hotwords_path = os.path.join(HERE, "_hotwords_probe.txt")
        with io.open(hotwords_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(HOTWORDS) + "\n")
    from instant_app.paths import model_paths

    tokens = model_paths()["tokens"]

    configurations = [
        ("greedy", dict(decoding="greedy_search")),
        ("greedy+hotwords", dict(decoding="greedy_search",
                                 hotwords_file=hotwords_path, bpe_vocab=tokens)),
        ("beam", dict(decoding="modified_beam_search")),
        ("beam+hotwords", dict(decoding="modified_beam_search",
                               hotwords_file=hotwords_path, bpe_vocab=tokens)),
    ]

    print(f"{len(phrases)} frases | hotwords: {os.path.basename(hotwords_path)}")
    print(f"hotwords ({len(HOTWORDS)}): {', '.join(HOTWORDS)}\n")
    print(f"{'config':<18}{'errores':>9}{'palabras':>10}{'WER':>8}"
          f"{'exactas':>10}{'s/frase':>9}{'carga':>8}")

    details = {}
    for name, kwargs in configurations:
        try:
            recognizer, load_seconds = build(**kwargs)
        except Exception as error:
            print(f"{name:<18}  no se pudo crear: {type(error).__name__}: "
                  f"{str(error)[:70]}")
            continue
        errors = words = exact = 0
        elapsed = 0.0
        rows = []
        for phrase in phrases:
            path = os.path.join(args.audio, phrase["id"] + ".wav")
            if not os.path.isfile(path):
                continue
            wav = load_audio(path)
            started = time.perf_counter()
            try:
                text = run(recognizer, wav)
            except Exception as error:
                text = f"<error: {type(error).__name__}>"
            elapsed += time.perf_counter() - started
            reference, hypothesis = normalize(phrase["text"]), normalize(text)
            distance = edit_distance(reference, hypothesis)
            errors += distance
            words += len(reference)
            exact += 1 if reference == hypothesis else 0
            rows.append({"id": phrase["id"], "text": text,
                         "reference": phrase["text"], "errors": distance})
        details[name] = rows
        count = len(rows) or 1
        print(f"{name:<18}{errors:>9}{words:>10}{errors / words:>8.3f}"
              f"{exact:>7}/{count:<2}{elapsed / count:>9.2f}{load_seconds:>8.2f}")

    if "greedy" in details and "beam+hotwords" in details:
        print("\n=== que cambio en las marcas y terminos tecnicos ===")
        base = {row["id"]: row for row in details["greedy"]}
        for row in details["beam+hotwords"]:
            before = base.get(row["id"])
            if before and before["text"] != row["text"]:
                mark = "MEJOR" if row["errors"] < before["errors"] else (
                    "PEOR" if row["errors"] > before["errors"] else "igual")
                print(f"  {row['id']:<6} [{mark}]")
                print(f"      antes : {before['text']}")
                print(f"      ahora : {row['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
