"""Pulido opcional por endpoint; el vocabulario local no requiere conexión.

Si `llm_url` está vacío, solo se aplican las variantes exactas del vocabulario.
Si el servidor falla o modifica palabras, se conserva el texto local corregido.
"""
import logging
import os
import re
import unicodedata

log = logging.getLogger("instant")

DEFAULT_SYSTEM = ("Corrige solo ortografía, tildes y puntuación de este dictado en español. "
                  "Pon los signos de apertura ¿ y ¡ cuando correspondan. "
                  "No agregues, elimines, sustituyas ni reformules palabras. "
                  "Respeta el sentido, nombres, cifras y orden. "
                  "Usa el glosario solo para elegir la grafía de un término ya presente; "
                  "nunca insertes términos del glosario que no aparezcan en el texto. "
                  "Devuelve SOLO el texto corregido, sin comillas ni explicaciones.")


def polish(text, url, timeout=8.0, system=None, context_terms=""):
    """Corrige `text` via endpoint OpenAI-compatible de llama-server."""
    import json
    import urllib.request

    if not text or not text.strip():
        return text
    base = (url or "").rstrip("/")
    if base.endswith(("/chat/completions", "/completions", "/completion")):
        endpoint = base
    else:
        endpoint = base + "/v1/chat/completions"
    system = system or DEFAULT_SYSTEM
    if context_terms:
        system += "\nGlosario de grafias preferidas (referencia, no contenido):\n" + context_terms
    body = {
        "model": "local",
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": text}],
        "temperature": 0.0,
        "max_tokens": max(256, len(text.split()) * 4),
    }
    req = urllib.request.Request(
        endpoint, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    try:
        out = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            "respuesta LLM inesperada: falta choices[0].message.content") from None
    out = (out or "").strip().strip("\"“”")
    if out and _words(out) != _words(text):
        log.warning("LLM cambió palabras; conservo la transcripción local.")
        return text
    return out or text


def resolve_url(cfg=None, url=None):
    if url is not None:
        return url
    cfg = cfg or {}
    return cfg.get("llm_url", "") or os.environ.get("DICTADO_LLM_URL", "")


# Palabras-Q que abren pregunta en español. Conservador a proposito: sin
# prosodia no se distingue "¡qué bueno!" de "¿qué hora es?", asi que solo
# se restaura `¿` (nunca `¡`) y solo si la oracion ya cierra con `?`.
_QUESTION_OPENERS = frozenset(
    "qué que cómo como cuándo cuando dónde donde cuál cual cuáles cuales "
    "cuánto cuanto cuánta cuanta cuánto cuanto quién quien quiénes quienes "
    "por qué porqué adónde adonde".split())


def restore_openers(text):
    """Agrega `¿` faltante en preguntas obvias. Determinista, sin red.

    Si una oracion termina en `?` sin abrir con `¿` y empieza con palabra-Q
    (o "por que/porque" inicial), antepone `¿`. No toca `¡`: sin prosodia
    una exclamacion es indistinguible y el falso positivo hace mas daño.
    Nunca reescribe palabras, solo inserta el signo.
    """
    if not text or "?" not in text:
        return text
    parts = re.split(r"(?<=[.?!])(\s+)", text)
    out = []
    for part in parts:
        stripped = part.lstrip()
        if stripped.endswith("?") and not stripped.startswith("¿"):
            first = re.match(r"([^\W\d_]+)", stripped, flags=re.UNICODE)
            word = (first.group(1).casefold() if first else "")
            low = stripped.casefold()
            is_q = (word in _QUESTION_OPENERS
                    or low.startswith(("por que ", "porque ")))
            if is_q:
                indent = part[:len(part) - len(stripped)]
                part = indent + "¿" + stripped
        out.append(part)
    return "".join(out)


def maybe_polish(text, cfg=None, url=None, conf=1.0, min_conf=0.85):
    """Glosario local siempre; LLM solo en takes dudosos; apertures siempre.

    El LLM suelto suele subir WER en habla espontanea: solo se le consulta
    cuando la confianza del decode (`conf`) baja de `min_conf`. El texto
    seguro se pega directo (mas rapido, sin red). `restore_openers` es
    determinista y corre siempre: es el gap medido (VoxCore pone el `¿`
    en 4/8 preguntas).
    """
    from instant_app import context

    corrected = context.correct_aliases(text, cfg)
    corrected = restore_openers(corrected)
    target = resolve_url(cfg, url)
    if not target:
        return corrected
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = 1.0
    if conf >= min_conf:
        return corrected
    try:
        from instant_app import bias as _bias

        _terms = context.prompt_context(cfg)
        _gen = _bias.terms_for_prompt()
        terms = (_terms + "\n" + _gen) if _terms else _gen
        return polish(corrected, target, context_terms=terms)
    except Exception as e:
        log.warning("LLM off/fail (%s): sigo con texto corregido localmente.", e)
        return corrected

def _words(text):
    normalized = unicodedata.normalize("NFD", text.casefold())
    return re.findall(
        r"\w+", "".join(char for char in normalized
                        if unicodedata.category(char) != "Mn"))
