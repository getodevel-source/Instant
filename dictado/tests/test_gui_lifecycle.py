"""Qt window lifecycle behavior, exercised when PySide6 is available."""
import os
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import PySide6  # noqa: F401
except ImportError:
    print("SKIP Qt lifecycle behavior: PySide6 is not installed")
else:
    from instant_app import gui

    class QtLifecycleTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            import gc as _gc
            _gc.disable()
            from PySide6.QtWidgets import QApplication
            cls.app = QApplication.instance() or QApplication([])

        @classmethod
        def tearDownClass(cls):
            import gc as _gc
            _gc.enable()
            _gc.collect()

        def setUp(self):
            # Las ventanas del test anterior se destruyen acá, fuera de todo
            # event loop: su GC cíclico durante un pump posterior aborta Qt
            # en offscreen. Producción no lo sufre (una ventana por proceso).
            import gc as _gc
            _gc.collect()

        def _wait_idle(self, window):
            from PySide6.QtCore import QEventLoop
            if not window._pending_workers: return
            loop = QEventLoop()
            window.workers_idle.connect(loop.quit)
            if window._pending_workers: loop.exec()
            self.assertFalse(window._pending_workers)

        def _close_and_wait(self, window):
            window.close()
            self._wait_idle(window)
        def test_closing_window_does_not_stop_or_query_daemon(self):
            Window = gui._main_window_class()
            with patch("instant_app.gui.config.load", return_value={"mic_hint": "", "mic_index": None, "key": "f9", "autostart": False}), \
                    patch("instant_app.gui.models.check", return_value={"parakeet": False, "vad": False}), \
                    patch("instant_app.gui.daemon_is_running", return_value=False), \
                    patch("instant_app.gui.audio.input_choices", return_value=[]), \
                    patch.dict(sys.modules, {"sounddevice": SimpleNamespace(default=SimpleNamespace(device=(-1, -1)))}):
                window = Window(autostart_override=False)
                self._wait_idle(window)
            window.show()
            started, release = threading.Event(), threading.Event()
            try:
                window._run_worker(lambda _emit: (started.set(), release.wait(3)), lambda _value: self.fail("closed window received late result"))
                self.assertTrue(started.wait(2))
                with patch("instant_app.gui.daemon_is_running", side_effect=AssertionError("close queried daemon")), \
                        patch.object(window, "stop_daemon", side_effect=AssertionError("close stopped daemon")):
                    window.close()
                    release.set()
                    self._wait_idle(window)
                self.assertTrue(window._closed)
            finally:
                release.set()
                self._close_and_wait(window)

        def test_daemon_inherits_resolved_model_directory(self):
            Window = gui._main_window_class()
            data_dir = os.path.join(os.getcwd(), "models")
            launch = Mock()
            with patch("instant_app.gui.config.load", return_value={"mic_hint": "", "mic_index": None, "key": "f9", "autostart": False}), \
                    patch("instant_app.gui.config.save", return_value="config.json"), \
                    patch("instant_app.gui.models.check", return_value={"parakeet": True, "vad": True}), \
                    patch("instant_app.gui.resolve_data_dir", return_value=data_dir), \
                    patch("instant_app.gui.daemon_is_running", return_value=False), \
                    patch("instant_app.gui.autostart.is_enabled", return_value=False), \
                    patch("instant_app.gui.audio.input_choices", return_value=[]), \
                    patch("subprocess.Popen", launch), \
                    patch.dict(sys.modules, {"sounddevice": SimpleNamespace(default=SimpleNamespace(device=(-1, -1)))}):
                window = Window(autostart_override=False)
                self._wait_idle(window)
                window.model_ready = True
                window._start_daemon()
                window._start_daemon()
                self.assertEqual(launch.call_count, 1)
                self.assertEqual(launch.call_args.kwargs["env"]["DICTADO_DATA"], data_dir)
                self.assertEqual(launch.call_args.kwargs["cwd"], gui._workdir())
                self._close_and_wait(window)

        def test_noargs_start_waits_for_readiness_and_starts_once(self):
            Window = gui._main_window_class()
            with patch("instant_app.gui.config.load", return_value={"mic_hint": "", "mic_index": None, "key": "f9", "autostart": False}), \
                    patch("instant_app.gui.models.check", return_value={"parakeet": True, "vad": True}), \
                    patch("instant_app.gui.daemon_is_running", return_value=False), \
                    patch("instant_app.gui.resolve_data_dir", return_value=os.path.join(os.getcwd(), "models")), \
                    patch("instant_app.gui.audio.input_choices", return_value=[]), \
                    patch("instant_app.gui.autostart.is_enabled", return_value=False), \
                    patch.dict(sys.modules, {"sounddevice": SimpleNamespace(default=SimpleNamespace(device=(-1, -1)))}):
                window = Window(start_daemon_on_open=True)
                with patch.object(window, "_start_daemon") as start_daemon:
                    window._maybe_start_daemon_on_open()
                    start_daemon.assert_not_called()
                    self._wait_idle(window)
                    self.assertTrue(window._daemon_state_ready)
                    self.assertTrue(window._microphones_loaded)
                    start_daemon.assert_called_once_with(save_settings=False)
                    window._maybe_start_daemon_on_open()
                    start_daemon.assert_called_once()
                    window._start_daemon_on_open = True
                    window._last_daemon_running = True
                    window._maybe_start_daemon_on_open()
                    start_daemon.assert_called_once()
                self._close_and_wait(window)

        def test_home_status_explains_cli_focus_for_both_daemon_states(self):
            Window = gui._main_window_class()
            for running in (False, True):
                with self.subTest(running=running), \
                        patch("instant_app.gui.config.load", return_value={"key": "f9", "autostart": False}), \
                        patch("instant_app.gui.models.check", return_value={"parakeet": False, "vad": False}), \
                        patch("instant_app.gui.daemon_is_running", return_value=running), \
                        patch("instant_app.gui.audio.input_choices", return_value=[]), \
                        patch.dict(sys.modules, {"sounddevice": SimpleNamespace(default=SimpleNamespace(device=(-1, -1)))}):
                    window = Window()
                    self._wait_idle(window)
                    hint = window.status_detail.text()
                    self.assertIn("prompt o campo editable de la CLI", hint)
                    self.assertIn("Ctrl+V", hint)
                    self.assertNotIn("transcribir", hint.lower())
                    self._close_and_wait(window)
                    del window
                    import gc as _gc
                    _gc.collect()

        def test_setup_route_scrolls_to_audio_section(self):
            Window = gui._main_window_class()
            with patch("instant_app.gui.config.load", return_value={"key": "f9", "autostart": False}), \
                    patch("instant_app.gui.models.check", return_value={"parakeet": False, "vad": False}), \
                    patch("instant_app.gui.daemon_is_running", return_value=False), \
                    patch("instant_app.gui.audio.input_choices", return_value=[]), \
                    patch.dict(sys.modules, {"sounddevice": SimpleNamespace(default=SimpleNamespace(device=(-1, -1)))}):
                window = Window(page="setup", autostart_override=False)
                self._wait_idle(window)
            self.assertEqual(set(window.pages), {"home", "audio", "settings", "models"})
            self.assertEqual(window._current_section, "audio")
            window.navigate("models")
            self.assertEqual(window._current_section, "models")
            window.navigate("home")
            self.assertEqual(window._current_section, "home")
            self._close_and_wait(window)


if __name__ == "__main__":
    unittest.main()
