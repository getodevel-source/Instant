"""User-managed local vocabulary profiles for transcription correction."""
import re

DEFAULT_PROFILE = "General"
DEFAULT_PROFILES = {DEFAULT_PROFILE: []}


def profiles(config):
    """Return a sanitized copy of configured context profiles."""
    raw = (config or {}).get("context_profiles", DEFAULT_PROFILES)
    result = {}
    if isinstance(raw, dict):
        for name, items in raw.items():
            name = str(name).strip()
            if not name or not isinstance(items, list):
                continue
            cleaned = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                term = str(item.get("term", "")).strip()
                aliases = item.get("aliases", [])
                if not term or not isinstance(aliases, list):
                    continue
                aliases = list(dict.fromkeys(
                    alias for alias in (str(value).strip() for value in aliases)
                    if alias and alias.casefold() != term.casefold()))
                cleaned.append({"term": term, "aliases": aliases})
            result[name] = cleaned
    if not result:
        result = {DEFAULT_PROFILE: []}
    return result


def active_name(config):
    available = profiles(config)
    name = str((config or {}).get("active_context", DEFAULT_PROFILE)).strip()
    return name if name in available else DEFAULT_PROFILE if DEFAULT_PROFILE in available else next(iter(available))


def active_terms(config):
    available = profiles(config)
    return available[active_name(config)]


def parse_editor(text):
    """Parse `preferred spelling<TAB>heard variant|another variant` rows."""
    terms = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        term, separator, variants = line.partition("\t")
        term = term.strip()
        aliases = [value.strip() for value in variants.split("|") if value.strip()] if separator else []
        if term:
            terms.append({"term": term, "aliases": list(dict.fromkeys(aliases))})
    return terms


def editor_text(items):
    """Format profile rows for the settings editor."""
    return "\n".join(
        item["term"] + ("\t" + " | ".join(item["aliases"]) if item["aliases"] else "")
        for item in items)


def correct_aliases(text, config):
    """Replace only explicitly listed whole-word recognition variants."""
    if not text:
        return text
    replacements = {}
    for item in active_terms(config):
        for alias in item["aliases"]:
            replacements.setdefault(alias.casefold(), item["term"])
    if not replacements:
        return text
    aliases = sorted(replacements, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(a) for a in aliases) + r")(?!\w)", re.IGNORECASE)
    return pattern.sub(lambda match: replacements[match.group(0).casefold()], text)


def prompt_context(config):
    """Return a compact spelling reference for a local correction model."""
    rows = active_terms(config)
    if not rows:
        return ""
    return "\n".join(
        f"- {item['term']}" + (f" (si se reconoce como: {'; '.join(item['aliases'])})" if item["aliases"] else "")
        for item in rows)
