"""Pulido opcional por endpoint; el vocabulario local no requiere conexión.

Si `llm_url` está vacío, solo se aplican las variantes exactas del vocabulario.
Si el servidor falla o modifica palabras, se conserva el texto local corregido.

Seguridad: `http://` en claro solo se permite contra loopback (localhost,
127.* o ::1); cualquier otro `http://` se rechaza con un error accionable
(pasá a `https://` o usá un túnel local). El token (`llm_token` en config o
`DICTADO_LLM_TOKEN`) viaja en `Authorization: Bearer` y nunca se loguea.
"""
import ipaddress
import logging
import os
import re
import unicodedata
from urllib.parse import urlsplit

log = logging.getLogger("instant")

# Hosts donde el claro es aceptable: solo esta máquina (nunca sale a la red).
_LOOPBACK_NAMES = frozenset({"localhost"})


def _is_loopback_host(host):
    """True si `host` es loopback (nombre o IP). Sin DNS: lo que no se puede
    clasificar con certeza, no es loopback."""
    if not host:
        return False
    name = host.strip().strip("[]").lower().rstrip(".")
    if name in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def check_url(url):
    """Valida el endpoint LLM. Devuelve la URL normalizada o lanza ValueError
    accionable. `http://` no-loopback se bloquea (usá `https://`)."""
    target = (url or "").strip()
    if not target:
        return ""
    try:
        parsed = urlsplit(target)
    except ValueError as exc:
        raise ValueError(f"URL del LLM no válida ({exc}); "
                         "usá http://localhost:8080 o https://…") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL del LLM no válida: usá http(s)://host… "
                         "o dejá el campo vacío para no usar red.")
    if parsed.scheme == "http" and not _is_loopback_host(parsed.hostname):
        raise ValueError(
            f"el LLM en http://{parsed.hostname} viaja en claro por la red: "
            "usá https:// o un endpoint local (http://localhost:… o http://127.0.0.1:…).")
    return target


def resolve_token(cfg=None):
    """Token Bearer del LLM (config `llm_token` o env `DICTADO_LLM_TOKEN`).
    Vacío = sin auth. Nunca se loguea ni se incluye en mensajes de error."""
    cfg = cfg or {}
    return (cfg.get("llm_token", "")
            or os.environ.get("DICTADO_LLM_TOKEN", ""))

DEFAULT_SYSTEM = ("Corrige solo ortografía, tildes y puntuación de este dictado en español. "
                  "Pon los signos de apertura ¿ y ¡ cuando correspondan. "
                  "No agregues, elimines, sustituyas ni reformules palabras. "
                  "Respeta el sentido, nombres, cifras y orden. "
                  "Usa el glosario solo para elegir la grafía de un término ya presente; "
                  "nunca insertes términos del glosario que no aparezcan en el texto. "
                  "Devuelve SOLO el texto corregido, sin comillas ni explicaciones.")


def polish(text, url, timeout=8.0, system=None, context_terms="", token=None,
           cfg=None):
    """Corrige `text` via endpoint OpenAI-compatible de llama-server."""
    import json
    import urllib.request

    if not text or not text.strip():
        return text
    # Falla rápido y accionable: un http:// no-loopback no sale a la red.
    base = check_url(url).rstrip("/")
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
    headers = {"Content-Type": "application/json"}
    bearer = token if token is not None else resolve_token(cfg)
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    req = urllib.request.Request(
        endpoint, data=json.dumps(body).encode("utf-8"),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    try:
        out = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            "respuesta LLM inesperada: falta choices[0].message.content") from None
    out = (out or "").strip().strip("\"'“”‘’")
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
    "adónde adonde porqué porque".split())
_POR_QUE_RE = re.compile(r"por\s+que\s+", flags=re.UNICODE)


def restore_openers(text):
    """Agrega `¿` faltante en preguntas obvias. Determinista, sin red.

    Si una oracion termina en `?` sin abrir con `¿` y empieza con palabra-Q
    (o "por que/porque/por-que" inicial como compuesto), antepone `¿`.
    "Por" suelto NO abre ("por favor, pasame eso?" queda intacto).
    No toca `¡`: sin prosodia una exclamacion es indistinguible y el
    falso positivo hace mas daño. Nunca reescribe palabras.
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
                    or low.startswith(("porque ", "por-que "))
                    or _POR_QUE_RE.match(low) is not None)
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
        return polish(corrected, target, context_terms=terms, cfg=cfg)
    except Exception as exc:
        # Clase del error, nunca la URL ni el cuerpo: la URL puede llevar
        # token en query y el texto dictado no va al log.
        log.warning("LLM off/fail (%s): sigo con texto corregido localmente.",
                    type(exc).__name__)
        return corrected

def _words(text):
    normalized = unicodedata.normalize("NFD", text.casefold())
    return re.findall(
        r"\w+", "".join(char for char in normalized
                        if unicodedata.category(char) != "Mn"))
