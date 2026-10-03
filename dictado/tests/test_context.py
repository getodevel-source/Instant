"""Contexto: perfiles de vocabulario local, config y pulido LLM."""
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import config, context, llm


def _check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        raise SystemExit(1)


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

# Context profiles apply only user-authored whole-word variants, without fuzzy
# substitutions that could rewrite ordinary words.
_work_context = {
    "active_context": "Trabajo",
    "context_profiles": {
        "General": [],
        "Trabajo": [
            {"term": "Instant", "aliases": ["instante", "in stand"]},
            {"term": "Parakeet", "aliases": ["para kit"]},
        ],
    },
}
_check("profile replaces explicit aliases only",
       context.correct_aliases(
           "instante abre el instanteo; in stand y para kit.",
           _work_context)
       == "Instant abre el instanteo; Instant y Parakeet.")
_check("inactive profile does not bias text",
       context.correct_aliases("instante", {
           **_work_context, "active_context": "General"
       }) == "instante")
_check("local glossary works with LLM disabled",
       llm.maybe_polish("in stand", _work_context) == "Instant")
with patch("urllib.request.urlopen", side_effect=OSError("server unavailable")):
    _check("LLM failure keeps the locally corrected text",
           llm.maybe_polish(
               "instante",
               {**_work_context, "llm_url": "http://local"})
           == "Instant")


class _FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def _llm_response(text):
    import json
    return _FakeResponse(json.dumps({
        "choices": [{"message": {"content": text}}],
    }).encode())


with patch("urllib.request.urlopen", return_value=_llm_response("¿Cómo estás?")):
    _check("LLM may improve punctuation and accents without changing words",
           llm.polish("como estas", "http://local") == "¿Cómo estás?")
with patch("urllib.request.urlopen", return_value=_llm_response("Hola, mundo y todo.")):
    _check("LLM additions are rejected",
           llm.polish("Hola mundo", "http://local") == "Hola mundo")

with tempfile.TemporaryDirectory() as temp:
    config_file = os.path.join(temp, "config.json")
    with patch("instant_app.config.config_path", return_value=config_file):
        config.save({
            **config.DEFAULTS,
            "active_context": "Trabajo",
            "context_profiles": _work_context["context_profiles"],
        })
        _roundtrip = config.load()
        with patch.dict(os.environ, {"DICTADO_CONTEXT": "General"}):
            _selected = config.load()
        _check("environment selects the active context profile",
               _selected["active_context"] == "General")
    _check("context profiles persist through config",
           _roundtrip["active_context"] == "Trabajo"
           and _roundtrip["context_profiles"]["Trabajo"][0]["term"] == "Instant")

print("OK: contexto y vocabulario verdes.")
