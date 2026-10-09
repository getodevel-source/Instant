"""STT: Silero VAD (frases) + Parakeet v3 int8 offline por segmento. CPU-only."""
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


def merge_short_bounds(bounds, min_len=1.5, max_gap=1.0):
    """Une un segmento corto (<min_len) con su vecino si el hueco <= max_gap.

    Evita decodificar palabras sueltas sin contexto (pierden precision).
    min_len 1.5s (antes 1.0s): los arranques de 1-1.5s sin contexto izquierdo
    son los que mas colapsan a blank en el transducer.
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


def _fit_level(wav):
    """Sube chunks debiles a un RMS nominal (solo boost, nunca recorta).

    Hablar bajito o lejos cambiaba la hipotesis aunque al oido sonara igual.
    Con voz presente (pico >= SILENCE_PEAK) y RMS < 0.03, aplica ganancia
    hasta RMS 0.06 (tope 8x). Devuelve (wav, ganancia).
    """
    if wav.size == 0:
        return wav, 1.0
    peak = float(np.max(np.abs(wav)))
    if peak < SILENCE_PEAK:
        return wav, 1.0
    rms = float(np.sqrt(np.mean(np.square(wav, dtype=np.float64))))
    if rms >= 0.03 or rms < 1e-6:
        return wav, 1.0
    gain = min(8.0, 0.06 / rms)
    if gain <= 1.0:
        return wav, 1.0
    return np.clip(wav * gain, -1.0, 1.0).astype(np.float32), gain


class Engine:
    # Tope del reintento total: decodificar hasta 120s de audio duplicaba
    # el pico de CPU/RAM justo en el peor caso (audio largo/ruidoso).
    FULL_RETRY_MAX_SECONDS = 30.0
    # Limites defensivos de hilos ONNX intra-op.
    MIN_THREADS = 1
    MAX_THREADS = 8

    def __init__(self, data_dir=None, threads=4, max_seg=20.0,
                 vad_sil=0.5, vad_pad=0.3, min_dur=0.4, save_wavs_dir=None):
        import os as _os
        cpu = _os.cpu_count() or 4
        try:
            threads = int(threads)
        except (TypeError, ValueError):
            threads = 4
        threads = max(self.MIN_THREADS, min(self.MAX_THREADS, min(threads, cpu)))
        self.paths = model_paths(data_dir)
        self.threads = threads
        self.max_seg = max_seg
        self.vad_sil = vad_sil
        self.vad_pad = vad_pad
        self.min_dur = min_dur
        # Opt-in (DICTADO_SAVE_WAVS): guarda los wavs que el modelo deja
        # vacios, para medir con voz real en vez de suponer.
        self.save_wavs_dir = save_wavs_dir
        self._rec = None
        self._vad = None
        self._lock = threading.Lock()
        # La inferencia sobre el recognizer compartido se serializa (_one):
        # con decodificaciones concurrentes el transducer colapsaba a blank de
        # forma intermitente (~6% de sesiones). RTF ~0.05x deja margen.
        self._decode_lock = threading.Lock()

    def unload(self):
        """Libera el recognizer (~670MB) y el VAD cacheado si existen."""
        with self._lock:
            self._rec = None
            self._vad = None

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
        # Reutiliza una instancia: antes se creaba un VadModel nativo en
        # CADA transcribe() sin liberarlo (leak nativo acumulativo).
        with self._lock:
            if self._vad is not None:
                return self._vad
        import sherpa_onnx

        if not os.path.isfile(self.paths["vad"]):
            raise FileNotFoundError(f"falta VAD: {self.paths['vad']} (corre `instant setup`)")
        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = self.paths["vad"]
        cfg.silero_vad.threshold = 0.5
        cfg.silero_vad.min_silence_duration = self.vad_sil
        # 0.20s (antes 0.25s): los ataques suaves de la primera palabra
        # quedaban marcados como no-voz y el onset se recortaba.
        cfg.silero_vad.min_speech_duration = 0.2
        cfg.silero_vad.window_size = 512
        cfg.sample_rate = SAMPLE_RATE
        inst = sherpa_onnx.VadModel.create(cfg)
        with self._lock:
            if self._vad is None:
                self._vad = inst
                return inst
            return self._vad

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
        # Serializa la inferencia: el recognizer es compartido y el decode
        # concurrente producia vacios intermitentes.
        with self._decode_lock:
            s = rec.create_stream()
            s.accept_waveform(SAMPLE_RATE, np.ascontiguousarray(wav, dtype=np.float32))
            rec.decode_stream(s)
            return idx, (s.result.text or "").strip()

    def _recover_empties(self, wav, peak, bounds, chunks, texts):
        """Reintento secuencial de segmentos vacios con contexto ampliado.

        El transducer colapsa a blank en chunks cortos o cortados a mitad de
        palabra aunque el pico sea bueno. Solo actua en la via de fallo: sin
        vacios no decodifica nada extra.
        """
        fixed = list(texts)
        for idx, text in enumerate(fixed):
            if text:
                continue
            s, e = bounds[idx]
            cpeak = float(np.max(np.abs(chunks[idx][1]))) if chunks[idx][1].size else 0.0
            cdur = len(chunks[idx][1]) / SAMPLE_RATE
            if cpeak < SILENCE_PEAK or cdur < 0.3:
                continue
            # Contexto +-1s: le devuelve al transducer el arranque que el
            # corte le saco (la causa del inicio recortado).
            rs = max(0.0, s - 1.0)
            re_ = min(len(wav) / SAMPLE_RATE, e + 1.0)
            rwav, rgain = _fit_level(wav[int(rs * SAMPLE_RATE):int(re_ * SAMPLE_RATE)])
            try:
                _, retry = self._one((-1, rwav))
                retry = (retry or "").strip()
            except Exception:
                log.exception("reintento seg %d fail", idx + 1)
                continue
            log.info("seg %d/%d reintento (%.1f-%.1fs pico=%.4f g=%.1f): %d caracteres",
                     idx + 1, len(chunks), rs, re_, cpeak, rgain, len(retry))
            if retry:
                fixed[idx] = retry
        if any(fixed):
            return fixed
        # Perdida total con audio fuerte: ultimo intento acotado (antes 120s:
        # duplicaba el pico de CPU/RAM justo en el peor caso).
        if peak >= SILENCE_PEAK and len(wav) / SAMPLE_RATE >= 0.3:
            capped = min(len(wav) / SAMPLE_RATE, self.FULL_RETRY_MAX_SECONDS)
            full = wav[:int(capped) * SAMPLE_RATE]
            try:
                _, retry = self._one((-1, full))
                retry = (retry or "").strip()
            except Exception:
                log.exception("reintento total fail")
                return fixed
            log.info("reintento total (%.1fs): %d caracteres",
                     len(full) / SAMPLE_RATE, len(retry))
            if retry:
                return [retry]
        return fixed

    def transcribe(self, audio):
        """VAD + Parakeet por segmento en serie. Devuelve texto unido."""
        wav = np.ascontiguousarray(np.asarray(audio).flatten(), dtype=np.float32)
        dur = len(wav) / SAMPLE_RATE
        peak = float(np.max(np.abs(wav))) if wav.size else 0.0
        log.info("audio %.1fs pico=%.4f, segmentando...", dur, peak)
        t0 = time.time()
        bounds = merge_short_bounds(self.segment(wav))
        log.info("%d segmentos en %.2fs: %s.", len(bounds), time.time() - t0,
                 ", ".join(f"{s:.2f}-{e:.2f}" for s, e in bounds))
        if not bounds:
            return ""
        chunks = []
        for i, (s, e) in enumerate(bounds):
            raw = wav[int(s * SAMPLE_RATE):int(e * SAMPLE_RATE)]
            normed, gain = _fit_level(raw)
            chunks.append((i, normed, gain))
            del raw
        t0 = time.time()
        # Decode SERIADO: el recognizer ya se serializaba con _decode_lock
        # (el decode concurrente colapsaba a blank) pero el ThreadPool
        # mantenia N hilos bloqueados reteniendo chunks mientras cada decode
        # usaba `threads` hilos ONNX -> pico NxM CPU-bound que congelaba el
        # SO. En serie el RTF es el mismo y el pico es 1xM.
        texts = [""] * len(chunks)
        for i, w, _g in chunks:
            idx, text = self._one((i, w))
            texts[idx] = (text or "").strip()
            cpeak = float(np.max(np.abs(chunks[idx][1]))) if chunks[idx][1].size else 0.0
            log.info("seg %d/%d (%.1fs pico=%.4f g=%.1f): %d caracteres", idx + 1, len(chunks),
                     len(chunks[idx][1]) / SAMPLE_RATE, cpeak, chunks[idx][2],
                     len(texts[idx]))
        log.info("decode %d segs en %.2fs.", len(chunks), time.time() - t0)
        texts = self._recover_empties(wav, peak, bounds, chunks, texts)
        if self.save_wavs_dir and not any(t.strip() for t in texts):
            self._dump_failure(wav, peak, dur, bounds)
        return join_texts(texts)

    def _dump_failure(self, wav, peak, dur, bounds):
        """Guarda el wav que el modelo dejo vacio + meta, sin tumbar nunca."""
        try:
            import datetime
            import wave

            os.makedirs(self.save_wavs_dir, exist_ok=True)
            wavs = sorted(
                (os.path.join(self.save_wavs_dir, f) for f in os.listdir(self.save_wavs_dir)
                 if f.endswith(".wav")),
                key=lambda p: os.path.getmtime(p))
            while len(wavs) >= 50:
                try:
                    os.remove(wavs.pop(0))
                except OSError:
                    break
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            base = os.path.join(self.save_wavs_dir, f"fallo-{stamp}")
            pcm = (np.clip(wav, -1.0, 1.0) * 32767).astype(np.int16)
            with wave.open(base + ".wav", "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SAMPLE_RATE)
                w.writeframes(pcm.tobytes())
            with open(base + ".txt", "w", encoding="utf-8") as f:
                f.write(f"dur={dur:.1f}s pico={peak:.4f} "
                        f"bounds={[(round(s, 2), round(e, 2)) for s, e in bounds]}\n")
            log.info("wav de fallo guardado en %s.", base + ".wav")
        except Exception:
            log.exception("no pude guardar wav de fallo")
