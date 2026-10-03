"""Repite la comparacion sobre dos pasadas de audio y comprueba si se sostiene.

La primera medicion uso una sola generacion de audio: un ritmo y dos voces.
Si la ventaja de un motor desaparece al cambiar de voz y de ritmo, la decision
no esta probada. Este script mide las dos pasadas y compara el ranking.

Uso (desde la raiz del repo, con el .venv del proyecto):

    python dictado/tests/corpus/generate_corpus.py
    python dictado/tests/corpus/generate_corpus.py --out dictado/tests/corpus/audio_b \\
        --voice-set voices_pass_b --rate=-12%
    python dictado/tests/corpus/robustness.py

Pasada A: voces es-AR y es-ES a ritmo normal.
Pasada B: voces es-MX y es-CO, 12 % mas lento.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(REPO, "dictado", "src"))
sys.path.insert(0, HERE)

from evaluate_models import build_runners, evaluate, summarize  # noqa: E402

MANIFEST = os.path.join(HERE, "manifest.json")
PASSES = [("A", os.path.join(HERE, "audio")),
          ("B", os.path.join(HERE, "audio_b"))]


def wer_of(rows, engine):
    subset = [row for row in rows if row["engine"] == engine]
    words = sum(row["ref_words"] for row in subset)
    errors = sum(row["errors"] for row in subset)
    return (errors / words if words else 0.0), subset


def main(argv=None):
    parser = argparse.ArgumentParser(description="Robustez entre pasadas de audio.")
    parser.add_argument("--engines", default="parakeet,qwen,qwen-sin-hotwords")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--hotwords", default="terminos",
                        choices=("terminos", "ninguno"))
    parser.add_argument("--save", default=os.path.join(HERE, "robustness.json"))
    args = parser.parse_args(argv)

    with open(MANIFEST, encoding="utf-8") as handle:
        manifest = json.load(handle)
    names = [value.strip() for value in args.engines.split(",") if value.strip()]

    all_rows = {}
    for label, audio_dir in PASSES:
        if not os.path.isdir(audio_dir):
            print(f"pasada {label}: falta {audio_dir}, se omite")
            continue
        print(f"\n########## pasada {label} ({audio_dir}) ##########")
        runners = build_runners(names, args.threads, args.hotwords)
        rows = evaluate(runners, manifest, audio_dir)
        summarize(rows)
        all_rows[label] = rows

    if len(all_rows) < 2:
        print("\nHace falta mas de una pasada para comparar robustez.")
        return 1

    print("\n\n########## robustez entre pasadas ##########")
    print(f"{'motor':<22}{'WER A':>9}{'WER B':>9}{'dif':>9}"
          f"{'exactas A':>11}{'exactas B':>11}{'s/frase A':>11}{'s/frase B':>11}")
    engines = []
    for row in all_rows["A"]:
        if row["engine"] not in engines:
            engines.append(row["engine"])
    verdict = {}
    for engine in engines:
        wer_a, rows_a = wer_of(all_rows["A"], engine)
        wer_b, rows_b = wer_of(all_rows["B"], engine)
        exact_a = sum(1 for row in rows_a if row["exact"])
        exact_b = sum(1 for row in rows_b if row["exact"])
        sec_a = sum(row["seconds"] for row in rows_a) / len(rows_a)
        sec_b = sum(row["seconds"] for row in rows_b) / len(rows_b)
        verdict[engine] = {"wer_a": wer_a, "wer_b": wer_b,
                           "exact_a": exact_a, "exact_b": exact_b,
                           "seconds_a": sec_a, "seconds_b": sec_b}
        print(f"{engine:<22}{wer_a:>9.3f}{wer_b:>9.3f}{wer_b - wer_a:>+9.3f}"
              f"{exact_a:>7}/{len(rows_a):<3}{exact_b:>7}/{len(rows_b):<3}"
              f"{sec_a:>11.2f}{sec_b:>11.2f}")

    print("\n=== el ranking se sostiene? ===")
    order_a = sorted(engines, key=lambda name: verdict[name]["wer_a"])
    order_b = sorted(engines, key=lambda name: verdict[name]["wer_b"])
    print(f"pasada A: {' < '.join(order_a)}")
    print(f"pasada B: {' < '.join(order_b)}")
    winner_a, winner_b = order_a[0], order_b[0]
    if winner_a == winner_b:
        print(f"SI: {winner_a} gana en las dos pasadas.")
    else:
        print(f"NO: gana {winner_a} en A y {winner_b} en B. La decision necesita "
              f"mas audio o mas frases antes de cerrarse.")
    speed_a = sorted(engines, key=lambda name: verdict[name]["seconds_a"])
    speed_b = sorted(engines, key=lambda name: verdict[name]["seconds_b"])
    print(f"mas rapido: {speed_a[0]} en A, {speed_b[0]} en B")

    if args.save:
        with open(args.save, "w", encoding="utf-8") as handle:
            json.dump({"verdict": verdict,
                       "order_a": order_a, "order_b": order_b,
                       "rows": all_rows}, handle, ensure_ascii=False, indent=2)
        print(f"\nresultados en {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
