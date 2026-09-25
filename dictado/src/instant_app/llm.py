"""Pulido opcional via llama-server local (opt-in, apagado por defecto).

Si `llm_url` (config) o `DICTADO_LLM_URL` (env) esta vacio -> no hace nada.
Si hay servidor pero falla -> devuelve el texto crudo (pipeline identico).
Solo stdlib, sin dependencias nuevas. NUNCA requiere red ni nube.
"""
import logging
import os

log = logging.getLogger("instant")

DEFAULT_SYSTEM = ("Corrige solo ortografia, tildes y puntuacion de este dictado en español. "
                  "No cambies palabras, nombres ni el sentido. "
                  "Devuelve SOLO el texto corregido, sin comillas ni explicaciones.")


def polish(text, url, timeout=15.0, system=None):
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
    body = {
        "model": "local",
        "messages": [{"role": "system", "content": system or DEFAULT_SYSTEM},
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
    return out or text


def resolve_url(cfg=None, url=None):
    if url is not None:
        return url
    cfg = cfg or {}
    return cfg.get("llm_url", "") or os.environ.get("DICTADO_LLM_URL", "")


def maybe_polish(text, cfg=None, url=None):
    """Texto corregido si hay LLM configurado; si no, el mismo texto."""
    target = resolve_url(cfg, url)
    if not target:
        return text
    try:
        return polish(text, target)
    except Exception as e:
        log.warning("LLM off/fail (%s): sigo con texto crudo.", e)
        return text
