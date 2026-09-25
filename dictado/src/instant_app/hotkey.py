"""Hotkey hold-to-talk por SO.
Windows: polling GetAsyncKeyState (probado; sin hook, sin admin, Deskflow no lo roba).
Linux/macOS: pynput (listener press/release). Sin backend -> error claro.
"""
import logging
import threading
import time

log = logging.getLogger("instant")

WINDOWS_KEYS = {"f9": 0x78, "f10": 0x79, "f20": 0x83, "scroll": 0x91, "pause": 0x13}
POSIX_KEYS = ("f9", "f10", "f11", "f12")


def available_keys():
    import sys
    if sys.platform == "win32":
        return tuple(WINDOWS_KEYS)
    return POSIX_KEYS


class WindowsPolling:
    def __init__(self, key_name):
        import ctypes
        vk = WINDOWS_KEYS.get(key_name.lower())
        if vk is None:
            raise ValueError(f"tecla {key_name!r} no soportada en Windows: {tuple(WINDOWS_KEYS)}")
        self.vk = vk
        self._user32 = ctypes.windll.user32
        self._stop = threading.Event()
        self._t = None

    def is_down(self):
        return bool(self._user32.GetAsyncKeyState(self.vk) & 0x8000)

    def start(self, on_press, on_release, interval=0.01):
        def _loop():
            was = False
            while not self._stop.is_set():
                down = bool(self.is_down())
                if down and not was:
                    on_press()
                elif not down and was:
                    on_release()
                was = down
                time.sleep(interval)

        self._t = threading.Thread(target=_loop, daemon=True)
        self._t.start()

    def stop(self):
        self._stop.set()


class PynputHotkey:
    def __init__(self, key_name):
        key_name = key_name.lower()
        if key_name not in POSIX_KEYS:
            raise ValueError(f"tecla {key_name!r} no soportada fuera de Windows: {POSIX_KEYS}")
        try:
            from pynput import keyboard as _pk
        except ImportError:
            raise RuntimeError("falta pynput: pip install 'instant' en linux/mac lo incluye; "
                               "si falla, instala pynput manual.") from None
        self._pk = _pk
        self._target = getattr(_pk.Key, key_name)
        self._listener = None
        self._down = False

    def _norm(self, key):
        try:
            return key == self._target
        except Exception:
            return False

    def start(self, on_press, on_release, interval=0.01):
        def _p(key):
            if not self._down and self._norm(key):
                self._down = True
                on_press()

        def _r(key):
            if self._down and self._norm(key):
                self._down = False
                on_release()

        self._listener = self._pk.Listener(on_press=_p, on_release=_r, suppress=False)
        self._listener.start()

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass


def create(key_name):
    import sys
    if sys.platform == "win32":
        return WindowsPolling(key_name)
    return PynputHotkey(key_name)
