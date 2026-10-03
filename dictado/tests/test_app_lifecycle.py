"""CLI-to-GUI startup mode and daemon singleton behavior."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import __main__ as entry


class AppLifecycleTests(unittest.TestCase):
    def test_frozen_child_environment_resets_onefile_extraction(self):
        from instant_app import launch
        with patch.object(launch.sys, "frozen", True, create=True), \
                patch.dict(os.environ, {"PYINSTALLER_RESET_ENVIRONMENT": "0"}):
            env = launch.app_environment()
            self.assertEqual(env["PYINSTALLER_RESET_ENVIRONMENT"], "1")
            self.assertEqual(os.environ["PYINSTALLER_RESET_ENVIRONMENT"], "0")

    def test_daemon_mutex_released_after_failed_start(self):
        handle = object()
        instance = SimpleNamespace(run=Mock(side_effect=FileNotFoundError("model missing")))
        daemon = Mock(return_value=instance)
        with patch.object(entry, "_log_setup"), \
                patch.object(entry.logging, "getLogger"), \
                patch("instant_app.config.load", return_value={}), \
                patch("instant_app.daemon_lifecycle.acquire_daemon_mutex", return_value=handle), \
                patch("instant_app.daemon_lifecycle.release_daemon_mutex") as release, \
                patch.dict(sys.modules, {"instant_app.daemon": SimpleNamespace(Daemon=daemon)}):
            self.assertEqual(entry.main(["run"]), 2)
        daemon.assert_called_once_with({})
        instance.run.assert_called_once_with()
        release.assert_called_once_with(handle)

    def test_existing_gui_receives_start_setup_and_close_actions(self):
        from instant_app import gui_lifecycle
        hwnd = 0x1234
        user32 = SimpleNamespace(
            FindWindowW=Mock(return_value=hwnd),
            ShowWindow=Mock(),
            SetForegroundWindow=Mock(),
            PostMessageW=Mock(return_value=1),
        )
        with patch("instant_app.gui_lifecycle.os.name", "nt"), \
                patch("instant_app.gui_lifecycle._user32", return_value=user32):
            self.assertTrue(gui_lifecycle.focus_existing_gui(request_daemon_start=True))
            user32.PostMessageW.assert_called_once_with(
                hwnd, gui_lifecycle._GUI_ACTION_MESSAGE,
                gui_lifecycle._ACTION_START_DAEMON, 0)
            user32.PostMessageW.reset_mock()
            self.assertTrue(gui_lifecycle.focus_existing_gui(page="setup"))
            user32.PostMessageW.assert_called_once_with(
                hwnd, gui_lifecycle._GUI_ACTION_MESSAGE,
                gui_lifecycle._ACTION_SETUP, 0)
            user32.PostMessageW.reset_mock()
            self.assertTrue(gui_lifecycle.close_existing_gui())
            user32.PostMessageW.assert_called_once_with(
                hwnd, gui_lifecycle._WM_CLOSE, 0, 0)

    def test_gui_mutex_failure_reports_open_error(self):
        from instant_app import gui
        with patch.object(gui.sys, "platform", "win32"), \
                patch("instant_app.gui_lifecycle.acquire_gui_mutex",
                      side_effect=OSError("mutex unavailable")), \
                self.assertLogs("instant", level="ERROR") as errors:
            self.assertEqual(gui.run_gui(), 2)
        self.assertIn("interfaz gráfica no disponible", errors.output[0])


    def test_direct_windows_launch_requests_daemon_start(self):
        with patch.object(entry, "_log_setup"), \
                patch.object(entry, "_run_gui", return_value=0) as run_gui, \
                patch.object(entry.sys, "platform", "win32"):
            self.assertEqual(entry.main([]), 0)
        run_gui.assert_called_once_with("home", start_daemon_on_open=True)

    def test_setup_and_os_autostart_flags_never_start_daemon(self):
        for argv, expected in (
                (["setup"], None),
                (["setup", "--autostart"], True),
                (["setup", "--no-autostart"], False)):
            with self.subTest(argv=argv), \
                    patch.object(entry, "_log_setup"), \
                    patch.object(entry, "_run_gui", return_value=0) as run_gui, \
                    patch.object(entry.sys, "platform", "win32"):
                self.assertEqual(entry.main(argv), 0)
            run_gui.assert_called_once_with("setup", autostart_override=expected)

    def test_existing_daemon_mutex_skips_second_daemon_construction(self):
        daemon = Mock()
        with patch.object(entry, "_log_setup"), \
                patch("instant_app.config.load", return_value={}), \
                patch("instant_app.daemon_lifecycle.acquire_daemon_mutex", return_value=None), \
                patch.dict(sys.modules, {"instant_app.daemon": SimpleNamespace(Daemon=daemon)}):
            self.assertEqual(entry.main(["run"]), 0)
        daemon.assert_not_called()



if __name__ == "__main__":
    unittest.main()
