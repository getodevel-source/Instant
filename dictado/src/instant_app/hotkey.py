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

def normalize_key(raw, default="f9"):
    """Normaliza nombre de tecla: minusculas, sin espacios; vacio/Enter -> default."""
    k = "" if raw is None else str(raw).strip().lower()
    if k in ("", "enter", "return"):
        return (default or "f9").lower()
    return k


# Scan codes extendidos win (tras prefijo \x00/\xe0) -> nombre. Solo captura.
_SCAN_WIN = {59: "f1", 60: "f2", 61: "f3", 62: "f4", 63: "f5", 64: "f6",
             65: "f7", 66: "f8", 67: "f9", 68: "f10", 133: "f11", 134: "f12"}
# Secuencias xterm posix -> nombre. Solo captura.
_SEQ_POSIX = {"\x1b[20~": "f9", "\x1b[21~": "f10",
              "\x1b[23~": "f11", "\x1b[24~": "f12"}


def _read_keypress():
    """Un keypress crudo -> nombre normalizado ("" = Enter) o None si no se pudo.
    Solo captura para el setup; el dictado sigue con GetAsyncKeyState/pynput."""
    import sys
    try:
        if sys.platform == "win32":
            import msvcrt
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                return _SCAN_WIN.get(ord(msvcrt.getwch()))
            if ch in ("\r", "\n"):
                return ""
            return ch.lower() if len(ch) == 1 else None
        import select
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = ch
                while len(seq) < 6 and select.select([sys.stdin], [], [], 0.15)[0]:
                    seq += sys.stdin.read(1)
                    if seq in _SEQ_POSIX:
                        break
                return _SEQ_POSIX.get(seq, seq.strip().lower() or None)
            if ch in ("\r", "\n"):
                return ""
            return ch.lower() if ch else None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        return None


def capture_key(prompt="Presiona la tecla para dictar... (Enter = F9)", default="f9"):
    """Modo captura: presiona la tecla y se asigna si esta en available_keys().
    Enter = default. Repite hasta tecla valida. Sin TTY usa linea escrita."""
    keys = available_keys()
    dflt = (default or "f9").lower()
    print(f"  {prompt}")
    while True:
        pressed = _read_keypress()
        if pressed is None:
            try:
                typed = input(f"  tecla [{dflt}] ({', '.join(keys)}): ")
            except (EOFError, KeyboardInterrupt):
                print()
                raise KeyboardInterrupt
            key = normalize_key(typed, dflt)
        elif pressed == "":
            key = dflt
        else:
            key = pressed
            print(f"  detectada: {key}")
        if key in keys:
            return key
        print(f"  '{key}' no valida. Opciones: {', '.join(keys)}. Intenta de nuevo.")


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
