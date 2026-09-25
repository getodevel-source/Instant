"""Descarga de modelos: Parakeet v3 int8 (~670MB) + Silero VAD (~1MB)."""
import logging
import os

PARAKEET_REPO = "csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
PARAKEET_FILES = ["encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"]
VAD_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"

log = logging.getLogger("instant")


def _names():
    # En disco sherpa espera encoder.int8.onnx etc; engine mapea esos nombres.
    return {"encoder.int8.onnx": "encoder.int8.onnx",
            "decoder.int8.onnx": "decoder.int8.onnx",
            "joiner.int8.onnx": "joiner.int8.onnx",
            "tokens.txt": "tokens.txt"}


def download_models(data_dir, progress=None):
    """Baja lo que falte. progress(path, done, total) opcional."""
    from huggingface_hub import snapshot_download

    import urllib.request

    from instant_app.paths import PARAKEET_SUBDIR, VAD_SUBDIR

    mdir = os.path.join(data_dir, PARAKEET_SUBDIR)
    os.makedirs(mdir, exist_ok=True)
    missing = [f for f in PARAKEET_FILES if not os.path.isfile(os.path.join(mdir, f))]
    if missing:
        log.info("descargando parakeet v3 int8 (~670MB)...")
        snapshot_download(PARAKEET_REPO, local_dir=mdir, local_dir_use_symlinks=False,
                          allow_patterns=PARAKEET_FILES)
    else:
        log.info("parakeet v3 int8 ya presente.")
    vdir = os.path.join(data_dir, VAD_SUBDIR)
    os.makedirs(vdir, exist_ok=True)
    vad = os.path.join(vdir, "silero_vad.onnx")
    if not os.path.isfile(vad):
        log.info("descargando silero VAD (~1MB)...")
        req = urllib.request.Request(VAD_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(vad, "wb") as f:
            f.write(r.read())
    else:
        log.info("silero VAD ya presente.")
    return data_dir


def check(data_dir):
    from instant_app.paths import model_paths

    p = model_paths(data_dir)
    return {k: os.path.isfile(v) for k, v in p.items()}
