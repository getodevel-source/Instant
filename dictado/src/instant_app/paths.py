"""Rutas: raiz de la app, datos por SO, resolucion del dir de modelos."""
import os
import sys

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PARAKEET_SUBDIR = "parakeet-v3-int8"
VAD_SUBDIR = "silero-vad"


def config_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "instant")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "instant")
    return os.path.join(os.path.expanduser("~"), ".config", "instant")


def user_data_dir():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(base, "instant", "models")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                            "instant", "models")
    xdg = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
    return os.path.join(xdg, "instant", "models")


def _has_models(d):
    return os.path.isfile(os.path.join(d, PARAKEET_SUBDIR, "encoder.int8.onnx"))


def resolve_data_dir():
    """DICTADO_DATA > ./models (dev) > user data dir. Solo lo usado, sin magia."""
    env = os.environ.get("DICTADO_DATA")
    if env:
        return env
    cwd_models = os.path.join(os.getcwd(), "models")
    if _has_models(cwd_models):
        return cwd_models
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
    }
