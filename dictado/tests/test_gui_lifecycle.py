"""Ciclo de vida del panel (`PanelLogic`), sin Qt ni WebEngine.

Cubre el comportamiento de consumidor: qué pasa al cerrar, cuándo arranca el
daemon, cómo se rutean las actualizaciones y qué copy ve el usuario en cada
estado. El dibujo de la página lo cubre `test_panel_page.py`; el motor real
(QtWebEngine) se prueba con el smoke manual.
"""
import os
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import gui


def daemon_spawns(mock):
    """Llamadas a Popen que son el arranque del daemon (instant ... run).

    En Linux, importar sounddevice dispara `ldconfig` por ctypes y ese Popen
    también pasa por el parche: contar crudo daba falsos positivos.
    """
    found = []
    for entry in mock.call_args_list:
        if not entry.args:
            continue
        argv = entry.args[0]
        if not isinstance(argv, (list, tuple)):
            continue
        if any("instant" in str(part).lower() for part in argv):
            found.append(entry)
    return found

CFG = {"mic_hint": "", "mic_index": None, "key": "f9", "autostart": False}


class SyncTasks:
    """TaskRunner sincrónico: aplica el trabajo en el acto (determinista)."""

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
            elif self.on_error is not None:
                self.on_error(exc)
            value = None
        else:
            if on_result is not None:
                on_result(value)
        finally:
            self.pending -= 1
        if self.on_idle is not None:
            self.on_idle()
        return id(fn)

    def drain(self):
        return 0

    def close(self):
        self.pending = 0


def make_logic(emitted=None, tasks=None, schedule=None, **kwargs):
    emitted = emitted if emitted is not None else []
    with patch("instant_app.gui.config.load", return_value=dict(CFG)), \
            patch("instant_app.gui.models.check", return_value={"parakeet": True, "vad": True}), \
            patch("instant_app.gui.resolve_data_dir", return_value=os.path.join(os.getcwd(), "models")), \
            patch("instant_app.gui.daemon_is_running", return_value=False), \
            patch("instant_app.gui.audio.input_choices", return_value=[]), \
            patch("instant_app.gui.autostart.is_enabled", return_value=False), \
            patch.dict(sys.modules, {"sounddevice": SimpleNamespace(
                default=SimpleNamespace(device=(-1, -1)))}):
        logic = gui.PanelLogic(
            emit=lambda kind, payload: emitted.append((kind, payload)),
            tasks=tasks if tasks is not None else SyncTasks(),
            schedule=schedule if schedule is not None else (lambda ms, fn: None),
            **kwargs)
    return logic, emitted


class PanelLifecycleTests(unittest.TestCase):
    def test_home_status_explains_cli_focus_for_both_daemon_states(self):
        for running in (False, True):
            with self.subTest(running=running):
                logic, _emitted = make_logic()
                with patch("instant_app.gui.daemon_is_running", return_value=running):
                    logic.refresh_daemon()
                state = logic.state_payload()
                self.assertEqual(state["status"]["state"],
                                 "ok" if running else "down")
                self.assertEqual(state["status"]["title"],
                                 "Instant está activo" if running else "Listo para dictar")
                self.assertIn("mantené F9", state["status"]["detail"])
                self.assertIn("Ctrl+V", state["status"]["detail"])

    def test_closing_drops_late_results_without_touching_daemon(self):
        started, release = threading.Event(), threading.Event()
        seen = []
        logic, _emitted = make_logic(tasks=gui.TaskRunner())

        def slow(_emit):
            started.set()
            release.wait(5)
            return "tarde"

        logic.tasks.submit(slow, lambda value: seen.append(value))
        self.assertTrue(started.wait(2))
        with patch("instant_app.gui.daemon_is_running",
                   side_effect=AssertionError("close consultó el daemon")), \
                patch("instant_app.gui.stop_daemon",
                      side_effect=AssertionError("close frenó el daemon")):
            logic.close()
        release.set()
        deadline = time.monotonic() + 3
        while logic.tasks.pending and time.monotonic() < deadline:
            logic.tasks.drain()
            time.sleep(0.02)
        logic.tasks.drain()
        self.assertTrue(logic._closed)
        self.assertEqual(seen, [])

    def test_daemon_inherits_resolved_model_directory_and_start_is_single_flight(self):
        launch = Mock()
        logic, _emitted = make_logic()
        logic._daemon_state_ready = True
        logic._microphones_loaded = True
        logic.model_ready = True
        with patch("subprocess.Popen", launch):
            logic._start_daemon(save_settings=False)
            logic._start_daemon(save_settings=False)
        spawns = daemon_spawns(launch)
        self.assertEqual(len(spawns), 1)
        self.assertEqual(spawns[0].kwargs["env"]["DICTADO_DATA"], logic.data_dir)
        self.assertEqual(spawns[0].kwargs["cwd"], gui._workdir())

    def test_noargs_start_waits_for_readiness_and_starts_once(self):
        import traceback

        calls = []

        def record_popen(*args, **kwargs):
            calls.append("".join(traceback.format_stack(limit=8)))
            return Mock()

        logic, _emitted = make_logic(start_daemon_on_open=True)
        logic.model_ready = True

        def why():
            return (f"spawns={len(daemon_spawns(launch))} "
                    f"pending={logic._daemon_start_pending} "
                    f"token={logic._daemon_start_token}\n" + "\n---\n".join(calls))

        with patch("subprocess.Popen", side_effect=record_popen) as launch:
            logic._maybe_start_daemon_on_open()
            self.assertEqual(daemon_spawns(launch), [])
            with patch("instant_app.gui.daemon_is_running", return_value=False):
                logic.refresh_daemon()
            logic.refresh_microphones(initial=True)
            self.assertTrue(logic._daemon_state_ready)
            self.assertTrue(logic._microphones_loaded)
            logic._maybe_start_daemon_on_open()
            self.assertEqual(len(daemon_spawns(launch)), 1, why())
            logic._maybe_start_daemon_on_open()
            self.assertEqual(len(daemon_spawns(launch)), 1, why())
            # Daemon ya corriendo: no se arranca de nuevo.
            logic._start_daemon_on_open = True
            logic._last_daemon_running = True
            logic._maybe_start_daemon_on_open()
            self.assertEqual(len(daemon_spawns(launch)), 1, why())

    def test_start_refuses_without_models(self):
        launch = Mock()
        logic, emitted = make_logic()
        logic._daemon_state_ready = True
        logic._microphones_loaded = True
        logic.model_ready = False
        with patch("subprocess.Popen", launch):
            self.assertFalse(logic._start_daemon(save_settings=False))
        self.assertEqual(daemon_spawns(launch), [])
        titles = [payload["title"] for kind, payload in emitted if kind == "toast"]
        self.assertIn("Modelos pendientes", titles)

    def test_daemon_start_timeout_sets_recovery_copy(self):
        scheduled = []
        logic, _emitted = make_logic(schedule=lambda ms, fn: scheduled.append((ms, fn)))
        logic._daemon_state_ready = True
        logic._microphones_loaded = True
        logic.model_ready = True
        with patch("subprocess.Popen", Mock()):
            self.assertTrue(logic._start_daemon(save_settings=False))
        timeouts = [fn for ms, fn in scheduled if ms == 10000]
        self.assertEqual(len(timeouts), 1)
        timeouts[0]()
        self.assertFalse(logic._daemon_start_pending)
        self.assertEqual(logic.status_detail, gui.DAEMON_MISSING_DETAIL)

    def test_update_routes_by_install_mode(self):
        # Instalado (Windows): frena el daemon y lanza el Setup en silencio.
        logic, _emitted = make_logic()
        with patch("instant_app.update.install_mode", return_value="installed"), \
                patch("instant_app.gui.stop_daemon") as stop, \
                patch("instant_app.gui.daemon_is_running", return_value=False), \
                patch("subprocess.Popen") as popen:
            logic._install_ready("C:/tmp/Instant-Setup.exe", "ab" * 32)
        stop.assert_called_once()
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0][1:],
                         ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
        self.assertTrue(logic._closed)

        # Unix congelado: reemplazo en caliente + reinicio del dictado.
        logic, emitted = make_logic()
        with patch.object(sys, "frozen", True, create=True), \
                patch.object(sys, "platform", "linux"), \
                patch("instant_app.update.install_mode", return_value="portable"), \
                patch("instant_app.update.apply_binary_update",
                      return_value="/usr/local/bin/instant") as apply_update, \
                patch.object(logic, "stop_daemon_flow") as restart:
            logic._install_ready("/tmp/instant-linux", "cd" * 32)
        apply_update.assert_called_once_with("/tmp/instant-linux")
        restart.assert_called_once_with(restart=True)

        # Portable sin script: aviso con instrucciones, sin lanzar nada.
        logic, emitted = make_logic()
        with patch("instant_app.update.install_mode", return_value="portable"), \
                patch("os.path.isfile", return_value=False), \
                patch("subprocess.Popen") as popen:
            logic._install_ready("C:/tmp/instant.exe", "ef" * 32)
        popen.assert_not_called()
        messages = [payload for kind, payload in emitted if kind == "toast"]
        self.assertTrue(any("instant-update.bat" in item["message"] for item in messages))

    def test_apply_gui_action_scrolls_to_audio_and_requests_start(self):
        logic, emitted = make_logic()
        logic.apply_gui_action("setup", start_daemon=False)
        self.assertIn(("navigate", {"page": "audio"}), emitted)
        logic.apply_gui_action(None, start_daemon=True)
        self.assertTrue(logic._start_daemon_on_open)
        self.assertIn(("navigate", {"page": "home"}), emitted)


if __name__ == "__main__":
    unittest.main()
