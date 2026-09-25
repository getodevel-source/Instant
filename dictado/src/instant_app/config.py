"""Config JSON por usuario + override por env DICTADO_*."""
import json
import logging
import os

from instant_app.paths import config_dir

log = logging.getLogger("instant")

DEFAULTS = {
    "mic_hint": "",
    "mic_index": None,
    "key": "f9",
    "lang": "es",
    "threads": 4,
    "sound": False,
    "max_seg": 20.0,
    "llm_url": "",
}

INT_KEYS = ("threads",)
FLOAT_KEYS = ("max_seg",)


def config_path():
    return os.path.join(config_dir(), "config.json")


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), encoding="utf-8") as f:
            disk = json.load(f)
        for k in DEFAULTS:
            if k in disk:
                cfg[k] = disk[k]
    except FileNotFoundError:
        pass
    except Exception:
        log.exception("config corrupta, uso defaults")
    # Env pisa archivo.
    env_map = {"DICTADO_MIC": "mic_hint", "DICTADO_KEY": "key",
               "DICTADO_THREADS": "threads", "DICTADO_SOUND": "sound",
               "DICTADO_MAX_SEG": "max_seg", "DICTADO_LLM_URL": "llm_url"}
    for env, k in env_map.items():
        v = os.environ.get(env)
        if v is None or v == "":
            continue
        if k in INT_KEYS:
            try:
                cfg[k] = int(v)
            except ValueError:
                log.warning("ignoro %s=%r (no es int)", env, v)
        elif k in FLOAT_KEYS:
            try:
                cfg[k] = float(v)
            except ValueError:
                log.warning("ignoro %s=%r (no es float)", env, v)
        elif k == "sound":
            cfg[k] = v == "1"
        elif k == "mic_hint" and v.lstrip("-").isdigit():
            cfg["mic_index"] = int(v)
            cfg["mic_hint"] = ""
        else:
            cfg[k] = v.lower() if k == "key" else v
    return cfg


def save(cfg):
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    slim = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2, ensure_ascii=False)
    log.info("config guardada en %s", path)
    return path
