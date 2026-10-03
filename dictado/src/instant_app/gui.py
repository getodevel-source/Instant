"""Windows control center for Instant, implemented with Qt Widgets."""
import ctypes
import threading

import logging
import os
import signal
import subprocess
import sys

from instant_app import audio, autostart, config, context, hotkey, models
from instant_app.branding import create_icon_image
from instant_app.paths import resolve_data_dir
from instant_app.launch import app_command, app_environment
_WORKER_MANAGERS = set()
_WORKER_MANAGER_LOCK = threading.Lock()


def _worker_manager(manager_type):
    with _WORKER_MANAGER_LOCK:
        for manager in _WORKER_MANAGERS:
            return manager
        QApplication = _qt_types()["QApplication"]
        manager = manager_type()
        manager.setParent(QApplication.instance())
        _WORKER_MANAGERS.add(manager)
        return manager
log = logging.getLogger("instant")

COLORS = {
    "background": "#10191f", "surface": "#18272e", "surface_alt": "#21363e",
    "line": "#3a5159", "text": "#e7eff1", "muted": "#a7b8bd",
    "accent": "#55d5c8", "accent_button": "#087c72", "accent_hover": "#0b9085",
    "hero": "#153744", "hero_text": "#f4f8f8", "green": "#7cdda6",
    "amber": "#f2c36a", "red": "#ff908b",
}



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


def stop_daemon():
    pid = _pid_value()
    if pid is None or not daemon_is_running():
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


# The Qt dependency is imported below the Windows GUI entrypoint, not at module
# import time: the daemon tray may import app_command without creating a GUI.
def _qt_types():
    from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
    from PySide6.QtGui import QFont, QIcon, QKeySequence
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout,
        QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
        QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy,
        QStackedWidget, QVBoxLayout, QWidget,
    )
    return locals()


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
            log.exception("no pude listar micrófonos para la GUI")
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


# Qt worker: arbitrary blocking call executes off the GUI thread. Every result
# reaches widgets through a queued Qt signal on the owning thread.
def _worker_class():
    qt = _qt_types()
    QObject, QRunnable, Signal, Slot, QTimer = (qt[k] for k in ("QObject", "QRunnable", "Signal", "Slot", "QTimer"))

    class Signals(QObject):
        progress = Signal(object)
        result = Signal(object)
        error = Signal(object)
        finished = Signal(object)

    class Worker(QRunnable):
        def __init__(self, fn):
            super().__init__()
            self.setAutoDelete(False)
            self.fn = fn
            self.signals = Signals()
            self.done = False
        @Slot()
        def run(self):
            try:
                self.signals.result.emit(self.fn(self.signals.progress.emit))
            except Exception as exc:
                self.signals.error.emit(exc)
            finally:
                self.signals.finished.emit(self)
                self.done = True

    class Manager(QObject):
        completed = Signal(object)
        released = Signal(object)
        def __init__(self):
            super().__init__()
            self.active = set()
            self.completed.connect(self._completed)

        def submit(self, worker, pool):
            self.active.add(worker)
            worker.signals.finished.connect(self.completed.emit)
            pool.start(worker)

        @Slot(object)
        def _completed(self, worker):
            if not worker.done:
                QTimer.singleShot(1, lambda w=worker: self._completed(w))
                return
            self.active.discard(worker)
            worker.signals.deleteLater()
            self.released.emit(worker)

    return Worker, Manager


def _main_window_class():
    qt = _qt_types()
    QApplication, QCheckBox, QComboBox, QDialog, QFrame = (qt[k] for k in ("QApplication", "QCheckBox", "QComboBox", "QDialog", "QFrame"))
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox = (qt[k] for k in ("QHBoxLayout", "QLabel", "QLineEdit", "QMainWindow", "QMessageBox"))
    QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy = (qt[k] for k in ("QPlainTextEdit", "QProgressBar", "QPushButton", "QSizePolicy"))
    QStackedWidget, QVBoxLayout, QWidget = (qt[k] for k in ("QStackedWidget", "QVBoxLayout", "QWidget"))
    Qt, QTimer, QIcon, QFont, QKeySequence = (qt[k] for k in ("Qt", "QTimer", "QIcon", "QFont", "QKeySequence"))
    Worker, Manager = _worker_class()

    class KeyCaptureDialog(QDialog):
        captured = qt["Signal"](str)
        def __init__(self, parent):
            super().__init__(parent)
            self.setWindowTitle("Elegí una tecla")
            self.setModal(True)
            self.setFixedWidth(430)
            self.setStyleSheet(STYLE)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(24, 22, 24, 20)
            title = QLabel("Apretá la tecla que quieras usar")
            title.setObjectName("dialogTitle")
            layout.addWidget(title)
            layout.addWidget(QLabel("Una tecla, sin combinación. Elegí una que no uses al escribir."))
            self.message = QLabel("Esperando una tecla…")
            self.message.setObjectName("accentText")
            layout.addWidget(self.message)
            row = QHBoxLayout()
            row.addStretch()
            cancel = QPushButton("Cancelar")
            cancel.clicked.connect(self.reject)
            row.addWidget(cancel)
            layout.addLayout(row)
            self.setFocusPolicy(Qt.StrongFocus)

        def keyPressEvent(self, event):
            modifiers = event.modifiers()
            if modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
                self.message.setText("Elegí una sola tecla, sin combinación.")
                event.accept()
                return
            vk = int(event.nativeVirtualKey())
            if os.name == "nt" and 8 <= vk <= 0xFE:
                value = f"vk:{vk}"
            else:
                name = QKeySequence(event.key()).toString().lower().replace(" ", "_")
                if not hotkey.is_valid_key(name):
                    self.message.setText("No pude identificar esa tecla; probá otra.")
                    event.accept()
                    return
                value = hotkey.normalize_key(name)
            self.captured.emit(value)
            self.accept()

    class TaskReceiver(qt["QObject"]):
        def __init__(self, owner, result_callback, error_callback, progress_callback):
            super().__init__(owner)
            self.owner = owner
            self.result_callback = result_callback
            self.error_callback = error_callback
            self.progress_callback = progress_callback

        @qt["Slot"](object)
        def result(self, value):
            if not self.owner._closed: self.result_callback(value)

        @qt["Slot"](object)
        def error(self, value):
            if not self.owner._closed: self.error_callback(value)

        @qt["Slot"](object)
        def progress(self, value):
            if not self.owner._closed and self.progress_callback:
                self.progress_callback(value)

    class InstantWindow(QMainWindow):
        microphones_loaded = qt["Signal"]()
        workers_idle = qt["Signal"]()
        def __init__(self, page="home", autostart_override=None,
                     start_daemon_on_open=False):
            super().__init__()
            self.page = page
            self._autostart_override = autostart_override
            self._start_daemon_on_open = start_daemon_on_open
            self._daemon_start_pending = False
            self._daemon_start_token = 0
            self.setWindowTitle("Instant")
            self.setMinimumSize(960, 680)
            self.resize(1120, 760)
            self.setStyleSheet(STYLE)
            self.pool = qt["QThreadPool"].globalInstance()
            self.worker_manager = _worker_manager(Manager)
            self.worker_manager.released.connect(self._worker_finished)
            self.cfg = config.load()
            self.data_dir = resolve_data_dir()
            self.catalog = DeviceCatalog(self.cfg)
            self.model_ready = all(models.check(self.data_dir).values())
            self._diagnostic_window = None
            self._diagnostic_text = None
            self._diagnostic_running = False
            self._key_capture_dialog = None
            self._closed = False
            self._saved_settings = None
            self._restart_settings = None
            self._restart_needed = False
            self._settings_daemon_state = None
            self._last_daemon_running = None
            self._daemon_state_ready = False
            self._daemon_check_pending = False
            self._pending_workers = set()
            self._worker_receivers = {}
            self._microphones_loaded = False
            self._build(autostart_override)
            self.refresh_microphones(initial=True)
            self.refresh_daemon()
            self._update_model_status()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh_daemon)
            self.timer.start(1000)
            if page == "diagnostics":
                QTimer.singleShot(150, self.show_diagnostics)

        def _worker_finished(self, worker):
            self._pending_workers.discard(worker)
            receiver = self._worker_receivers.pop(worker, None)
            if receiver is not None: receiver.deleteLater()
            if not self._pending_workers:
                self.workers_idle.emit()
                if self._closed: QApplication.instance().quit()

        def _label(self, text, name=None):
            label = QLabel(text)
            if name:
                label.setObjectName(name)
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            return label

        def _device_catalog_copy(self):
            catalog = DeviceCatalog(dict(self.cfg))
            catalog.rows = self.catalog.rows
            catalog.devices = dict(self.catalog.devices)
            catalog.collisions = set(self.catalog.collisions)
            catalog.pending_device = self.catalog.pending_device
            catalog.pending_identity = self.catalog.pending_identity
            return catalog

        def _update_save_enabled(self):
            ready = self._daemon_state_ready and self._microphones_loaded
            if hasattr(self, "save_button"):
                self.save_button.setEnabled(ready)
            if hasattr(self, "run_button"):
                self.run_button.setEnabled(ready and not self._daemon_start_pending)

        def _card(self, layout, title, subtitle=None):
            frame = QFrame()
            frame.setObjectName("card")
            frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            box = QVBoxLayout(frame)
            box.setContentsMargins(22, 20, 22, 20)
            box.setSpacing(12)
            heading = QLabel(title)
            heading.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            heading.setObjectName("cardTitle")
            box.addWidget(heading)
            if subtitle:
                sub = self._label(subtitle, "muted")
                box.addWidget(sub)
            layout.addWidget(frame)
            return frame, box

        def _build(self, autostart_override):
            shell = QWidget()
            root = QHBoxLayout(shell)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
            rail = QFrame()
            rail.setObjectName("rail")
            rail.setFixedWidth(228)
            nav = QVBoxLayout(rail)
            nav.setContentsMargins(18, 25, 18, 20)
            brand = QLabel("Instant")
            brand.setObjectName("brand")
            nav.addWidget(brand)
            nav.addWidget(self._label("DICTADO LOCAL · ESPAÑOL", "railCaption"))
            nav.addSpacing(25)
            self.stack = QStackedWidget()
            self.nav_buttons = {}
            for key, label in (("home", "Inicio"), ("audio", "Audio"), ("settings", "Preferencias"), ("models", "Modelos")):
                button = QPushButton(label)
                button.setObjectName("navButton")
                button.setCheckable(True)
                button.clicked.connect(lambda checked=False, name=key: self.navigate(name))
                nav.addWidget(button)
                self.nav_buttons[key] = button
            nav.addStretch()
            diag = QPushButton("Diagnóstico")
            diag.setObjectName("navButton")
            diag.clicked.connect(self.show_diagnostics)
            nav.addWidget(diag)
            nav.addWidget(self._label("Tu voz se procesa en este equipo.", "railFoot"))
            root.addWidget(rail)
            content = QWidget()
            self.content_layout = QVBoxLayout(content)
            self.content_layout.setContentsMargins(34, 28, 34, 24)
            self.content_layout.setSpacing(18)
            head = QHBoxLayout()
            heading = QVBoxLayout()
            heading.addWidget(self._label("Instant", "pageTitle"))
            heading.addWidget(self._label("Dictado local, simple y privado.", "muted"))
            head.addLayout(heading)
            head.addStretch()
            self.header_state = QLabel("Comprobando estado…")
            self.header_state.setObjectName("pill")
            head.addWidget(self.header_state)
            self.content_layout.addLayout(head)
            root.addWidget(content, 1)
            self.setCentralWidget(shell)
            self._make_pages()
            self.content_layout.addWidget(self.stack, 1)
            self.navigate("home" if self.page in ("home", "diagnostics") else self.page)
            if self.page == "setup":
                self.navigate("audio")
            self._init_settings(autostart_override)

        def _make_pages(self):
            # Home dashboard
            page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(16)
            hero = QFrame(); hero.setObjectName("hero"); hero.setMinimumHeight(250); hero.setMaximumHeight(300)
            hero_l = QHBoxLayout(hero); hero_l.setContentsMargins(28, 24, 28, 24)
            left = QVBoxLayout(); self.status_var = QLabel("Listo para dictar"); self.status_var.setObjectName("heroStatus"); self.status_var.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.status_detail = self._label("Enfocá el prompt o campo editable de la CLI antes de mantener F9. Instant pega con Ctrl+V.", "heroDetail")
            hero_title = self._label("Hablá. Soltá. Listo.", "heroTitle"); hero_title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            left.addWidget(self.status_var); left.addWidget(hero_title); left.addWidget(self.status_detail)
            hero_l.addLayout(left, 1); hero_l.setAlignment(left, Qt.AlignVCenter)
            action = QVBoxLayout(); self.key_badge = QLabel(hotkey.key_label(self.cfg.get("key", "f9"))); self.key_badge.setObjectName("keyBadge"); self.key_badge.setMaximumHeight(64); action.addWidget(self._label("TECLA", "railCaption"), alignment=Qt.AlignRight); action.addWidget(self.key_badge, alignment=Qt.AlignRight)
            self.run_button = QPushButton("Iniciar dictado"); self.run_button.setObjectName("primaryButton"); self.run_button.setEnabled(False); self.run_button.clicked.connect(self.toggle_daemon); action.addWidget(self.run_button)
            self.stop_button = QPushButton("Detener"); self.stop_button.clicked.connect(self.stop_daemon); action.addWidget(self.stop_button); self.stop_button.hide()
            hero_l.addLayout(action); layout.addWidget(hero)
            card, box = self._card(layout, "Tu espacio de dictado", "Ajustes clave siempre a mano.")
            quick = QHBoxLayout(); self.quick_mic = QLabel("Micrófono: —"); self.quick_mic.setMinimumWidth(350); self.quick_model = QLabel("Modelos: —"); quick.addWidget(self.quick_mic); quick.addStretch(); quick.addWidget(self.quick_model); box.addLayout(quick)
            self.settings_status = QLabel(""); self.settings_status.setObjectName("statusLine"); self.settings_status.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum); box.addWidget(self.settings_status)
            self.stack.addWidget(page); self.pages = {"home": 0}

            # Audio page
            page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(16)
            layout.addWidget(self._label("Audio", "pageTitle")); layout.addWidget(self._label("Elegí una entrada y comprobá que la señal llegue con claridad.", "muted"))
            card, box = self._card(layout, "Micrófono de entrada", "La lista vuelve a respetar tu selección al actualizar dispositivos.")
            row = QHBoxLayout(); self.mic_combo = QComboBox(); self.mic_combo.currentIndexChanged.connect(self._mic_selected); row.addWidget(self.mic_combo, 1)
            self.refresh_button = QPushButton("Actualizar"); self.refresh_button.clicked.connect(self.refresh_microphones); row.addWidget(self.refresh_button)
            self.test_button = QPushButton("Probar 3 s"); self.test_button.clicked.connect(self.test_microphone); row.addWidget(self.test_button); box.addLayout(row)
            self.meter = QProgressBar(); self.meter.setRange(0, 100); self.meter.setValue(0); self.meter.setTextVisible(False); box.addWidget(self.meter)
            self.meter_text = self._label("La prueba no guarda audio.", "muted"); box.addWidget(self.meter_text)
            self.stack.addWidget(page); self.pages["audio"] = self.stack.count()-1

            # Preferences page
            page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(16)
            layout.addWidget(self._label("Preferencias", "pageTitle")); layout.addWidget(self._label("Guardá los cambios para aplicarlos a Instant.", "muted"))
            card, box = self._card(layout, "Tecla de dictado", "Una tecla individual, sin combinación.")
            row = QHBoxLayout(); self.key_value = QLabel(hotkey.key_label(self.cfg.get("key", "f9"))); self.key_value.setObjectName("keyBadge"); row.addWidget(self.key_value); row.addStretch(); self.key_capture_button = QPushButton("Elegir tecla"); self.key_capture_button.clicked.connect(self.begin_key_capture); row.addWidget(self.key_capture_button); box.addLayout(row)
            card, box = self._card(layout, "Inicio y cambios", "El arranque con Windows es independiente de reiniciar el motor.")
            try: enabled = autostart.is_enabled()
            except Exception: enabled = bool(self.cfg.get("autostart"))
            if self._autostart_override is not None: enabled = self._autostart_override
            self.autostart_check = QCheckBox("Iniciar Instant con Windows"); self.autostart_check.setChecked(enabled); self.autostart_check.toggled.connect(self.settings_changed); box.addWidget(self.autostart_check)
            card, box = self._card(
                layout, "Contexto y vocabulario",
                "Perfil local para corregir términos reconocidos con grafía errónea. Una línea por término: grafía final, tabulador y variantes completas separadas por |. No modifica el audio ni fuerza vocabulario en el reconocedor.")
            row = QHBoxLayout()
            self.context_combo = QComboBox()
            self.context_combo.currentIndexChanged.connect(self._context_profile_changed)
            row.addWidget(self.context_combo, 1)
            self.context_add_button = QPushButton("Añadir perfil")
            self.context_add_button.clicked.connect(self._add_context_profile)
            row.addWidget(self.context_add_button)
            self.context_remove_button = QPushButton("Eliminar perfil")
            self.context_remove_button.clicked.connect(self._remove_context_profile)
            row.addWidget(self.context_remove_button)
            box.addLayout(row)
            self.context_editor = QPlainTextEdit()
            self.context_editor.setPlaceholderText(
                "Ejemplo: Instant\tinstante | in stand\nParakeet\tpara kit")
            self.context_editor.textChanged.connect(self.settings_changed)
            box.addWidget(self.context_editor)
            box.addWidget(self._label(
                "Variantes exactas se corrigen siempre en local. Un LLM local puede añadir puntuación de preguntas y tildes; solo recibe el texto, nunca el audio.",
                "muted"))
            self.llm_url_edit = QLineEdit(self.cfg.get("llm_url", ""))
            self.llm_url_edit.setPlaceholderText(
                "URL local de llama-server (opcional), p. ej. http://127.0.0.1:8080")
            self.llm_url_edit.textChanged.connect(self.settings_changed)
            box.addWidget(self.llm_url_edit)
            self.save_button = QPushButton("Guardar ajustes"); self.save_button.setObjectName("primaryButton"); self.save_button.setEnabled(False); self.save_button.clicked.connect(self.save_config); box.addWidget(self.save_button, alignment=Qt.AlignRight)
            self.stack.addWidget(page); self.pages["settings"] = self.stack.count()-1

            # Models page
            page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(16)
            layout.addWidget(self._label("Modelos de voz", "pageTitle")); layout.addWidget(self._label("Se descargan una vez y se ejecutan localmente.", "muted"))
            card, box = self._card(layout, "Parakeet v3 + Silero VAD", "La descarga inicial ocupa aproximadamente 670 MB.")
            self.model_status = self._label("Comprobando modelos…", "muted"); box.addWidget(self.model_status)
            self.model_progress = QProgressBar(); self.model_progress.setRange(0, 0); self.model_progress.hide(); box.addWidget(self.model_progress)
            self.model_button = QPushButton("Descargar modelos"); self.model_button.setObjectName("primaryButton"); self.model_button.clicked.connect(self.download_models); box.addWidget(self.model_button, alignment=Qt.AlignLeft)
            compare_card, compare_box = self._card(
                layout, "Comparar Parakeet y Qwen",
                "Detén el dictado y habla durante 15 segundos. Ambos modelos reciben la misma grabación; se procesa en memoria, sin guardarla, copiarla ni subirla.")
            self.compare_button = QPushButton("Grabar 15 s y comparar")
            self.compare_button.setEnabled(False)
            self.compare_button.clicked.connect(self.compare_models)
            compare_box.addWidget(self.compare_button, alignment=Qt.AlignLeft)
            self.compare_status = self._label(
                "Qwen se usa solo en esta prueba; el dictado normal sigue con Parakeet.",
                "muted")
            compare_box.addWidget(self.compare_status)
            self.compare_results = QPlainTextEdit()
            self.compare_results.setReadOnly(True)
            self.compare_results.setMaximumHeight(150)
            self.compare_results.setPlaceholderText(
                "Las transcripciones y tiempos aparecerán aquí.")
            compare_box.addWidget(self.compare_results)
            self.stack.addWidget(page); self.pages["models"] = self.stack.count()-1

        def _init_settings(self, autostart_override):
            configured = context.profiles(self.cfg)
            self.context_combo.blockSignals(True)
            self.context_combo.addItems(configured)
            active = context.active_name(self.cfg)
            self.context_combo.setCurrentText(active)
            self.context_combo.blockSignals(False)
            self._loaded_context_name = active
            self.context_editor.setPlainText(context.editor_text(configured[active]))
            self.context_remove_button.setEnabled(active != context.DEFAULT_PROFILE)
            self.key_value.setText(hotkey.key_label(self.cfg.get("key", "f9")))
            self._saved_settings = self._snapshot()
            self._restart_settings = self._restart_signature(self._saved_settings)
            self._settings_daemon_state = None
            self._update_settings_status()

        def _store_context_editor(self):
            name = getattr(self, "_loaded_context_name",
                           self.context_combo.currentText()) or context.DEFAULT_PROFILE
            configured = context.profiles(self.cfg)
            configured[name] = context.parse_editor(self.context_editor.toPlainText())
            self.cfg["context_profiles"] = configured
            self.cfg["active_context"] = self.context_combo.currentText() or name
            self._loaded_context_name = name
        def _context_profile_changed(self, _index):
            if not hasattr(self, "context_editor") or not self.context_combo.currentText():
                return
            self._store_context_editor()
            configured = context.profiles(self.cfg)
            name = self.context_combo.currentText()
            self.cfg["active_context"] = name
            self.context_editor.blockSignals(True)
            self.context_editor.setPlainText(context.editor_text(configured.get(name, [])))
            self.context_editor.blockSignals(False)
            self._loaded_context_name = name
            self.context_remove_button.setEnabled(name != context.DEFAULT_PROFILE)
            self.settings_changed()

        def _add_context_profile(self):
            qt = _qt_types()
            name, accepted = qt["QInputDialog"].getText(
                self, "Añadir perfil", "Nombre del perfil:")
            name = name.strip()
            if not accepted or not name:
                return
            configured = context.profiles(self.cfg)
            if name in configured:
                qt["QMessageBox"].warning(self, "Instant", "Ya existe ese perfil.")
                return
            self._store_context_editor()
            configured[name] = []
            self.cfg["context_profiles"] = configured
            self.context_combo.addItem(name)
            self.context_combo.setCurrentText(name)

        def _remove_context_profile(self):
            name = self.context_combo.currentText()
            if name == context.DEFAULT_PROFILE:
                return
            qt = _qt_types()
            answer = qt["QMessageBox"].question(
                self, "Eliminar perfil",
                f"¿Eliminar el perfil «{name}» y sus términos?")
            if answer != qt["QMessageBox"].Yes:
                return
            self._store_context_editor()
            configured = context.profiles(self.cfg)
            configured.pop(name, None)
            configured.setdefault(context.DEFAULT_PROFILE, [])
            self.cfg["context_profiles"] = configured
            self.context_combo.blockSignals(True)
            self.context_combo.removeItem(self.context_combo.currentIndex())
            self.context_combo.setCurrentText(context.DEFAULT_PROFILE)
            self.context_combo.blockSignals(False)
            self.cfg["active_context"] = context.DEFAULT_PROFILE
            self._loaded_context_name = context.DEFAULT_PROFILE
            self.context_editor.setPlainText(
                context.editor_text(configured[context.DEFAULT_PROFILE]))
            self.context_remove_button.setEnabled(False)
            self.settings_changed()

        def navigate(self, name):
            if name not in self.pages: return
            self.stack.setCurrentIndex(self.pages[name])
            for key, button in self.nav_buttons.items(): button.setChecked(key == name)

        def _selected_device(self):
            value = self.mic_combo.currentData()
            return tuple(value) if value is not None else None

        def _snapshot(self):
            device = self._selected_device()
            if device: self.catalog.remember(device)
            mic = self.catalog.pending_identity or DeviceCatalog.identity((self.cfg.get("mic_index"), self.cfg.get("mic_hint", "")))
            self._store_context_editor()
            context_state = tuple(
                (name, tuple((row["term"], tuple(row["aliases"])) for row in items))
                for name, items in context.profiles(self.cfg).items())
            return (mic, self.key_value.text().strip().lower(),
                    self.autostart_check.isChecked(),
                    self.cfg["active_context"], context_state,
                    self.llm_url_edit.text().strip())

        def _restart_signature(self, snapshot):
            return snapshot[0], snapshot[1], snapshot[3], snapshot[4], snapshot[5]
        def _same_settings(self, left, right):
            return self.catalog.same_identity(left[0], right[0]) and left[1:] == right[1:]

        def settings_changed(self, *_):
            self._update_settings_status()

        def _update_settings_status(self):
            if self._saved_settings is None: return
            snapshot = self._snapshot()
            text = "Hay cambios sin guardar." if not self._same_settings(snapshot, self._saved_settings) else ("Guardado; reiniciá Instant para aplicar micrófono, tecla, vocabulario o LLM." if self._restart_needed else "Ajustes guardados.")
            self.settings_status.setText(text)

        def _settings_daemon_changed(self, running):
            previous = self._settings_daemon_state
            self._settings_daemon_state = bool(running)
            if previous is None:
                if not running: self._restart_needed = False
            elif previous != bool(running):
                self._restart_needed = False
                if running: self._restart_settings = self._restart_signature(self._saved_settings)
            self._update_settings_status()

        def refresh_microphones(self, initial=False):
            self.refresh_button.setEnabled(False)
            self.mic_combo.setEnabled(False)
            self._microphones_loaded = False
            self._update_save_enabled()
            catalog = self._device_catalog_copy()
            preferred = None if initial else catalog.pending_device
            def enumerate_devices(_emit):
                result = catalog.refresh(preferred, preserve=not initial)
                return catalog, result
            def populated(payload):
                self.catalog, result = payload
                self.refresh_button.setEnabled(True)
                labels, selected, missing = result
                self.mic_combo.blockSignals(True); self.mic_combo.clear()
                for label in labels:
                    self.mic_combo.addItem(label, self.catalog.devices[label])
                if selected is not None: self.mic_combo.setCurrentIndex(labels.index(selected))
                elif missing:
                    self.mic_combo.addItem("El micrófono seleccionado no está disponible", None); self.mic_combo.setCurrentIndex(self.mic_combo.count()-1)
                elif labels: self.mic_combo.setCurrentIndex(0)
                else: self.mic_combo.addItem("No se detectaron micrófonos", None)
                self.mic_combo.setEnabled(bool(labels)); self.test_button.setEnabled(bool(labels)); self.mic_combo.blockSignals(False)
                device = self._selected_device()
                if device: self.catalog.remember(device)
                if initial and self._saved_settings is not None:
                    snapshot = self._snapshot()
                    self._saved_settings = (snapshot[0], self._saved_settings[1], *self._saved_settings[2:])
                    self._restart_settings = (snapshot[0], *self._restart_settings[1:])
                self.quick_mic.setText("Micrófono: " + (self.mic_combo.currentText() if device else "No disponible"))
                if not labels: self.meter_text.setText("No se detectaron micrófonos. Conectá una entrada y actualizá la lista.")
                elif not device and missing: self.meter_text.setText("El micrófono elegido no está disponible; seleccioná otro.")
                elif not initial: self.meter_text.setText("Lista de micrófonos actualizada.")
                self._microphones_loaded = True
                self._update_save_enabled()
                self.meter.setValue(0); self._update_settings_status()
                self._maybe_start_daemon_on_open()
                self.microphones_loaded.emit()
            def failed(error):
                self.refresh_button.setEnabled(True)
                self.mic_combo.setEnabled(bool(self.mic_combo.count()))
                self.meter_text.setText(f"No se pudo actualizar la lista: {error}")
                self._microphones_loaded = True
                self._update_save_enabled()
                self._maybe_start_daemon_on_open()
                self.microphones_loaded.emit()
            self._run_worker(enumerate_devices, populated, failed)

        def _mic_selected(self, _index):
            if not hasattr(self, "catalog"): return
            device = self._selected_device()
            if device:
                self.catalog.remember(device); self.meter_text.setText("Entrada seleccionada."); self.quick_mic.setText("Micrófono: " + self.mic_combo.currentText())
            self.meter.setValue(0); self._update_settings_status()

        def _run_worker(self, fn, on_result, on_error=None, on_progress=None):
            worker = Worker(fn)
            receiver = TaskReceiver(self, on_result, on_error or self._show_worker_error, on_progress)
            self._pending_workers.add(worker)
            self._worker_receivers[worker] = receiver
            worker.signals.result.connect(receiver.result, Qt.QueuedConnection)
            worker.signals.error.connect(receiver.error, Qt.QueuedConnection)
            if on_progress: worker.signals.progress.connect(receiver.progress, Qt.QueuedConnection)
            self.worker_manager.submit(worker, self.pool)
            return worker

        def _show_worker_error(self, error):
            QMessageBox.critical(self, "Instant", str(error))

        def test_microphone(self):
            selected = self._selected_device()
            if not selected:
                QMessageBox.warning(self, "Instant", "Elegí un micrófono de entrada."); return
            self.test_button.setEnabled(False); self.meter.setValue(0); self.meter_text.setText("Hablá ahora…")
            def capture(emit):
                def level(value): emit(("level", value))
                return audio.peak_meter(selected[0], seconds=3.0, on_level=level)
            def progress(event):
                if event[0] == "level":
                    self.meter.setValue(min(100, int(event[1] * 200))); self.meter_text.setText(f"Señal {event[1]:.3f}")
            def done(peak):
                self.test_button.setEnabled(True)
                self.meter_text.setText(f"Señal detectada ({peak:.3f})." if peak > .005 else "No detecté señal; revisá micrófono/volumen.")
            self._run_worker(capture, done, lambda error: (self.test_button.setEnabled(True), QMessageBox.warning(self, "Prueba de micrófono", str(error))), progress)

        def compare_models(self):
            if not self._daemon_state_ready:
                QMessageBox.information(
                    self, "Comparación de modelos",
                    "Espera a que Instant compruebe el estado del daemon.")
                return
            if self._last_daemon_running:
                QMessageBox.information(
                    self, "Comparación de modelos",
                    "Detén el dictado normal antes de comparar; ambos modelos usan CPU y el mismo micrófono.")
                return
            if not self.model_ready or not self.qwen_ready:
                QMessageBox.warning(
                    self, "Modelos pendientes",
                    "La comparación requiere Parakeet y los archivos locales de Qwen3-ASR 0.6B.")
                return
            from instant_app.comparison import RECORD_SECONDS
            self._snapshot()
            cfg = dict(self.cfg)
            self.compare_button.setEnabled(False)
            self.compare_status.setText(
                f"Grabando {int(RECORD_SECONDS)} segundos… di tu frase una sola vez.")
            self.compare_results.clear()

            def run(emit):
                import time
                import numpy as np

                mic = audio.resolve_mic(
                    cfg.get("mic_hint", ""), cfg.get("mic_index"),
                    strict_hint=bool(cfg.get("mic_hint")))
                if cfg.get("mic_hint") and mic is None:
                    raise RuntimeError("El micrófono guardado no está disponible.")
                frames = []

                def callback(indata, _frames, _time_info, status):
                    if status:
                        log.warning("comparación de audio: %s", status)
                    frames.append(indata.copy())

                stream, _selected = audio.open_input_stream(mic, callback=callback)
                try:
                    end = time.monotonic() + RECORD_SECONDS
                    while True:
                        remaining = end - time.monotonic()
                        if remaining <= 0:
                            break
                        emit(("recording", RECORD_SECONDS - remaining))
                        time.sleep(min(0.1, remaining))
                finally:
                    stream.stop()
                    stream.close()
                if not frames:
                    raise RuntimeError("El micrófono no entregó audio.")
                wav = audio.to_mono(np.concatenate(frames, axis=0))
                from instant_app.comparison import compare_models as compare
                return compare(
                    wav, cfg, self.data_dir,
                    progress=lambda message: emit(("processing", message)))

            def progress(event):
                kind, value = event
                if kind == "recording":
                    self.compare_status.setText(
                        f"Grabando… {int(value) + 1}/{int(RECORD_SECONDS)} s. Habla normal.")
                else:
                    self.compare_status.setText(value)

            def done(results):
                self.compare_button.setEnabled(
                    self.qwen_ready and self.model_ready
                    and self._daemon_state_ready and not self._last_daemon_running)
                self.compare_status.setText(
                    "Comparación completa. Se usó el mismo audio y el contexto activo.")
                from instant_app.comparison import format_results
                self.compare_results.setPlainText(format_results(results))

            def failed(error):
                self.compare_button.setEnabled(
                    self.qwen_ready and self.model_ready
                    and self._daemon_state_ready and not self._last_daemon_running)
                self.compare_status.setText(f"No se pudo comparar: {error}")

            self._run_worker(run, done, failed, progress)

        def save_config(self, show_message=True):
            selected = self._selected_device()
            if selected:
                self.catalog.remember(selected)
                self.cfg["mic_index"], self.cfg["mic_hint"] = selected
            snapshot = self._snapshot()
            self.cfg["key"], self.cfg["lang"], self.cfg["autostart"] = snapshot[1], "es", snapshot[2]
            self.cfg["llm_url"] = snapshot[5]
            path = config.save(self.cfg)
            warning = None
            try:
                desired = snapshot[2]
                if autostart.is_enabled() != desired: (autostart.enable if desired else autostart.disable)()
            except Exception as exc: warning = str(exc)
            saved = (DeviceCatalog.identity((self.cfg.get("mic_index"), self.cfg.get("mic_hint", ""))), *snapshot[1:])
            running = bool(self._last_daemon_running)
            signature = self._restart_signature(saved)
            if running:
                self._restart_needed = not (
                    self.catalog.same_identity(signature[0], self._restart_settings[0])
                    and signature[1:] == self._restart_settings[1:])
            else:
                self._restart_settings = signature
                self._restart_needed = False
            self._saved_settings = saved; self._update_settings_status()
            if warning: QMessageBox.warning(self, "Arranque con Windows", warning)
            if show_message:
                note = "\nMicrófono, tecla, vocabulario y LLM guardados; reiniciá Instant para aplicarlos." if self._restart_needed else ""
                QMessageBox.information(self, "Instant", f"Ajustes guardados.{note}\n{path}")
            return True

        def toggle_daemon(self):
            if self._daemon_start_pending:
                return
            if self._last_daemon_running:
                self.save_config(False); self.stop_daemon(restart=True)
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
                QMessageBox.warning(self, "Modelos pendientes", "Descargá los modelos de voz antes de iniciar Instant."); return False
            if save_settings:
                self.save_config(False)
            try:
                env = app_environment()
                env["DICTADO_DATA"] = self.data_dir
                self._daemon_start_pending = True
                self._daemon_start_token += 1
                token = self._daemon_start_token
                self._update_save_enabled()
                subprocess.Popen(app_command(("run",)), cwd=_workdir(),
                                 env=env,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.status_detail.setText("Iniciando Instant…")
                QTimer.singleShot(10000, lambda: self._daemon_start_timeout(token))
                QTimer.singleShot(700, self.refresh_daemon)
                return True
            except Exception as exc:
                self._daemon_start_pending = False
                self._update_save_enabled()
                QMessageBox.critical(self, "No se pudo iniciar Instant", str(exc))
                return False

        def _daemon_start_timeout(self, token):
            if token != self._daemon_start_token or not self._daemon_start_pending:
                return
            self._daemon_start_pending = False
            self._update_save_enabled()
            if not self._last_daemon_running:
                self.status_detail.setText("Instant no pudo iniciar. Revisá Diagnóstico.")
                log.warning("el daemon no confirmó inicio dentro del plazo")
        def stop_daemon(self, restart=False):
            pid = _pid_value()
            if pid is None or not self._last_daemon_running:
                if restart: self._start_daemon()
                else: self.refresh_daemon()
                return
            if os.name == "nt":
                subprocess.Popen(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                try: os.kill(pid, signal.SIGTERM)
                except OSError: pass
            self.status_detail.setText("Cerrando Instant…")
            if restart: QTimer.singleShot(350, self._wait_before_restart)
            else: QTimer.singleShot(700, self.refresh_daemon)

        def _wait_before_restart(self):
            if self._last_daemon_running:
                self.refresh_daemon(); QTimer.singleShot(250, self._wait_before_restart)
            else: self._start_daemon()

        def refresh_daemon(self):
            if self._daemon_check_pending: return
            self._daemon_check_pending = True
            def result(running):
                self._daemon_check_pending = False
                self._daemon_state_ready = True
                if running and self._daemon_start_pending:
                    self._daemon_start_pending = False
                    self._daemon_start_token += 1
                if running != self._last_daemon_running:
                    self._last_daemon_running = running; self._settings_daemon_changed(running)
                self._update_save_enabled()
                if hasattr(self, "qwen_ready"):
                    self.compare_button.setEnabled(
                        self.model_ready and self.qwen_ready and not running)
                self.header_state.setText("●  Instant activo" if running else "●  Listo para dictar")
                self.header_state.setProperty("active", running); self.header_state.style().unpolish(self.header_state); self.header_state.style().polish(self.header_state)
                if running:
                    self.status_var.setText("Instant está activo"); self.status_detail.setText("Enfocá el prompt o campo editable de la CLI antes de mantener F9. Instant pega con Ctrl+V."); self.run_button.setText("Reiniciar con cambios"); self.stop_button.show()
                else:
                    self.status_var.setText("Listo para dictar"); self.status_detail.setText("Enfocá el prompt o campo editable de la CLI antes de mantener F9. Instant pega con Ctrl+V."); self.run_button.setText("Iniciar dictado"); self.stop_button.hide()
                self._maybe_start_daemon_on_open()
            def failed(error):
                self._daemon_check_pending = False
                log.warning("no se pudo comprobar el daemon desde la GUI: %s", error)
            self._run_worker(lambda _emit: daemon_is_running(), result, failed)

        def _update_model_status(self):
            self.model_ready = all(models.check(self.data_dir).values())
            self.quick_model.setText("Modelos: listos" if self.model_ready else "Modelos: pendientes")
            if self.model_ready:
                self.model_status.setText("Parakeet y VAD listos en este equipo."); self.model_button.setText("Modelos listos"); self.model_button.setEnabled(False)
            else:
                self.model_status.setText("Faltan modelos; se descargan una sola vez (~670 MB)."); self.model_button.setText("Descargar modelos"); self.model_button.setEnabled(True)
            self.qwen_ready = all(models.check_qwen3_asr(self.data_dir).values())
            self.compare_button.setEnabled(
                self.model_ready and self.qwen_ready
                and self._daemon_state_ready and not self._last_daemon_running)
            if self.qwen_ready:
                self.compare_status.setText(
                    "Qwen 0.6B listo. La comparación usa el vocabulario del perfil activo.")
            else:
                self.compare_status.setText(
                    "Faltan los archivos opcionales Qwen3-ASR 0.6B INT8 para comparar.")

        def download_models(self):
            if self.model_ready: return
            self.model_button.setEnabled(False); self.model_button.setText("Descargando…"); self.model_status.setText("Descargando modelos de voz…"); self.model_progress.show()
            def download(emit):
                return models.download_models(self.data_dir, progress=lambda *args: emit(args))
            def progress(event):
                step, done, total = event
                if step == "parakeet": self.model_status.setText("Parakeet descargado; preparando VAD…")
                elif total: self.model_status.setText(f"Descargando VAD: {done / total:.0%}")
            def done(_):
                self.model_progress.hide(); self._update_model_status()
            def failed(error):
                self.model_progress.hide(); self.model_button.setEnabled(True); self.model_button.setText("Reintentar"); self.model_status.setText("No se pudieron descargar los modelos."); QMessageBox.critical(self, "Descarga fallida", str(error))
            self._run_worker(download, done, failed, progress)

        def show_diagnostics(self):
            if self._diagnostic_window is not None:
                self._diagnostic_window.showNormal(); self._diagnostic_window.raise_(); self._diagnostic_window.activateWindow(); return
            dialog = QDialog(self); self._diagnostic_window = dialog; dialog.setWindowTitle("Diagnóstico de Instant"); dialog.resize(680, 470); dialog.setStyleSheet(STYLE)
            layout = QVBoxLayout(dialog); layout.addWidget(self._label("Diagnóstico", "pageTitle")); layout.addWidget(self._label("Micrófono, tecla y modelos", "muted"))
            output = QPlainTextEdit(); output.setReadOnly(True); output.setPlainText("Ejecutando comprobaciones…"); layout.addWidget(output)
            self._diagnostic_text = output
            dialog.finished.connect(self._close_diagnostics)
            dialog.show(); dialog.raise_(); dialog.activateWindow()
            if self._diagnostic_running: return
            self._diagnostic_running = True
            def diagnose(_emit):
                from instant_app.daemon import cmd_check
                from contextlib import redirect_stdout
                from io import StringIO
                stream = StringIO()
                with redirect_stdout(stream): rc = cmd_check(config.load())
                return rc, stream.getvalue()
            def done(result):
                self._diagnostic_running = False
                if self._diagnostic_text is not None: self._diagnostic_text.setPlainText(result[1] or "Sin salida de diagnóstico.")
            def failed(error):
                self._diagnostic_running = False
                if self._diagnostic_text is not None: self._diagnostic_text.setPlainText(f"Diagnóstico fallido: {error}")
            self._run_worker(diagnose, done, failed)

        def _close_diagnostics(self, *_):
            self._diagnostic_window = None; self._diagnostic_text = None

        def begin_key_capture(self):
            if self._key_capture_dialog is not None:
                self._key_capture_dialog.raise_(); self._key_capture_dialog.activateWindow(); return
            dialog = KeyCaptureDialog(self); self._key_capture_dialog = dialog
            dialog.captured.connect(self._set_key); dialog.finished.connect(lambda *_: setattr(self, "_key_capture_dialog", None)); dialog.open()

        def _set_key(self, key):
            self.key_value.setText(hotkey.key_label(key)); self._update_settings_status()

        def request_daemon_start(self):
            self._start_daemon_on_open = True
            self._maybe_start_daemon_on_open()
        def nativeEvent(self, event_type, message):
            if sys.platform == "win32":
                from ctypes import wintypes
                from instant_app.gui_lifecycle import (
                    _ACTION_DIAGNOSTICS, _ACTION_SETUP,
                    _ACTION_START_DAEMON, _GUI_ACTION_MESSAGE)
                native = ctypes.cast(
                    int(message), ctypes.POINTER(wintypes.MSG)).contents
                if native.message == _GUI_ACTION_MESSAGE:
                    if native.wParam == _ACTION_START_DAEMON:
                        self.navigate("home")
                        self.request_daemon_start()
                    elif native.wParam == _ACTION_SETUP:
                        self.navigate("audio")
                    elif native.wParam == _ACTION_DIAGNOSTICS:
                        self.show_diagnostics()
                    return True, 0
            return super().nativeEvent(event_type, message)

        def closeEvent(self, event):
            self._closed = True
            self.timer.stop()
            app = QApplication.instance()
            app.setQuitOnLastWindowClosed(False)
            if not self._pending_workers:
                app.quit()
            event.accept()

    return InstantWindow


STYLE = f"""
QMainWindow, QWidget {{ background:{COLORS['background']}; color:{COLORS['text']}; font-family:'Segoe UI'; font-size:10pt; }}
QLabel {{ background:transparent; }}
QFrame#rail {{ background:#0d2028; }}
QLabel#brand {{ color:#f5fbfb; font-size:22pt; font-weight:700; }}
QLabel#railCaption {{ color:#9bb2b9; font-size:8pt; letter-spacing:1px; }}
QLabel#railFoot {{ color:#a8bbc0; font-size:9pt; }}
QPushButton#navButton {{ text-align:left; color:#d3e1e3; background:transparent; border:0; border-radius:8px; padding:12px 13px; font-weight:600; }}
QPushButton#navButton:hover {{ background:#203b46; }}
QPushButton#navButton:checked {{ background:{COLORS['accent_button']}; color:white; }}
QLabel#pageTitle {{ font-size:23pt; font-weight:700; }}
QLabel#muted {{ color:{COLORS['muted']}; }}
QLabel#pill {{ background:#263941; color:#d7e4e7; border-radius:12px; padding:8px 13px; font-weight:700; }}
QLabel#pill[active="true"] {{ background:#173e35; color:{COLORS['green']}; }}
QFrame#hero {{ background:{COLORS['hero']}; border-radius:16px; }}
QLabel#heroStatus {{ color:#8fe0c3; font-size:12pt; font-weight:700; }}
QLabel#heroTitle {{ color:{COLORS['hero_text']}; font-size:23pt; font-weight:700; }}
QLabel#heroDetail {{ color:#c7d9dc; }}
QLabel#keyBadge {{ background:#28505a; color:white; border-radius:9px; padding:8px 14px; font-size:15pt; font-weight:700; }}
QFrame#card {{ background:{COLORS['surface']}; border:1px solid {COLORS['line']}; border-radius:13px; }}
QLabel#cardTitle {{ font-size:13pt; font-weight:700; }}
QLabel#statusLine {{ color:{COLORS['muted']}; }}
QPushButton {{ background:{COLORS['surface_alt']}; color:{COLORS['text']}; border:1px solid {COLORS['line']}; border-radius:8px; padding:10px 15px; font-weight:600; }}
QPushButton:hover {{ background:#2b454e; }}
QPushButton:disabled {{ color:#819399; background:#1b2a30; }}
QPushButton#primaryButton {{ background:{COLORS['accent_button']}; color:white; border:0; }}
QPushButton#primaryButton:hover {{ background:{COLORS['accent_hover']}; }}
QComboBox, QPlainTextEdit {{ background:{COLORS['surface_alt']}; color:{COLORS['text']}; border:1px solid {COLORS['line']}; border-radius:8px; padding:9px; selection-color:white; selection-background-color:{COLORS['accent_button']}; }}
QComboBox QAbstractItemView {{ background:{COLORS['surface_alt']}; color:{COLORS['text']}; border:1px solid {COLORS['line']}; selection-color:white; selection-background-color:{COLORS['accent_button']}; }}
QProgressBar {{ min-height:10px; max-height:10px; border:0; background:#293e46; border-radius:5px; }}
QProgressBar::chunk {{ background:{COLORS['accent']}; border-radius:5px; }}
QCheckBox {{ spacing:10px; padding:7px; }}
QCheckBox::indicator {{ width:18px; height:18px; border:1px solid {COLORS['line']}; border-radius:4px; background:{COLORS['surface_alt']}; }}
QCheckBox::indicator:checked {{ background:{COLORS['accent_button']}; border-color:{COLORS['accent_button']}; }}
QPlainTextEdit {{ selection-color:white; }}
QToolTip {{ background:{COLORS['surface_alt']}; color:{COLORS['text']}; border:1px solid {COLORS['line']}; }}
"""


def run_gui(page="home", autostart_override=None, start_daemon_on_open=False):
    mutex = None
    try:
        if sys.platform == "win32":
            from instant_app.gui_lifecycle import acquire_gui_mutex
            mutex = acquire_gui_mutex(
                request_daemon_start=start_daemon_on_open, page=page)
            if mutex is None: return 0
        qt = _qt_types()
        QApplication = qt["QApplication"]
        app = QApplication.instance() or QApplication(sys.argv[:1])
        app.setApplicationName("Instant")
        app.setStyle("Fusion")
        from io import BytesIO
        from PySide6.QtGui import QIcon, QPixmap
        icon_bytes = BytesIO()
        create_icon_image(64).save(icon_bytes, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(icon_bytes.getvalue(), "PNG")
        app.setWindowIcon(QIcon(pixmap))
        window = _main_window_class()(
            page=page, autostart_override=autostart_override,
            start_daemon_on_open=start_daemon_on_open)
        window.show()
        log.info("interfaz gráfica abierta (%s).", page)
        return app.exec()
    except Exception:
        logging.getLogger("instant").exception("interfaz gráfica no disponible")
        return 2
    finally:
        if mutex is not None:
            from instant_app.gui_lifecycle import release_gui_mutex
            release_gui_mutex(mutex)
