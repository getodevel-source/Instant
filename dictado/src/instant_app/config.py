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
    "vad_model": "silero",
    "blank_penalty": 0.0,
    "llm_url": "",
    "llm_token": "",
    "active_context": "General",
    "context_profiles": {"General": []},
    "autostart": False,
    "overlay_style": "orbital",
    "update_mode": "notify",
    "update_last_check": 0,
}

INT_KEYS = ("threads",)
FLOAT_KEYS = ("max_seg", "blank_penalty")


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
            v = disk[k]
            if k in INT_KEYS and isinstance(v, bool):
                continue
            if k in INT_KEYS and not isinstance(v, int):
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    log.warning("ignoro %s=%r de la config (no es int)", k, disk[k])
                    continue
            if k in FLOAT_KEYS and isinstance(v, bool):
                continue
            if k in FLOAT_KEYS and not isinstance(v, (int, float)):
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    log.warning("ignoro %s=%r de la config (no es float)", k, disk[k])
                    continue
                v = float(v)
            cfg[k] = v
    # Env pisa archivo.
    env_map = {"DICTADO_MIC": "mic_hint", "DICTADO_KEY": "key",
               "DICTADO_THREADS": "threads", "DICTADO_SOUND": "sound",
               "DICTADO_MAX_SEG": "max_seg", "DICTADO_VAD": "vad_model",
               "DICTADO_BLANK": "blank_penalty",
               "DICTADO_LLM_URL": "llm_url",
               "DICTADO_LLM_TOKEN": "llm_token",
               "DICTADO_UPDATE": "update_mode",
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
                try:
                    cpu = os.cpu_count() or 4
                except Exception:
                    cpu = 4
                value = max(1, min(8, min(value, cpu)))
            cfg[k] = value
        elif k in FLOAT_KEYS:
            try:
                cfg[k] = float(v)
            except ValueError:
                log.warning("ignoro %s=%r (no es float)", env, v)
        elif k == "sound":
            cfg[k] = v.strip().lower() in ("1", "true", "yes", "y", "on", "si", "s")
        elif k == "autostart":
            cfg[k] = v.strip().lower() in ("1", "true", "yes", "y", "s", "si", "on")
        elif k == "mic_hint" and v.lstrip("-").isdigit():
            cfg["mic_index"] = int(v)
            cfg["mic_hint"] = ""
        elif k == "vad_model":
            v = v.strip().lower()
            cfg[k] = v if v in ("silero", "ten") else "silero"
        else:
            cfg[k] = v.lower() if k == "key" else v
    if cfg.get("update_mode") not in ("notify", "auto", "off"):
        cfg["update_mode"] = "notify"
    tok = cfg.get("llm_token", "")
    cfg["llm_token"] = tok if isinstance(tok, str) else ""
    if (os.environ.get("INSTANT_NO_UPDATE") or "").strip().lower() in (
            "1", "true", "yes", "y", "on", "si", "s"):
        cfg["update_mode"] = "off"
    try:
        cfg["blank_penalty"] = max(0.0, min(1.0, float(cfg.get("blank_penalty", 0.0))))
    except (TypeError, ValueError):
        cfg["blank_penalty"] = 0.0
    return cfg


def save(cfg):
    from instant_app.paths import ensure_private_dir, restrict_file

    path = config_path()
    directory = os.path.dirname(path) or "."
    ensure_private_dir(directory)
    temp_path = None
    slim = {k: cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}
    try:
        temp_path = _write_temp_json(path, slim)

        # Nota: config.json guarda `llm_url` en claro (URL sin token: el token
        # va en `DICTADO_LLM_TOKEN`/env o config `llm_token`, nunca en la URL).
        # Preserve the last valid config only after the replacement content
        # has been serialized successfully. El .bak se escribe atomico con
        if os.path.isfile(path):
            try:
                bak_tmp = _write_temp_json(path + ".bak", _read_json(path))
                os.replace(bak_tmp, path + ".bak")
                try:
                    fd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
                except OSError:
                    pass
                else:
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
            except Exception:
                log.warning("no pude respaldar la config anterior", exc_info=True)
        os.replace(temp_path, path)
        temp_path = None
        # Best-effort (no rompe Windows): solo el usuario lee la config.
        restrict_file(path + ".bak")
        restrict_file(path)
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
    log.info("config guardada en %s", path)
    return path
