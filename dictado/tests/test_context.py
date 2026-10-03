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

# Emparejamiento por sonido: el motor no solo sustituye sonidos, tambien pierde
# letras («Qwen» -> «ken») y parte palabras («OpenAI» -> «O en Pi»). Se activa
# por termino con `~` en el editor y nunca debe tocar texto corriente.
_sonido_context = {
    "active_context": "General",
    "context_profiles": {"General": [
        {"term": "Qwen", "aliases": ["cuentres"], "sonido": True},
        {"term": "GitHub", "aliases": ["hit hub"], "sonido": True},
        {"term": "OpenAI", "aliases": [], "sonido": True},
    ]},
}
_check("sound key groups what the recognizer confuses",
       context._sound_key("Qwen") == context._sound_key("cuen")
       and context._sound_key("GitHub") == context._sound_key("git hub"))
_check("sound matching fixes a lost letter",
       context.correct_aliases("decime si Quen puede hacerlo", _sonido_context)
       == "decime si Qwen puede hacerlo")
_check("sound matching fixes a split word",
       context.correct_aliases("la velocidad con O en Pi y Pi", _sonido_context)
       == "la velocidad con OpenAI y Pi")
_check("listed alias still works with sound on",
       context.correct_aliases("teniendo Cuentres ASR", _sonido_context)
       == "teniendo Qwen ASR")
_check("sound matching leaves ordinary Spanish alone",
       context.correct_aliases(
           "Preguntale a quien quieras, para que esto funcione y para que sirva.",
           _sonido_context)
       == "Preguntale a quien quieras, para que esto funcione y para que sirva.")
_check("sound matching never rewrites the preferred spelling",
       context.correct_aliases("Qwen y GitHub y OpenAI", _sonido_context)
       == "Qwen y GitHub y OpenAI")
_check("sound off means no guessing",
       context.correct_aliases("decime si Quen puede", {
           "context_profiles": {"General": [
               {"term": "Qwen", "aliases": [], "sonido": False}]}})
       == "decime si Quen puede")

# El editor marca el sonido con `~` y lo conserva al ida y vuelta.
_editor = context.editor_text(context.parse_editor("~Qwen\tcuen | quen\nParakeet\tpara kit"))
_check("editor marks sound terms and round-trips them",
       _editor.startswith("~Qwen\t") and "Parakeet\t" in _editor
       and context.parse_editor(_editor)[0]["sonido"] is True
       and context.parse_editor(_editor)[1]["sonido"] is False)
_check("editor keeps a term without aliases",
       context.parse_editor("~GitHub")[0]
       == {"term": "GitHub", "aliases": [], "sonido": True})

print("OK: contexto y vocabulario verdes.")
