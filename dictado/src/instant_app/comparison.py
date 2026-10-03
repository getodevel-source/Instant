"""Compare local recognizers on one in-memory audio clip."""
import time

import numpy as np

from instant_app import context, models
from instant_app.engine import Engine, SAMPLE_RATE
from instant_app.paths import qwen3_asr_paths

RECORD_SECONDS = 15.0


def compare_models(audio, cfg, data_dir=None, progress=None):
    """Run Parakeet and Qwen on identical samples; return raw ASR and wall time."""
    wav = np.ascontiguousarray(np.asarray(audio, dtype=np.float32).reshape(-1))
    if not wav.size:
        raise ValueError("No hay audio capturado para comparar.")

    results = []
    if progress:
        progress("Transcribiendo con Parakeet…")
    started = time.perf_counter()
    engine = None
    try:
        engine = Engine(data_dir, threads=cfg.get("threads", 4),
                        max_seg=cfg.get("max_seg", 20.0))
        text = engine.transcribe(wav)
        results.append(("Parakeet v3", text, time.perf_counter() - started, ""))
    except Exception as error:
        results.append(("Parakeet v3", "", time.perf_counter() - started,
                        str(error)))
    finally:
        engine = None
    if progress:
        progress("Transcribiendo con Qwen3-ASR 0.6B…")
    started = time.perf_counter()
    try:
        missing = [name for name, ok in models.check_qwen3_asr(data_dir).items()
                   if not ok]
        if missing:
            raise FileNotFoundError(
                "Falta el modelo de prueba Qwen3-ASR: " + ", ".join(missing))
        import sherpa_onnx

        paths = qwen3_asr_paths(data_dir)
        hotwords = ",".join(
            item["term"].replace(",", " ")
            for item in context.active_terms(cfg))
        recognizer = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
            conv_frontend=paths["conv_frontend"],
            encoder=paths["encoder"],
            decoder=paths["decoder"],
            tokenizer=paths["tokenizer"],
            num_threads=cfg.get("threads", 4),
            sample_rate=SAMPLE_RATE,
            provider="cpu",
            hotwords=hotwords,
        )
        stream = recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, wav)
        recognizer.decode_stream(stream)
        results.append(("Qwen3-ASR 0.6B", (stream.result.text or "").strip(),
                        time.perf_counter() - started, ""))
    except Exception as error:
        results.append(("Qwen3-ASR 0.6B", "", time.perf_counter() - started,
                        str(error)))

    return results


def format_results(results):
    """Render comparison output without altering either model's transcript."""
    sections = []
    for name, text, elapsed, error in results:
        sections.append(f"{name} — {elapsed:.2f} s (carga + transcripción)")
        sections.append(error if error else (text or "(sin texto reconocido)"))
    return "\n\n".join(sections)
