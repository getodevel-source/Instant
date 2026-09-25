"""STT: Silero VAD (frases) + Parakeet v3 int8 offline por segmento. CPU-only."""
import concurrent.futures
import logging
import os
import re
import threading
import time

import numpy as np

from instant_app.paths import model_paths

log = logging.getLogger("instant")

SAMPLE_RATE = 16000
SILENCE_PEAK = 0.005


def join_texts(texts):
    """Une textos de segmentos: filtra vacios, pega puntuacion, colapsa espacios."""
    parts = [t.strip() for t in texts if t and t.strip()]
    s = " ".join(parts)
    s = re.sub(r"\s+([,.;:!?%)\]])", r"\1", s)
    s = re.sub(r"([(¿¡])\s+", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def merge_short_bounds(bounds, min_len=1.0, max_gap=1.0):
    """Une un segmento corto (<min_len) con su vecino si el hueco <= max_gap.

    Evita decodificar palabras sueltas sin contexto (pierden precision).
    `bounds`: [(t0, t1)] en segundos. Devuelve lista nueva.
    """
    bs = [(float(s), float(e)) for s, e in bounds]
    if len(bs) < 2:
        return bs
    out = [bs[0]]
    for s, e in bs[1:]:
        ps, pe = out[-1]
        if (s - pe) <= max_gap and ((pe - ps) < min_len or (e - s) < min_len):
            out[-1] = (ps, e)
        else:
            out.append((s, e))
    return out


class Engine:
    def __init__(self, data_dir=None, threads=4, max_seg=20.0,
                 vad_sil=0.5, vad_pad=0.2, min_dur=0.4):
        self.paths = model_paths(data_dir)
        self.threads = threads
        self.max_seg = max_seg
        self.vad_sil = vad_sil
        self.vad_pad = vad_pad
        self.min_dur = min_dur
        self._rec = None
        self._lock = threading.Lock()

    def recognizer(self):
        with self._lock:
            if self._rec is None:
                import sherpa_onnx

                p = self.paths
                for k in ("encoder", "decoder", "joiner", "tokens"):
                    if not os.path.isfile(p[k]):
                        raise FileNotFoundError(f"modelo parakeet incompleto, falta: {p[k]} "
                                                f"(corre `instant setup`)")
                log.info("cargando parakeet v3 int8 threads=%d ...", self.threads)
                t0 = time.time()
                self._rec = sherpa_onnx.OfflineRecognizer.from_transducer(
                    encoder=p["encoder"], decoder=p["decoder"], joiner=p["joiner"],
                    tokens=p["tokens"], num_threads=self.threads,
                    decoding_method="greedy_search",
                    model_type="nemo_transducer", provider="cpu", debug=False)
                log.info("modelo listo en %.1fs. GPU intacta (provider=cpu).", time.time() - t0)
                try:
                    s = self._rec.create_stream()
                    s.accept_waveform(SAMPLE_RATE, np.zeros(SAMPLE_RATE, dtype=np.float32))
                    self._rec.decode_stream(s)
                    log.info("warmup ok.")
                except Exception as e:
                    log.warning("warmup fail (no bloqueante): %s", e)
            return self._rec

    def vad(self):
        import sherpa_onnx

        if not os.path.isfile(self.paths["vad"]):
            raise FileNotFoundError(f"falta VAD: {self.paths['vad']} (corre `instant setup`)")
        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = self.paths["vad"]
        cfg.silero_vad.threshold = 0.5
        cfg.silero_vad.min_silence_duration = self.vad_sil
        cfg.silero_vad.min_speech_duration = 0.25
        cfg.silero_vad.window_size = 512
        cfg.sample_rate = SAMPLE_RATE
        return sherpa_onnx.VadModel.create(cfg)

    def segment(self, audio):
        """Corta audio en frases por VAD. Devuelve [(t0, t1)] en segundos."""
        wav = np.ascontiguousarray(np.asarray(audio).flatten(), dtype=np.float32)
        vad = self.vad()
        ws = vad.window_size()
        min_sil_w = max(1, int(self.vad_sil * SAMPLE_RATE / ws))
        speeches = []
        for i in range(0, len(wav) - ws + 1, ws):
            try:
                speeches.append(bool(vad.is_speech(wav[i:i + ws])))
            except Exception:
                log.exception("VAD window fail en %d", i)
                speeches.append(False)
        segs, start, sil = [], None, 0
        for i, sp in enumerate(speeches):
            if sp:
                if start is None:
                    start = i * ws
                sil = 0
            elif start is not None:
                sil += 1
                if sil >= min_sil_w:
                    segs.append((start, min(len(wav), i * ws)))
                    start, sil = None, 0
        if start is not None:
            segs.append((start, len(wav)))
        out = []
        for s, e in segs:
            while (e - s) / SAMPLE_RATE > self.max_seg:
                mid = (s + e) // 2
                w = SAMPLE_RATE
                lo, hi = max(s, mid - w), min(e, mid + w)
                if hi - lo < 1600:
                    cut = mid
                else:
                    frame = 1600
                    ergy = np.array([np.abs(wav[j:j + frame]).mean()
                                     for j in range(lo, hi - frame, frame)])
                    cut = lo + int(np.argmin(ergy)) * frame if len(ergy) else mid
                cut = max(s + SAMPLE_RATE, min(e - SAMPLE_RATE, cut))
                out.append((s, cut))
                s = cut
            out.append((s, e))
        res = []
        for s, e in out:
            s = max(0, int(s - self.vad_pad * SAMPLE_RATE))
            e = min(len(wav), int(e + self.vad_pad * SAMPLE_RATE))
            if (e - s) / SAMPLE_RATE >= 0.3:
                res.append((s / SAMPLE_RATE, e / SAMPLE_RATE))
        if not res and len(wav) / SAMPLE_RATE >= self.min_dur:
            peak = float(np.max(np.abs(wav))) if wav.size else 0.0
            if peak >= SILENCE_PEAK:
                log.warning("VAD no corto nada (habla continua?), todo junto %.1fs.",
                            len(wav) / SAMPLE_RATE)
                res = [(0.0, min(len(wav) / SAMPLE_RATE, 120.0))]
        return res

    def _one(self, args):
        idx, wav = args
        rec = self.recognizer()
        s = rec.create_stream()
        s.accept_waveform(SAMPLE_RATE, np.ascontiguousarray(wav, dtype=np.float32))
        rec.decode_stream(s)
        return idx, (s.result.text or "").strip()

    def transcribe(self, audio):
        """VAD + Parakeet por segmento en paralelo. Devuelve texto unido."""
        wav = np.ascontiguousarray(np.asarray(audio).flatten(), dtype=np.float32)
        dur = len(wav) / SAMPLE_RATE
        peak = float(np.max(np.abs(wav))) if wav.size else 0.0
        log.info("audio %.1fs pico=%.4f, segmentando...", dur, peak)
        t0 = time.time()
        bounds = merge_short_bounds(self.segment(wav))
        log.info("%d segmentos en %.2fs.", len(bounds), time.time() - t0)
        if not bounds:
            return ""
        chunks = [(i, wav[int(s * SAMPLE_RATE):int(e * SAMPLE_RATE)])
                  for i, (s, e) in enumerate(bounds)]
        t0 = time.time()
        texts = [""] * len(chunks)
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(self.threads, len(chunks))) as ex:
            for idx, text in ex.map(self._one, chunks):
                texts[idx] = (text or "").strip()
                log.info("seg %d/%d: %s", idx + 1, len(chunks), texts[idx][:80])
        log.info("decode %d segs en %.2fs.", len(chunks), time.time() - t0)
        return join_texts(texts)
