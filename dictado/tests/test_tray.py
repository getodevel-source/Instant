"""Ciclo de vida del icono de bandeja."""
import os
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app.tray import TrayIcon


class TrayLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.shutdown = threading.Event()
        self.tray = TrayIcon(self.shutdown)

    def test_menu_offers_open_as_default_action(self):
        try:
            import pystray
        except ImportError:
            self.skipTest("pystray no disponible")
        menu = self.tray._build_menu(pystray)
        default_item = next(
            (item for item in menu if getattr(item, "default", False)), None)
        self.assertIsNotNone(default_item)
        self.assertEqual(default_item.text, "Abrir ventana de Instant")
        self.assertTrue(default_item.visible)
        self.assertTrue(default_item.enabled)

    def test_exit_closes_gui_and_requests_shutdown(self):
        self.shutdown.clear()
        with patch("instant_app.tray.close_existing_gui") as close_gui:
            self.tray._on_exit(None, None)
        self.assertTrue(self.shutdown.is_set())
        self.assertTrue(close_gui.called)

    def test_launch_reuses_existing_gui_without_duplicate(self):
        for args, requested, page in (((), True, None), (("setup",), False, "setup")):
            with (
                patch("instant_app.tray.focus_existing_gui", return_value=True) as focus,
                patch("instant_app.tray.subprocess.Popen") as launch,
            ):
                outcome = self.tray._launch_gui(args)
            self.assertEqual(outcome, "focused")
            focus.assert_called_once_with(request_daemon_start=requested, page=page)
            launch.assert_not_called()

    def test_open_launches_isolated_gui_without_importing_gui(self):
        with (
            patch("instant_app.tray.focus_existing_gui", return_value=False),
            patch("instant_app.tray.app_command", return_value=["Instant.exe"]) as command,
            patch("instant_app.tray.app_environment",
                  return_value={"PYINSTALLER_RESET_ENVIRONMENT": "1"}),
            patch("instant_app.tray.subprocess.Popen") as launch,
            patch.dict(sys.modules, {"instant_app.gui": None}),
        ):
            outcome = self.tray._open(None, None)
        self.assertEqual(outcome, "launched")
        launch.assert_called_once()
        command.assert_called_once_with(())
        self.assertEqual(launch.call_args.kwargs["env"].get("PYINSTALLER_RESET_ENVIRONMENT"), "1")

    def test_open_reports_popen_failures(self):
        with (
            patch("instant_app.tray.focus_existing_gui", return_value=False),
            patch("instant_app.tray.app_command", return_value=["Instant.exe"]),
            patch("instant_app.tray.subprocess.Popen", side_effect=OSError("launch failed")),
        ):
            with self.assertLogs("instant", level="ERROR") as errors:
                outcome = self.tray._open(None, None)
        self.assertEqual(outcome, "failed")
        self.assertTrue(any("no pude abrir la interfaz" in line for line in errors.output))


if __name__ == "__main__":
    unittest.main()
