"""Rutas: raiz de la app, datos por SO, resolucion del dir de modelos."""
import os
import sys

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PARAKEET_SUBDIR = "parakeet-v3-int8"
QWEN3_ASR_SUBDIR = "qwen3-asr-0.6b-int8-2026-03-25"
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
    """DICTADO_DATA > cwd/models > frozen checkout models > user data."""
    env = os.environ.get("DICTADO_DATA")
    if env:
        return env
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
    }


def qwen3_asr_paths(data_dir=None):
    """Prefer the active model directory, then the user-data Qwen trial model."""
    roots = [data_dir or resolve_data_dir()]
    user = user_data_dir()
    if user not in roots:
        roots.append(user)

    def paths(root):
        model_dir = os.path.join(root, QWEN3_ASR_SUBDIR)
        return {
            "conv_frontend": os.path.join(model_dir, "conv_frontend.onnx"),
            "encoder": os.path.join(model_dir, "encoder.int8.onnx"),
            "decoder": os.path.join(model_dir, "decoder.int8.onnx"),
            "tokenizer": os.path.join(model_dir, "tokenizer"),
        }

    def complete(candidate):
        required = ("conv_frontend", "encoder", "decoder")
        tokenizer = candidate["tokenizer"]
        return (all(os.path.isfile(candidate[name]) for name in required)
                and all(os.path.isfile(os.path.join(tokenizer, name))
                        for name in ("tokenizer_config.json", "vocab.json", "merges.txt")))

    for root in roots:
        candidate = paths(root)
        if complete(candidate):
            return candidate
    return paths(roots[0])
