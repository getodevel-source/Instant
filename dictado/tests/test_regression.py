"""Regresion minima: solo comportamiento consumidor-visible."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import config, llm
from instant_app.engine import join_texts, merge_short_bounds


def _check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        raise SystemExit(1)


# join_texts: une, pega puntuacion, colapsa espacios.
_check("join vacios", join_texts(["", "  ", ""]) == "")
_check("join puntuacion", join_texts(["hola mundo", ", ¿ como estas ?"]) == "hola mundo, ¿como estas?")
_check("join espacios", join_texts(["  hola   mundo  "]) == "hola mundo")

# merge_short_bounds: une cortos adyacentes, deja largos solos.
_check("merge cortos", merge_short_bounds([(0.0, 0.3), (0.5, 2.0)]) == [(0.0, 2.0)])
_check("merge largos", merge_short_bounds([(0.0, 3.0), (5.0, 8.0)]) == [(0.0, 3.0), (5.0, 8.0)])
_check("merge gap grande", merge_short_bounds([(0.0, 0.3), (5.0, 5.5)]) == [(0.0, 0.3), (5.0, 5.5)])

# config: defaults + env override + roundtrip de llm_url.
os.environ.pop("DICTADO_LLM_URL", None)
c = config.load()
_check("default llm_url vacio", c.get("llm_url", "") == "")
_check("default sound off", c.get("sound") is False)
_check("default lang es", c.get("lang") == "es")
_check("default threads 4", c.get("threads") == 4)
os.environ["DICTADO_LLM_URL"] = "http://127.0.0.1:8080"
_check("env llm_url", config.load()["llm_url"] == "http://127.0.0.1:8080")
del os.environ["DICTADO_LLM_URL"]

# llm: sin URL -> identico (pipeline sin red).
_check("llm off identico", llm.maybe_polish("hola mundo", {"llm_url": ""}) == "hola mundo")
_check("llm sin server identico",
        llm.maybe_polish("hola mundo", {"llm_url": "http://127.0.0.1:9"}) == "hola mundo")

# hotkey: claves win esperadas.
from instant_app import hotkey
_check("keys win", set(hotkey.WINDOWS_KEYS) == {"f9", "f10", "f20", "scroll", "pause"})
_check("keys posix", tuple(hotkey.POSIX_KEYS) == ("f9", "f10", "f11", "f12"))

# hotkey: normalizacion para captura (Enter/vacio -> default, case-insensible).
_check("normalize enter", hotkey.normalize_key("", "f9") == "f9")
_check("normalize none", hotkey.normalize_key(None, "f9") == "f9")
_check("normalize case", hotkey.normalize_key("F10", "f9") == "f10")
_check("normalize strip", hotkey.normalize_key("  f9  ", "f9") == "f9")

# hotkey: captura asigna tecla valida, Enter = default, repite si invalida.
_orig_read = hotkey._read_keypress
try:
    hotkey._read_keypress = lambda: "f10"
    _check("capture directa", hotkey.capture_key("prompt", "f9") == "f10")
    hotkey._read_keypress = lambda: ""
    _check("capture enter default", hotkey.capture_key("prompt", "f9") == "f9")
    seq = iter(["invalida", "f9"])
    hotkey._read_keypress = lambda: next(seq)
    _check("capture reintenta", hotkey.capture_key("prompt", "f9") == "f9")
finally:
    hotkey._read_keypress = _orig_read

# setup: flags no-interactivos intactos (--yes/--key/--threads/--sound/--llm-url/--mic).
from instant_app.setup import _parse_args
o = _parse_args(["--yes", "--no-probe"])
_check("setup yes noprobe", o.yes and o.no_probe)
o = _parse_args(["--yes", "--mic", "3", "--key", "f9", "--threads", "4", "--no-sound"])
_check("setup flags", o.mic == 3 and o.key == "f9" and o.threads == 4 and o.no_sound)

# modelos: descarga conjunta Parakeet + VAD en un solo paso con progreso claro.
from instant_app import models
with tempfile.TemporaryDirectory() as d:
    import os as _os
    mdir = _os.path.join(d, "parakeet-v3-int8")
    vdir = _os.path.join(d, "silero-vad")
    _os.makedirs(mdir)
    _os.makedirs(vdir)
    for f in models.PARAKEET_FILES:
        open(_os.path.join(mdir, f), "wb").close()
    open(_os.path.join(vdir, "silero_vad.onnx"), "wb").close()
    seen = []
    models.download_models(d, progress=lambda step, done, total: seen.append(step))
    _check("joint parakeet+vad", "parakeet" in seen and "vad" in seen)

print("OK: regresion minima verde.")
