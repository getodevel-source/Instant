"""Panel de Instant: ventana QtWebEngine con la UI en web (web/panel.html).

La migración separa el comportamiento de la ventana:

- `PanelLogic`: todo el estado y las acciones del panel, sin Qt. Los hilos de
  trabajo entregan por `TaskRunner` y el hilo de UI aplica con `drain()`. Los
  efectos visibles salen por `emit(kind, payload)`:
      state | toast | meter | progress | diagnostics | key_result | navigate | close
- `_WebPanel`: la ventana (host QML + WebEngineView + QWebChannel) que conecta
  el protocolo de `web/panel.html` con `PanelLogic`.

Contrato con la página (QWebChannel, objeto `bridge`):
    JS -> Python: bridge.call(json)   con {"op": ..., ...} (ver PanelLogic.handle)
    Python -> JS: señales state/toast/meter/progress/diagnostics/key_result
                  (cada payload es un JSON string)
La API pública hacia afuera es la de siempre: `run_gui`, `daemon_is_running`,
`stop_daemon`, `DeviceCatalog`, el canal de instancia única y los helpers.
"""
import ctypes
import json
import logging
import os
import queue
import signal
import subprocess
import sys
import threading
import time

from instant_app import audio, autostart, config, context, hotkey, models
from instant_app.branding import PALETTE  # noqa: F401  (paleta viva del proyecto)
from instant_app.launch import app_command, app_environment
from instant_app.paths import resolve_data_dir

log = logging.getLogger("instant")

_APP_USER_MODEL_ID = "getodevel-source.Instant.0.1"
UPDATE_CHECK_INTERVAL = 86400
DAEMON_MISSING_DETAIL = ("Instant no pudo iniciar. Revisá Diagnóstico.")
STATUS_DETAIL = ("Enfocá el prompt o campo editable de la CLI, mantené F9 y "
                 "soltá: Instant pega con Ctrl+V.")


def _workdir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _pid_value():
    from instant_app.daemon import pid_path
    try:
        with open(pid_path(), encoding="utf-8") as file:
            return int(file.read().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def daemon_is_running():
    pid = _pid_value()
    if pid is None:
        return False
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5, creationflags=flags)
        except (OSError, subprocess.TimeoutExpired):
            return False
        for row in result.stdout.splitlines():
            columns = [part.strip().strip('"') for part in row.split('","')]
            if len(columns) > 1 and columns[1] == str(pid):
                return columns[0].lower() in {"python.exe", "pythonw.exe", "instant.exe"}
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _display_input_name(name):
    label = name.strip()
    open_paren = label.find("(")
    if open_paren >= 0 and label.endswith(")"):
        kind, detail = label[:open_paren].strip(), label[open_paren + 1:-1].strip()
        label = detail if kind.casefold() == "microphone" else f"{kind}: {detail}"
    prefix, separator, rest = label.partition("-")
    if separator and prefix.strip().isdigit():
        label = rest.strip()
    return label


def _pid_is_instant(pid):
    """El PID file puede quedar rancio y el SO reciclar el número: antes de
    matar se confirma que la línea de comando sea de Instant."""
    if os.name != "nt":
        return True
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
            capture_output=True, text=True, timeout=10, creationflags=flags)
    except (OSError, subprocess.TimeoutExpired):
        return True
    command = (result.stdout or "").casefold()
    return "instant" in command


def stop_daemon():
    pid = _pid_value()
    if pid is None or not daemon_is_running():
        return False
    if not _pid_is_instant(pid):
        log.warning("PID %d reciclado por el SO (no es Instant); no se mata.", pid)
        return False
    if os.name == "nt":
        try:
            subprocess.Popen(
                ["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return True
        except OSError:
            return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False


_GUI_SERVER_BASE = "instant-gui"


def _gui_server_name():
    """Canal de instancia única del panel; en Unix lleva el uid del usuario."""
    if os.name == "nt":
        return _GUI_SERVER_BASE
    return f"{_GUI_SERVER_BASE}-{os.getuid()}"


def _forward_to_existing_gui(page, start_daemon_on_open):
    """Pasa el pedido a la ventana ya abierta. True si había otra instancia.

    QLocalSocket/QLocalServer son el mecanismo portable de Qt: en Windows es
    la ruta de la bandeja (mutex + FindWindow), en Linux/macOS este canal.
    El panel contesta `ok`; sin esa confirmación este proceso, que sale
    enseguida, podría morir con el pedido todavía en el buffer (en Windows
    cerrar el socket con datos sin leer los descarta).
    """
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtNetwork import QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(_gui_server_name())
    if not socket.waitForConnected(500):
        return False
    payload = json.dumps(
        {"page": page, "daemon": bool(start_daemon_on_open)}).encode("utf-8")
    socket.write(payload)
    socket.flush()
    loop = QEventLoop()
    socket.readyRead.connect(loop.quit)
    socket.disconnected.connect(loop.quit)
    if not socket.bytesAvailable():
        QTimer.singleShot(1000, loop.quit)
        loop.exec()
    socket.disconnectFromServer()
    return True


def _install_gui_server(window):
    """La ventana atiende los pedidos de instancias nuevas (Linux/macOS)."""
    from PySide6.QtNetwork import QLocalServer

    name = _gui_server_name()
    # Un cierre sucio deja el socket huérfano: se limpia antes de escuchar.
    QLocalServer.removeServer(name)
    server = QLocalServer(window)
    if not server.listen(name):
        log.warning("sin canal de instancia única: %s", server.errorString())
        return None

    def on_connection():
        socket = server.nextPendingConnection()
        if socket is None:
            return

        def on_ready():
            raw = bytes(socket.readAll().data())
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                payload = {}
            if payload:
                window.apply_gui_action(
                    payload.get("page"), bool(payload.get("daemon")))
            # Acuse: el lanzador no sale hasta que el pedido llegó acá.
            socket.write(b"ok")
            socket.flush()
            socket.disconnectFromServer()

        socket.readyRead.connect(on_ready)
        if socket.bytesAvailable():
            on_ready()

    server.newConnection.connect(on_connection)
    return server


class DeviceCatalog:
    """Toolkit-independent microphone choice tracking and ambiguity handling."""
    def __init__(self, cfg):
        self.cfg = cfg
        self.rows = ()
        self.devices = {}
        self.collisions = set()
        self.pending_device = None
        self.pending_identity = None

    @staticmethod
    def identity(device):
        if not device:
            return "", None
        name = " ".join(_display_input_name(str(device[1])).casefold().split())
        return name, device[0]

    def same_identity(self, left, right):
        if left[0] != right[0]:
            return False
        return left[0] not in self.collisions or left[1] == right[1]

    def remember(self, device):
        if device:
            self.pending_device = device
            self.pending_identity = self.identity(device)

    def refresh(self, preferred=None, preserve=False):
        previous = self.rows
        try:
            inputs = audio.input_choices()
        except Exception:
            log.exception("no pude listar micrófonos para el panel")
            inputs = []
        try:
            import sounddevice as sd
            default = tuple(sd.default.device)[0]
        except Exception:
            default = None
        default = audio.preferred_input_index(default, inputs) if inputs else None
        if preserve:
            preferred = preferred or self.pending_device
            current = None
            if preferred and inputs:
                old_index, old_name = preferred
                current = next((i for i, name, _ch, _rate in inputs
                                if i == old_index and name.casefold() == old_name.casefold()), None)
                if current is None:
                    old_display = _display_input_name(old_name).casefold()
                    was = [row for row in previous if _display_input_name(row[1]).casefold() == old_display]
                    now = [row for row in inputs if _display_input_name(row[1]).casefold() == old_display]
                    prior = next((row for row in was if row[0] == old_index and row[1].casefold() == old_name.casefold()), None)
                    if prior and len(was) == len(now) == 1 and (prior[2], prior[3]) == (now[0][2], now[0][3]):
                        current = now[0][0]
        else:
            current = audio.resolve_mic(self.cfg.get("mic_hint", ""), self.cfg.get("mic_index")) if inputs else None
            current = audio.preferred_input_index(current, inputs)
            if current is None:
                current = default
        self.rows = tuple(inputs)
        labels, devices, counts = [], {}, {}
        for index, name, _channels, _rate in inputs:
            display = _display_input_name(name)
            counts[display.casefold()] = counts.get(display.casefold(), 0) + 1
        self.collisions = {name for name, count in counts.items() if count > 1}
        selected = None
        for index, name, _channels, _rate in inputs:
            label = _display_input_name(name)
            if counts[label.casefold()] > 1:
                label += f" [{index}]"
            if index == default:
                label += " (predeterminado)"
            labels.append(label)
            devices[label] = (index, name)
            if index == current:
                selected = label
        self.devices = devices
        return labels, selected, bool(preserve and preferred and selected is None and labels)


class TaskRunner:
    """Trabajo bloqueante en hilos, resultados encolados para el hilo de UI.

    Los hilos NUNCA tocan la UI: encolan y quien llama a `drain()` (el timer
    del panel, o un test) los aplica en su hilo. `close()` descarta lo que
    llegue después: una ventana cerrada no recibe resultados tardíos.
    """
    def __init__(self):
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._handlers = {}
        self._pending = 0
        self._closed = False
        self.on_idle = None
        self.on_error = None

    @property
    def pending(self):
        with self._lock:
            return self._pending

    def submit(self, fn, on_result=None, on_error=None, on_progress=None):
        with self._lock:
            if self._closed:
                return None
            token = id(fn) ^ time.monotonic_ns()
            self._handlers[token] = (on_result, on_error, on_progress)
            self._pending += 1

        def runner():
            try:
                value = fn(lambda payload: self._queue.put(("progress", token, payload)))
                self._queue.put(("result", token, value))
            except Exception as exc:  # noqa: BLE001  (cruza el hilo a la UI)
                self._queue.put(("error", token, exc))
            finally:
                self._queue.put(("done", token, None))

        threading.Thread(target=runner, daemon=True).start()
        return token

    def drain(self):
        """Aplica los eventos encolados; devuelve cuántos atendió."""
        applied = 0
        while True:
            try:
                kind, token, value = self._queue.get_nowait()
            except queue.Empty:
                break
            with self._lock:
                handlers = self._handlers.get(token)
                closed = self._closed
            if kind == "done":
                with self._lock:
                    self._handlers.pop(token, None)
                    if self._pending:
                        self._pending -= 1
                    idle = self._pending == 0
                if idle and self.on_idle is not None and not closed:
                    self.on_idle()
                continue
            if closed or handlers is None:
                continue
            on_result, on_error, on_progress = handlers
            if kind == "progress" and on_progress is not None:
                on_progress(value)
            elif kind == "result" and on_result is not None:
                on_result(value)
            elif kind == "error":
                if on_error is not None:
                    on_error(value)
                elif self.on_error is not None:
                    self.on_error(value)
            applied += 1
        return applied

    def close(self):
        with self._lock:
            self._closed = True
            self._handlers.clear()
            self._pending = 0


class PanelLogic:
    """Estado y acciones del panel, sin Qt. Ver el docstring del módulo."""

    def __init__(self, page="home", autostart_override=None,
                 start_daemon_on_open=False, emit=None, tasks=None, schedule=None):
        self.emit = emit or (lambda kind, payload: None)
        self.tasks = tasks or TaskRunner()
        self.tasks.on_idle = lambda: self.emit("idle", {})
        # El shell inyecta su QTimer.singleShot; en tests alcanza sin reloj.
        self.schedule = schedule or (lambda milliseconds, fn: None)
        self.page = page
        self.cfg = config.load()
        self.data_dir = resolve_data_dir()
        self.catalog = DeviceCatalog(self.cfg)
        self.model_ready = all(models.check(self.data_dir).values())
        self._autostart_override = autostart_override
        self._start_daemon_on_open = start_daemon_on_open
        self._closed = False
        self._daemon_start_pending = False
        self._daemon_start_token = 0
        self._daemon_check_pending = False
        self._daemon_state_ready = False
        self._last_daemon_running = False
        self._microphones_loaded = False
        self._settings_daemon_state = None
        self._restart_needed = False
        self._restart_settings = None
        self._saved_settings = None
        self._loaded_context_name = None
        self._vocab_rows_cache = []
        self._available_update = None
        self._pending_update = None
        self._update_silent_done = False
        self._diagnostic_running = False
        self._diagnostics_open = False
        self._diagnostics_text = "Ejecutando comprobaciones…"
        self._toast_callbacks = {}
        self.mic_labels = []
        self.mic_selected = None
        self.key_value = hotkey.key_label(self.cfg.get("key", "f9"))
        self.status_var = "Listo para dictar"
        self.status_detail = STATUS_DETAIL
        self.meter = {"percent": 0, "text": "La prueba no guarda audio."}
        self.model_status = ""
        self.model_progress = {"visible": False, "percent": 0}
        self.update_button = "Buscar actualizaciones"
        self.settings_status = ""
        self._autostart_enabled = False
        self._init_settings(autostart_override)
        self._update_model_status()

    # ------------------------------------------------------------------ estado

    def state_payload(self):
        configured = context.profiles(self.cfg)
        try:
            active = context.active_name(self.cfg)
        except Exception:
            active = context.DEFAULT_PROFILE
        return {
            "version": _current_version(),
            "status": {
                "state": "ok" if self._last_daemon_running else "down",
                "title": self.status_var,
                "detail": self.status_detail,
                "can_start": bool(self._daemon_state_ready and self._microphones_loaded
                                  and not self._daemon_start_pending
                                  and not self._last_daemon_running),
                "can_stop": bool(self._last_daemon_running),
            },
            "key_label": self.key_value,
            "autostart": bool(self._autostart_enabled),
            "mic": {
                "labels": list(self.mic_labels),
                "selected": self.mic_selected,
                "meter": dict(self.meter),
            },
            "model": {
                "ready": bool(self.model_ready),
                "status": self.model_status,
                "progress": dict(self.model_progress),
                "button": "Voz lista" if self.model_ready else "Descargar voz",
            },
            "vocab": {
                "profiles": list(configured),
                "active": active,
                "removable": active != context.DEFAULT_PROFILE,
                "rows": [
                    {"term": row.get("term", ""),
                     "heard": " | ".join(row.get("aliases", ())),
                     "sound": bool(row.get("sonido"))}
                    for row in self._vocab_rows_cache
                ],
            },
            "updates": {"button": self.update_button},
            "dirty": bool(self._dirty()),
            "settings_status": self.settings_status,
            "data_dir": self.data_dir,
            "diagnostics": {
                "open": self._diagnostics_open,
                "running": self._diagnostic_running,
                "text": self._diagnostics_text,
            },
        }

    def push_state(self):
        self.emit("state", self.state_payload())

    def toast(self, title, message="", level="info", actions=(), ms=4500):
        if self._closed:
            return
        toast_id = f"t{time.monotonic_ns()}"
        self._toast_callbacks[toast_id] = [callback for _label, callback in actions]
        self.emit("toast", {
            "id": toast_id,
            "title": title, "message": message, "level": level,
            "actions": [{"id": str(i), "label": label}
                        for i, (label, _callback) in enumerate(actions)],
            "ms": max(ms, 10000) if actions else ms,
        })

    # ------------------------------------------------------------- protocolo

    def handle(self, message):
        """Despacha un mensaje del bridge (`{"op": ...}`). Nunca propaga."""
        if not isinstance(message, dict):
            return
        op = message.get("op")
        handler = getattr(self, f"_op_{op}", None) if isinstance(op, str) else None
        try:
            if handler is not None:
                handler(message)
        except Exception:
            log.exception("op del panel falló: %s", op)

    def _op_ready(self, _message):
        self.push_state()

    def _op_navigate(self, message):
        self.navigate(message.get("page") or "home")

    def _op_toggle_daemon(self, _message):
        self.toggle_daemon()

    def _op_stop_daemon(self, _message):
        self.stop_daemon_flow()

    def _op_refresh_mics(self, _message):
        self.refresh_microphones()

    def _op_select_mic(self, message):
        self.select_mic(message.get("label"))

    def _op_test_mic(self, _message):
        self.test_microphone()

    def _op_key_capture_open(self, _message):
        self.begin_key_capture()

    def _op_key_captured(self, message):
        self.key_captured(message.get("code"), message.get("name"))

    def _op_key_cancel(self, _message):
        pass

    def _op_set_autostart(self, message):
        self._autostart_enabled = bool(message.get("value"))
        self._update_settings_status()
        self.push_state()

    def _op_context_select(self, message):
        self.context_select(message.get("name"))

    def _op_context_add(self, message):
        self.context_add(message.get("name"))

    def _op_context_remove(self, _message):
        self.context_remove()

    def _op_vocab_add(self, _message):
        self.vocab_add()

    def _op_vocab_set(self, message):
        self.vocab_set(message.get("row"), message.get("col"), message.get("value"))

    def _op_vocab_toggle_sound(self, message):
        self.vocab_toggle_sound(message.get("row"))

    def _op_vocab_delete(self, message):
        self.vocab_delete(message.get("row"))

    def _op_save_config(self, _message):
        self.save_config(show_message=True)

    def _op_download_models(self, _message):
        self.download_models()

    def _op_check_updates(self, _message):
        self.check_updates()

    def _op_toast_action(self, message):
        callbacks = self._toast_callbacks.pop(message.get("id"), None)
        if not callbacks:
            return
        try:
            callbacks[int(message.get("action") or 0)]()
        except (IndexError, TypeError, ValueError):
            log.warning("acción de toast inválida: %s", message)

    def _op_diagnostics(self, _message):
        self.show_diagnostics()

    def _op_diagnostics_close(self, _message):
        self._diagnostics_open = False
        self.push_state()

    # -------------------------------------------------------------- settings

    def _init_settings(self, autostart_override):
        configured = context.profiles(self.cfg)
        try:
            active = context.active_name(self.cfg)
        except Exception:
            active = context.DEFAULT_PROFILE
        if active not in configured:
            active = context.DEFAULT_PROFILE
        self._loaded_context_name = active
        self.cfg["active_context"] = active
        self._vocab_load_rows(configured.get(active, []))
        try:
            enabled = bool(autostart.is_enabled())
        except Exception:
            enabled = bool(self.cfg.get("autostart"))
        if autostart_override is not None:
            enabled = autostart_override
        self._autostart_enabled = enabled
        self._saved_settings = self._snapshot()
        self._restart_settings = self._restart_signature(self._saved_settings)
        self._settings_daemon_state = None
        self._update_settings_status()

    def _dirty(self):
        if self._saved_settings is None:
            return False
        return not self._same_settings(self._snapshot(), self._saved_settings)

    def _snapshot(self):
        device = self._selected_device()
        if device:
            self.catalog.remember(device)
        mic = self.catalog.pending_identity or DeviceCatalog.identity(
            (self.cfg.get("mic_index"), self.cfg.get("mic_hint", "")))
        self._store_vocab_table()
        context_state = tuple(
            (name, tuple((row["term"], tuple(row["aliases"]), bool(row.get("sonido")))
                         for row in items))
            for name, items in context.profiles(self.cfg).items())
        return (mic, self.key_value.strip().lower(), bool(self._autostart_enabled),
                self.cfg["active_context"], context_state,
                self.cfg.get("llm_url", ""))

    @staticmethod
    def _restart_signature(snapshot):
        return snapshot[0], snapshot[1], snapshot[3], snapshot[4], snapshot[5]

    def _same_settings(self, left, right):
        return (self.catalog.same_identity(left[0], right[0])
                and left[1:] == right[1:])

    def _update_settings_status(self):
        if self._saved_settings is None:
            self.settings_status = ""
        elif self._dirty():
            self.settings_status = "Hay cambios sin guardar."
        elif self._restart_needed:
            self.settings_status = ("Guardado; reiniciá Instant para aplicar "
                                    "micrófono, tecla, vocabulario o LLM.")
        else:
            self.settings_status = "Ajustes guardados."

    def _settings_daemon_changed(self, running):
        previous = self._settings_daemon_state
        self._settings_daemon_state = bool(running)
        if previous is None:
            if not running:
                self._restart_needed = False
        elif previous != bool(running):
            self._restart_needed = False
            if running:
                self._restart_settings = self._restart_signature(self._saved_settings)
        self._update_settings_status()

    # ------------------------------------------------------------ micrófonos

    def refresh_microphones(self, initial=False):
        self._microphones_loaded = False
        preferred = None if initial else self.catalog.pending_device
        refresh = self.catalog.refresh

        def enumerate_devices(_emit):
            return refresh(preferred, preserve=not initial)

        def populated(result):
            if self._closed:
                return
            labels, selected, missing = result
            self.mic_labels = list(labels)
            if selected is not None:
                self.mic_selected = selected
            elif missing:
                self.mic_labels.append("El micrófono seleccionado no está disponible")
                self.mic_selected = self.mic_labels[-1]
            elif labels:
                self.mic_selected = labels[0]
            else:
                self.mic_labels = ["No se detectaron micrófonos"]
                self.mic_selected = None
            device = self._selected_device()
            if device:
                self.catalog.remember(device)
            if initial and self._saved_settings is not None:
                snapshot = self._snapshot()
                self._saved_settings = (snapshot[0], self._saved_settings[1],
                                        *self._saved_settings[2:])
                self._restart_settings = (snapshot[0], *self._restart_settings[1:])
            if not labels:
                self.meter = {"percent": 0, "text": "No se detectaron micrófonos. "
                              "Conectá una entrada y actualizá la lista."}
            elif not device and missing:
                self.meter = {"percent": 0, "text": "El micrófono elegido no está "
                              "disponible; seleccioná otro."}
            elif not initial:
                self.meter = {"percent": 0, "text": "Lista de micrófonos actualizada."}
            self._microphones_loaded = True
            self._update_settings_status()
            self.push_state()
            self.emit("mic_loaded", {"labels": self.mic_labels,
                                     "selected": self.mic_selected})
            self._maybe_start_daemon_on_open()

        def failed(error):
            if self._closed:
                return
            self.meter = {"percent": 0,
                          "text": f"No se pudo actualizar la lista: {error}"}
            self._microphones_loaded = True
            self._update_settings_status()
            self.push_state()
            self.emit("mic_loaded", {"labels": self.mic_labels,
                                     "selected": self.mic_selected})
            self._maybe_start_daemon_on_open()

        self.tasks.submit(enumerate_devices, populated, failed)

    def _selected_device(self):
        label = self.mic_selected
        if not label:
            return None
        device = self.catalog.devices.get(label)
        return tuple(device) if device is not None else None

    def select_mic(self, label):
        if label is None:
            return
        self.mic_selected = label
        device = self._selected_device()
        if device:
            self.catalog.remember(device)
            self.meter = {"percent": 0, "text": "Entrada seleccionada."}
        self._update_settings_status()
        self.push_state()

    def test_microphone(self):
        selected = self._selected_device()
        if not selected:
            self.toast("Sin micrófono", "Elegí un micrófono de entrada.",
                       level="warn")
            return
        self.meter = {"percent": 0, "text": "Hablá ahora…"}
        self.push_state()

        def capture(emit):
            def level(value):
                emit(("level", value))
            return audio.peak_meter(selected[0], seconds=3.0, on_level=level)

        def progress(event):
            if event and event[0] == "level":
                self.meter = {"percent": min(100, int(event[1] * 200)),
                              "text": f"Señal {event[1]:.3f}"}
                self.emit("meter", dict(self.meter))

        def done(peak):
            if self._closed:
                return
            self.meter = {"percent": self.meter["percent"],
                          "text": (f"Señal detectada ({peak:.3f})." if peak > .005
                                   else "No detecté señal; revisá micrófono/volumen.")}
            self.push_state()

        def failed(error):
            if self._closed:
                return
            self.toast("Prueba de micrófono", str(error), level="warn")

        self.tasks.submit(capture, done, failed, progress)

    # ------------------------------------------------------------------ tecla

    def begin_key_capture(self):
        self.emit("key_capture", {"state": "open"})

    def key_captured(self, code, name):
        name = (name or "").strip().lower().replace(" ", "_")
        if os.name == "nt":
            try:
                vk = int(code)
            except (TypeError, ValueError):
                vk = 0
            if 8 <= vk <= 0xFE:
                value = f"vk:{vk}"
            elif hotkey.is_valid_key(name):
                value = hotkey.normalize_key(name)
            else:
                self.emit("key_result", {"ok": False,
                                         "message": "No pude identificar esa tecla; probá otra."})
                return
        elif hotkey.is_valid_key(name):
            value = hotkey.normalize_key(name)
        else:
            self.emit("key_result", {"ok": False,
                                     "message": "No pude identificar esa tecla; probá otra."})
            return
        self._set_key(value)
        self.emit("key_result", {"ok": True, "message": ""})

    def _set_key(self, key):
        self.key_value = hotkey.key_label(key)
        self._update_settings_status()
        self.push_state()

    # ------------------------------------------------------------ vocabulario

    def _vocab_load_rows(self, rows):
        """Vuelca filas normalizadas al cache sin marcar cambios."""
        self._vocab_rows_cache = [
            {"term": row.get("term", ""),
             "aliases": list(row.get("aliases", ())),
             "sonido": bool(row.get("sonido"))}
            for row in rows]
        if not rows:
            # Perfil vacío: una fila en blanco invita a escribir. No se guarda.
            self._vocab_rows_cache = [{"term": "", "aliases": [], "sonido": False}]

    def _vocab_rows(self):
        """Normaliza el cache con el mismo formato del editor."""
        draft = []
        for row in self._vocab_rows_cache:
            term = str(row.get("term", "")).strip()
            if not term:
                continue
            aliases = row.get("aliases", ())
            if isinstance(aliases, str):
                aliases = [part.strip() for part in aliases.split("|") if part.strip()]
            draft.append({"term": term, "aliases": list(aliases),
                          "sonido": bool(row.get("sonido"))})
        return context.parse_editor(context.editor_text(draft))

    def _store_vocab_table(self):
        name = self._loaded_context_name or context.DEFAULT_PROFILE
        configured = context.profiles(self.cfg)
        configured[name] = self._vocab_rows()
        self.cfg["context_profiles"] = configured
        self.cfg["active_context"] = self._loaded_context_name or name

    def context_select(self, name):
        if not name:
            return
        self._store_vocab_table()
        configured = context.profiles(self.cfg)
        if name not in configured:
            return
        self.cfg["active_context"] = name
        self._loaded_context_name = name
        self._vocab_load_rows(configured.get(name, []))
        self._update_settings_status()
        self.push_state()

    def context_add(self, name):
        name = (name or "").strip()
        if not name:
            return
        configured = context.profiles(self.cfg)
        if name in configured:
            self.toast("Instant", "Ya existe ese perfil.", level="warn")
            return
        self._store_vocab_table()
        configured[name] = []
        self.cfg["context_profiles"] = configured
        self.cfg["active_context"] = name
        self._loaded_context_name = name
        self._vocab_load_rows([])
        self._update_settings_status()
        self.push_state()

    def context_remove(self):
        name = self._loaded_context_name or context.DEFAULT_PROFILE
        if name == context.DEFAULT_PROFILE:
            return
        self._store_vocab_table()
        configured = context.profiles(self.cfg)
        configured.pop(name, None)
        configured.setdefault(context.DEFAULT_PROFILE, [])
        self.cfg["context_profiles"] = configured
        self.cfg["active_context"] = context.DEFAULT_PROFILE
        self._loaded_context_name = context.DEFAULT_PROFILE
        self._vocab_load_rows(configured[context.DEFAULT_PROFILE])
        self._update_settings_status()
        self.push_state()

    def vocab_add(self):
        self._vocab_rows_cache.append({"term": "", "aliases": [], "sonido": False})
        self._update_settings_status()
        self.push_state()

    def vocab_set(self, row, col, value):
        try:
            index = int(row)
        except (TypeError, ValueError):
            return
        if not (0 <= index < len(self._vocab_rows_cache)):
            return
        entry = self._vocab_rows_cache[index]
        if col == "term":
            entry["term"] = str(value or "")
        elif col == "heard":
            entry["aliases"] = [part.strip() for part in str(value or "").split("|")
                                if part.strip()]
        else:
            return
        self._update_settings_status()
        self.push_state()

    def vocab_toggle_sound(self, row):
        try:
            index = int(row)
        except (TypeError, ValueError):
            return
        if not (0 <= index < len(self._vocab_rows_cache)):
            return
        entry = self._vocab_rows_cache[index]
        entry["sonido"] = not entry.get("sonido", False)
        self._update_settings_status()
        self.push_state()

    def vocab_delete(self, row):
        try:
            index = int(row)
        except (TypeError, ValueError):
            return
        if not (0 <= index < len(self._vocab_rows_cache)):
            return
        del self._vocab_rows_cache[index]
        self._update_settings_status()
        self.push_state()

    # --------------------------------------------------------------- guardar

    def save_config(self, show_message=True):
        selected = self._selected_device()
        if selected:
            self.catalog.remember(selected)
            self.cfg["mic_index"], self.cfg["mic_hint"] = selected
        snapshot = self._snapshot()
        self.cfg["key"], self.cfg["lang"], self.cfg["autostart"] = (
            snapshot[1], "es", snapshot[2])
        self.cfg["llm_url"] = snapshot[5]
        path = config.save(self.cfg)
        warning = None
        try:
            desired = snapshot[2]
            if autostart.is_enabled() != desired:
                (autostart.enable if desired else autostart.disable)()
        except Exception as exc:  # noqa: BLE001  (se informa, no se mata)
            warning = str(exc)
        saved = (DeviceCatalog.identity(
            (self.cfg.get("mic_index"), self.cfg.get("mic_hint", ""))), *snapshot[1:])
        running = bool(self._last_daemon_running)
        signature = self._restart_signature(saved)
        if running:
            self._restart_needed = not (
                self.catalog.same_identity(signature[0], self._restart_settings[0])
                and signature[1:] == self._restart_settings[1:])
        else:
            self._restart_settings = signature
            self._restart_needed = False
        self._saved_settings = saved
        self._update_settings_status()
        if warning:
            self.toast("Arranque con Windows", warning, level="warn")
        if show_message:
            note = (" Micrófono, tecla, vocabulario y LLM guardados; reiniciá "
                    "Instant para aplicarlos." if self._restart_needed else "")
            self.toast("Ajustes guardados", f"{note}\n{path}".strip())
        self.push_state()
        return True

    # ---------------------------------------------------------------- daemon

    def toggle_daemon(self):
        if self._daemon_start_pending:
            return
        if self._last_daemon_running:
            self.save_config(False)
            self.stop_daemon_flow(restart=True)
        else:
            self._start_daemon()

    def _maybe_start_daemon_on_open(self):
        if (not self._start_daemon_on_open or self._closed
                or not self._daemon_state_ready or self._daemon_check_pending
                or not self._microphones_loaded):
            return
        self._start_daemon_on_open = False
        if not self._last_daemon_running:
            self._start_daemon(save_settings=False)

    def _start_daemon(self, save_settings=True):
        if (self._daemon_start_pending or not self._daemon_state_ready
                or self._daemon_check_pending or not self._microphones_loaded
                or self._last_daemon_running):
            return False
        if not self.model_ready:
            self.toast("Modelos pendientes",
                       "Descargá los modelos de voz antes de iniciar Instant.",
                       level="warn")
            return False
        if save_settings:
            self.save_config(False)
        try:
            env = app_environment()
            env["DICTADO_DATA"] = self.data_dir
            self._daemon_start_pending = True
            self._daemon_start_token += 1
            token = self._daemon_start_token
            self.push_state()
            subprocess.Popen(app_command(("run",)), cwd=_workdir(),
                             env=env,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.status_detail = "Iniciando Instant…"
            self.push_state()
            self.schedule(10000, lambda: self._daemon_start_timeout(token))
            self.schedule(700, self.refresh_daemon)
            return True
        except Exception as exc:  # noqa: BLE001  (se informa al usuario)
            self._daemon_start_pending = False
            self.push_state()
            self.toast("No se pudo iniciar Instant", str(exc), level="error")
            return False

    def _daemon_start_timeout(self, token):
        if self._closed:
            return
        if token != self._daemon_start_token or not self._daemon_start_pending:
            return
        self._daemon_start_pending = False
        if not self._last_daemon_running:
            self.status_detail = DAEMON_MISSING_DETAIL
            log.warning("el daemon no confirmó inicio dentro del plazo")
        self.push_state()

    def stop_daemon_flow(self, restart=False):
        from instant_app.daemon import pid_path  # noqa: F401  (compat: mismo camino)

        pid = _pid_value()
        if pid is None or not self._last_daemon_running:
            if restart:
                self._start_daemon()
            else:
                self.refresh_daemon()
            return
        # _pid_is_instant hace powershell/Get-CimInstance (hasta 10s):
        # NUNCA en hilo UI. Se verifica en worker y recién ahí se mata.
        self.status_detail = "Verificando Instant…"
        self.push_state()

        def check(_emit):
            return _pid_is_instant(pid)

        def checked(is_ours):
            if self._closed:
                return
            if not is_ours:
                log.warning("PID %d reciclado por el SO (no es Instant); no se mata.", pid)
                self.status_detail = "El daemon ya no estaba; actualizando estado…"
                self.refresh_daemon()
                return
            if os.name == "nt":
                subprocess.Popen(["taskkill", "/F", "/PID", str(pid)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
            self.status_detail = "Cerrando Instant…"
            self.push_state()
            if self._closed:
                return
            if restart:
                self.schedule(350, self._wait_before_restart)
            else:
                self.schedule(700, self.refresh_daemon)

        self.tasks.submit(check, checked)

    def _wait_before_restart(self):
        if self._closed:
            return
        if self._last_daemon_running:
            self.refresh_daemon()
            self.schedule(250, self._wait_before_restart)
        else:
            self._start_daemon()

    def refresh_daemon(self):
        if self._daemon_check_pending:
            return
        self._daemon_check_pending = True

        def result(running):
            if self._closed:
                return
            self._daemon_check_pending = False
            self._daemon_state_ready = True
            if running and self._daemon_start_pending:
                self._daemon_start_pending = False
                self._daemon_start_token += 1
            if running != self._last_daemon_running:
                self._last_daemon_running = running
                self._settings_daemon_changed(running)
            if running:
                self.status_var = "Instant está activo"
                self.status_detail = STATUS_DETAIL
            else:
                self.status_var = "Listo para dictar"
                self.status_detail = STATUS_DETAIL
            self.push_state()
            self._maybe_start_daemon_on_open()

        def failed(error):
            self._daemon_check_pending = False
            log.warning("no se pudo comprobar el daemon desde el panel: %s", error)

        self.tasks.submit(lambda _emit: daemon_is_running(), result, failed)

    # ---------------------------------------------------------------- modelos

    def _update_model_status(self):
        self.model_ready = all(models.check(self.data_dir).values())
        if self.model_ready:
            self.model_status = "Voz lista en este equipo."
            self.model_progress = {"visible": False, "percent": 100}
        else:
            self.model_status = "Falta descargar la voz (~670 MB)."
            self.model_progress = {"visible": False, "percent": 0}

    def download_models(self):
        if self.model_ready:
            return
        self.model_status = "Descargando la voz…"
        self.model_progress = {"visible": True, "percent": 0}
        self.push_state()

        def download(emit):
            return models.download_models(
                self.data_dir, progress=lambda *args: emit(args))

        def progress(event):
            if not event:
                return
            step, done, total = event
            if not total:
                return
            label = "la voz" if step == "parakeet" else "el detector de voz"
            self.model_status = (f"Descargando {label}: {done / total:.0%} "
                                 f"({done / 1e6:.0f}/{total / 1e6:.0f} MB)")
            self.model_progress = {"visible": True,
                                   "percent": int(100 * done / total)}
            self.emit("progress", {"percent": self.model_progress["percent"],
                                   "text": self.model_status})

        def done(_value):
            if self._closed:
                return
            self._update_model_status()
            self.push_state()

        def failed(error):
            if self._closed:
                return
            self.model_progress = {"visible": False, "percent": 0}
            self.model_status = "No se pudo descargar la voz."
            self.push_state()
            self.toast("Descarga fallida", str(error), level="error")

        self.tasks.submit(download, done, failed, progress)

    # ----------------------------------------------------------- diagnóstico

    def show_diagnostics(self):
        self._diagnostics_open = True
        self._diagnostics_text = ("Ejecutando comprobaciones…"
                                  if not self._diagnostic_running else self._diagnostics_text)
        self.push_state()
        self.emit("diagnostics", {"state": "running", "text": self._diagnostics_text})
        if self._diagnostic_running:
            return
        self._diagnostic_running = True

        def diagnose(_emit):
            from contextlib import redirect_stdout
            from io import StringIO

            from instant_app.daemon import cmd_check
            stream = StringIO()
            with redirect_stdout(stream):
                rc = cmd_check(config.load())
            return rc, stream.getvalue()

        def done(result):
            if self._closed:
                return
            self._diagnostic_running = False
            self._diagnostics_text = result[1] or "Sin salida de diagnóstico."
            self.push_state()
            self.emit("diagnostics", {"state": "done", "text": self._diagnostics_text})

        def failed(error):
            if self._closed:
                return
            self._diagnostic_running = False
            self._diagnostics_text = f"Diagnóstico fallido: {error}"
            self.push_state()
            self.emit("diagnostics", {"state": "done", "text": self._diagnostics_text})

        self.tasks.submit(diagnose, done, failed)

    # ---------------------------------------------------------- actualizar

    def _silent_update_check(self):
        """Chequeo diario silencioso: nunca interrumpe, solo avisa."""
        if self._update_silent_done or self._closed:
            return
        self._update_silent_done = True
        try:
            if time.time() - float(self.cfg.get("update_last_check", 0)) < UPDATE_CHECK_INTERVAL:
                return
        except (TypeError, ValueError):
            pass
        from instant_app import update as update_module
        self.tasks.submit(lambda _emit: update_module.check(),
                          self._silent_update_result, lambda _error: None)

    def _silent_update_result(self, info):
        try:
            self.cfg["update_last_check"] = int(time.time())
            config.save(self.cfg)
        except Exception:
            log.warning("no pude sellar el chequeo de versión", exc_info=True)
        if self._closed or not info.get("update"):
            return
        self._apply_update_available(info)

    def _apply_update_available(self, info):
        self._available_update = info
        self.update_button = f"↓ Actualizar a v{info['latest']}"
        self.push_state()

    def check_updates(self):
        from instant_app import update as update_module
        self.push_state()
        self.tasks.submit(lambda _emit: update_module.check(),
                          self._updates_result, self._updates_failed)

    def _updates_failed(self, error):
        if self._closed:
            return
        self.toast("Actualizaciones", f"No se pudo consultar versiones:\n{error}",
                   level="warn")

    def _updates_result(self, info):
        if self._closed:
            return
        if not info.get("update"):
            self._available_update = None
            self.update_button = "Buscar actualizaciones"
            self.push_state()
            self.toast("Actualizaciones",
                       f"Estás al día (versión {info.get('current') or '?'}).")
            return
        from instant_app import update as update_module
        notes = update_module.clean_notes(info.get("notes"))
        self._available_update = info
        self.toast(f"Hay versión nueva: {info['latest']}",
                   f"Tenés {info.get('current') or '?'}.\n{notes}",
                   actions=(("Descargar", self._download_pending),
                            ("Ahora no", lambda: None)))

    def _download_pending(self):
        self._pending_update = self._available_update
        self.tasks.submit(self._download_update, self._update_ready,
                          self._updates_failed)

    def _download_update(self, _emit):
        import tempfile
        from instant_app import update as update_module
        info = self._pending_update
        target = os.path.join(tempfile.gettempdir(), "instant_update", info["asset"])
        expected = update_module.fetch_expected_sha256(info["asset_url"])
        update_module.download(info["asset_url"], target, expected_sha256=expected)
        return target, expected

    def _update_ready(self, payload):
        if self._closed:
            return
        target, expected = payload
        self.toast("Descarga verificada",
                   f"{target}\n\nSe frena el dictado un momento (si estás "
                   "por dictar, mejor después) y se aplica la actualización.",
                   actions=(("Instalar ahora",
                             lambda: self._install_ready(target, expected)),
                            ("Después", lambda: None)))

    def _install_ready(self, target, expected):
        from instant_app import update as update_module

        mode = update_module.install_mode()
        if mode == "installed":
            self._install_via_setup(target)
            return
        if sys.platform != "win32" and getattr(sys, "frozen", False):
            self._install_in_place(target)
            return
        root = _workdir()
        script = os.path.join(root, "instant-update.bat")
        if not os.path.isfile(script):
            self.toast(
                "Actualizaciones",
                "No encuentro instant-update.bat junto a la app "
                "(instalación portable sin scripts).\n\n"
                f"Instalá a mano: cerrá Instant por completo y copiá\n{target}\n"
                f"sobre tu binario de Instant (SHA256 {expected[:16]}…).",
                level="warn")
            return
        try:
            subprocess.Popen(["cmd", "/c", script, target, expected], cwd=root)
        except Exception as exc:  # noqa: BLE001  (se informa al usuario)
            self.toast("Actualizaciones", f"No pude lanzar el instalador:\n{exc}",
                       level="error")
            return
        self.close()

    def _install_via_setup(self, installer_path):
        """Modo instalado (Windows): el Setup nuevo actualiza y reabre solo."""
        # El daemon no tiene ventana: el Restart Manager del instalador no
        # puede cerrarlo, así que se frena acá y se espera a que suelte
        # los archivos antes de copiar encima.
        stop_daemon()
        deadline = time.monotonic() + 3.0
        while daemon_is_running() and time.monotonic() < deadline:
            time.sleep(0.1)
        try:
            subprocess.Popen(
                [installer_path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                close_fds=True)
        except Exception as exc:  # noqa: BLE001  (se informa al usuario)
            self.toast("Actualizaciones", f"No pude lanzar el instalador:\n{exc}",
                       level="error")
            return
        log.info("instalador %s lanzado en silencio", installer_path)
        self.close()

    def _install_in_place(self, downloaded):
        """Linux/macOS: reemplazo en caliente del binario y reinicio del daemon."""
        from instant_app import update as update_module

        try:
            applied = update_module.apply_binary_update(downloaded)
        except Exception as exc:  # noqa: BLE001  (se informa al usuario)
            self.toast("Actualizaciones", f"No pude aplicar:\n{exc}", level="error")
            return
        log.info("binario actualizado en %s", applied)
        self.toast("Actualizaciones",
                   "Versión nueva aplicada al binario. Se reinicia el "
                   "dictado con ella; reabrí el panel para tenerla también acá.",
                   level="info")
        self.stop_daemon_flow(restart=True)

    # ------------------------------------------------------------- navegación

    def navigate(self, name):
        self.page = name or "home"
        self.emit("navigate", {"page": self.page})

    def request_daemon_start(self):
        self._start_daemon_on_open = True
        self._maybe_start_daemon_on_open()

    def apply_gui_action(self, page=None, start_daemon=False):
        """Pedido de otra instancia: enfoca la ventana y aplica la acción."""
        if page == "diagnostics":
            self.show_diagnostics()
        elif page == "setup":
            self.navigate("audio")
        if start_daemon:
            self.navigate("home")
            self.request_daemon_start()

    def close(self):
        self._closed = True
        self.tasks.close()
        self.emit("close", {})


def _current_version():
    try:
        from instant_app import __version__
        return __version__
    except Exception:  # pragma: no cover - versión siempre presente
        return "?"


def _panel_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def compose_panel_page(html, qwebchannel_js):
    """Inyecta qwebchannel.js en la plantilla (marcador comentado)."""
    return html.replace("<!--QWEBCHANNEL-->", "<script>\n" + qwebchannel_js + "\n</script>")


def write_panel_page():
    """Compone web/panel.html + qwebchannel.js en el dir de datos."""
    from PySide6.QtCore import QFile, QIODevice
    import PySide6.QtWebChannel  # noqa: F401  (registra :/qtwebchannel/qwebchannel.js)

    from instant_app.paths import config_dir

    handle = QFile(":/qtwebchannel/qwebchannel.js")
    if not handle.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError("no pude leer :/qtwebchannel/qwebchannel.js")
    try:
        channel_js = bytes(handle.readAll()).decode("utf-8")
    finally:
        handle.close()
    with open(os.path.join(_panel_dir(), "panel.html"), encoding="utf-8") as source:
        html = source.read()
    directory = os.path.join(config_dir(), "webui")
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, "panel.html")
    with open(target, "w", encoding="utf-8") as destination:
        destination.write(compose_panel_page(html, channel_js))
    return target


class _WebPanel:
    """Ventana QtWebEngine del panel; conecta la página con `PanelLogic`."""

    def __init__(self, page="home", autostart_override=None,
                 start_daemon_on_open=False):
        import importlib

        qtcore = importlib.import_module("PySide6.QtCore")
        qtgui = importlib.import_module("PySide6.QtGui")
        qtqml = importlib.import_module("PySide6.QtQml")
        webengine = importlib.import_module("PySide6.QtWebEngineQuick")
        QObject, QPoint, QThread, QTimer, Qt, QUrl = (
            getattr(qtcore, name) for name in
            ("QObject", "QPoint", "QThread", "QTimer", "Qt", "QUrl"))
        Signal, Slot = qtcore.Signal, qtcore.Slot
        QGuiApplication = qtgui.QGuiApplication
        QQmlApplicationEngine = qtqml.QQmlApplicationEngine

        # Inicialización del motor ANTES de crear la QGuiApplication (requisito
        # de QtWebEngine; idempotente si ya se llamó).
        webengine.QtWebEngineQuick.initialize()
        self.application = QGuiApplication.instance() or QGuiApplication(["Instant"])
        if QThread.currentThread() != self.application.thread():
            raise RuntimeError("web panel must be created on the QApplication thread")
        self.application.setQuitOnLastWindowClosed(False)

        self._engine = QQmlApplicationEngine()
        host_path = os.path.join(os.path.dirname(__file__), "qml", "panel_web_host.qml")
        self._engine.load(QUrl.fromLocalFile(host_path))
        roots = self._engine.rootObjects()
        if not roots:
            raise RuntimeError(f"Could not load panel host: {host_path}")
        self.root = roots[0]
        self.view = self.root.findChild(QObject, "view")
        if self.view is None:
            raise RuntimeError("WebEngineView not found in panel host")

        class Bridge(QObject):
            state = Signal(str)
            toast = Signal(str)
            meter = Signal(str)
            progress = Signal(str)
            diagnostics = Signal(str)
            key_result = Signal(str)
            key_capture = Signal(str)
            navigate = Signal(str)

            @Slot(str)
            def call(self, payload):
                self.received(payload)

            received = Signal(str)

        self.bridge = Bridge(self.application)
        self.root.registerBridge(self.bridge)

        self.logic = PanelLogic(
            page=page, autostart_override=autostart_override,
            start_daemon_on_open=start_daemon_on_open,
            emit=self._emit, schedule=self._schedule)
        self.bridge.received.connect(
            self._handle_call, Qt.ConnectionType.QueuedConnection)

        self.root.setProperty("pageUrl", QUrl.fromLocalFile(write_panel_page()))
        self.root.setProperty("visible", True)

        # Drenaje de resultados de workers + latido de estado del daemon.
        self._drain_timer = QTimer(self.root)
        self._drain_timer.setInterval(30)
        self._drain_timer.timeout.connect(self.logic.tasks.drain)
        self._drain_timer.start()
        self._daemon_timer = QTimer(self.root)
        self._daemon_timer.setInterval(3000)
        self._daemon_timer.timeout.connect(self.logic.refresh_daemon)
        self._daemon_timer.start()

        QTimer.singleShot(0, lambda: self.logic.refresh_microphones(initial=True))
        QTimer.singleShot(800, self.logic.refresh_daemon)
        QTimer.singleShot(8000, self.logic._silent_update_check)
        try:
            if page == "diagnostics":
                QTimer.singleShot(150, self.logic.show_diagnostics)
            self.apply_gui_action(page, start_daemon_on_open)
        except Exception:
            log.warning("no pude aplicar la acción de arranque", exc_info=True)

        try:
            self.root.closed.connect(self._on_closed)
        except Exception:
            log.debug("no pude conectar closed del host", exc_info=True)

    # ------------------------------------------------------------ conexiones

    def _emit(self, kind, payload):
        try:
            if kind == "state":
                self.bridge.state.emit(json.dumps(payload, ensure_ascii=False))
            elif kind == "toast":
                self.bridge.toast.emit(json.dumps(payload, ensure_ascii=False))
            elif kind == "meter":
                self.bridge.meter.emit(json.dumps(payload, ensure_ascii=False))
            elif kind == "progress":
                self.bridge.progress.emit(json.dumps(payload, ensure_ascii=False))
            elif kind == "diagnostics":
                self.bridge.diagnostics.emit(json.dumps(payload, ensure_ascii=False))
            elif kind == "key_result":
                self.bridge.key_result.emit(json.dumps(payload, ensure_ascii=False))
            elif kind == "key_capture":
                self.bridge.key_capture.emit(json.dumps(payload, ensure_ascii=False))
            elif kind == "navigate":
                self.bridge.navigate.emit(json.dumps(payload, ensure_ascii=False))
            elif kind == "close":
                self.close()
            # "idle" y "mic_loaded" no tienen contraparte en la página.
        except Exception:
            log.debug("no pude empujar %s al panel", kind, exc_info=True)

    def _handle_call(self, payload):
        try:
            message = json.loads(payload)
        except ValueError:
            return
        self.logic.handle(message)

    def _schedule(self, milliseconds, fn):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(milliseconds, fn)

    def _on_closed(self):
        """El usuario cerró la ventana: se cierra la lógica y sale el proceso."""
        try:
            self.logic.close()
        finally:
            self.application.quit()

    # ------------------------------------------------------------- pública

    def apply_gui_action(self, page=None, start_daemon=False):
        """Pedido de otra instancia: enfoca la ventana y aplica la acción."""
        try:
            self.root.setProperty("visible", True)
            self.root.showNormal()
            self.root.raise_()
            self.root.requestActivate()
        except Exception:
            log.debug("no pude enfocar el panel", exc_info=True)
        self.logic.apply_gui_action(page, start_daemon)

    @property
    def _closed(self):
        return self.logic._closed

    def close(self):
        self.logic.close()

    def show(self):
        self.root.setProperty("visible", True)

    def showNormal(self):
        self.show()

    def raise_(self):
        try:
            self.root.raise_()
        except Exception:
            pass

    def activateWindow(self):
        try:
            self.root.requestActivate()
        except Exception:
            pass


def run_gui(page="home", autostart_override=None, start_daemon_on_open=False):
    mutex = None
    try:
        if sys.platform == "win32":
            # Icono propio en la barra de tareas: sin AppUserModelID explícito,
            # Windows agrupa la ventana bajo el icono de Python (pythonw.exe).
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    _APP_USER_MODEL_ID)
            except Exception:
                log.warning("no pude fijar el AppUserModelID", exc_info=True)
            from instant_app.gui_lifecycle import acquire_gui_mutex
            mutex = acquire_gui_mutex(
                request_daemon_start=start_daemon_on_open, page=page)
            if mutex is None:
                return 0
        elif sys.platform.startswith("linux") and not (
                os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            # Sin servidor gráfico Qt aborta el proceso: se avisa y se sale.
            logging.getLogger("instant").error(
                "sin entorno gráfico (DISPLAY/WAYLAND_DISPLAY); "
                "para configurar sin ventana: instant setup --tui")
            return 2
        from PySide6.QtWebEngineQuick import QtWebEngineQuick
        QtWebEngineQuick.initialize()
        from PySide6.QtGui import QGuiApplication
        app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        if sys.platform != "win32" and _forward_to_existing_gui(
                page, start_daemon_on_open):
            log.info("el panel ya estaba abierto; se le pasó el pedido.")
            return 0
        app.setApplicationName("Instant")
        from io import BytesIO

        from PySide6.QtGui import QIcon, QPixmap

        from instant_app.branding import create_icon_image
        icon_bytes = BytesIO()
        create_icon_image(64).save(icon_bytes, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(icon_bytes.getvalue(), "PNG")
        app.setWindowIcon(QIcon(pixmap))
        window = _WebPanel(page=page, autostart_override=autostart_override,
                           start_daemon_on_open=start_daemon_on_open)
        if sys.platform != "win32":
            # La referencia vive en la ventana: el canal muere con ella.
            window._gui_server = _install_gui_server(window)
        log.info("panel abierto (%s).", page)
        return app.exec()
    except Exception:
        logging.getLogger("instant").exception("interfaz gráfica no disponible")
        return 2
    finally:
        if mutex is not None:
            from instant_app.gui_lifecycle import release_gui_mutex
            release_gui_mutex(mutex)
