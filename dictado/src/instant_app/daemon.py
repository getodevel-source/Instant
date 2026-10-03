"""Daemon hold-to-talk: graba en RAM, al soltar VAD+Parakeet y pega. Cross-platform."""
import logging
import queue
import threading
import time

import numpy as np

from instant_app import audio, hotkey, llm
from instant_app.engine import Engine, SILENCE_PEAK
from instant_app.overlay import Overlay
from instant_app.tray import TrayIcon

log = logging.getLogger("instant")


def pid_path():
    """Ruta del PID file: %APPDATA%/instant/instant.pid (config_dir)."""
    from instant_app.paths import config_dir
    import os
    return os.path.join(config_dir(), "instant.pid")


def write_pid():
    """Registra el PID al arrancar para stop/status. Nunca tumba el daemon."""
    import os
    try:
        p = pid_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        log.warning("no pude escribir instant.pid", exc_info=True)


def clear_pid():
    """Borra el PID file al salir limpio, solo si es el propio."""
    import os
    try:
        p = pid_path()
        with open(p, encoding="utf-8") as f:
            if f.read().strip() != str(os.getpid()):
                return
        os.remove(p)
    except FileNotFoundError:
        pass
    except Exception:
        log.warning("no pude borrar instant.pid", exc_info=True)


class Daemon:
    def __init__(self, cfg, data_dir=None):
        self.cfg = cfg
        self.engine = Engine(data_dir,
                             threads=cfg.get("threads", 4),
                             max_seg=cfg.get("max_seg", 20.0))
        self.overlay = Overlay(hotkey.key_label(cfg.get("key", "f9")))
        self.mic = audio.resolve_mic(
            cfg.get("mic_hint", ""), cfg.get("mic_index"),
            strict_hint=bool(cfg.get("mic_hint")))
        self.hk = hotkey.create(cfg.get("key", "f9"))
        self.rec = {"sid": 0, "grabando": False, "frames": [], "t_start": 0.0,
                    "done": None, "busy": False}
        self.lock = threading.Lock()
        self._shutdown = threading.Event()
        self.tray = TrayIcon(self._shutdown)

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

        q = queue.Queue()
        frames = []

        def cb(indata, frames_, t, status):
            if status:
                log.warning("audio status: %s", status)
            q.put(indata.copy())

        try:
            mic = audio.resolve_mic(
                self.cfg.get("mic_hint", ""), self.cfg.get("mic_index"),
                strict_hint=True)
            if self.cfg.get("mic_hint") and mic is None:
                raise RuntimeError(
                    f"Configured microphone '{self.cfg['mic_hint']}' is no longer available")
            stream, mic = audio.open_input_stream(mic, callback=cb)
        except Exception:
            log.exception("ERROR abriendo microfono")
            with self.lock:
                if self.rec["sid"] == sid:
                    self.rec["grabando"] = False
            self.overlay.show_error_for(
                sid,
                "No se pudo iniciar el micrófono. Revisá conexión, permiso del sistema y "
                "que otra app no lo esté usando. El log tiene el error detallado.",
                "#f87171", 6000)
            done.set()
            return
        log.info("grabando sesion %d...", sid)
        self.overlay.listening(sid)
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
        try:
            if dur < self.engine.min_dur:
                log.info("muy corto (<%.1fs), descarto.", self.engine.min_dur)
                key = hotkey.key_label(self.cfg.get("key", "f9"))
                self.overlay.show_notice_for(
                    sid, f"Dictado muy corto — mantené {key} un poco más.", "#f2c36a")
                return
            peak = float(np.max(np.abs(wav))) if wav.size else 0.0
            if peak < SILENCE_PEAK:
                log.info("silencio (pico %.4f), descarto sin inferencia.", peak)
                self.overlay.show_notice_for(sid, "No detecté voz.", "#f2c36a")
                return
            t0 = time.time()
            text = self.engine.transcribe(wav)
            text = llm.maybe_polish(text, self.cfg)
            dt = time.time() - t0
            if not text:
                log.info("vacio tras %.1fs audio (%.2fs), nada que pegar.", dur, dt)
                self.overlay.show_notice_for(
                    sid,
                    "No pude reconocer el audio. Probá hablar más cerca del micrófono.",
                    "#f2c36a", 2600)
                return
            log.info("[%.1fs audio -> %.2fs, RTF=%.2fx] %s",
                     dur, dt, dt / max(dur, 0.1), text[:200])
            import instant_app.paste as _paste_mod
            _paste_mod.paste(text + " ")
            self.overlay.success_for(sid)
        except Exception:
            log.exception("ERROR transcripcion sesion %d", sid)
            self.overlay.show_error_for(
                sid, "No se pudo completar el dictado. Abrí Diagnóstico.",
                "#ff908b", 3000)
        finally:
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
        self.overlay.starting(sid)
        threading.Thread(target=self._record, args=(sid, done), daemon=True).start()

    def on_release(self):
        with self.lock:
            if not self.rec["grabando"]:
                return
            self.rec["grabando"] = False
            dur = time.time() - self.rec["t_start"]
            done = self.rec["done"]
            sid = self.rec["sid"]
        self.overlay.processing(sid)
        if done is not None and not done.wait(timeout=10.0):
            log.warning("sesion %d no cerro mic en 10s, transcribo lo que hay.", sid)
        with self.lock:
            frames = self.rec["frames"]
            self.rec["frames"] = []
            self.rec["busy"] = True
        wav = audio.to_mono(np.concatenate(frames, axis=0)) if frames \
            else np.zeros(0, dtype=np.float32)
        log.info("soltado tras %.1fs, %d bloques -> VAD+Parakeet.", dur, len(frames))
        threading.Thread(target=self._job, args=(wav, dur, sid), daemon=True).start()

    def run(self):
        write_pid()
        try:
            if self.cfg.get("mic_hint") and self.mic is None:
                log.error("micrófono configurado no encontrado; no pruebo otro default.")
            elif not audio.probe(self.mic):
                log.warning("mic probe FAIL; revisá conexión, permisos y uso por otra app.")
            self.engine.recognizer()
            self.engine.vad()
            try:
                self.tray.start()
            except Exception:
                log.exception("no pude iniciar el icono de bandeja")
            key = hotkey.key_label(self.cfg.get("key", "f9"))
            log.info("listo. Manten %s para dictar (60-120s), suelta para transcribir. Ctrl+C sale.", key)
            self.hk.start(self.on_press, self.on_release)
            if not self.overlay.run_event_loop(
                    self._shutdown, lambda: log.info("vivo, esperando %s...", key)):
                while not self._shutdown.wait(60):
                    log.info("vivo, esperando %s...", key)
        except KeyboardInterrupt:
            log.info("chau.")
        finally:
            self._shutdown.set()
            self.overlay.hide()
            try:
                self.hk.stop()
            except Exception:
                pass
            self.tray.stop()
            clear_pid()


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
    print(f"  tecla: {hotkey.key_label(key)} OK")
    hint = cfg.get("mic_hint", "")
    mic = audio.resolve_mic(hint, cfg.get("mic_index"), strict_hint=bool(hint))
    if hint and mic is None:
        ok = False
        print("  mic callback probe: FAIL (micrófono guardado no encontrado; "
              "reconectalo o elegí otro en Configuración)")
    else:
        ok = audio.probe(mic)
        print("  mic callback probe: "
              f"{'OK' if ok else 'FAIL (revisa conexión, permisos y uso por otra app)'}")
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
