"""Pegado por SO. Windows: clipboard + Ctrl+V (probado, respeta ñ/á).
Linux: xclip/xsel + xdotool Ctrl+V (X11). macOS: pbcopy + pynput Cmd+V.
"""
import logging
import time

log = logging.getLogger("instant")


def paste(text):
    import sys
    if sys.platform == "win32":
        import pyperclip
        import keyboard
        pyperclip.copy(text)
        time.sleep(0.05)
        keyboard.press_and_release("ctrl+v")
        return
    if sys.platform == "darwin":
        _paste_macos(text)
        return
    _paste_linux(text)


def _paste_linux(text):
    import shutil
    import subprocess
    tool = shutil.which("xclip") or shutil.which("xsel")
    if tool is None:
        raise RuntimeError("falta xclip o xsel: sudo apt install xclip xdotool")
    if tool.endswith("xclip"):
        subprocess.run([tool, "-selection", "clipboard"], input=text.encode("utf-8"),
                       check=True, timeout=10)
    else:
        subprocess.run([tool, "--clipboard", "--input"], input=text.encode("utf-8"),
                       check=True, timeout=10)
    time.sleep(0.05)
    xdotool = shutil.which("xdotool")
    if xdotool is None:
        raise RuntimeError("falta xdotool: sudo apt install xdotool (solo X11; en Wayland no pega teclas)")
    subprocess.run([xdotool, "key", "ctrl+v"], check=True, timeout=10)


def _paste_macos(text):
    import subprocess
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=10)
    time.sleep(0.05)
    try:
        from pynput.keyboard import Controller, Key
    except ImportError:
        raise RuntimeError("falta pynput para pegar en macOS.") from None
    kb = Controller()
    with kb.pressed(Key.cmd):
        kb.press("v")
        kb.release("v")
