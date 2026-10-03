"""Transcribe: reintento de segmentos vacios con contexto ampliado."""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app.engine import Engine, SAMPLE_RATE, SILENCE_PEAK, _fit_level


def _check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        raise SystemExit(1)


class _FakeStream:
    def __init__(self, decide, counter):
        self._decide = decide
        self._counter = counter
        self._wav = None

    def accept_waveform(self, _sr, wav):
        self._wav = np.asarray(wav, dtype=np.float32)


class _FakeRec:
    def __init__(self, decide):
        self._decide = decide
        self.calls = 0

    def create_stream(self):
        self.calls += 1
        return _FakeStream(self._decide, self)

    def decode_stream(self, s):
        s.result = type("R", (), {"text": self._decide(s._wav)})


def _engine(segment, decide):
    eng = Engine(data_dir=tempfile.mkdtemp(), threads=2)
    eng.segment = lambda _wav: segment
    eng._rec = _FakeRec(decide)
    return eng


def _dur(wav):
    return len(wav) / SAMPLE_RATE


# 1. Perdida total con audio fuerte: el reintento con contexto recupera.
wav = np.full(3 * SAMPLE_RATE, 0.05, dtype=np.float32)
eng = _engine([(0.0, 1.0)], lambda w: "" if _dur(w) < 1.5 else "hola mundo")
_check("fallback recupera vacio total", eng.transcribe(wav) == "hola mundo")
_check("fallback total usa 2 decodes", eng._rec.calls == 2)

# 2. Sin vacios no hay decodes extra.
eng = _engine([(0.0, 1.0)], lambda _w: "ok")
_check("sin vacios no reintenta", eng.transcribe(wav) == "ok" and eng._rec.calls == 1)

# 3. Chunk en silencio no se reintenta (el modelo devuelve vacio real).
silencio = np.zeros(2 * SAMPLE_RATE, dtype=np.float32)
eng = _engine([(0.0, 1.0)],
              lambda w: "" if float(np.max(np.abs(w))) < 0.005 else "nunca")
_check("silencio no reintenta", eng.transcribe(silencio) == "" and eng._rec.calls == 1)


# 4. Perdida parcial: solo el segmento vacio se reintenta y se empalma.
# Gap 1.2s (> max_gap) para que el merge no los una: el contexto del
# reintento (+-1s) igual alcanza la zona de 0.09.
wav4 = np.concatenate([
    np.full(int(3.2 * SAMPLE_RATE), 0.05, dtype=np.float32),
    np.full(int(0.5 * SAMPLE_RATE), 0.09, dtype=np.float32),
    np.full(int(1.3 * SAMPLE_RATE), 0.05, dtype=np.float32),
])


def _decide(w):
    if _dur(w) < 1.5:
        return ""
    return "segunda" if float(np.max(np.abs(w))) > 0.07 else "primera"


eng = _engine([(0.0, 2.0), (3.2, 3.7)], _decide)
_check("fallback parcial empalma", eng.transcribe(wav4) == "primera segunda")
_check("fallback parcial usa 3 decodes", eng._rec.calls == 3)


# 5. _fit_level: solo boost, nunca recorta ni toca el silencio.
_out, g = _fit_level(np.zeros(1600, dtype=np.float32))
_check("nivel silencio intacto", g == 1.0)
_out, g = _fit_level(np.full(16000, 0.5, dtype=np.float32))
_check("nivel fuerte intacto", g == 1.0)
out, g = _fit_level(np.full(16000, 0.01, dtype=np.float32))
_check("nivel debil con boost", abs(g - 6.0) < 1e-6)
_check("nivel debil llega a nominal",
        abs(float(np.sqrt(np.mean(np.square(out, dtype=np.float64)))) - 0.06) < 1e-6)

# 6. Un take bajito que el modelo solo entiende nominal se rescata en el
# primer decode (sin reintentos).
bajo = np.full(2 * SAMPLE_RATE, 0.01, dtype=np.float32)
eng = _engine([(0.0, 1.0)],
              lambda w: "se escucha" if float(
                  np.sqrt(np.mean(np.square(w, dtype=np.float64)))) >= 0.05 else "")
_check("take bajito se rescata", eng.transcribe(bajo) == "se escucha"
        and eng._rec.calls == 1)

print("OK: fallback de transcripcion verde.")
