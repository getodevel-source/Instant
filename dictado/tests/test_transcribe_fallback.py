"""Transcribe: reintento de segmentos vacios con contexto ampliado."""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app.engine import Engine, SAMPLE_RATE, _fit_level


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


def _tone(seconds, amp=0.05, freq=220.0):
    """Senoide con contenido AC: sobrevive al frontend (DC-remove + HP),
    como la voz real. Las constantes puras son offset ADC, no voz."""
    n = int(seconds * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    return (np.sin(2 * np.pi * freq * t) * amp).astype(np.float32)


# 1. Perdida total con audio fuerte: el reintento con contexto recupera.
wav = _tone(3.0)
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
# reintento (+-1s) igual alcanza la zona fuerte.
wav4 = np.concatenate([_tone(3.2, amp=0.05), _tone(0.5, amp=0.09),
                       _tone(1.3, amp=0.05)])


def _decide(w):
    if _dur(w) < 1.5:
        return ""
    return "segunda" if float(np.max(np.abs(w))) > 0.07 else "primera"


eng = _engine([(0.0, 2.0), (3.2, 3.7)], _decide)
_check("fallback parcial empalma", eng.transcribe(wav4) == "primera segunda")
# Con overlap de bordes el seg 2 ya trae contexto y decodifica directo:
# 2 decodes, sin reintentos (antes 3: el overlap mejoro el caso).
_check("overlap evita el reintento", eng._rec.calls == 2)

# 4b. Si aun con overlap el seg sale vacio, el retry +-1s lo rescata.
eng = _engine([(0.0, 2.0), (3.2, 3.7)],
              lambda w: "rescatada" if _dur(w) >= 2.6 else "")
_check("retry rescata vacio con overlap", eng.transcribe(wav4) == "rescatada")
_check("retry parcial usa 4 decodes", eng._rec.calls == 4)

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
bajo = _tone(2.0, amp=0.01)
eng = _engine([(0.0, 1.0)],
              lambda w: "se escucha" if float(
                  np.sqrt(np.mean(np.square(w, dtype=np.float64)))) >= 0.05 else "")
_check("take bajito se rescata", eng.transcribe(bajo) == "se escucha"
        and eng._rec.calls == 1)

# 7. Confianza: exp(media log-probs); sin scores no se castiga.
from instant_app.engine import _mean_conf
_check("conf sin scores es 1", _mean_conf(None) == 1.0 and _mean_conf([]) == 1.0)
_check("conf tokens seguros alta",
        abs(_mean_conf([-0.1, -0.2, -0.05]) - 0.89) < 0.02)
_check("conf tokens dudosos baja", _mean_conf([-2.0, -3.0]) < 0.1)
_check("conf acotada", 0.0 <= _mean_conf([-1000.0]) <= 1.0)

# 8. blank_penalty y vad_model: defaults seguros, clamp 0..1.
_e = Engine(data_dir=tempfile.mkdtemp())
_check("blank default 0", _e.blank_penalty == 0.0 and _e.vad_model == "silero")
_e = Engine(data_dir=tempfile.mkdtemp(), blank_penalty=2.0, vad_model="TEN")
_check("blank clamp + vad norm", _e.blank_penalty == 1.0 and _e.vad_model == "ten")
_e = Engine(data_dir=tempfile.mkdtemp(), blank_penalty="mal")
_check("blank invalido a 0", _e.blank_penalty == 0.0)
_check("word_confs init vacio", _e.last_word_confs == [])

# 9. Gate por palabra: alinea tokens a palabras con el eslabon debil.
from instant_app.engine import _word_confs
_wc = _word_confs(
    [" S", "ub", "í", " qu", "em", "ita"],
    [-0.01, -0.0, -0.0, -0.68, -0.0, -0.01],
    [0.0, 0.16, 0.32, 0.56, 0.72, 0.88])
_check("word_confs alinea",
        [w for w, _c, _a, _b in _wc] == ["Subí", "quemita"]
        and abs(_wc[1][1] - 0.51) < 0.02)
_check("word_confs sin scores vacio", _word_confs(None, None, None) == [])
