"""User-visible Qt settings and microphone-selection regressions."""
import os
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import gui


class DeviceCatalogTests(unittest.TestCase):
    def test_unique_device_survives_index_shift_and_ambiguous_duplicate_does_not(self):
        catalog = gui.DeviceCatalog({"mic_hint": "USB Mic", "mic_index": 5})
        choices = [(5, "USB Mic", 1, 48000), (8, "USB Mic", 1, 48000)]
        sd = SimpleNamespace(default=SimpleNamespace(device=(5, -1)))
        with patch("instant_app.gui.audio.input_choices", return_value=choices), \
                patch("instant_app.gui.audio.preferred_input_index", side_effect=lambda default, _rows: default), \
                patch.dict(sys.modules, {"sounddevice": sd}):
            labels, selected, missing = catalog.refresh()
        self.assertEqual(selected, "USB Mic [5] (predeterminado)")
        self.assertFalse(missing)
        catalog.remember(catalog.devices["USB Mic [8]"])
        shifted = [(12, "USB Mic", 1, 48000), (18, "USB Mic", 1, 48000)]
        sd.default.device = (12, -1)
        with patch("instant_app.gui.audio.input_choices", return_value=shifted), \
                patch("instant_app.gui.audio.preferred_input_index", side_effect=lambda default, _rows: default), \
                patch.dict(sys.modules, {"sounddevice": sd}):
            labels, selected, missing = catalog.refresh(catalog.pending_device, preserve=True)
        self.assertIsNone(selected)
        self.assertTrue(missing)
        self.assertEqual(set(labels), {"USB Mic [12] (predeterminado)", "USB Mic [18]"})

    def test_refresh_preserves_unique_name_when_only_index_changes(self):
        catalog = gui.DeviceCatalog({"mic_hint": "USB Mic", "mic_index": 5})
        sd = SimpleNamespace(default=SimpleNamespace(device=(5, -1)))
        with patch("instant_app.gui.audio.input_choices", return_value=[(5, "USB Mic", 1, 48000)]), \
                patch("instant_app.gui.audio.preferred_input_index", side_effect=lambda default, _rows: default), \
                patch.dict(sys.modules, {"sounddevice": sd}):
            catalog.refresh()
        catalog.remember((5, "USB Mic"))
        sd.default.device = (12, -1)
        with patch("instant_app.gui.audio.input_choices", return_value=[(12, "USB Mic", 1, 48000)]), \
                patch("instant_app.gui.audio.preferred_input_index", side_effect=lambda default, _rows: default), \
                patch.dict(sys.modules, {"sounddevice": sd}):
            _labels, selected, missing = catalog.refresh(catalog.pending_device, preserve=True)
        self.assertIsNotNone(selected)
        self.assertFalse(missing)
        self.assertEqual(catalog.devices[selected], (12, "USB Mic"))


try:
    import PySide6  # noqa: F401
except ImportError:
    print("SKIP Qt settings behavior: PySide6 is not installed")
else:
    class QtSettingsTests(unittest.TestCase):
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
            # Igual que en test_gui_lifecycle: destruir ventanas viejas fuera
            # de todo event loop para un teardown determinista en offscreen.
            import gc as _gc
            _gc.collect()

        def _wait_idle(self, window):
            """Espera a que no haya workers y a que se apliquen sus resultados.

            `workers_idle` sale del pool apenas termina el worker, pero el
            resultado viaja como señal encolada y puede aplicarse un instante
            después; sin drenar el loop, el estado del panel queda a medias
            (en macOS esto hacía flaky el test del poll fallido).
            """
            from PySide6.QtCore import QEventLoop, QTimer

            loop = QEventLoop()
            window.workers_idle.connect(loop.quit)
            if window._pending_workers:
                loop.exec()
            settle = QEventLoop()
            QTimer.singleShot(30, settle.quit)
            settle.exec()
            self.assertFalse(window._pending_workers)

        def _close_and_wait(self, window):
            if not window._closed:
                window.close()
            self._wait_idle(window)

        def _window(self):
            from PySide6.QtCore import QEventLoop
            Window = gui._main_window_class()
            with patch("instant_app.gui.config.load", return_value={"mic_hint": "USB Mic", "mic_index": 5, "key": "f9", "autostart": False}), \
                    patch("instant_app.gui.models.check", return_value={"parakeet": False, "vad": False}), \
                    patch("instant_app.gui.daemon_is_running", return_value=False), \
                    patch("instant_app.gui.audio.input_choices", return_value=[(5, "USB Mic", 1, 48000)]), \
                    patch("instant_app.gui.audio.preferred_input_index", side_effect=lambda default, _rows: default), \
                    patch("instant_app.gui.autostart.is_enabled", return_value=False), \
                    patch.dict(sys.modules, {"sounddevice": SimpleNamespace(default=SimpleNamespace(device=(5, -1)))}):
                window = Window(autostart_override=False)
                window.show()
                if not window._microphones_loaded:
                    loop = QEventLoop()
                    window.microphones_loaded.connect(loop.quit)
                    if not window._microphones_loaded:
                        loop.exec()
                self._wait_idle(window)
            return window

        def test_dirty_saved_restart_and_autostart_precedence(self):
            window = self._window()
            try:
                self.assertEqual(window._selected_device(), (5, "USB Mic"))
                window._set_key("f10")
                window._last_daemon_running = True
                self.assertIn("sin guardar", window.settings_status.text().casefold())
                with patch("instant_app.gui.config.save", return_value="settings.json"), \
                        patch("instant_app.gui.autostart.is_enabled", return_value=False):
                    window.save_config(show_message=False)
                self.assertIn("reiniciá Instant", window.settings_status.text())
                window._settings_daemon_changed(False)
                window._settings_daemon_changed(True)
                self.assertEqual(window.settings_status.text(), "Ajustes guardados.")
                window.autostart_check.setChecked(True)
                with patch("instant_app.gui.config.save", return_value="settings.json"), \
                        patch("instant_app.gui.autostart.is_enabled", return_value=False), \
                        patch("instant_app.gui.autostart.enable"):
                    window.save_config(show_message=False)
                self.assertEqual(window.settings_status.text(), "Ajustes guardados.")
            finally:
                self._close_and_wait(window)

        def test_start_is_ready_after_daemon_check_without_a_microphone(self):
            Window = gui._main_window_class()
            with patch("instant_app.gui.config.load", return_value={"key": "f9", "autostart": False}), \
                    patch("instant_app.gui.models.check", return_value={"parakeet": True, "vad": True}), \
                    patch("instant_app.gui.daemon_is_running", return_value=False), \
                    patch("instant_app.gui.audio.input_choices", return_value=[]), \
                    patch("instant_app.gui.autostart.is_enabled", return_value=False), \
                    patch.dict(sys.modules, {"sounddevice": SimpleNamespace(default=SimpleNamespace(device=(-1, -1)))}):
                window = Window(autostart_override=False)
                window.show()
                try:
                    self.assertFalse(window._daemon_state_ready)
                    self.assertFalse(window.run_button.isEnabled())
                    self._wait_idle(window)
                    self.assertTrue(window._daemon_state_ready)
                    self.assertIsNone(window._selected_device())
                    self.assertTrue(window.run_button.isEnabled())
                    with patch.object(gui.sys, "frozen", True, create=True):
                        expected = gui.app_command(("run",))
                        with patch.object(window, "save_config") as save, \
                                patch("instant_app.gui.subprocess.Popen") as launch, \
                                patch("instant_app.gui._workdir", return_value="workdir"):
                            window.toggle_daemon()
                    save.assert_called_once_with(False)
                    launch.assert_called_once()
                    self.assertEqual(launch.call_args.args[0], expected)
                    self.assertEqual(
                        launch.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"],
                        "1")
                finally:
                    self._close_and_wait(window)

        def test_failed_daemon_poll_keeps_start_disabled_until_retry(self):
            Window = gui._main_window_class()
            attempts = iter((RuntimeError("status unavailable"), False))
            def status():
                result = next(attempts)
                if isinstance(result, Exception):
                    raise result
                return result
            with patch("instant_app.gui.config.load", return_value={"key": "f9", "autostart": False}), \
                    patch("instant_app.gui.models.check", return_value={"parakeet": False, "vad": False}), \
                    patch("instant_app.gui.daemon_is_running", side_effect=status), \
                    patch("instant_app.gui.audio.input_choices", return_value=[]), \
                    patch("instant_app.gui.autostart.is_enabled", return_value=False), \
                    patch.dict(sys.modules, {"sounddevice": SimpleNamespace(default=SimpleNamespace(device=(-1, -1)))}):
                window = Window(autostart_override=False)
                window.show()
                try:
                    self._wait_idle(window)
                    self.assertFalse(window._daemon_state_ready)
                    self.assertFalse(window._daemon_check_pending)
                    self.assertFalse(window.run_button.isEnabled())
                    window.refresh_daemon()
                    self._wait_idle(window)
                    self.assertTrue(window._daemon_state_ready)
                    self.assertTrue(window.run_button.isEnabled())
                finally:
                    self._close_and_wait(window)

        def test_callback_microphone_probe_uses_selected_device_for_three_seconds(self):
            from PySide6.QtCore import QEventLoop
            window = self._window()
            def fake_peak(device, seconds, on_level):
                on_level(0.25)
                return 0.25
            try:
                with patch("instant_app.gui.audio.peak_meter", side_effect=fake_peak) as capture:
                    window.test_microphone()
                    loop = QEventLoop()
                    window.workers_idle.connect(loop.quit)
                    if window._pending_workers:
                        loop.exec()
                capture.assert_called_once()
                self.assertEqual(capture.call_args.args[0], 5)
                self.assertEqual(capture.call_args.kwargs["seconds"], 3.0)
                self.assertIn("Señal detectada", window.meter_text.text())
            finally:
                self._close_and_wait(window)

        def test_key_capture_rejects_combinations_normalizes_key_and_cancels(self):
            from PySide6.QtCore import Qt
            from PySide6.QtTest import QTest
            window = self._window()
            try:
                window.begin_key_capture()
                dialog = window._key_capture_dialog
                QTest.keyClick(dialog, Qt.Key_F10, Qt.ControlModifier)
                self.assertTrue(dialog.isVisible())
                self.assertIn("sin combinación", dialog.message.text())
                QTest.keyClick(dialog, Qt.Key_F10)
                self.assertEqual(window.key_value.text(), "F10")
                window.begin_key_capture()
                window._key_capture_dialog.reject()
                self.assertEqual(window.key_value.text(), "F10")
            finally:
                self._close_and_wait(window)

        def test_refresh_keeps_catalog_stable_and_disables_save_until_commit(self):
            from PySide6.QtCore import QEventLoop
            window = self._window()
            started, release = threading.Event(), threading.Event()
            old_catalog = window.catalog
            old_snapshot = window._snapshot()
            def blocked_inputs():
                started.set()
                if not release.wait(3):
                    raise TimeoutError("test did not release microphone enumeration")
                return [(12, "USB Mic", 1, 48000)]
            try:
                with patch("instant_app.gui.audio.input_choices", side_effect=blocked_inputs), \
                        patch("instant_app.gui.audio.preferred_input_index", side_effect=lambda default, _rows: default), \
                        patch.dict(sys.modules, {"sounddevice": SimpleNamespace(default=SimpleNamespace(device=(12, -1)))}):
                    loop = QEventLoop()
                    window.microphones_loaded.connect(loop.quit)
                    window.refresh_microphones()
                    self.assertTrue(started.wait(2))
                    self.assertIs(window.catalog, old_catalog)
                    self.assertEqual(window.catalog.rows, old_catalog.rows)
                    self.assertEqual(window._snapshot(), old_snapshot)
                    self.assertFalse(window.save_button.isEnabled())
                    release.set()
                    if not window._microphones_loaded:
                        loop.exec()
                    self._wait_idle(window)
                self.assertIsNot(window.catalog, old_catalog)
                self.assertEqual(window._selected_device(), (12, "USB Mic"))
                self.assertTrue(window.save_button.isEnabled())
            finally:
                release.set()
                self._close_and_wait(window)

        def test_context_profiles_save_terms_and_preserve_unsaved_profile_edits(self):
            window = self._window()
            window._last_daemon_running = True
            window._settings_daemon_changed(True)
            saved = {}
            def save(value):
                saved.update(value)
                return "settings.json"
            try:
                window.navigate("settings")
                self.assertEqual(window._current_section, "settings")
                self.assertTrue(window.context_combo.isVisible())
                self.assertTrue(window.vocab_table.isVisible())
                self.assertFalse(hasattr(window, "llm_url_edit"))
                window._vocab_set_rows([
                    {"term": "Instant", "aliases": ["instante", "in stand"],
                     "sonido": False}])
                self.assertEqual(window._vocab_rows(), [
                    {"term": "Instant", "aliases": ["instante", "in stand"],
                     "sonido": False}])
                window.context_combo.addItem("Trabajo")
                window.context_combo.setCurrentText("Trabajo")
                window._vocab_set_rows([
                    {"term": "Parakeet", "aliases": ["para kit"],
                     "sonido": True}])
                window.cfg["llm_url"] = "http://127.0.0.1:8080"
                with patch("instant_app.gui.config.save", side_effect=save), \
                        patch("instant_app.gui.autostart.is_enabled", return_value=False):
                    window.save_config(show_message=False)
                self.assertEqual(saved["active_context"], "Trabajo")
                self.assertEqual(saved["llm_url"], "http://127.0.0.1:8080")
                self.assertEqual(
                    saved["context_profiles"]["General"],
                    [{"term": "Instant", "aliases": ["instante", "in stand"],
                      "sonido": False}])
                self.assertEqual(
                    saved["context_profiles"]["Trabajo"],
                    [{"term": "Parakeet", "aliases": ["para kit"],
                      "sonido": True}])
                self.assertIn("vocabulario", window.settings_status.text())
                self.assertIn("LLM", window.settings_status.text())
                window._settings_daemon_changed(True)
                self.assertIn("vocabulario", window.settings_status.text())
            finally:
                self._close_and_wait(window)

        def test_vocab_delete_button_removes_only_its_row(self):
            from PySide6.QtWidgets import QPushButton
            window = self._window()
            try:
                window._vocab_set_rows([
                    {"term": "Instant", "aliases": ["instante"],
                     "sonido": False},
                    {"term": "Parakeet", "aliases": ["para kit"],
                     "sonido": True}])
                table = window.vocab_table
                self.assertEqual(table.rowCount(), 2)
                wrap = table.cellWidget(0, 3)
                button = wrap.findChild(QPushButton)
                button.click()
                self.assertEqual(table.rowCount(), 1)
                self.assertEqual(window._vocab_rows(), [
                    {"term": "Parakeet", "aliases": ["para kit"],
                     "sonido": True}])
            finally:
                self._close_and_wait(window)

        def test_close_keeps_daemon_independent(self):
            window = self._window()
            try:
                with patch("instant_app.gui.daemon_is_running", side_effect=AssertionError("close must not inspect daemon")):
                    window.close()
                self.assertTrue(window._closed)
            finally:
                self._close_and_wait(window)


if __name__ == "__main__":
    unittest.main()
