"""Rutas: raiz de la app, datos por SO, resolucion del dir de modelos."""
import os
import sys


def _restrict(path, mode):
    """chmod best-effort: en Windows no hay bits POSIX (se ignora), en POSIX
    un fallo de permiso no puede romper el arranque ni el guardado."""
    if os.name == "nt":
        return
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def ensure_private_dir(path):
    """Crea `path` con 0o700 best-effort (config/datos solo del usuario).
    Idempotente: si ya existe, solo intenta restringir bits sin romper nada."""
    os.makedirs(path, mode=0o700, exist_ok=True)
    _restrict(path, 0o700)
    return path


def restrict_file(path):
    """chmod 0o600 best-effort para secretos/logs (config.json/.bak, pid,
    instant.log, wavs). Nunca lanza."""
    _restrict(path, 0o600)
    return path

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PARAKEET_SUBDIR = "parakeet-v3-int8"
VAD_SUBDIR = "silero-vad"


def config_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "instant")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "instant")
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and xdg.strip():
        return os.path.join(xdg.strip(), "instant")
    return os.path.join(os.path.expanduser("~"), ".config", "instant")


def user_data_dir():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(base, "instant", "models")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                            "instant", "models")
    xdg = os.environ.get("XDG_DATA_HOME")
    if not (xdg and xdg.strip()):
        xdg = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(xdg.strip(), "instant", "models")


def _has_models(d):
    return os.path.isfile(os.path.join(d, PARAKEET_SUBDIR, "encoder.int8.onnx"))


def resolve_data_dir():
    """DICTADO_DATA > cwd/models > frozen checkout models > user data."""
    env = os.environ.get("DICTADO_DATA")
    if env and env.strip():
        return os.path.expanduser(os.path.expandvars(env.strip()))
    cwd_models = os.path.join(os.getcwd(), "models")
    if _has_models(cwd_models):
        return cwd_models
    if getattr(sys, "frozen", False):
        executable_dir = os.path.dirname(sys.executable)
        checkout_models = os.path.join(os.path.dirname(executable_dir), "models")
        if _has_models(checkout_models):
            return checkout_models
    return user_data_dir()


def model_paths(data_dir=None):
    d = data_dir or resolve_data_dir()
    mdir = os.path.join(d, PARAKEET_SUBDIR)
    return {
        "encoder": os.path.join(mdir, "encoder.int8.onnx"),
        "decoder": os.path.join(mdir, "decoder.int8.onnx"),
        "joiner": os.path.join(mdir, "joiner.int8.onnx"),
        "tokens": os.path.join(mdir, "tokens.txt"),
        "vad": os.path.join(d, VAD_SUBDIR, "silero_vad.onnx"),
        "ten_vad": os.path.join(d, VAD_SUBDIR, "ten_vad.onnx"),
    }
