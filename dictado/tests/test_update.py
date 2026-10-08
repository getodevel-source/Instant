"""Actualizador: versiones, sidecar y ciclo descarga->verifica sin red."""
import hashlib
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import update as update_module


class VersionTests(unittest.TestCase):
    def test_normalize_tolerates_v_prefix(self):
        self.assertEqual(update_module.normalize("v0.1.0"), "0.1.0")
        self.assertEqual(update_module.normalize("  V2.0  "), "2.0")

    def test_is_newer_compares_numbers_not_strings(self):
        self.assertTrue(update_module.is_newer("0.1.0", "0.0.9"))
        self.assertTrue(update_module.is_newer("0.10.0", "0.9.9"))
        self.assertFalse(update_module.is_newer("0.1.0", "0.1.0"))
        self.assertFalse(update_module.is_newer("0.1.0", "0.2.0"))

    def test_check_detects_update_with_mocked_api(self):
        payload = {"tag_name": "v9.9.9", "body": "notas",
                   "assets": [{"name": "Instant.exe",
                               "browser_download_url": "https://x/Instant.exe"}]}
        with patch.object(update_module, "fetch_json", return_value=payload), \
                patch.object(update_module, "current_version", return_value="0.1.0"), \
                patch.object(update_module.sys, "platform", "win32"):
            info = update_module.check()
        self.assertTrue(info["update"])
        self.assertEqual(info["latest"], "9.9.9")
        self.assertEqual(info["asset_url"], "https://x/Instant.exe")

    def test_check_up_to_date(self):
        payload = {"tag_name": "v0.1.0", "body": "",
                   "assets": [{"name": "Instant.exe",
                               "browser_download_url": "https://x/Instant.exe"}]}
        with patch.object(update_module, "fetch_json", return_value=payload), \
                patch.object(update_module, "current_version", return_value="0.1.0"), \
                patch.object(update_module.sys, "platform", "win32"):
            info = update_module.check()
        self.assertFalse(info["update"])

    def test_missing_platform_asset_is_loud(self):
        payload = {"tag_name": "v9.9.9", "body": "", "assets": []}
        with patch.object(update_module, "fetch_json", return_value=payload), \
                patch.object(update_module, "current_version", return_value="0.1.0"), \
                patch.object(update_module.sys, "platform", "win32"):
            with self.assertRaises(LookupError):
                update_module.check()

    def test_api_without_version_raises_instead_of_up_to_date(self):
        with patch.object(update_module, "fetch_json", return_value={}), \
                patch.object(update_module, "current_version", return_value="0.1.0"), \
                patch.object(update_module.sys, "platform", "win32"):
            with self.assertRaises(RuntimeError):
                update_module.check()

    def test_clean_notes_strips_markdown_prefix(self):
        notes = "# Título\n\n- **Cambios** varios\n\nTexto"
        cleaned = update_module.clean_notes(notes)
        self.assertIn("Título", cleaned)
        self.assertNotIn("#", cleaned.splitlines()[0])
        self.assertLessEqual(len(cleaned.splitlines()), 8)


class InstallModeTests(unittest.TestCase):
    def test_source_mode_when_not_frozen(self):
        self.assertEqual(update_module.install_mode(), "source")
        with patch.object(update_module.sys, "platform", "win32"):
            self.assertEqual(update_module.platform_asset("source"),
                             "Instant.exe")

    def test_installed_mode_requires_uninstaller_next_to_exe(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = os.path.join(directory, "Instant.exe")
            open(exe, "wb").close()
            with patch.object(update_module.sys, "frozen", True, create=True), \
                    patch.object(update_module.sys, "executable", exe), \
                    patch.object(update_module.sys, "platform", "win32"):
                self.assertEqual(update_module.install_mode(), "portable")
                self.assertEqual(update_module.platform_asset(),
                                 "Instant.exe")
                open(os.path.join(directory, update_module.UNINSTALLER),
                     "wb").close()
                self.assertEqual(update_module.install_mode(), "installed")
                self.assertEqual(update_module.platform_asset(),
                                 "Instant-Setup.exe")

    def test_check_uses_the_installer_asset_when_installed(self):
        payload = {"tag_name": "v9.9.9", "body": "",
                   "assets": [{"name": "Instant-Setup.exe",
                               "browser_download_url": "https://x/Instant-Setup.exe"}]}
        with tempfile.TemporaryDirectory() as directory:
            exe = os.path.join(directory, "Instant.exe")
            open(exe, "wb").close()
            open(os.path.join(directory, update_module.UNINSTALLER),
                 "wb").close()
            with patch.object(update_module.sys, "frozen", True, create=True), \
                    patch.object(update_module.sys, "executable", exe), \
                    patch.object(update_module.sys, "platform", "win32"), \
                    patch.object(update_module, "fetch_json", return_value=payload), \
                    patch.object(update_module, "current_version",
                                 return_value="0.1.0"):
                info = update_module.check()
        self.assertEqual(info["asset_url"], "https://x/Instant-Setup.exe")

    def test_frozen_unix_is_portable_with_its_own_asset(self):
        with patch.object(update_module.sys, "frozen", True, create=True), \
                patch.object(update_module.sys, "executable",
                             "/opt/instant/instant"), \
                patch.object(update_module.sys, "platform", "linux"):
            self.assertEqual(update_module.install_mode(), "portable")
            self.assertEqual(update_module.platform_asset(), "instant-linux")


class ApplyUpdateTests(unittest.TestCase):
    def test_apply_binary_update_replaces_the_target(self):
        with tempfile.TemporaryDirectory() as directory:
            downloaded = os.path.join(directory, "instant-linux.download")
            target = os.path.join(directory, "instant")
            with open(downloaded, "wb") as handle:
                handle.write(b"nuevo")
            with open(target, "wb") as handle:
                handle.write(b"viejo")
            with patch.object(update_module.sys, "platform", "linux"):
                applied = update_module.apply_binary_update(downloaded, target)
            self.assertEqual(applied, target)
            with open(target, "rb") as handle:
                self.assertEqual(handle.read(), b"nuevo")
            self.assertFalse(os.path.isfile(downloaded))

    def test_apply_binary_update_refuses_on_windows(self):
        with patch.object(update_module.sys, "platform", "win32"):
            with self.assertRaises(RuntimeError):
                update_module.apply_binary_update("descarga", "destino")

    @unittest.skipIf(os.name == "nt",
                     "la semántica de reemplazo en caliente es de POSIX")
    def test_replace_while_running_keeps_the_old_binary_alive(self):
        """El reemplazo en caliente es seguro: el proceso vivo sigue con el inodo viejo."""
        with tempfile.TemporaryDirectory() as directory:
            downloaded = os.path.join(directory, "nuevo")
            target = os.path.join(directory, "binario")
            with open(downloaded, "wb") as handle:
                handle.write(b"version nueva")
            with open(target, "wb") as handle:
                handle.write(b"version vieja")
            with open(target, "rb") as running:
                update_module.apply_binary_update(downloaded, target)
                self.assertEqual(running.read(), b"version vieja")
            with open(target, "rb") as handle:
                self.assertEqual(handle.read(), b"version nueva")


class DownloadVerifyTests(unittest.TestCase):
    def _fixture(self, body):
        directory = tempfile.mkdtemp(prefix="instant-update-test-")
        source = os.path.join(directory, "asset.bin")
        with open(source, "wb") as handle:
            handle.write(body)
        digest = hashlib.sha256(body).hexdigest()
        with open(source + ".sha256", "w", encoding="utf-8") as handle:
            handle.write(f"{digest}  asset.bin\n")
        return directory, source, digest

    def _file_url(self, path):
        return "file:" + path.replace(os.sep, "/")

    def test_cycle_download_verify_ok(self):
        _dir, source, digest = self._fixture(b"nuevo-exe-" * 1000)
        dest = os.path.join(_dir, "out", "Instant.exe")
        expected = update_module.fetch_expected_sha256(self._file_url(source))
        self.assertEqual(expected, digest)
        seen = []
        result = update_module.download(
            self._file_url(source), dest,
            progress=lambda done, total: seen.append((done, total)),
            expected_sha256=expected)
        self.assertEqual(result, dest)
        with open(dest, "rb") as handle:
            self.assertEqual(handle.read(), b"nuevo-exe-" * 1000)
        self.assertTrue(seen)

    def test_tampered_download_is_deleted(self):
        _dir, source, digest = self._fixture(b"original")
        dest = os.path.join(_dir, "Instant.exe")
        with self.assertRaises(ValueError):
            update_module.download(
                self._file_url(source), dest, expected_sha256="0" * 64)
        self.assertFalse(os.path.exists(dest))

    def test_missing_sidecar_refuses(self):
        directory = tempfile.mkdtemp(prefix="instant-update-test-")
        source = os.path.join(directory, "asset.bin")
        with open(source, "wb") as handle:
            handle.write(b"sin-sidecar")
        with self.assertRaises(RuntimeError):
            update_module.fetch_expected_sha256(self._file_url(source))

    def test_midstream_failure_leaves_no_part(self):
        from unittest.mock import MagicMock
        directory = tempfile.mkdtemp(prefix="instant-update-test-")
        dest = os.path.join(directory, "Instant.exe")
        response = MagicMock()
        response.read.side_effect = [b"mitad", ConnectionError("corte")]
        context = MagicMock()
        context.__enter__.return_value = response
        with patch("urllib.request.urlopen", return_value=context):
            with self.assertRaises(ConnectionError):
                update_module.download("https://x/Instant.exe", dest,
                                       expected_sha256="f" * 64)
        self.assertFalse(os.path.exists(dest))
        self.assertFalse(os.path.exists(dest + ".part"))

    def test_verified_file_lands_at_final_path(self):
        _dir, source, digest = self._fixture(b"final-" * 500)
        dest = os.path.join(_dir, "Instant.exe")
        result = update_module.download(
            self._file_url(source), dest, expected_sha256=digest)
        self.assertEqual(result, dest)
        self.assertTrue(os.path.exists(dest))
        self.assertFalse(os.path.exists(dest + ".part"))


try:
    import PySide6  # noqa: F401
except ImportError:
    print("SKIP Qt update button: PySide6 is not installed")
else:
    import os as _os
    from types import SimpleNamespace as _SimpleNamespace
    from unittest.mock import patch as _patch

    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    class QtUpdateButtonTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            import gc as _gc
            _gc.disable()
            from PySide6.QtWidgets import QApplication
            cls.app = QApplication.instance() or QApplication([])

        @classmethod
        def tearDownClass(cls):
            import gc as _gc
            _gc.enable()
            _gc.collect()

        def _window(self):
            from PySide6.QtCore import QEventLoop
            from instant_app import gui
            Window = gui._main_window_class()
            with _patch("instant_app.gui.config.load", return_value={"mic_hint": "USB Mic", "mic_index": 5, "key": "f9", "autostart": False}), \
                    _patch("instant_app.gui.models.check", return_value={"parakeet": True, "vad": True}), \
                    _patch("instant_app.gui.daemon_is_running", return_value=False), \
                    _patch("instant_app.gui.audio.input_choices", return_value=[(5, "USB Mic", 1, 48000)]), \
                    _patch("instant_app.gui.audio.preferred_input_index", side_effect=lambda default, _rows: default), \
                    _patch("instant_app.gui.autostart.is_enabled", return_value=False), \
                    _patch.dict(sys.modules, {"sounddevice": _SimpleNamespace(default=_SimpleNamespace(device=(5, -1)))}):
                window = Window(autostart_override=False)
                window.show()
                if not window._microphones_loaded:
                    loop = QEventLoop()
                    window.microphones_loaded.connect(loop.quit)
                    if not window._microphones_loaded:
                        loop.exec()
                if window._pending_workers:
                    idle = QEventLoop()
                    window.workers_idle.connect(idle.quit)
                    if window._pending_workers:
                        idle.exec()
            return window

        def _toasts(self, window):
            from PySide6.QtWidgets import QFrame
            return window._toast_host.findChildren(QFrame, "toast")

        def _toast_texts(self, window):
            from PySide6.QtWidgets import QLabel
            texts = []
            for card in self._toasts(window):
                texts.append(" ".join(
                    label.text() for label in card.findChildren(QLabel)))
            return texts

        def _click_toast_button(self, window, label):
            from PySide6.QtWidgets import QPushButton
            for card in self._toasts(window):
                for button in card.findChildren(QPushButton):
                    if button.text() == label:
                        button.click()
                        return True
            return False

        def _wait_idle(self, window):
            from PySide6.QtCore import QEventLoop
            if window._pending_workers:
                loop = QEventLoop()
                window.workers_idle.connect(loop.quit)
                if window._pending_workers:
                    loop.exec()

        def _close(self, window):
            from PySide6.QtCore import QEventLoop
            if not window._closed:
                window.close()
            if window._pending_workers:
                loop = QEventLoop()
                window.workers_idle.connect(loop.quit)
                if window._pending_workers:
                    loop.exec()

        def test_check_reports_up_to_date_as_toast(self):
            window = self._window()
            try:
                info = {"update": False, "current": "0.1.0", "latest": "0.1.0",
                        "notes": "", "asset": "Instant.exe", "asset_url": ""}
                with _patch("instant_app.update.check", return_value=info):
                    window.update_button.click()
                    self._wait_idle(window)
                self.assertTrue(window.update_button.isEnabled())
                self.assertTrue(
                    any("al día" in text for text in self._toast_texts(window)),
                    self._toast_texts(window))
            finally:
                self._close(window)

        def test_silent_check_dresses_button_without_modals(self):
            window = self._window()
            try:
                info = {"update": True, "current": "0.1.0", "latest": "0.2.0",
                        "notes": "", "asset": "Instant.exe", "asset_url": ""}
                window._apply_update_available(info)
                self.assertIn("0.2.0", window.update_button.text())
                self.assertEqual(window.update_button.objectName(), "primaryButton")
            finally:
                self._close(window)

        def test_update_decisions_happen_in_toasts(self):
            window = self._window()
            try:
                info = {"update": True, "current": "0.1.0", "latest": "0.2.0",
                        "notes": "Novedades", "asset": "Instant.exe",
                        "asset_url": "https://x/Instant.exe"}
                with _patch("instant_app.update.check", return_value=info):
                    window.update_button.click()
                    self._wait_idle(window)
                with _patch("instant_app.update.fetch_expected_sha256",
                             return_value="a" * 64), \
                        _patch("instant_app.update.download",
                               return_value=("C:\\tmp\\Instant.exe", "a" * 64)), \
                        _patch("instant_app.gui.os.path.isfile",
                               return_value=True), \
                        _patch("instant_app.gui.subprocess.Popen") as popen:
                    self.assertTrue(
                        self._click_toast_button(window, "Descargar"),
                        self._toast_texts(window))
                    self._wait_idle(window)
                    self.assertTrue(
                        self._click_toast_button(window, "Instalar ahora"),
                        self._toast_texts(window))
                    popen.assert_called_once()
                    args, kwargs = popen.call_args
                    self.assertEqual(args[0][:3], ["cmd", "/c", args[0][2]])
                    self.assertTrue(args[0][2].endswith("instant-update.bat"))
                self.assertTrue(window._closed)
            finally:
                self._close(window)

if __name__ == "__main__":
    unittest.main()
