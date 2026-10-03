"""Fusion de dos motores: alinea sus hipotesis por palabra y vota.

Idea: Parakeet y Qwen se equivocan en palabras distintas. Si se alinean las dos
transcripciones contra el mismo audio, en cada posicion se puede elegir la
palabra en la que coinciden, o desempatar con una regla cuando discrepan.

Se prueban varias reglas de desempate para no elegir a ojo:
  - parakeet: gana Parakeet en el desacuerdo (es el motor por defecto)
  - qwen: gana Qwen
  - largo: gana la palabra mas larga (los terminos ingleses mal oidos suelen
    acortarse: «pus» por «push», «bill» por «build»)

La referencia se usa solo para medir; la fusion no la ve. Es lo que se podria
correr en produccion con las dos transcripciones reales.

Uso (desde la raiz del repo):
    python dictado/tests/corpus/evaluate_models.py --engines parakeet --save results_a_parakeet.json
    python dictado/tests/corpus/evaluate_models.py --engines qwen --save results_a_qwen.json
    python dictado/tests/corpus/fuse_engines.py --a results_a_parakeet.json --b results_a_qwen.json
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from evaluate_models import edit_distance, normalize  # noqa: E402


def align(left, right):
    """Alinea dos listas de palabras. Devuelve pares (palabra_a, palabra_b).

    Programacion dinamica con costo 1 por sustitucion, insercion o borrado.
    Cuando una palabra no tiene par, el otro lado aporta None.
    """
    rows, cols = len(left), len(right)
    cost = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(rows + 1):
        cost[i][0] = i
    for j in range(cols + 1):
        cost[0][j] = j
    for i in range(1, rows + 1):
        for j in range(1, cols + 1):
            same = left[i - 1] == right[j - 1]
            cost[i][j] = min(cost[i - 1][j] + 1, cost[i][j - 1] + 1,
                             cost[i - 1][j - 1] + (0 if same else 1))
    pairs = []
    i, j = rows, cols
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            same = left[i - 1] == right[j - 1]
            if cost[i][j] == cost[i - 1][j - 1] + (0 if same else 1):
                pairs.append((left[i - 1], right[j - 1]))
                i, j = i - 1, j - 1
                continue
        if i > 0 and cost[i][j] == cost[i - 1][j] + 1:
            pairs.append((left[i - 1], None))
            i -= 1
            continue
        pairs.append((None, right[j - 1]))
        j -= 1
    pairs.reverse()
    return pairs


def fuse(left_text, right_text, rule, left_words=None, right_words=None):
    """Devuelve el texto fusionado palabra por palabra."""
    left = left_words if left_words is not None else normalize(left_text)
    right = right_words if right_words is not None else normalize(right_text)
    out = []
    for word_a, word_b in align(left, right):
        if word_a == word_b:
            chosen = word_a
        elif word_a is None:
            chosen = word_b
        elif word_b is None:
            chosen = word_a
        elif rule == "parakeet":
            chosen = word_a
        elif rule == "qwen":
            chosen = word_b
        elif rule == "largo":
            chosen = word_a if len(word_a) >= len(word_b) else word_b
        else:
            raise SystemExit(f"regla desconocida: {rule}")
        if chosen:
            out.append(chosen)
    return " ".join(out)


def score(reference, hypothesis):
    ref, hyp = normalize(reference), normalize(hypothesis)
    errors = edit_distance(ref, hyp)
    return errors, len(ref), ref == hyp


def load_rows(path):
    with io.open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return {row["id"]: row for row in data["rows"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fusiona dos motores y mide.")
    parser.add_argument("--a", required=True, help="resultados del motor A (Parakeet)")
    parser.add_argument("--b", required=True, help="resultados del motor B (Qwen)")
    parser.add_argument("--rules", default="parakeet,qwen,largo")
    args = parser.parse_args(argv)

    engine_a, engine_b = load_rows(args.a), load_rows(args.b)
    rules = [value.strip() for value in args.rules.split(",") if value.strip()]

    print(f"{'regla':<12}{'errores':>9}{'palabras':>10}{'WER':>8}{'exactas':>10}")
    for name, rows in (("A solo", engine_a), ("B solo", engine_b)):
        errors = sum(score(r["reference"], r["hypothesis"])[0] for r in rows.values())
        words = sum(score(r["reference"], r["hypothesis"])[1] for r in rows.values())
        exact = sum(1 for r in rows.values() if score(r["reference"], r["hypothesis"])[2])
        print(f"{name:<12}{errors:>9}{words:>10}{errors / words:>8.3f}"
              f"{exact:>7}/{len(rows)}")

    ids = sorted(set(engine_a) & set(engine_b))
    for rule in rules:
        errors = words = exact = 0
        for phrase_id in ids:
            reference = engine_a[phrase_id]["reference"]
            fused = fuse(engine_a[phrase_id]["hypothesis"],
                         engine_b[phrase_id]["hypothesis"], rule)
            e, w, ok = score(reference, fused)
            errors += e
            words += w
            exact += 1 if ok else 0
        print(f"{rule:<12}{errors:>9}{words:>10}{errors / words:>8.3f}"
              f"{exact:>7}/{len(ids)}")

    print("\n=== en que frases gana cada uno (para ver si la fusion aporta) ===")
    for phrase_id in ids:
        ref = engine_a[phrase_id]["reference"]
        a_ok = score(ref, engine_a[phrase_id]["hypothesis"])[2]
        b_ok = score(ref, engine_b[phrase_id]["hypothesis"])[2]
        if a_ok != b_ok:
            quien = "A(parakeet)" if a_ok else "B(qwen)"
            print(f"  {phrase_id:<6} gana {quien}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
