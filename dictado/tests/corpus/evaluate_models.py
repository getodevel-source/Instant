"""Compara motores sobre el corpus etiquetado: WER, frases exactas y tiempos.

Uso (desde la raiz del repo, con el .venv del proyecto):

    python dictado/tests/corpus/evaluate_models.py
    python dictado/tests/corpus/evaluate_models.py --engines parakeet
    python dictado/tests/corpus/evaluate_models.py --hotwords terminos
    python dictado/tests/corpus/evaluate_models.py --save results.json

Metricas:
- WER: distancia de edicion por palabra sobre texto normalizado (minusculas y
  sin tildes), porque la ortografia no deberia contar como error del motor.
- Frase exacta: coincidencia completa tras normalizar.
- Signos: si el texto reconocido trae ¿ y ¡ de apertura cuando la etiqueta los
  tiene. Es el unico aspecto donde el pulido LLM puede aportar.
- Tiempo: pared por frase, con el modelo ya cargado (medida en caliente).

Aviso: el audio del corpus es voz sintetica. Compara motores entre si; no
reemplaza una grabacion humana.
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(REPO, "dictado", "src"))

MANIFEST = os.path.join(HERE, "manifest.json")
AUDIO_DIR = os.path.join(HERE, "audio")
SAMPLE_RATE = 16000

# Terminos que Parakeet suele devolver por fonetica. No salen del manifiesto:
# son la lista que un usuario escribiaria en su perfil de vocabulario.
USER_HOTWORDS = ["Instant", "Parakeet", "Qwen", "commit", "deploy", "push",
                 "build", "staging", "feedback", "workflow", "frontend",
                 "backend", "plugin", "driver", "benchmark", "script"]


def load_audio(path):
    with wave.open(path, "rb") as handle:
        frames, rate = handle.getnframes(), handle.getframerate()
        raw = handle.readframes(frames)
    if rate != SAMPLE_RATE:
        raise SystemExit(f"{path}: se esperaba {SAMPLE_RATE} Hz, hay {rate}.")
    return np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0


def normalize(text):
    """Minusculas, sin tildes ni signos: lo que se compara palabra a palabra."""
    decomposed = unicodedata.normalize("NFD", (text or "").casefold())
    stripped = "".join(char for char in decomposed
                       if unicodedata.category(char) != "Mn")
    return re.findall(r"[a-z0-9]+", stripped)


def edit_distance(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, start=1):
        current = [i]
        for j, hyp in enumerate(hypothesis, start=1):
            cost = 0 if ref == hyp else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + cost))
        previous = current
    return previous[-1]


def score(reference, hypothesis):
    ref_words, hyp_words = normalize(reference), normalize(hypothesis)
    distance = edit_distance(ref_words, hyp_words)
    return {
        "ref_words": len(ref_words),
        "errors": distance,
        "wer": distance / len(ref_words) if ref_words else 0.0,
        "exact": ref_words == hyp_words,
    }


def openings_ok(reference, hypothesis):
    """¿Trae los signos de apertura que la etiqueta tiene?"""
    expected = [mark for mark in "¿¡" if mark in reference]
    if not expected:
        return None
    return all(mark in hypothesis for mark in expected)


def punctuation_ok(reference, hypothesis):
    """Cuenta los signos que la etiqueta tiene y el motor puso.

    Compara cantidad, no tipo: si el motor escribe tres puntos donde la
    etiqueta tiene `¿ ? .`, cuenta 3 de 3. Es una cota superior, suficiente
    para ver si el motor puntua en absoluto. La dimension donde el pulido LLM
    puede compensar al motor es esta: no cambia palabras, agrega signos.
    """
    if not hypothesis:
        return 0, 0
    expected = sum(reference.count(mark) for mark in "¿¡?!.,")
    present = sum(hypothesis.count(mark) for mark in "¿¡?!.,")
    return min(present, expected), expected


class ParakeetRunner:
    name = "parakeet"

    def __init__(self, threads):
        from instant_app.engine import Engine

        self.engine = Engine(threads=threads)
        started = time.perf_counter()
        self.engine.recognizer()
        self.engine.vad()
        self.load_seconds = time.perf_counter() - started

    def transcribe(self, wav):
        started = time.perf_counter()
        text = self.engine.transcribe(wav)
        return text, time.perf_counter() - started


class QwenRunner:
    def __init__(self, threads, hotwords=(), name="qwen"):
        import sherpa_onnx

        from instant_app import models
        from instant_app.paths import qwen3_asr_paths

        self.name = name
        missing = [key for key, ok in models.check_qwen3_asr(None).items() if not ok]
        if missing:
            raise SystemExit("falta el modelo de prueba Qwen3-ASR: "
                             + ", ".join(missing))
        paths = qwen3_asr_paths(None)
        started = time.perf_counter()
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
            conv_frontend=paths["conv_frontend"],
            encoder=paths["encoder"],
            decoder=paths["decoder"],
            tokenizer=paths["tokenizer"],
            num_threads=threads,
            sample_rate=SAMPLE_RATE,
            provider="cpu",
            hotwords=",".join(hotwords),
        )
        self.load_seconds = time.perf_counter() - started

    def transcribe(self, wav):
        started = time.perf_counter()
        stream = self.recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, np.ascontiguousarray(wav, dtype=np.float32))
        self.recognizer.decode_stream(stream)
        return (stream.result.text or "").strip(), time.perf_counter() - started


def build_runners(names, threads, hotword_mode):
    hotwords = USER_HOTWORDS if hotword_mode == "terminos" else ()
    runners = []
    for name in names:
        if name == "parakeet":
            runners.append(ParakeetRunner(threads))
        elif name == "qwen":
            runners.append(QwenRunner(threads, hotwords, "qwen+hotwords"))
        elif name == "qwen-sin-hotwords":
            runners.append(QwenRunner(threads, (), "qwen"))
        else:
            raise SystemExit(f"motor desconocido: {name}")
    return runners


def evaluate(runners, manifest, audio_dir):
    rows = []
    for runner in runners:
        print(f"\n=== {runner.name} (carga {runner.load_seconds:.2f}s) ===")
        for phrase in manifest["phrases"]:
            path = os.path.join(audio_dir, phrase["id"] + ".wav")
            if not os.path.isfile(path):
                print(f"  {phrase['id']:<6} sin audio, se omite")
                continue
            wav = load_audio(path)
            text, elapsed = runner.transcribe(wav)
            result = score(phrase["text"], text)
            marks_present, marks_expected = punctuation_ok(phrase["text"], text)
            rows.append({
                "engine": runner.name,
                "id": phrase["id"],
                "category": phrase["category"],
                "reference": phrase["text"],
                "hypothesis": text,
                "seconds": elapsed,
                **result,
                "openings": openings_ok(phrase["text"], text),
                "marks_present": marks_present,
                "marks_expected": marks_expected,
            })
            flag = "" if result["exact"] else "  <-- difiere"
            print(f"  {phrase['id']:<6} WER {result['wer']:.2f} "
                  f"{elapsed:.2f}s{flag}")
    return rows


def summarize(rows):
    engines = []
    for row in rows:
        if row["engine"] not in engines:
            engines.append(row["engine"])
    print("\n=== resumen por motor ===")
    print(f"{'motor':<22}{'palabras':>9}{'errores':>9}{'WER':>8}"
          f"{'exactas':>9}{'s/frase':>9}")
    for engine in engines:
        subset = [row for row in rows if row["engine"] == engine]
        words = sum(row["ref_words"] for row in subset)
        errors = sum(row["errors"] for row in subset)
        exact = sum(1 for row in subset if row["exact"])
        seconds = sum(row["seconds"] for row in subset)
        print(f"{engine:<22}{words:>9}{errors:>9}"
              f"{errors / words if words else 0:>8.3f}"
              f"{exact:>6}/{len(subset):<2}{seconds / len(subset):>9.2f}")

    categories = []
    for row in rows:
        if row["category"] not in categories:
            categories.append(row["category"])
    print("\n=== WER por categoria ===")
    header = f"{'categoria':<20}" + "".join(f"{engine:>22}" for engine in engines)
    print(header)
    for category in categories:
        cells = []
        for engine in engines:
            subset = [row for row in rows
                      if row["engine"] == engine and row["category"] == category]
            words = sum(row["ref_words"] for row in subset)
            errors = sum(row["errors"] for row in subset)
            exact = sum(1 for row in subset if row["exact"])
            cells.append(f"{errors / words if words else 0:.3f} ({exact}/{len(subset)})"
                         if words else "-")
        print(f"{category:<20}" + "".join(f"{cell:>22}" for cell in cells))

    print("\n=== signos de apertura (¿ / ¡) ===")
    for engine in engines:
        subset = [row for row in rows
                  if row["engine"] == engine and row["openings"] is not None]
        if not subset:
            continue
        ok = sum(1 for row in subset if row["openings"])
        print(f"{engine:<22}{ok}/{len(subset)} frases con los signos esperados")

    print("\n=== puntuacion y tildes (cuanto del total esperado puso el motor) ===")
    for engine in engines:
        subset = [row for row in rows if row["engine"] == engine]
        present = sum(row["marks_present"] for row in subset)
        expected = sum(row["marks_expected"] for row in subset)
        print(f"{engine:<22}{present}/{expected} signos"
              f"  ({present / expected * 100 if expected else 0:.0f} %)")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evalua motores sobre el corpus.")
    parser.add_argument("--manifest", default=MANIFEST)
    parser.add_argument("--audio", default=AUDIO_DIR)
    parser.add_argument("--engines", default="parakeet,qwen",
                        help="parakeet, qwen, qwen-sin-hotwords (separados por coma)")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--hotwords", default="terminos", choices=("terminos", "ninguno"),
                        help="si qwen recibe la lista de terminos del usuario")
    parser.add_argument("--save", default="", help="escribe los resultados en JSON")
    args = parser.parse_args(argv)

    with open(args.manifest, encoding="utf-8") as handle:
        manifest = json.load(handle)
    names = [value.strip() for value in args.engines.split(",") if value.strip()]
    runners = build_runners(names, args.threads, args.hotwords)
    rows = evaluate(runners, manifest, args.audio)
    summarize(rows)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as handle:
            json.dump({"hotwords": args.hotwords, "rows": rows}, handle,
                      ensure_ascii=False, indent=2)
        print(f"\nresultados en {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
