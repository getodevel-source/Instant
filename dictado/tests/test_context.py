"""Contexto: perfiles de vocabulario local, config y pulido LLM."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import bias as _bias
from instant_app import config, context, llm

_WORK_CONTEXT = {
    "active_context": "Trabajo",
    "context_profiles": {
        "General": [],
        "Trabajo": [
            {"term": "Instant", "aliases": ["instante", "in stand"]},
            {"term": "Parakeet", "aliases": ["para kit"]},
        ],
    },
}

_SONIDO_CONTEXT = {
    "active_context": "General",
    "context_profiles": {"General": [
        {"term": "Qwen", "aliases": ["cuentres"], "sonido": True},
        {"term": "GitHub", "aliases": ["hit hub"], "sonido": True},
        {"term": "OpenAI", "aliases": [], "sonido": True},
    ]},
}

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

_WC_WAY = [("El", 0.99, 0, 1), ("Way", 0.55, 1, 2), ("fall", 0.97, 2, 3),
           ("por", 0.99, 3, 4), ("el", 1.0, 4, 5), ("driver", 0.96, 5, 6)]
_WC_SANO = [("Ese", 0.9, 0, 1), ("wey", 0.6, 1, 2), ("es", 0.99, 2, 3),
            ("mi", 0.99, 3, 4), ("amigo", 0.97, 4, 5)]


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
    return _FakeResponse(json.dumps({
        "choices": [{"message": {"content": text}}],
    }).encode())


class ConfigDefaultsTests(unittest.TestCase):
    def test_defaults_and_env_override(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DICTADO_LLM_URL", None)
            self.addCleanup(os.environ.pop, "DICTADO_LLM_URL", None)
            c = config.load()
            self.assertEqual(c.get("llm_url", ""), "")
            self.assertIs(c.get("sound"), False)
            self.assertEqual(c.get("lang"), "es")
            self.assertEqual(c.get("threads"), 4)
            self.assertEqual(config.DEFAULTS.get("overlay_style"), "orbital")
            with patch.dict(os.environ, {"DICTADO_LLM_URL": "http://127.0.0.1:8080"}):
                self.assertEqual(config.load()["llm_url"], "http://127.0.0.1:8080")


class LlmPolishTests(unittest.TestCase):
    def test_disabled_pipeline_returns_identical(self):
        self.assertEqual(llm.maybe_polish("hola mundo", {"llm_url": ""}), "hola mundo")
        self.assertEqual(
            llm.maybe_polish("hola mundo", {"llm_url": "http://127.0.0.1:9"}),
            "hola mundo")

    def test_high_confidence_skips_network(self):
        with patch("urllib.request.urlopen") as urlopen:
            self.assertEqual(
                llm.maybe_polish("hola mundo", {"llm_url": "http://127.0.0.1:8080"}, conf=0.95),
                "hola mundo")
            urlopen.assert_not_called()

    def test_low_confidence_falls_back_to_local(self):
        with patch("urllib.request.urlopen", side_effect=OSError("caido")):
            self.assertEqual(
                llm.maybe_polish("hola mundo", {"llm_url": "http://127.0.0.1:8080"}, conf=0.5),
                "hola mundo")

    def test_restore_openers(self):
        self.assertEqual(llm.restore_openers("que hora es?"), "¿que hora es?")
        self.assertEqual(llm.restore_openers("cómo estás?"), "¿cómo estás?")
        self.assertEqual(llm.restore_openers("¿qué hora es?"), "¿qué hora es?")
        self.assertEqual(llm.restore_openers("que bueno."), "que bueno.")
        self.assertEqual(llm.restore_openers("que hora es"), "que hora es")
        self.assertEqual(llm.restore_openers("qué bueno!"), "qué bueno!")
        self.assertEqual(llm.restore_openers("hola. dónde estás?"),
                         "hola. ¿dónde estás?")

    def test_llm_response_accepts_punctuation_only(self):
        with patch("urllib.request.urlopen", return_value=_llm_response("¿Cómo estás?")):
            self.assertEqual(llm.polish("como estas", "http://127.0.0.1:8080"), "¿Cómo estás?")
        with patch("urllib.request.urlopen", return_value=_llm_response("Hola, mundo y todo.")):
            self.assertEqual(llm.polish("Hola mundo", "http://127.0.0.1:8080"), "Hola mundo")

    def test_local_glossary_with_llm_disabled(self):
        self.assertEqual(llm.maybe_polish("in stand", _WORK_CONTEXT), "Instant")

    def test_llm_failure_keeps_locally_corrected_text(self):
        with patch("urllib.request.urlopen", side_effect=OSError("server unavailable")):
            self.assertEqual(
                llm.maybe_polish("instante", {**_WORK_CONTEXT, "llm_url": "http://127.0.0.1:8080"}),
                "Instant")


class ContextProfileTests(unittest.TestCase):
    def test_replaces_explicit_aliases_only(self):
        self.assertEqual(
            context.correct_aliases(
                "instante abre el instanteo; in stand y para kit.", _WORK_CONTEXT),
            "Instant abre el instanteo; Instant y Parakeet.")

    def test_exact_multiword_aliases_preserve_punctuation(self):
        self.assertEqual(context.correct_aliases("in, stand", _WORK_CONTEXT), "in, stand")

    def test_inactive_profile_does_not_bias(self):
        self.assertEqual(
            context.correct_aliases("instante", {**_WORK_CONTEXT, "active_context": "General"}),
            "instante")

    def test_profiles_persist_through_config(self):
        with tempfile.TemporaryDirectory() as temp:
            config_file = os.path.join(temp, "config.json")
            with patch("instant_app.config.config_path", return_value=config_file):
                config.save({
                    **config.DEFAULTS,
                    "active_context": "Trabajo",
                    "context_profiles": _WORK_CONTEXT["context_profiles"],
                })
                roundtrip = config.load()
                with patch.dict(os.environ, {"DICTADO_CONTEXT": "General"}):
                    selected = config.load()
                self.assertEqual(selected["active_context"], "General")
            self.assertEqual(roundtrip["active_context"], "Trabajo")
            self.assertEqual(roundtrip["context_profiles"]["Trabajo"][0]["term"], "Instant")

    def test_sound_key_groups_recognizer_confusions(self):
        self.assertEqual(context._sound_key("Qwen"), context._sound_key("cuen"))
        self.assertEqual(context._sound_key("GitHub"), context._sound_key("git hub"))

    def test_sound_matching_fixes_lost_letter_and_split_word(self):
        self.assertEqual(
            context.correct_aliases("decime si Quen puede hacerlo", _SONIDO_CONTEXT),
            "decime si Qwen puede hacerlo")
        self.assertEqual(
            context.correct_aliases("la velocidad con O en Pi y Pi", _SONIDO_CONTEXT),
            "la velocidad con OpenAI y Pi")

    def test_listed_alias_still_works_with_sound_on(self):
        self.assertEqual(
            context.correct_aliases("teniendo Cuentres ASR", _SONIDO_CONTEXT),
            "teniendo Qwen ASR")

    def test_sound_matching_leaves_ordinary_spanish_alone(self):
        text = "Preguntale a quien quieras, para que esto funcione y para que sirva."
        self.assertEqual(context.correct_aliases(text, _SONIDO_CONTEXT), text)
        self.assertEqual(
            context.correct_aliases("Qwen y GitHub y OpenAI", _SONIDO_CONTEXT),
            "Qwen y GitHub y OpenAI")

    def test_sound_off_means_no_guessing(self):
        ctx = {"context_profiles": {"General": [
            {"term": "Qwen", "aliases": [], "sonido": False}]}}
        self.assertEqual(context.correct_aliases("decime si Quen puede", ctx),
                         "decime si Quen puede")

    def test_editor_marks_sound_terms_and_round_trips(self):
        editor = context.editor_text(context.parse_editor("~Qwen\tcuen | quen\nParakeet\tpara kit"))
        self.assertTrue(editor.startswith("~Qwen\t"))
        self.assertIn("Parakeet\t", editor)
        self.assertIs(context.parse_editor(editor)[0]["sonido"], True)
        self.assertIs(context.parse_editor(editor)[1]["sonido"], False)

    def test_editor_keeps_term_without_aliases(self):
        self.assertEqual(context.parse_editor("~GitHub")[0],
                         {"term": "GitHub", "aliases": [], "sonido": True})


class BiasCorrectionTests(unittest.TestCase):
    def test_general_rescues_doubtful_and_keeps_safe(self):
        tech = "probando Instant con Parkit. Hice un comic del workflow."
        fixed = "probando Instant con Parakeet. Hice un commit del workflow."
        self.assertEqual(_bias.correct_biased(tech, conf=0.5), fixed)
        self.assertEqual(_bias.correct_biased(tech, conf=0.95), tech)
        self.assertEqual(_bias.correct_biased("hola mundo", conf=0.3), "hola mundo")
        self.assertEqual(_bias.correct_biased("", conf=0.1), "")
        self.assertEqual(
            _bias.correct_biased("para que funcione quien quiera", conf=0.2),
            "para que funcione quien quiera")

    def test_context_neighbor_confirms_or_protects(self):
        self.assertEqual(
            _bias.correct_biased("hice un comic del workflow", conf=0.5),
            "hice un commit del workflow")
        self.assertEqual(
            _bias.correct_biased("lei un comic de superheroes", conf=0.5),
            "lei un comic de superheroes")
        self.assertEqual(
            _bias.correct_biased("voy a comer con el equipo del workflow", conf=0.5),
            "voy a comer con el equipo del workflow")
        self.assertEqual(
            _bias.correct_biased("hay que comer antes del deploy", conf=0.5),
            "hay que comer antes del deploy")
        self.assertEqual(
            _bias.correct_biased("el wey fallo por el driver", conf=0.5),
            "el build fallo por el driver")
        self.assertEqual(
            _bias.correct_biased("ese wey es mi amigo", conf=0.5),
            "ese wey es mi amigo")
        self.assertEqual(
            _bias.correct_biased("subi el quemita hithub y corri el workflow", conf=0.5),
            "subi el commit GitHub y corri el workflow")

    def test_word_gate_rescues_with_neighbor(self):
        self.assertEqual(
            _bias.correct_biased("El Way fall por el driver.", conf=0.95, word_confs=_WC_WAY),
            "El build fall por el driver.")
        self.assertEqual(
            _bias.correct_biased("El Way fall por el driver.", conf=0.95),
            "El Way fall por el driver.")
        self.assertEqual(
            _bias.correct_biased("Ese wey es mi amigo.", conf=0.95, word_confs=_WC_SANO),
            "Ese wey es mi amigo.")

    def test_healthy_spanish_battery_untouched(self):
        bad = [s for s in _ADVERS
               if _bias.correct_biased(s, conf=0.3) != s
               or _bias.correct_biased(s, conf=0.95) != s]
        self.assertEqual(bad, [])

    def test_strong_rule_rescues_and_protects(self):
        self.assertEqual(
            _bias.correct_biased("El Will fallo en la manana por el driver.", conf=0.99),
            "El build fallo en la manana por el driver.")
        self.assertEqual(
            _bias.correct_biased("Will Walchar no molesta.", conf=0.99),
            "Will Walchar no molesta.")
        self.assertEqual(
            _bias.correct_biased("El Will fall otra vez por el driver viejo.", conf=0.99),
            "El build fall otra vez por el driver viejo.")
        self.assertEqual(
            _bias.correct_biased("Voy a hablar del testamento de Will.", conf=0.99),
            "Voy a hablar del testamento de Will.")
        self.assertEqual(
            _bias.correct_biased("El wild anda suelto en el bosque.", conf=0.99),
            "El wild anda suelto en el bosque.")
        self.assertEqual(
            _bias.correct_biased("The will to build something and the way it works.", conf=0.3),
            "The will to build something and the way it works.")


if __name__ == "__main__":
    unittest.main()
