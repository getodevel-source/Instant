"""Graba frames.jsonl del bake-off: la MISMA matematica de features que usa el
daemon en produccion (_LevelTracker), alimentada con una pista silabica
sintetica deterministica (sin microfono, reproducible bit a bit).

El reloj se falsea (stub en instant_app.daemon.time) para que el throttle de
50 ms de tick() corra sobre tiempo de audio: la grabacion es instantanea y los
timestamps del JSONL son de la pista, no de pared.

Uso:
    python record_frames.py [--out frames.jsonl] [--rate-hz 20] [--seed 7]

Salida: primera linea meta, luego una linea por frame de emision (~20 Hz):
    {"t": ms, "mode": "...", "level": 0..1, "bands": [9], "pitch": 0..1}
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "src")))

SR = 16000
BLOCK_MS = 10

# Linea de tiempo de la pista (ms). Refleja una sesion real: tecla, dictado
# con dos frases, procesado, aviso y despedida.
T_STARTING = 600
T_LISTENING = 1000
T_PROCESSING = 7000
T_NOTICE = 8700
T_END = 9800
DURATION = 10600


def syllable(f0, dur_s, amp, rng):
    """Silaba sintetica: armonicos 1/2/3.02 con jitter de fase, como
    bench_numbers.py (los tonos no son voz; alcanza para la dinamica)."""
    n = int(SR * dur_s)
    t = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f0 * t + float(rng.random()))
         + 0.5 * np.sin(2 * np.pi * f0 * 2 * t + float(rng.random()))
         + 0.25 * np.sin(2 * np.pi * f0 * 3.02 * t + float(rng.random()))
         + 0.02 * rng.standard_normal(n))
    r = int(0.015 * SR)
    env = np.ones(n)
    env[:r] = np.linspace(0, 1, r)
    env[-r:] = np.linspace(1, 0, r)
    return (x * env * amp / np.max(np.abs(x))).astype(np.float32)


def synth_track(seed):
    rng = np.random.default_rng(seed)
    total = np.zeros(int(SR * DURATION / 1000), dtype=np.float32)

    def put(start_ms, buf):
        i = int(SR * start_ms / 1000)
        total[i:i + len(buf)] += buf[:len(total) - i]

    # "starting": ruido de respiracion por debajo de la puerta de silencio.
    put(T_STARTING, (0.004 * rng.standard_normal(int(SR * 0.4))).astype(np.float32))

    # Dictado: dos frases de silabas con pausas, f0 variando 100..320 Hz.
    cursor = T_LISTENING
    for phrase_end in (3400, T_PROCESSING):
        while cursor < phrase_end:
            f0 = float(100 + 220 * rng.random() ** 0.8)
            dur = 0.12 + 0.14 * rng.random()
            amp = 0.12 + 0.34 * rng.random()
            if rng.random() < 0.12:
                amp *= 0.4  # silaba baja suelta
            buf = syllable(f0, dur, amp, rng)
            if cursor + len(buf) / SR * 1000 > phrase_end:
                break
            put(cursor, buf)
            cursor += len(buf) / SR * 1000 + 30 + 120 * rng.random()
        cursor = phrase_end + 300  # pausa entre frases
    return total


class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


def mode_for(t_ms):
    if t_ms < T_STARTING:
        return "idle"
    if t_ms < T_LISTENING:
        return "starting"
    if t_ms < T_PROCESSING:
        return "listening"
    if t_ms < T_NOTICE:
        return "processing"
    if t_ms < T_END:
        return "notice"
    return "idle"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(HERE, "frames.jsonl"))
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    track = synth_track(args.seed)

    import instant_app.daemon as daemon_mod
    from instant_app.daemon import _LevelTracker

    clock = _FakeClock()
    daemon_mod.time = clock  # tick() lee solo monotonic(); el stub lo controla

    frames = []
    pending = {}

    class Recorder:
        def set_level(self, sid, value):
            pending["level"] = round(float(value), 4)

        def set_bands(self, sid, values):
            pending["bands"] = [round(float(v), 4) for v in values]

        def set_pitch(self, sid, value):
            pending["pitch"] = round(float(value), 4)

    tracker = _LevelTracker("bakeoff", Recorder())
    block = int(SR * BLOCK_MS / 1000)
    for i in range(0, len(track), block):
        clock.now += len(track[i:i + block]) / SR
        tracker.add(track[i:i + block])
        pending.clear()
        tracker.tick()
        if pending:
            t_ms = int(round(clock.now * 1000))
            frame = {"t": t_ms, "mode": mode_for(t_ms)}
            frame.update(pending)
            if frame["mode"] == "notice":
                frame["message"] = "Listo"
            frames.append(frame)

    meta = {"rate_hz": 20, "duration_ms": DURATION, "source": "synth-syllabic",
            "seed": args.seed, "audio_sr": SR, "block_ms": BLOCK_MS,
            "modes": {"idle": [0, T_STARTING], "starting": [T_STARTING, T_LISTENING],
                      "listening": [T_LISTENING, T_PROCESSING],
                      "processing": [T_PROCESSING, T_NOTICE],
                      "notice": [T_NOTICE, T_END], "idle_end": [T_END, DURATION]}}
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(meta) + "\n")
        for frame in frames:
            fh.write(json.dumps(frame, separators=(",", ":")) + "\n")

    listening = [f for f in frames if f["mode"] == "listening"]
    levels = [f["level"] for f in listening]
    bands_mean = np.mean([f["bands"] for f in listening], axis=0).round(3).tolist()
    pitches = [f["pitch"] for f in listening]
    print(json.dumps({
        "event": "recorded", "out": args.out, "frames": len(frames),
        "listening_frames": len(listening),
        "level_min": round(min(levels), 3), "level_max": round(max(levels), 3),
        "level_mean": round(float(np.mean(levels)), 3),
        "bands_mean": bands_mean,
        "pitch_min": round(min(pitches), 3), "pitch_max": round(max(pitches), 3),
        "modes": sorted({f["mode"] for f in frames}),
    }))


if __name__ == "__main__":
    main()
