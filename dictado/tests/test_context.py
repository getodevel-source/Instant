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
_check("default orbital overlay", config.DEFAULTS.get("overlay_style") == "orbital")
os.environ["DICTADO_LLM_URL"] = "http://127.0.0.1:8080"
_check("env llm_url", config.load()["llm_url"] == "http://127.0.0.1:8080")
del os.environ["DICTADO_LLM_URL"]

# llm: sin URL -> identico (pipeline sin red).
_check("llm off identico", llm.maybe_polish("hola mundo", {"llm_url": ""}) == "hola mundo")
_check("llm sin server identico",
        llm.maybe_polish("hola mundo", {"llm_url": "http://127.0.0.1:9"}) == "hola mundo")

# Gate de confianza: texto seguro no toca la red aunque haya URL.
with patch("urllib.request.urlopen") as _urlopen:
    _check("confianza alta no llama LLM",
           llm.maybe_polish("hola mundo", {"llm_url": "http://local"}, conf=0.95)
           == "hola mundo" and not _urlopen.called)
with patch("urllib.request.urlopen", side_effect=OSError("caido")):
    _check("confianza baja intenta LLM y cae a local",
           llm.maybe_polish("hola mundo", {"llm_url": "http://local"}, conf=0.5)
           == "hola mundo")

# restore_openers: ¿ determinista, sin red, sin reescribir palabras.
_check("opener pregunta que", llm.restore_openers("que hora es?") == "¿que hora es?")
_check("opener pregunta como", llm.restore_openers("cómo estás?") == "¿cómo estás?")
_check("opener con apertura intacta",
        llm.restore_openers("¿qué hora es?") == "¿qué hora es?")
_check("opener no toca afirmacion", llm.restore_openers("que bueno.") == "que bueno.")
_check("opener no inventa sin cierre",
        llm.restore_openers("que hora es") == "que hora es")
_check("opener no toca exclamacion", llm.restore_openers("qué bueno!") == "qué bueno!")
_check("opener multi-oracion",
        llm.restore_openers("hola. dónde estás?") == "hola. ¿dónde estás?")

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
_check("exact multiword aliases preserve punctuation boundaries",
       context.correct_aliases("in, stand", _work_context) == "in, stand")
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

# Bias general: rescata tecnicos en takes dudosos, intacto en seguros.
from instant_app import bias as _bias
_tech = "probando Instant con Parkit. Hice un comic del workflow."
_fixed = "probando Instant con Parakeet. Hice un commit del workflow."
_check("bias rescata con duda", _bias.correct_biased(_tech, conf=0.5) == _fixed)
_check("bias intacto sin duda", _bias.correct_biased(_tech, conf=0.95) == _tech)
_check("bias no toca sano ni vacio",
        _bias.correct_biased("hola mundo", conf=0.3) == "hola mundo"
        and _bias.correct_biased("", conf=0.1) == "")
_check("bias no reescribe palabras corrientes",
        _bias.correct_biased("para que funcione quien quiera", conf=0.2)
        == "para que funcione quien quiera")

# Bias con contexto: la vecina confirma, su ausencia protege.
_check("bias contexto rescata con vecina",
        _bias.correct_biased("hice un comic del workflow", conf=0.5)
        == "hice un commit del workflow")
_check("bias contexto protege comic sano",
        _bias.correct_biased("lei un comic de superheroes", conf=0.5)
        == "lei un comic de superheroes")
_check("bias contexto protege comer verbo",
        _bias.correct_biased("voy a comer con el equipo del workflow",
                             conf=0.5)
        == "voy a comer con el equipo del workflow")
_check("bias contexto protege comer tras que",
        _bias.correct_biased("hay que comer antes del deploy", conf=0.5)
        == "hay que comer antes del deploy")
_check("bias contexto rescata wey con vecina",
        _bias.correct_biased("el wey fallo por el driver", conf=0.5)
        == "el build fallo por el driver")
_check("bias contexto protege wey sano",
        _bias.correct_biased("ese wey es mi amigo", conf=0.5)
        == "ese wey es mi amigo")
_check("bias contexto rescata debil con vecina",
        _bias.correct_biased("subi el quemita hithub y corri el workflow",
                             conf=0.5)
        == "subi el commit GitHub y corri el workflow")

# Gate por palabra: take seguro + palabra dudosa con vecina rescata.
_wc_way = [("El", 0.99, 0, 1), ("Way", 0.55, 1, 2), ("fall", 0.97, 2, 3),
           ("por", 0.99, 3, 4), ("el", 1.0, 4, 5), ("driver", 0.96, 5, 6)]
_check("bias palabra rescata en take seguro",
        _bias.correct_biased("El Way fall por el driver.", conf=0.95,
                             word_confs=_wc_way)
        == "El build fall por el driver.")
_check("bias palabra intacto sin word_confs",
        _bias.correct_biased("El Way fall por el driver.", conf=0.95)
        == "El Way fall por el driver.")
_wc_sano = [("Ese", 0.9, 0, 1), ("wey", 0.6, 1, 2), ("es", 0.99, 2, 3),
            ("mi", 0.99, 3, 4), ("amigo", 0.97, 4, 5)]
_check("bias palabra protege sin vecina",
        _bias.correct_biased("Ese wey es mi amigo.", conf=0.95,
                             word_confs=_wc_sano)
        == "Ese wey es mi amigo.")

# Bateria adversaria: español sano sin nada tecnico. El bias NO debe tocar
# ni una coma, con duda o sin ella. Cada frase es un falso positivo que
# un corrector agresivo cometeria.
_ADVERS = [
    "lei un comic de superheroes en la plaza",
    "voy a comer una pizza con mis amigos",
    "hay que comer antes de salir al cine",
    "ese wey es mi amigo de la infancia",
    "el instante preciso en que llego el tren",
    "para que funcione quien quiera venir",
    "voy a comer un asado el domingo en familia",
    "compramos comida para el viaje en auto",
    "el nene juega a la pelota en el parque",
    "mi mama cocina muy bien los domingos",
    "el partido estuvo buenisimo hasta el final",
    "trabajo en una oficina del centro todo el dia",
    "el perro ladra cuando tocan el timbre",
    "hicimos una fiesta sorpresa para ana",
    "el medico dijo que tome agua y descanse",
    "la pelicula que vimos anoche fue larga",
    "quiero aprender a tocar la guitarra",
    "el supermercado cierra a las nueve",
    "mi hermana estudia medicina en rosario",
    "el colectivo llego tarde por el trafico",
    "cosechamos tomates y lechuga en la quinta",
    "el bebe duerme toda la noche seguida",
    "fuimos a la playa en enero con calor",
    "la receta lleva harina huevos y leche",
    "mi abuelo cuenta historias de la guerra",
    "el jardin se lleno de flores en primavera",
    "jugamos al truco hasta la madrugada",
    "la escuela queda a tres cuadras de casa",
    "el vecino puso musica fuerte ayer",
    "compre pan y facturas para el mate",
]
_advers_bad = [s for s in _ADVERS
               if _bias.correct_biased(s, conf=0.3) != s
               or _bias.correct_biased(s, conf=0.95) != s]
_check("bias adversaria intacta (30 sanas)", _advers_bad == [])

# Regla C: caso medido en voz real, sin gate de confianza.
_check("bias strong rescata will con 2 vecinas",
        _bias.correct_biased("El Will fallo en la manana por el driver.",
                             conf=0.99)
        == "El build fallo en la manana por el driver.")
_check("bias strong protege will sin vecinas",
        _bias.correct_biased("Will Walchar no molesta.", conf=0.99)
        == "Will Walchar no molesta.")
_check("bias strong rescata will con vecina deformada",
        _bias.correct_biased("El Will fall otra vez por el driver viejo.",
                             conf=0.99)
        == "El build fall otra vez por el driver viejo.")
_check("bias strong protege nombre real",
        _bias.correct_biased("Voy a hablar del testamento de Will.", conf=0.99)
        == "Voy a hablar del testamento de Will.")
_check("bias strong protege wild sano",
        _bias.correct_biased("El wild anda suelto en el bosque.", conf=0.99)
        == "El wild anda suelto en el bosque.")
_check("bias protege dictado en ingles",
        _bias.correct_biased(
            "The will to build something and the way it works.", conf=0.3)
        == "The will to build something and the way it works.")

print("OK: contexto y vocabulario verdes.")
