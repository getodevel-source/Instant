"""Daemon hold-to-talk: graba en RAM, al soltar VAD+Parakeet y pega. Cross-platform."""
import logging
import queue
import threading
import time

import numpy as np

from instant_app import audio, hotkey, llm, paste
from instant_app.engine import Engine, SAMPLE_RATE, SILENCE_PEAK
from instant_app.overlay import Overlay

log = logging.getLogger("instant")


class Daemon:
    def __init__(self, cfg, data_dir=None):
        self.cfg = cfg
        self.engine = Engine(data_dir,
                             threads=cfg.get("threads", 4),
                             max_seg=cfg.get("max_seg", 20.0))
        self.overlay = Overlay()
        self.mic = audio.resolve_mic(cfg.get("mic_hint", ""), cfg.get("mic_index"))
        self.hk = hotkey.create(cfg.get("key", "f9"))
        self.rec = {"sid": 0, "grabando": False, "frames": [], "t_start": 0.0,
                    "done": None, "busy": False}
        self.lock = threading.Lock()

    def beep(self, freq=880, ms=120):
        if not self.cfg.get("sound"):
            return
        try:
            import sys
            if sys.platform == "win32":
                import winsound
                winsound.Beep(freq, ms)
            else:
                print("\a", end="", flush=True)
        except Exception as e:
            log.warning("beep fail: %s", e)

    # ---- sesion ----
    def _record(self, sid, done):
        import sounddevice as sd

        q = queue.Queue()
        frames = []

        def cb(indata, frames_, t, status):
            if status:
                log.warning("audio status: %s", status)
            q.put(indata.copy())

        try:
            stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=audio.CHANNELS,
                                    dtype="float32", device=self.mic, callback=cb)
            stream.start()
        except Exception:
            log.exception("ERROR abriendo microfono")
            with self.lock:
                if self.rec["sid"] == sid:
                    self.rec["grabando"] = False
            self.overlay.hide()
            done.set()
            return
        key = self.cfg.get("key", "f9").upper()
        log.info("grabando sesion %d...", sid)
        self.overlay.show(f"Grabando... (suelta {key})", "#ff4444")
        self.beep(freq=880)
        last_sec = -1
        try:
            while True:
                try:
                    blk = q.get(timeout=0.1)
                except queue.Empty:
                    blk = None
                    with self.lock:
                        alive = self.rec["grabando"] and self.rec["sid"] == sid
                    if not alive and not frames:
                        break
                    if blk is None and frames:
                        with self.lock:
                            alive = self.rec["grabando"] and self.rec["sid"] == sid
                        if not alive:
                            break
                        continue
                    continue
                frames.append(blk)
                with self.lock:
                    alive = self.rec["grabando"] and self.rec["sid"] == sid
                n = sum(int(f.shape[0]) for f in frames)
                sec = n // SAMPLE_RATE
                if sec != last_sec:
                    last_sec = sec
                    self.overlay.show(f"Grabando... {sec}s (suelta {key})", "#ff4444")
                if not alive:
                    try:
                        while True:
                            frames.append(q.get_nowait())
                    except queue.Empty:
                        pass
                    break
        except Exception:
            log.exception("sesion %d fail en loop", sid)
        try:
            stream.stop()
            stream.close()
        except Exception:
            log.exception("cerrando stream audio")
        with self.lock:
            if self.rec["sid"] == sid:
                self.rec["frames"] = frames
        done.set()

    def _job(self, wav, dur, sid):
        self.overlay.show("Transcribiendo...", "#ffcc00")
        try:
            if dur < self.engine.min_dur:
                log.info("muy corto (<%.1fs), descarto.", self.engine.min_dur)
                return
            peak = float(np.max(np.abs(wav))) if wav.size else 0.0
            if peak < SILENCE_PEAK:
                log.info("silencio (pico %.4f), descarto sin inferencia.", peak)
                return
            t0 = time.time()
            text = self.engine.transcribe(wav)
            text = llm.maybe_polish(text, self.cfg)
            dt = time.time() - t0
            if not text:
                log.info("vacio tras %.1fs audio (%.2fs), nada que pegar.", dur, dt)
                return
            log.info("[%.1fs audio -> %.2fs, RTF=%.2fx] %s",
                     dur, dt, dt / max(dur, 0.1), text[:200])
            import instant_app.paste as _paste_mod
            _paste_mod.paste(text + " ")
        except Exception:
            log.exception("ERROR transcripcion sesion %d", sid)
        finally:
            self.overlay.hide()
            with self.lock:
                self.rec["busy"] = False
            self.beep(freq=440)

    def on_press(self):
        with self.lock:
            if self.rec["grabando"]:
                return
            if self.rec["busy"]:
                log.info("ocupado transcribiendo, ignoro.")
                return
            self.rec["sid"] += 1
            self.rec["grabando"] = True
            self.rec["frames"] = []
            self.rec["t_start"] = time.time()
            done = threading.Event()
            self.rec["done"] = done
            sid = self.rec["sid"]
        threading.Thread(target=self._record, args=(sid, done), daemon=True).start()

    def on_release(self):
        with self.lock:
            if not self.rec["grabando"]:
                return
            self.rec["grabando"] = False
            dur = time.time() - self.rec["t_start"]
            done = self.rec["done"]
            sid = self.rec["sid"]
        self.overlay.hide()
        if done is not None and not done.wait(timeout=10.0):
            log.warning("sesion %d no cerro mic en 10s, transcribo lo que hay.", sid)
        with self.lock:
            frames = self.rec["frames"]
            self.rec["frames"] = []
            self.rec["busy"] = True
        wav = np.concatenate(frames, axis=0).flatten() if frames else np.zeros(0, dtype=np.float32)
        log.info("soltado tras %.1fs, %d bloques -> VAD+Parakeet.", dur, len(frames))
        threading.Thread(target=self._job, args=(wav, dur, sid), daemon=True).start()

    def run(self):
        if not audio.probe(self.mic):
            log.warning("sigue sin default. `instant setup` para elegir mic.")
        self.engine.recognizer()
        self.engine.vad()
        key = self.cfg.get("key", "f9").upper()
        log.info("listo. Manten %s para dictar (60-120s), suelta para transcribir. Ctrl+C sale.", key)
        self.hk.start(self.on_press, self.on_release)
        try:
            while True:
                time.sleep(60)
                log.info("vivo, esperando %s...", key)
        except KeyboardInterrupt:
            self.overlay.hide()
            log.info("chau.")
        finally:
            try:
                self.hk.stop()
            except Exception:
                pass


def cmd_check(cfg):
    """Boot rapido sin colgarse: valida tecla, mic y warmup de modelos."""
    t0 = time.time()
    key = cfg.get("key", "f9")
    try:
        hk = hotkey.create(key)
        hk.stop()
    except (ValueError, RuntimeError) as e:
        print(f"  tecla: FAIL ({e}). Opciones: {', '.join(hotkey.available_keys())}")
        return 2
    print(f"  tecla: {key} OK")
    mic = audio.resolve_mic(cfg.get("mic_hint", ""), cfg.get("mic_index"))
    ok = audio.probe(mic)
    print(f"  mic probe: {'OK' if ok else 'FAIL (revisa uso exclusivo)'}")
    try:
        eng = Engine(threads=cfg.get("threads", 4), max_seg=cfg.get("max_seg", 20.0))
        eng.recognizer()
        eng.vad()
    except FileNotFoundError as e:
        print(f"  SIN MODELOS: {e}")
        return 2
    dt = time.time() - t0
    print(f"  boot mic+warmup: {dt:.1f}s ({'OK <5s' if dt < 5 else 'LENTO >5s'})")
    return 0 if (ok and dt < 5) else 2
