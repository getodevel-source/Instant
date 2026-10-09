"""Config JSON por usuario + override por env DICTADO_*."""
import json
import logging
import os
import tempfile

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
    "active_context": "General",
    "context_profiles": {"General": []},
    "autostart": False,
    "overlay_style": "orbital",
    "update_last_check": 0,
}

INT_KEYS = ("threads",)
FLOAT_KEYS = ("max_seg",)


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError("la raíz de la config no es un objeto JSON")
    return value


def _write_temp_json(path, value):
    directory = os.path.dirname(path) or "."
    fd, temp_path = tempfile.mkstemp(prefix=".config-", suffix=".tmp",
                                     dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        return temp_path
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _replace_json_atomically(path, value):
    temp_path = _write_temp_json(path, value)
    try:
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


def config_path():
    return os.path.join(config_dir(), "config.json")


def load():
    cfg = dict(DEFAULTS)
    path = config_path()
    try:
        disk = _read_json(path)
    except FileNotFoundError:
        disk = {}
    except Exception:
        log.exception("config corrupta; intento recuperar el respaldo")
        try:
            disk = _read_json(path + ".bak")
        except FileNotFoundError:
            disk = {}
        except Exception:
            log.exception("respaldo de config ausente o corrupto; uso defaults")
            disk = {}
        else:
            try:
                _replace_json_atomically(path, disk)
                log.warning("config recuperada desde el respaldo")
            except OSError:
                log.exception("leí el respaldo, pero no pude reparar la config")
    for k in DEFAULTS:
        if k in disk:
            cfg[k] = disk[k]
    # Env pisa archivo.
    env_map = {"DICTADO_MIC": "mic_hint", "DICTADO_KEY": "key",
               "DICTADO_THREADS": "threads", "DICTADO_SOUND": "sound",
               "DICTADO_MAX_SEG": "max_seg", "DICTADO_LLM_URL": "llm_url",
               "DICTADO_CONTEXT": "active_context",
               "DICTADO_AUTOSTART": "autostart",
               "DICTADO_OVERLAY": "overlay_style"}
    for env, k in env_map.items():
        v = os.environ.get(env)
        if v is None or v == "":
            continue
        if k in INT_KEYS:
            try:
                value = int(v)
            except ValueError:
                log.warning("ignoro %s=%r (no es int)", env, v)
                continue
            if k == "threads":
                import os as _os
                cpu = _os.cpu_count() or 4
                value = max(1, min(8, min(value, cpu)))
            cfg[k] = value
        elif k in FLOAT_KEYS:
            try:
                cfg[k] = float(v)
            except ValueError:
                log.warning("ignoro %s=%r (no es float)", env, v)
        elif k == "sound":
            cfg[k] = v == "1"
        elif k == "autostart":
            cfg[k] = v.strip().lower() in ("1", "true", "yes", "y", "s", "si", "on")
        elif k == "mic_hint" and v.lstrip("-").isdigit():
            cfg["mic_index"] = int(v)
            cfg["mic_hint"] = ""
        else:
            cfg[k] = v.lower() if k == "key" else v
    return cfg


def save(cfg):
    path = config_path()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    temp_path = None
    slim = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    try:
        temp_path = _write_temp_json(path, slim)

        # Preserve the last valid config only after the replacement content
        # has been serialized successfully.
        if os.path.isfile(path):
            try:
                import shutil
                shutil.copyfile(path, path + ".bak")
            except Exception:
                log.warning("no pude respaldar la config anterior", exc_info=True)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
    log.info("config guardada en %s", path)
    return path
