"""Descarga de modelos: Parakeet v3 int8 (~670MB) + Silero VAD (~1MB).

Cada archivo se verifica con su SHA-256 antes de darlo por bueno. Sin eso, una
descarga cortada o corrupta deja la aplicación fallando después, al cargar el
modelo, con un error que no explica nada. Los hashes de Parakeet son los que
publica Hugging Face en la metadata LFS del repositorio; el de Silero VAD se
calculó sobre el archivo oficial de la release de sherpa-onnx.
"""
import hashlib
import logging
import os
import time

PARAKEET_REPO = "csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
PARAKEET_FILES = ["encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"]
VAD_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"

# Nombre de archivo -> (bytes, sha256). Los tres ONNX son LFS en Hugging Face y
# su sha256 esta publicado; tokens.txt es pequeño y no esta en LFS, pero al ser
# el vocabulario del modelo conviene verificar su tamaño.
PARAKEET_SHA256 = {
    "encoder.int8.onnx": (652184281,
                          "acfc2b4456377e15d04f0243af540b7fe7c992f8d898d751cf134c3a55fd2247"),
    "decoder.int8.onnx": (11845275,
                          "179e50c43d1a9de79c8a24149a2f9bac6eb5981823f2a2ed88d655b24248db4e"),
    "joiner.int8.onnx": (6355277,
                         "3164c13fc2821009440d20fcb5fdc78bff28b4db2f8d0f0b329101719c0948b3"),
    "tokens.txt": (93939,
                   "d58544679ea4bc6ac563d1f545eb7d474bd6cfa467f0a6e2c1dc1c7d37e3c35d"),
}
VAD_SHA256 = (643854,
              "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6")

DOWNLOAD_ATTEMPTS = 3

log = logging.getLogger("instant")


class ModelIntegrityError(RuntimeError):
    """El archivo descargado no coincide con el hash esperado."""


def _names():
    # En disco sherpa espera encoder.int8.onnx etc; engine mapea esos nombres.
    return {"encoder.int8.onnx": "encoder.int8.onnx",
            "decoder.int8.onnx": "decoder.int8.onnx",
            "joiner.int8.onnx": "joiner.int8.onnx",
            "tokens.txt": "tokens.txt"}


def sha256_of(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def verify_file(path, expected):
    """(ok, motivo) comparando tamaño y sha256 contra `expected`."""
    size, digest = expected
    if not os.path.isfile(path):
        return False, "no existe"
    actual_size = os.path.getsize(path)
    if actual_size != size:
        return False, f"tamaño {actual_size} != {size}"
    actual = sha256_of(path)
    if actual != digest:
        return False, f"sha256 {actual[:16]}… != {digest[:16]}…"
    return True, ""


def missing_or_corrupt(directory, expectations):
    """Archivos que faltan o no verifican. Devuelve [(nombre, motivo)]."""
    problems = []
    for name, expected in expectations.items():
        ok, reason = verify_file(os.path.join(directory, name), expected)
        if not ok:
            problems.append((name, reason))
    return problems


def _download_vad(destination, report):
    """Baja Silero VAD a un temporal, verifica y recien ahi lo pone en su lugar.

    La escritura atomica evita dejar un .onnx a medias que despues parece
    valido por existir. Se reintenta porque es una descarga de red y el fallo
    tipico es transitorio.
    """
    import urllib.request

    temporary = destination + ".part"
    last_error = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            request = urllib.request.Request(
                VAD_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=120) as response, \
                    open(temporary, "wb") as handle:
                try:
                    total = int(response.headers.get("Content-Length") or 0) or None
                except (TypeError, ValueError):
                    total = None
                done = 0
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    report("vad", done, total)
            ok, reason = verify_file(temporary, VAD_SHA256)
            if not ok:
                raise ModelIntegrityError(f"silero VAD {reason}")
            os.replace(temporary, destination)
            return
        except Exception as error:  # red, hash o disco: se reintenta igual
            last_error = error
            log.warning("descarga de VAD fallo (intento %d/%d): %s",
                        attempt, DOWNLOAD_ATTEMPTS, error)
            if attempt < DOWNLOAD_ATTEMPTS:
                time.sleep(2 * attempt)
    if os.path.isfile(temporary):
        try:
            os.remove(temporary)
        except OSError:
            pass
    raise ModelIntegrityError(
        f"no se pudo descargar Silero VAD tras {DOWNLOAD_ATTEMPTS} intentos: {last_error}")


def download_models(data_dir, progress=None):
    """Baja Parakeet v3 int8 (~670MB) + Silero VAD (~1MB) juntos en un solo paso.

    progress(step, done, total): step = "parakeet"|"vad", done/total en bytes
    (total None si se desconoce). Sin callback usa log + print simple.

    Cada archivo se verifica con SHA-256. Un archivo presente pero corrupto se
    vuelve a descargar en lugar de darse por bueno.
    """
    from huggingface_hub import snapshot_download

    from instant_app.paths import PARAKEET_SUBDIR, VAD_SUBDIR

    def _report(step, done, total):
        if progress is not None:
            progress(step, done, total)
        elif total and total > (1 << 20):
            print(f"\r  {step}: {done / 1e6:.0f}/{total / 1e6:.0f} MB", end="", flush=True)

    mdir = os.path.join(data_dir, PARAKEET_SUBDIR)
    os.makedirs(mdir, exist_ok=True)
    problems = missing_or_corrupt(mdir, PARAKEET_SHA256)
    if problems:
        for name, reason in problems:
            log.warning("parakeet: %s %s", name, reason)
        if progress is None:
            print("  [1/2] Parakeet v3 int8 (~670MB)...")
        log.info("descargando parakeet v3 int8 (~670MB); faltan o no verifican %d archivo(s)",
                 len(problems))
        # Los que no verifican se borran para que la descarga los traiga de nuevo.
        for name, _reason in problems:
            target = os.path.join(mdir, name)
            if os.path.isfile(target):
                try:
                    os.remove(target)
                except OSError:
                    log.exception("no pude borrar %s para re-descargarlo", target)
        snapshot_download(PARAKEET_REPO, local_dir=mdir,
                          allow_patterns=PARAKEET_FILES)
        still = missing_or_corrupt(mdir, PARAKEET_SHA256)
        if still:
            detail = "; ".join(f"{name}: {reason}" for name, reason in still)
            raise ModelIntegrityError(
                f"los modelos descargados no verifican ({detail}). "
                f"Reintentá `instant setup`; si persiste, revisá la conexión o el disco.")
        _report("parakeet", 1, 1)
        if progress is None:
            print("  [1/2] Parakeet OK (verificado).")
    else:
        log.info("parakeet v3 int8 ya presente y verificado.")
        if progress is None:
            print("  [1/2] Parakeet ya presente y verificado.")
        _report("parakeet", 1, 1)

    vdir = os.path.join(data_dir, VAD_SUBDIR)
    os.makedirs(vdir, exist_ok=True)
    vad = os.path.join(vdir, "silero_vad.onnx")
    ok, reason = verify_file(vad, VAD_SHA256)
    if not ok:
        if progress is None:
            print("  [2/2] Silero VAD (~1MB)...")
        log.info("descargando silero VAD (~1MB); el actual %s", reason)
        _download_vad(vad, _report)
        if progress is None:
            print("  [2/2] Silero VAD OK (verificado).")
    else:
        log.info("silero VAD ya presente y verificado.")
        if progress is None:
            print("  [2/2] Silero VAD ya presente y verificado.")
        _report("vad", 1, 1)
    return data_dir


def check(data_dir):
    from instant_app.paths import model_paths

    p = model_paths(data_dir)
    return {k: os.path.isfile(v) for k, v in p.items()}


def check_integrity(data_dir, parakeet=None, vad=None):
    """Estado por archivo: True si verifica, o el motivo si no.

    `check` responde si el archivo existe; esto responde si además sirve. Los
    hashes se pueden pasar para probar sin los 670 MB reales.
    """
    from instant_app.paths import PARAKEET_SUBDIR, VAD_SUBDIR

    parakeet = PARAKEET_SHA256 if parakeet is None else parakeet
    vad = VAD_SHA256 if vad is None else vad
    result = {}
    for name, expected in parakeet.items():
        ok, reason = verify_file(
            os.path.join(data_dir, PARAKEET_SUBDIR, name), expected)
        result[name] = True if ok else reason
    ok, reason = verify_file(os.path.join(data_dir, VAD_SUBDIR, "silero_vad.onnx"),
                             vad)
    result["silero_vad.onnx"] = True if ok else reason
    return result
