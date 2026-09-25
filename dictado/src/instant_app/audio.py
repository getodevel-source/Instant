"""Audio: lista de entradas, seleccion, probe y medidor de nivel (stdlib+TUI)."""
import logging
import time

log = logging.getLogger("instant")

SAMPLE_RATE = 16000
CHANNELS = 1


def list_inputs():
    """[(index, name, channels, default_rate)] solo dispositivos con entrada."""
    import sounddevice as sd

    out = []
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) > 0:
            out.append((i, d["name"], d["max_input_channels"],
                        d.get("default_samplerate", 0)))
    return out


def resolve_mic(mic_hint="", mic_index=None):
    """Indice sounddevice o None (= default del sistema)."""
    import sounddevice as sd

    if mic_index is not None:
        try:
            d = sd.query_devices(mic_index)
            if d["max_input_channels"] > 0:
                log.info("mic: [%d] %s (fijado por config)", mic_index, d["name"])
                return mic_index
            log.warning("mic_index %d sin entrada, busco por hint/default.", mic_index)
        except Exception:
            log.exception("mic_index %d invalido", mic_index)
    if mic_hint:
        for i, name, _ch, _r in list_inputs():
            if mic_hint.lower() in name.lower():
                log.info("mic: [%d] %s", i, name)
                return i
        log.warning("mic '%s' no encontrado, uso default. Entradas:", mic_hint)
        for i, name, _ch, _r in list_inputs():
            log.warning("  [%d] %s", i, name)
        return None
    try:
        log.info("mic: default del sistema (%s)", sd.default.device)
    except Exception:
        pass
    return None


def probe(device, seconds=0.3):
    """Abre/cierra el mic: falla rapido si esta en uso exclusivo."""
    import sounddevice as sd

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype="float32", device=device):
            time.sleep(seconds)
        log.info("mic probe OK.")
        return True
    except Exception:
        log.exception("mic probe FAIL (en uso exclusivo o formato no soportado)")
        return False


def peak_meter(device, seconds=3.0, width=40):
    """Medidor de nivel para la TUI. Habla y mira las barras. Devuelve pico max."""
    import numpy as np
    import sounddevice as sd

    print(f"  Midiendo {seconds:.0f}s... habla ahora!")
    peak_max = 0.0
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype="float32", device=device, blocksize=1600) as stream:
            t0 = time.time()
            while time.time() - t0 < seconds:
                data, _overflow = stream.read(1600)
                peak = float(np.max(np.abs(data))) if data.size else 0.0
                peak_max = max(peak_max, peak)
                bars = int(min(1.0, peak * 8) * width)
                print(f"\r  [{'#' * bars}{' ' * (width - bars)}] {peak:.3f}", end="", flush=True)
        print(f"\n  pico maximo: {peak_max:.3f} "
              f"({'OK hay senal' if peak_max > 0.005 else 'SILENCIO: revisa mic/volume'})")
    except Exception:
        log.exception("medidor fail")
    return peak_max
