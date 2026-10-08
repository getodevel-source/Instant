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


class SyncTasks:
    """TaskRunner sincrónico para los flujos de actualización."""

    def __init__(self):
        self.pending = 0
        self.on_idle = None
        self.on_error = None

    def submit(self, fn, on_result=None, on_error=None, on_progress=None):
        self.pending += 1
        try:
            value = fn(lambda payload: on_progress and on_progress(payload))
        except Exception as exc:  # noqa: BLE001  (igual que el runner real)
            if on_error is not None:
                on_error(exc)
            value = None
        else:
            if on_result is not None:
                on_result(value)
        finally:
            self.pending -= 1
        return id(fn)

    def drain(self):
        return 0

    def close(self):
        self.pending = 0


class UpdateFlowTests(unittest.TestCase):
    """Botón y toasts de actualización: el flujo completo de PanelLogic."""

    def _logic(self, cfg=None):
        from types import SimpleNamespace
        from instant_app import gui
        emitted = []
        base_cfg = {"mic_hint": "", "mic_index": None, "key": "f9",
                    "autostart": False, "update_last_check": 0}
        base_cfg.update(cfg or {})
        with patch("instant_app.gui.config.load", return_value=base_cfg), \
                patch("instant_app.gui.models.check", return_value={"parakeet": True, "vad": True}), \
                patch("instant_app.gui.resolve_data_dir", return_value=os.path.join(os.getcwd(), "models")), \
                patch("instant_app.gui.daemon_is_running", return_value=False), \
                patch("instant_app.gui.audio.input_choices", return_value=[]), \
                patch("instant_app.gui.autostart.is_enabled", return_value=False), \
                patch.dict(sys.modules, {"sounddevice": SimpleNamespace(
                    default=SimpleNamespace(device=(-1, -1)))}):
            logic = gui.PanelLogic(
                emit=lambda kind, payload: emitted.append((kind, payload)),
                tasks=SyncTasks(), schedule=lambda ms, fn: None)
        return logic, emitted

    def _toasts(self, emitted):
        return [payload for kind, payload in emitted if kind == "toast"]

    def test_check_reports_up_to_date_as_toast(self):
        logic, emitted = self._logic()
        info = {"update": False, "current": "0.1.0", "latest": "0.1.0",
                "notes": "", "asset": "Instant.exe", "asset_url": ""}
        with patch("instant_app.update.check", return_value=info):
            logic.check_updates()
        self.assertEqual(logic.update_button, "Buscar actualizaciones")
        self.assertTrue(any("al día" in toast["message"] for toast in self._toasts(emitted)),
                        self._toasts(emitted))

    def test_silent_check_dresses_button_without_modals(self):
        logic, emitted = self._logic()
        info = {"update": True, "current": "0.1.0", "latest": "0.2.0",
                "notes": "", "asset": "Instant.exe", "asset_url": ""}
        with patch("instant_app.update.check", return_value=info) as check, \
                patch("instant_app.gui.config.save", return_value="config.json"):
            logic._silent_update_check()
            self.assertIn("0.2.0", logic.update_button)
            self.assertEqual(logic.state_payload()["updates"]["button"],
                             logic.update_button)
            # Silencioso: avisa con el botón, sin toasts.
            self.assertEqual(self._toasts(emitted), [])
            # Sellado diario: un segundo intento no vuelve a consultar.
            logic._update_silent_done = False
            logic._silent_update_check()
            self.assertEqual(check.call_count, 1)

    def test_update_decisions_happen_in_toasts(self):
        logic, emitted = self._logic()
        info = {"update": True, "current": "0.1.0", "latest": "0.2.0",
                "notes": "Novedades", "asset": "Instant.exe",
                "asset_url": "https://x/Instant.exe"}
        with patch("instant_app.update.check", return_value=info):
            logic.check_updates()
        offer = [toast for toast in self._toasts(emitted)
                 if "versión nueva" in toast["title"]]
        self.assertTrue(offer)
        self.assertEqual([a["label"] for a in offer[-1]["actions"]],
                         ["Descargar", "Ahora no"])

        # "Descargar" → descarga verificada → oferta de instalar.
        with patch("instant_app.update.fetch_expected_sha256", return_value="a" * 64), \
                patch("instant_app.update.download",
                      return_value=("C:\\tmp\\Instant.exe", "a" * 64)):
            logic._op_toast_action({"op": "toast_action", "id": offer[-1]["id"],
                                    "action": "0"})
        verified = [toast for toast in self._toasts(emitted)
                    if toast["title"] == "Descarga verificada"]
        self.assertTrue(verified)
        self.assertEqual([a["label"] for a in verified[-1]["actions"]],
                         ["Instalar ahora", "Después"])

        # "Instalar ahora" → portable con script: lanza el .bat y cierra.
        with patch("instant_app.update.install_mode", return_value="portable"), \
                patch("instant_app.gui.os.path.isfile", return_value=True), \
                patch("instant_app.gui.subprocess.Popen") as popen:
            logic._op_toast_action({"op": "toast_action", "id": verified[-1]["id"],
                                    "action": "0"})
        popen.assert_called_once()
        args = popen.call_args.args[0]
        self.assertEqual(args[0], "cmd")
        self.assertTrue(args[2].endswith("instant-update.bat"))
        self.assertTrue(logic._closed)


if __name__ == "__main__":
    unittest.main()
