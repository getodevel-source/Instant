"""Pegado por SO. Windows: clipboard + Ctrl+V (probado, respeta ñ/á).
Linux: xclip/xsel + xdotool Ctrl+V (X11). macOS: pbcopy + pynput Cmd+V.

El clipboard previo se guarda y restaura (el dictado no debe comerse lo
que el usuario tenia copiado). En Wayland/XWayland no hay inyeccion de teclas:
se avisa ANTES de pisar el clipboard (texto ya en el portapapeles,
pegar con Ctrl+V manual). `paste("")` es no-op.
"""
import logging
import time

log = logging.getLogger("instant")

# Espera de pegado: el Ctrl+V necesita que el clipboard ya este escrito.
# Poll corto con tope (hasta ~200 ms) en vez de sleep fijo ciego.
_PASTE_WAIT_S = 0.2


def _wait_paste_ready(check=None):
    """Espera robusta del pegado: poll con tope, no sleep fijo ciego.

    `check`: vuelve a leer el clipboard y devuelve True cuando ya tiene
    el texto (solo donde se puede leer). Sin `check`, pausa minima de
    20 ms para ceder el turno al SO. Nunca supera `_PASTE_WAIT_S`.
    """
    if check is None:
        time.sleep(0.02)
        return
    deadline = time.monotonic() + _PASTE_WAIT_S
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except Exception:
            return
        time.sleep(0.02)


def paste(text):
    import sys
    if not text:
        return
    if sys.platform == "win32":
        _paste_windows(text)
        return
    if sys.platform == "darwin":
        _paste_macos(text)
        return
    _paste_linux(text)


def _paste_windows(text):
    import pyperclip
    import keyboard
    try:
        prev = pyperclip.paste()
    except Exception:
        prev = None
    pyperclip.copy(text)
    _wait_paste_ready(lambda: pyperclip.paste() == text)
    try:
        keyboard.press_and_release("ctrl+v")
    finally:
        if prev is not None:
            _wait_paste_ready()
            try:
                pyperclip.copy(prev)
            except Exception:
                pass


def _paste_linux(text):
    import os
    import shutil
    import subprocess
    # Wayland/XWayland no inyecta teclas con xdotool: chequear ANTES de
    # pisar el clipboard, para no comer lo copiado a cambio de nada. El
    # texto ya queda en el portapapeles; el usuario pega con Ctrl+V manual.
    # Sin colapsar vars con `or`: en XWayland XDG_SESSION_TYPE es "x11"
    # pero WAYLAND_DISPLAY sigue seteado y xdotool tampoco inyecta.
    session_type = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
    wayland_display = (os.environ.get("WAYLAND_DISPLAY") or "").strip()
    is_wayland = (session_type == "wayland" or "wayland" in session_type
                  or bool(wayland_display))
    if is_wayland:
        tool = shutil.which("xclip") or shutil.which("xsel") \
            or shutil.which("wl-copy")
        if tool is None:
            raise RuntimeError(
                "en Wayland no hay inyeccion de teclas (xdotool es solo X11): "
                "instala xclip o wl-clipboard y pega con Ctrl+V manual; "
                "no se piso el clipboard")
        if tool.endswith("wl-copy"):
            subprocess.run([tool], input=text.encode("utf-8"),
                           check=True, timeout=10)
        elif tool.endswith("xclip"):
            subprocess.run([tool, "-selection", "clipboard"],
                           input=text.encode("utf-8"), check=True, timeout=10)
        else:
            subprocess.run([tool, "--clipboard", "--input"],
                           input=text.encode("utf-8"), check=True, timeout=10)
        log.warning("Wayland: texto en el portapapeles; "
                    "pega con Ctrl+V manual (sin inyeccion de teclas).")
        return
    tool = shutil.which("xclip") or shutil.which("xsel")
    if tool is None:
        raise RuntimeError("falta xclip o xsel: sudo apt install xclip xdotool")
    xdotool = shutil.which("xdotool")
    if xdotool is None:
        raise RuntimeError(
            "falta xdotool: sudo apt install xdotool "
            "(solo X11; en Wayland no pega teclas; no se piso el clipboard)")
    try:
        prev = subprocess.run(
            [tool, "-selection", "clipboard", "-o"] if tool.endswith("xclip")
            else [tool, "--clipboard", "--output"],
            capture_output=True, timeout=10).stdout
    except Exception:
        prev = None
    if tool.endswith("xclip"):
        subprocess.run([tool, "-selection", "clipboard"], input=text.encode("utf-8"),
                       check=True, timeout=10)
    else:
        subprocess.run([tool, "--clipboard", "--input"], input=text.encode("utf-8"),
                       check=True, timeout=10)
    _wait_paste_ready()
    try:
        subprocess.run([xdotool, "key", "ctrl+v"], check=True, timeout=10)
    finally:
        if prev is not None:
            _wait_paste_ready()
            try:
                if tool.endswith("xclip"):
                    subprocess.run([tool, "-selection", "clipboard"],
                                   input=prev, check=True, timeout=10)
                else:
                    subprocess.run([tool, "--clipboard", "--input"],
                                   input=prev, check=True, timeout=10)
            except Exception:
                pass


def _paste_macos(text):
    import subprocess
    try:
        prev = subprocess.run(["pbpaste"], capture_output=True,
                              timeout=10).stdout
    except Exception:
        prev = None
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=10)
    _wait_paste_ready()
    try:
        from pynput.keyboard import Controller, Key
    except ImportError:
        raise RuntimeError("falta pynput para pegar en macOS.") from None
    kb = Controller()
    try:
        with kb.pressed(Key.cmd):
            kb.press("v")
            kb.release("v")
    finally:
        if prev is not None:
            _wait_paste_ready()
            try:
                subprocess.run(["pbcopy"], input=prev,
                               check=True, timeout=10)
            except Exception:
                pass
