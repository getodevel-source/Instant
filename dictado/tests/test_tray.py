"""Ciclo de vida del icono de bandeja."""
import os
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app.tray import TrayIcon

shutdown = threading.Event()
tray = TrayIcon(shutdown)

try:
    import pystray
except ImportError:
    pystray = None
if pystray is not None:
    menu = tray._build_menu(pystray)
    default_item = next(
        (item for item in menu if getattr(item, "default", False)), None)
    if (default_item is None or default_item.text != "Abrir ventana de Instant"
            or not default_item.visible or not default_item.enabled):
        raise SystemExit("FAIL menú sin acción visible para abrir Instant")
    print("PASS bandeja ofrece abrir Instant como acción predeterminada")

shutdown.clear()
with patch("instant_app.tray.close_existing_gui") as close_gui:
    tray._on_exit(None, None)
if not shutdown.is_set() or not close_gui.called:
    raise SystemExit("FAIL salir no cerró GUI y solicitó apagar daemon")
print("PASS salir cierra GUI y solicita cierre del daemon")

for args, requested, page in (((), True, None), (("setup",), False, "setup")):
    with patch("instant_app.tray.focus_existing_gui", return_value=True) as focus, \
            patch("instant_app.tray.subprocess.Popen") as launch:
        outcome = tray._launch_gui(args)
    if outcome != "focused":
        raise SystemExit("FAIL existing GUI was not reported as focused")
    focus.assert_called_once_with(request_daemon_start=requested, page=page)
    launch.assert_not_called()
print("PASS abrir/configurar reutiliza la GUI existente sin proceso duplicado")

with patch("instant_app.tray.focus_existing_gui", return_value=False), \
        patch("instant_app.tray.app_command", return_value=["Instant.exe"]) as command, \
        patch("instant_app.tray.app_environment", return_value={"PYINSTALLER_RESET_ENVIRONMENT": "1"}), \
        patch("instant_app.tray.subprocess.Popen") as launch, \
        patch.dict(sys.modules, {"instant_app.gui": None}):
    outcome = tray._open(None, None)
if outcome != "launched":
    raise SystemExit("FAIL tray Open no reportó el inicio de una ventana")
launch.assert_called_once()
command.assert_called_once_with(())
if launch.call_args.kwargs["env"].get("PYINSTALLER_RESET_ENVIRONMENT") != "1":
    raise SystemExit("FAIL tray child did not reset one-file extraction")
print("PASS tray Open launches isolated GUI without importing GUI in daemon")

with patch("instant_app.tray.focus_existing_gui", return_value=False), \
        patch("instant_app.tray.app_command", return_value=["Instant.exe"]), \
        patch("instant_app.tray.subprocess.Popen", side_effect=OSError("launch failed")):
    with unittest.TestCase().assertLogs("instant", level="ERROR") as errors:
        outcome = tray._open(None, None)
if outcome != "failed" or not any("no pude abrir la interfaz" in line for line in errors.output):
    raise SystemExit("FAIL tray Open no reportó el error de lanzamiento")
print("PASS tray Open informa fallas de Popen")
