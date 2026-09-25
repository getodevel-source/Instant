"""Regresion minima: solo comportamiento consumidor-visible."""
import os
import sys

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

print("OK: regresion minima verde.")
