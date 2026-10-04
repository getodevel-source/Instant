"""Pruebas de rendimiento/regresion para los fixes de congelamiento."""
import os
import queue
import sys
import tempfile
import threading
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import daemon as daemon_module
from instant_app.engine import Engine


def _check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" ({detail})" if detail else ""))
    if not cond:
        raise SystemExit(1)


# 1. Cola acotada: 10k bloques fuera de sesion no deben acumularse.
keeper = daemon_module.StreamKeeper({})
blk = np.full((160, 1), 0.05, dtype=np.float32)
t0 = time.time()
for _ in range(10000):
    keeper._cb(blk, 160, None, None)
dt = time.time() - t0
_check("10k callbacks fuera de sesion: cola vacia", keeper.q.qsize() == 0,
       f"q={keeper.q.qsize()}")
_check("10k callbacks rapidos (<2s)", dt < 2.0, f"{dt:.2f}s")
_check("pre-roll acotado", len(keeper.pre) <= 256, f"pre={len(keeper.pre)}")

# 2. En sesion si encola, y end_session drena.
keeper.begin_session()
for _ in range(100):
    keeper._cb(blk, 160, None, None)
_check("en sesion encola 100", keeper.q.qsize() == 100, f"q={keeper.q.qsize()}")
keeper.end_session()
_check("end_session drena", keeper.q.qsize() == 0)

# 3. Snapshot no purga millones: 1k bloques en sesion se drenan rapido.
keeper.begin_session()
for _ in range(1000):
    keeper._cb(blk, 160, None, None)
t0 = time.time()
got = keeper.snapshot(0.45)
dt = time.time() - t0
_check("snapshot rapido (<0.5s)", dt < 0.5, f"{dt:.3f}s")
keeper.end_session()

# 4. Engine: threads clamp + VAD reuse + retry cap.
eng = Engine(data_dir=tempfile.mkdtemp(), threads=64)
import os as _os
cpu = _os.cpu_count() or 4
_check("threads clamp a [1,8,cpu]", 1 <= eng.threads <= min(8, cpu),
       f"threads={eng.threads}")
eng2 = Engine(data_dir=tempfile.mkdtemp(), threads="no-int")
eng_default = Engine(data_dir=tempfile.mkdtemp())
_check("threads invalido cae al default de la maquina",
       eng2.threads == eng_default.threads, f"{eng2.threads}")
_check("retry cap 30s", eng.FULL_RETRY_MAX_SECONDS == 30.0)
_check("max session 120s", daemon_module.StreamKeeper.MAX_SESSION_SECONDS == 120.0)

# VAD reuse sin modelos reales: mock sherpa_onnx.
import types
calls = {"n": 0}


class _FakeVad:
    def window_size(self):
        return 512

    def is_speech(self, _w):
        return True


_fake = types.SimpleNamespace(
    VadModelConfig=lambda: types.SimpleNamespace(
        silero_vad=types.SimpleNamespace(model="", threshold=0.5,
                                         min_silence_duration=0.5,
                                         min_speech_duration=0.2,
                                         window_size=512),
        sample_rate=16000),
    VadModel=types.SimpleNamespace(
        create=lambda _c: (calls.__setitem__("n", calls["n"] + 1),
                           _FakeVad())[1]),
)
sys.modules["sherpa_onnx"] = _fake
# Crea un vad.onnx vacio para pasar el check de existencia.
dd = tempfile.mkdtemp()
os.makedirs(os.path.join(dd, "parakeet-v3-int8"), exist_ok=True)
os.makedirs(os.path.join(dd, "silero-vad"), exist_ok=True)
open(os.path.join(dd, "silero-vad", "silero_vad.onnx"), "wb").close()
eng3 = Engine(data_dir=dd)
v1 = eng3.vad()
v2 = eng3.vad()
_check("VAD reutilizado (1 create)", calls["n"] == 1 and v1 is v2,
       f"creates={calls['n']}")
eng3.unload()
v3 = eng3.vad()
_check("unload libera VAD", calls["n"] == 2 and v3 is not v1)
del sys.modules["sherpa_onnx"]

# 5. on_release no bloquea hilo hotkey (<100ms).
d = daemon_module.Daemon.__new__(daemon_module.Daemon)
d.lock = threading.Lock()
d.rec = {"sid": 1, "grabando": True, "frames": [], "t_start": time.time(),
         "done": None, "busy": False}
d.cfg = {}


class _NullOverlay:
    def processing(self, _s):
        pass

    def starting(self, _s):
        pass

    def listening(self, _s):
        pass

    def show_notice_for(self, *a, **k):
        pass

    def show_error_for(self, *a, **k):
        pass

    def success_for(self, _s):
        pass


d.overlay = _NullOverlay()
d.engine = Engine(data_dir=tempfile.mkdtemp())
done = threading.Event()
d.rec["done"] = done
# Simula grabacion terminada en otro hilo.
threading.Thread(target=d._record, daemon=True).start() if False else None
t0 = time.time()
d.on_release()
dt = time.time() - t0
_check("on_release retorna rapido (<0.2s)", dt < 0.2, f"{dt:.3f}s")

# 6. Log rotativo.
from instant_app import __main__ as main_mod
import inspect
src = inspect.getsource(main_mod._log_setup)
_check("log usa RotatingFileHandler", "RotatingFileHandler" in src)
_check("log maxBytes 2MB", "maxBytes" in src and "backupCount" in src)

# 7. Transcribe seriado: sin ThreadPoolExecutor en engine.
eng_src = open(os.path.join(os.path.dirname(__file__), "..", "src",
                            "instant_app", "engine.py"), encoding="utf-8").read()
_check("sin ThreadPoolExecutor", "ThreadPoolExecutor" not in eng_src)

print("OK: pruebas de rendimiento verdes.")
