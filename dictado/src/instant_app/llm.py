"""Pulido local opcional; los reemplazos explícitos del glosario no requieren LLM.

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


def polish(text, url, timeout=15.0, system=None, context_terms=""):
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
    except Exception:
        raise RuntimeError(f"respuesta LLM inesperada: {str(data)[:120]}")
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


def maybe_polish(text, cfg=None, url=None):
    """Apply explicit local glossary replacements and optionally polish text."""
    from instant_app import context

    corrected = context.correct_aliases(text, cfg)
    target = resolve_url(cfg, url)
    if not target:
        return corrected
    try:
        return polish(corrected, target, context_terms=context.prompt_context(cfg))
    except Exception as e:
        log.warning("LLM off/fail (%s): sigo con texto corregido localmente.", e)
        return corrected

def _words(text):
    normalized = unicodedata.normalize("NFD", text.casefold())
    return re.findall(
        r"\w+", "".join(char for char in normalized
                        if unicodedata.category(char) != "Mn"))
