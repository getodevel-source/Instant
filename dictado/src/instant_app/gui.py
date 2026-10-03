"""Windows control center for Instant, implemented with Qt Widgets."""
import ctypes
import threading

import logging
import os
import signal
import subprocess
import sys

from instant_app import audio, autostart, config, context, hotkey, models, theme
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


# The Qt dependency is imported below the Windows GUI entrypoint, not at module
# import time: the daemon tray may import app_command without creating a GUI.
def _qt_types():
    # Qt se importa aca adentro, no en la cabecera, para que la bandeja del
    # daemon pueda abrir la ventana en otro proceso sin cargar Qt. Los nombres
    # vuelven por locals() y las clases los usan por `qt[...]`, asi que el
    # linter los ve como no usados: el noqa es a proposito, no un descuido.
    from PySide6.QtCore import QObject, QEvent, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot  # noqa: F401
    from PySide6.QtGui import QFont, QIcon, QKeySequence, QPixmap  # noqa: F401
    from PySide6.QtWidgets import (  # noqa: F401
        QApplication, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout,
        QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
        QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy,
        QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem,
        QVBoxLayout, QWidget,
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
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget = (qt[k] for k in ("QScrollArea", "QStackedWidget", "QVBoxLayout", "QWidget"))
    QTableWidget, QTableWidgetItem, QHeaderView = (qt[k] for k in ("QTableWidget", "QTableWidgetItem", "QHeaderView"))
    Qt, QTimer, QIcon, QFont, QKeySequence, QPixmap, QEvent = (qt[k] for k in ("Qt", "QTimer", "QIcon", "QFont", "QKeySequence", "QPixmap", "QEvent"))
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

    class WheelPassThrough(qt["QObject"]):
        """La rueda scrollea la página: los combos no cambian solos."""

        def __init__(self, scroll):
            super().__init__(scroll)
            self._scroll = scroll

        def eventFilter(self, _watched, event):
            if event.type() == qt["QEvent"].Wheel:
                self._scroll.wheelEvent(event)
                return True
            return False

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
            self.setMinimumSize(1000, 640)
            self.resize(1360, 760)
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
            self._brand_image = None
            self._build(autostart_override)
            self.refresh_microphones(initial=True)
            self.refresh_daemon()
            self._update_model_status()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh_daemon)
            self.timer.start(1000)
            if page == "diagnostics":
                QTimer.singleShot(150, self.show_diagnostics)
            self._update_silent_done = False
            self._available_update = None
            QTimer.singleShot(8000, self._silent_update_check)

        def _worker_finished(self, worker):
            self._pending_workers.discard(worker)
            receiver = self._worker_receivers.pop(worker, None)
            if receiver is not None: receiver.deleteLater()
            if not self._pending_workers:
                self.workers_idle.emit()
                if self._closed: QApplication.instance().quit()

        def _label(self, text, name=None, wrap=True):
            label = QLabel(text)
            if name:
                label.setObjectName(name)
            label.setWordWrap(wrap)
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            return label

        def _rule(self):
            """Separador de un píxel: ordena la página sin agregar peso visual."""
            line = QFrame()
            line.setObjectName("rule")
            line.setFixedHeight(1)
            return line

        def _brand_mark(self, size=30):
            """Marca de la aplicación para la barra lateral."""
            if self._brand_image is None:
                try:
                    from io import BytesIO
                    stream = BytesIO()
                    create_icon_image(size * 2).save(stream, format="PNG")
                    pixmap = QPixmap()
                    pixmap.loadFromData(stream.getvalue(), "PNG")
                    self._brand_image = pixmap.scaled(
                        size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                except Exception:
                    log.exception("no pude dibujar la marca de la barra lateral")
                    self._brand_image = QPixmap()
            if self._brand_image.isNull():
                return None
            mark = QLabel()
            mark.setPixmap(self._brand_image)
            mark.setFixedSize(size, size)
            return mark

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
            box.setContentsMargins(26, 22, 26, 24)
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
            # Una sola pantalla apaisada: el scroll ES la ventana (sin
            # envoltorios intermedios que rompan el pintado del viewport).
            # Sin barra lateral ni páginas: todo Instant en un vistazo.
            self._scroll = QScrollArea()
            self._scroll.setObjectName("pageScroll")
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QFrame.NoFrame)
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            holder = QWidget()
            self.content_layout = QVBoxLayout(holder)
            self.content_layout.setContentsMargins(28, 26, 28, 30)
            self.content_layout.setSpacing(18)
            self._scroll.setWidget(holder)
            self.setCentralWidget(self._scroll)
            self._make_page()
            self._page = holder
            self._current_section = "home"
            if self.page == "setup":
                self.navigate("audio")
            self._init_settings(autostart_override)

        def _scroll_to(self, widget):
            area = getattr(self, "_scroll", None)
            if area is not None:
                area.ensureWidgetVisible(widget)

        def _make_page(self):
            layout = self.content_layout
            # Encabezado: marca, estado y diagnóstico. Nada más.
            head = QHBoxLayout()
            head.setSpacing(12)
            mark = self._brand_mark(26)
            if mark is not None:
                head.addWidget(mark)
            brand = QLabel("Instant")
            brand.setObjectName("brand")
            head.addWidget(brand)
            head.addStretch()
            layout.addLayout(head)
            layout.addWidget(self._rule())

            # Estado: portada fina con lo esencial para dictar ya. Sin altura
            # máxima: el contenido manda (a 150 % de escala o ventana angosta
            # el título puede ocupar dos líneas y nada debe recortarse).
            hero = QFrame(); hero.setObjectName("hero"); hero.setMinimumHeight(160)
            hero_l = QHBoxLayout(hero); hero_l.setContentsMargins(28, 20, 28, 20); hero_l.setSpacing(20)
            left = QVBoxLayout(); left.setSpacing(8)
            self.status_var = QLabel("Listo para dictar"); self.status_var.setObjectName("heroStatus"); self.status_var.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.status_detail = self._label("Enfocá el prompt o campo editable de la CLI, mantené F9 y soltá: Instant pega con Ctrl+V.", "heroDetail")
            hero_title = self._label("Hablá. Soltá. Listo.", "heroTitle"); hero_title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed); hero_title.setWordWrap(False)
            left.addStretch(); left.addWidget(self.status_var); left.addWidget(hero_title); left.addWidget(self.status_detail); left.addStretch()
            hero_l.addLayout(left, 1)
            action = QVBoxLayout(); action.setSpacing(8)
            self.key_badge = QLabel(hotkey.key_label(self.cfg.get("key", "f9"))); self.key_badge.setObjectName("keyBadge"); self.key_badge.setAlignment(Qt.AlignCenter)
            action.addStretch()
            action.addWidget(self._label("Tecla", "railCaption", wrap=False), alignment=Qt.AlignRight)
            action.addWidget(self.key_badge, alignment=Qt.AlignRight)
            action.addSpacing(4)
            self.run_button = QPushButton("Iniciar dictado"); self.run_button.setObjectName("primaryButton"); self.run_button.setMinimumWidth(150); self.run_button.setEnabled(False); self.run_button.setCursor(Qt.PointingHandCursor); self.run_button.clicked.connect(self.toggle_daemon); action.addWidget(self.run_button)
            self.stop_button = QPushButton("Detener"); self.stop_button.setMinimumWidth(150); self.stop_button.setCursor(Qt.PointingHandCursor); self.stop_button.clicked.connect(self.stop_daemon); action.addWidget(self.stop_button); self.stop_button.hide()
            action.addStretch()
            hero_l.addLayout(action); layout.addWidget(hero)
            # Estado sin tarjeta: una línea tenue en vez de una caja entera.
            quick = QHBoxLayout(); quick.setSpacing(12)
            self.quick_mic = QLabel("Micrófono: —"); self.quick_mic.setObjectName("softStatus")
            self.quick_model = QLabel("Voz: —"); self.quick_model.setObjectName("softStatus")
            quick.addWidget(self.quick_mic); quick.addStretch(); quick.addWidget(self.quick_model)
            layout.addLayout(quick)

            # Dos columnas: izquierda ajustes, derecha vocabulario ancho.
            cols = QHBoxLayout(); cols.setSpacing(18)
            leftV = QVBoxLayout(); leftV.setSpacing(18)
            rightV = QVBoxLayout(); rightV.setSpacing(18)
            cols.addLayout(leftV, 4)
            cols.addLayout(rightV, 6)
            layout.addLayout(cols)

            # Micrófono.
            mic_card, box = self._card(leftV, "Micrófono")
            self.mic_combo = QComboBox(); self.mic_combo.currentIndexChanged.connect(self._mic_selected); box.addWidget(self.mic_combo)
            row = QHBoxLayout(); row.setSpacing(10)
            self.refresh_button = QPushButton("Actualizar"); self.refresh_button.setCursor(Qt.PointingHandCursor); self.refresh_button.clicked.connect(self.refresh_microphones); row.addWidget(self.refresh_button)
            self.test_button = QPushButton("Probar"); self.test_button.setCursor(Qt.PointingHandCursor); self.test_button.clicked.connect(self.test_microphone); row.addWidget(self.test_button); row.addStretch(1); box.addLayout(row)
            self.meter = QProgressBar(); self.meter.setRange(0, 100); self.meter.setValue(0); self.meter.setTextVisible(False); box.addWidget(self.meter)
            self.meter_text = self._label("La prueba no guarda audio.", "muted"); box.addWidget(self.meter_text)

            # General: tecla y arranque en una sola tarjeta.
            general_card, box = self._card(leftV, "General", "Tecla y arranque.")
            row = QHBoxLayout(); self.key_value = QLabel(hotkey.key_label(self.cfg.get("key", "f9"))); self.key_value.setObjectName("keyBadge"); row.addWidget(self.key_value); row.addStretch(); self.key_capture_button = QPushButton("Elegir tecla"); self.key_capture_button.setCursor(Qt.PointingHandCursor); self.key_capture_button.clicked.connect(self.begin_key_capture); row.addWidget(self.key_capture_button); box.addLayout(row)
            try: enabled = autostart.is_enabled()
            except Exception: enabled = bool(self.cfg.get("autostart"))
            if self._autostart_override is not None: enabled = self._autostart_override
            self.autostart_check = QCheckBox("Iniciar Instant con Windows"); self.autostart_check.setChecked(enabled); self.autostart_check.setCursor(Qt.PointingHandCursor); self.autostart_check.toggled.connect(self.settings_changed); box.addWidget(self.autostart_check)

            # Vocabulario: tabla estructurada en vez de texto crudo.
            vocab_card, box = self._card(
                rightV, "Vocabulario",
                "Tus palabras como se escriben y como el motor suele escucharlas.")
            row = QHBoxLayout()
            self.context_combo = QComboBox()
            self.context_combo.currentIndexChanged.connect(self._context_profile_changed)
            row.addWidget(self.context_combo, 1)
            self.context_add_button = QPushButton("Añadir perfil")
            self.context_add_button.setCursor(Qt.PointingHandCursor)
            self.context_add_button.clicked.connect(self._add_context_profile)
            row.addWidget(self.context_add_button)
            self.context_remove_button = QPushButton("Eliminar perfil")
            self.context_remove_button.setCursor(Qt.PointingHandCursor)
            self.context_remove_button.clicked.connect(self._remove_context_profile)
            row.addWidget(self.context_remove_button)
            box.addLayout(row)
            self.vocab_table = QTableWidget(0, 4)
            self.vocab_table.setHorizontalHeaderLabels(
                ["Término", "Así se escucha", "Sonido", ""])
            header = self.vocab_table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.Fixed)
            header.resizeSection(2, 76)
            header.setSectionResizeMode(3, QHeaderView.Fixed)
            header.resizeSection(3, 54)
            self.vocab_table.verticalHeader().setVisible(False)
            self.vocab_table.verticalHeader().setMinimumSectionSize(46)
            self.vocab_table.verticalHeader().setDefaultSectionSize(46)
            self.vocab_table.setMinimumHeight(160)
            self.vocab_table.setShowGrid(False)
            self.vocab_table.setSelectionBehavior(QTableWidget.SelectRows)
            self.vocab_table.viewport().setContentsMargins(0, 0, 0, 0)
            self.vocab_table.cellChanged.connect(self._vocab_changed)
            box.addWidget(self.vocab_table)
            self.vocab_add_button = QPushButton("Añadir término")
            self.vocab_add_button.setCursor(Qt.PointingHandCursor)
            self.vocab_add_button.clicked.connect(self._vocab_add_blank_row)
            box.addWidget(self.vocab_add_button, alignment=Qt.AlignLeft)
            box.addWidget(self._label(
                "Una fila por término: variantes separadas con |. ≈ corrige también "
                "lo que suena parecido. Solo recibe texto, nunca audio.",
                "muted"))

            # Voz: una línea solo si falta algo; lista no muestra nada.
            models_row = QWidget()
            self.models_row = models_row
            models_l = QHBoxLayout(models_row)
            models_l.setContentsMargins(2, 0, 2, 0)
            models_l.setSpacing(12)
            self.model_status = self._label("Comprobando voz…", "muted")
            self.model_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            models_l.addWidget(self.model_status, 1)
            self.model_progress = QProgressBar(); self.model_progress.setRange(0, 0); self.model_progress.setFixedWidth(140); self.model_progress.hide(); models_l.addWidget(self.model_progress)
            self.model_button = QPushButton("Descargar voz"); self.model_button.setCursor(Qt.PointingHandCursor); self.model_button.clicked.connect(self.download_models); models_l.addWidget(self.model_button)
            leftV.addWidget(models_row)
            leftV.addStretch(1)

            # Guardar: solo el botón visible; el estado vive oculto para los
            # avisos internos (el texto sobraba en la UI).
            save_row = QHBoxLayout(); save_row.setSpacing(12)
            self.settings_status = QLabel(""); self.settings_status.setObjectName("softStatus"); self.settings_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum); self.settings_status.setVisible(False); save_row.addWidget(self.settings_status, 1)
            self.save_button = QPushButton("Guardar ajustes"); self.save_button.setObjectName("primaryButton"); self.save_button.setCursor(Qt.PointingHandCursor); self.save_button.setEnabled(False); self.save_button.clicked.connect(self.save_config); save_row.addWidget(self.save_button)
            rightV.addLayout(save_row)

            foot = QHBoxLayout(); foot.setSpacing(12)
            self.diag_button = QPushButton("Diagnóstico")
            self.diag_button.setObjectName("ghostButton")
            self.diag_button.setCursor(Qt.PointingHandCursor)
            self.diag_button.clicked.connect(self.show_diagnostics)
            self.update_button = QPushButton("Buscar actualizaciones")
            self.update_button.setObjectName("ghostButton")
            self.update_button.setCursor(Qt.PointingHandCursor)
            self.update_button.clicked.connect(self.check_updates)
            foot.addStretch(1)
            foot.addWidget(self.diag_button)
            foot.addWidget(self.update_button)
            foot.addStretch(1)
            layout.addLayout(foot)
            layout.addStretch(1)
            layout.addStretch(1)

            # Una sola página con scroll: las "secciones" son anclas, no páginas.
            self.pages = {"home": hero, "audio": mic_card,
                          "settings": general_card, "models": models_row}
            self._wheel_filter = WheelPassThrough(self._scroll)
            self.mic_combo.installEventFilter(self._wheel_filter)
            self.context_combo.installEventFilter(self._wheel_filter)

        def navigate(self, name):
            """Ir a una sección de la página única (compat: páginas→anclas)."""
            target = self.pages.get(name)
            if target is None:
                return
            self._current_section = name
            self._scroll_to(target)


        def _init_settings(self, autostart_override):
            configured = context.profiles(self.cfg)
            self.context_combo.blockSignals(True)
            self.context_combo.addItems(configured)
            active = context.active_name(self.cfg)
            self.context_combo.setCurrentText(active)
            self.context_combo.blockSignals(False)
            self._loaded_context_name = active
            self._vocab_load_rows(configured[active])
            self.context_remove_button.setEnabled(active != context.DEFAULT_PROFILE)
            self.key_value.setText(hotkey.key_label(self.cfg.get("key", "f9")))
            self._saved_settings = self._snapshot()
            self._restart_settings = self._restart_signature(self._saved_settings)
            self._settings_daemon_state = None
            self._update_settings_status()

        def _store_vocab_table(self):
            name = getattr(self, "_loaded_context_name",
                           self.context_combo.currentText()) or context.DEFAULT_PROFILE
            configured = context.profiles(self.cfg)
            configured[name] = self._vocab_rows()
            self.cfg["context_profiles"] = configured
            self.cfg["active_context"] = self.context_combo.currentText() or name
            self._loaded_context_name = name

        def _context_profile_changed(self, _index):
            if not hasattr(self, "vocab_table") or not self.context_combo.currentText():
                return
            self._store_vocab_table()
            configured = context.profiles(self.cfg)
            name = self.context_combo.currentText()
            self.cfg["active_context"] = name
            self._vocab_load_rows(configured.get(name, []))
            self._loaded_context_name = name
            self.context_remove_button.setEnabled(name != context.DEFAULT_PROFILE)
            self.settings_changed()

        def _vocab_load_rows(self, rows):
            """Vuelca filas normalizadas a la tabla sin marcar cambios."""
            table = self.vocab_table
            table.blockSignals(True)
            self._vocab_loading = True
            try:
                table.setRowCount(0)
                for row in rows:
                    self._vocab_append_row(
                        row.get("term", ""), row.get("aliases", ()),
                        bool(row.get("sonido")))
                if not rows:
                    # Perfil vacío: una fila en blanco invita a escribir en vez
                    # de mostrar una caja muerta. No marca cambios ni se guarda.
                    self._vocab_append_row()
            finally:
                self._vocab_loading = False
                table.blockSignals(False)
            table.resizeRowsToContents()
            # resizeRowsToContents puede dejar filas más bajas que el botón:
            # se impone un mínimo para que el pill (≈) y la X nunca se recorten.
            for row in range(table.rowCount()):
                if table.rowHeight(row) < 46:
                    table.setRowHeight(row, 46)
            self._vocab_fit_height()

        def _vocab_append_row(self, term="", aliases=(), sonido=False):
            table = self.vocab_table
            row = table.rowCount()
            table.insertRow(row)
            table.setRowHeight(row, 46)
            table.setItem(row, 0, QTableWidgetItem(str(term)))
            table.setItem(row, 1, QTableWidgetItem(" | ".join(aliases)))
            # Botón Sonido (≈): pill centrada en un envoltorio transparente.
            # El envoltorio no pinta fondo (ver QSS #vocabCell): antes heredaba
            # el fondo global de QWidget y se veía un recuadro detrás.
            sound_wrap = QWidget()
            sound_wrap.setObjectName("vocabCell")
            sound_wrap.setAttribute(Qt.WA_StyledBackground, False)
            sound_layout = QHBoxLayout(sound_wrap)
            sound_layout.setContentsMargins(0, 0, 0, 0)
            sound_layout.setSpacing(0)
            sound_layout.setAlignment(Qt.AlignCenter)
            sound = QPushButton("≈")
            sound.setObjectName("soundToggle")
            sound.setCheckable(True)
            sound.setChecked(bool(sonido))
            sound.setCursor(Qt.PointingHandCursor)
            sound.setFocusPolicy(Qt.NoFocus)
            sound.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            sound.setToolTip("Corrige también lo que suena parecido (≈)")
            sound.toggled.connect(lambda _value: self._vocab_changed(-1, -1))
            sound_layout.addWidget(sound)
            table.setCellWidget(row, 2, sound_wrap)
            # Botón eliminar (✕): círculo centrado, mismo envoltorio
            # transparente para que no quede ningún cuadrado alrededor.
            delete = QPushButton("✕")
            delete.setObjectName("rowDelete")
            delete.setCursor(Qt.PointingHandCursor)
            delete.setFocusPolicy(Qt.NoFocus)
            delete.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            delete.setToolTip("Quitar término")
            delete.clicked.connect(
                lambda _checked=False, button=delete: self._vocab_delete_row(button))
            del_wrap = QWidget()
            del_wrap.setObjectName("vocabCell")
            del_wrap.setAttribute(Qt.WA_StyledBackground, False)
            del_wrap.setFixedWidth(48)
            del_layout = QHBoxLayout(del_wrap)
            del_layout.setContentsMargins(0, 0, 0, 0)
            del_layout.setSpacing(0)
            del_layout.setAlignment(Qt.AlignCenter)
            del_layout.addWidget(delete)
            table.setCellWidget(row, 3, del_wrap)

        def _vocab_rows(self):
            """Lee la tabla y normaliza con el mismo formato del editor."""
            table = self.vocab_table
            draft = []
            for row in range(table.rowCount()):
                term_item = table.item(row, 0)
                term = term_item.text().strip() if term_item is not None else ""
                if not term:
                    continue
                variants_item = table.item(row, 1)
                variants = variants_item.text() if variants_item is not None else ""
                wrap = table.cellWidget(row, 2)
                toggle = wrap.findChild(QPushButton) if wrap is not None else None
                draft.append({
                    "term": term,
                    "aliases": [v.strip() for v in variants.split("|") if v.strip()],
                    "sonido": bool(toggle is not None and toggle.isChecked()),
                })
            return context.parse_editor(context.editor_text(draft))

        def _vocab_fit_height(self):
            """La tabla crece con las filas hasta ~7 visibles y luego scrollea."""
            table = self.vocab_table
            table.setMinimumHeight(min(160 + table.rowCount() * 46, 480))

        def _vocab_set_rows(self, rows):
            """Carga filas como si las hubiera escrito el usuario (tests y UI)."""
            self._vocab_load_rows(rows)
            self.settings_changed()

        def _vocab_add_blank_row(self):
            self._vocab_append_row()
            table = self.vocab_table
            last = table.rowCount() - 1
            item = table.item(last, 0)
            if item is not None:
                table.setCurrentCell(last, 0)
                table.scrollToItem(item)
                table.editItem(item)
            self._vocab_fit_height()
            self.settings_changed()

        def _vocab_changed(self, _row, _column):
            if getattr(self, "_vocab_loading", False):
                return
            self.settings_changed()

        def _vocab_delete_row(self, button):
            table = self.vocab_table
            pos = button.mapTo(table.viewport(), button.rect().center())
            row = table.indexAt(pos).row()
            if row >= 0:
                table.removeRow(row)
                self._vocab_fit_height()
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
            self._store_vocab_table()
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
            self._store_vocab_table()
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
            self._vocab_load_rows(configured[context.DEFAULT_PROFILE])
            self.context_remove_button.setEnabled(False)
            self.settings_changed()

        def _selected_device(self):
            value = self.mic_combo.currentData()
            return tuple(value) if value is not None else None

        def _snapshot(self):
            device = self._selected_device()
            if device: self.catalog.remember(device)
            mic = self.catalog.pending_identity or DeviceCatalog.identity((self.cfg.get("mic_index"), self.cfg.get("mic_hint", "")))
            self._store_vocab_table()
            context_state = tuple(
                (name, tuple((row["term"], tuple(row["aliases"]), bool(row.get("sonido")))
                             for row in items))
                for name, items in context.profiles(self.cfg).items())
            return (mic, self.key_value.text().strip().lower(),
                    self.autostart_check.isChecked(),
                    self.cfg["active_context"], context_state,
                    self.cfg.get("llm_url", ""))

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
            if not _pid_is_instant(pid):
                log.warning("PID %d reciclado por el SO (no es Instant); no se mata.", pid)
                self.status_detail.setText("El daemon ya no estaba; actualizando estado…")
                self.refresh_daemon()
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
                if running:
                    self.status_var.setText("Instant está activo"); self.status_detail.setText("Enfocá el prompt o campo editable de la CLI, mantené F9 y soltá: Instant pega con Ctrl+V."); self.run_button.setText("Reiniciar"); self.stop_button.show()
                else:
                    self.status_var.setText("Listo para dictar"); self.status_detail.setText("Enfocá el prompt o campo editable de la CLI, mantené F9 y soltá: Instant pega con Ctrl+V."); self.run_button.setText("Iniciar dictado"); self.stop_button.hide()
                self._maybe_start_daemon_on_open()
            def failed(error):
                self._daemon_check_pending = False
                log.warning("no se pudo comprobar el daemon desde la GUI: %s", error)
            self._run_worker(lambda _emit: daemon_is_running(), result, failed)

        def _update_model_status(self):
            self.model_ready = all(models.check(self.data_dir).values())
            self.quick_model.setText("Voz: lista" if self.model_ready else "Voz: pendiente")
            self.models_row.setVisible(not self.model_ready)
            if self.model_ready:
                self.model_status.setText("Voz lista en este equipo."); self.model_button.setText("Voz lista"); self.model_button.setEnabled(False)
            else:
                self.model_status.setText("Falta descargar la voz (~670 MB)."); self.model_button.setText("Descargar voz"); self.model_button.setEnabled(True)

        def download_models(self):
            if self.model_ready: return
            self.model_button.setEnabled(False); self.model_button.setText("Descargando…"); self.model_status.setText("Descargando la voz…"); self.model_progress.show()
            def download(emit):
                return models.download_models(self.data_dir, progress=lambda *args: emit(args))
            def progress(event):
                step, done, total = event
                if step == "parakeet": self.model_status.setText("Voz descargada; verificando…")
                elif total: self.model_status.setText(f"Descargando la voz: {done / total:.0%}")
            def done(_):
                self.model_progress.hide(); self._update_model_status()
            def failed(error):
                self.model_progress.hide(); self.model_button.setEnabled(True); self.model_button.setText("Reintentar"); self.model_status.setText("No se pudo descargar la voz."); QMessageBox.critical(self, "Descarga fallida", str(error))
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

        def _silent_update_check(self):
            """Chequeo diario silencioso: nunca interrumpe, solo avisa."""
            if self._update_silent_done or self._closed:
                return
            self._update_silent_done = True
            try:
                import time
                if time.time() - float(self.cfg.get("update_last_check", 0)) < 86400:
                    return
            except (TypeError, ValueError):
                pass
            from instant_app import update as update_module
            self._run_worker(lambda _emit: update_module.check(),
                             self._silent_update_result,
                             lambda _error: None)

        def _silent_update_result(self, info):
            try:
                import time
                self.cfg["update_last_check"] = int(time.time())
                config.save(self.cfg)
            except Exception:
                log.warning("no pude sellar el chequeo de versión", exc_info=True)
            if self._closed or not info.get("update"):
                return
            self._apply_update_available(info)

        def _apply_update_available(self, info):
            """El botón se viste de primario: la novedad se ve sin modales."""
            self._available_update = info
            self.update_button.setText(f"↓ Actualizar a v{info['latest']}")
            self.update_button.setToolTip(
                f"Hay versión nueva ({info['latest']}); la tenés en un clic.")
            self.update_button.setObjectName("primaryButton")
            polish = self.update_button.style()
            polish.unpolish(self.update_button)
            polish.polish(self.update_button)

        def check_updates(self):
            """Consulta GitHub sin bloquear: informa o propone descargar."""
            from instant_app import update as update_module
            self.update_button.setEnabled(False)
            self._run_worker(
                lambda _emit: update_module.check(),
                self._updates_result,
                self._updates_failed)

        def _updates_failed(self, error):
            self.update_button.setEnabled(True)
            QMessageBox.warning(
                self, "Actualizaciones",
                f"No se pudo consultar versiones:\n{error}")

        def _updates_result(self, info):
            self.update_button.setEnabled(True)
            if not info.get("update"):
                self._available_update = None
                self.update_button.setText("Buscar actualizaciones")
                self.update_button.setToolTip("")
                self.update_button.setObjectName("ghostButton")
                polish = self.update_button.style()
                polish.unpolish(self.update_button)
                polish.polish(self.update_button)
                QMessageBox.information(
                    self, "Actualizaciones",
                    f"Estás al día (versión {info.get('current') or '?'}).")
                return
            from instant_app import update as update_module
            notes = update_module.clean_notes(info.get("notes"))
            answer = QMessageBox.question(
                self, "Actualizaciones",
                f"Hay versión nueva: {info['latest']} "
                f"(tenés {info.get('current') or '?'}).\n\n"
                f"{notes}\n\n¿Descargar {info['asset']} verificado?")
            if answer != QMessageBox.Yes:
                return
            self.update_button.setEnabled(False)
            self._pending_update = info
            self._run_worker(self._download_update, self._update_ready,
                             self._updates_failed)

        def _download_update(self, _emit):
            import os
            import tempfile
            from instant_app import update as update_module
            info = self._pending_update
            target = os.path.join(tempfile.gettempdir(), "instant_update",
                                  info["asset"])
            expected = update_module.fetch_expected_sha256(info["asset_url"])
            update_module.download(info["asset_url"], target,
                                   expected_sha256=expected)
            return target, expected

        def _update_ready(self, payload):
            self.update_button.setEnabled(True)
            target, expected = payload
            answer = QMessageBox.question(
                self, "Actualizaciones",
                f"Descargado y verificado:\n{target}\n\n"
                "¿Instalar ahora? Se frena el dictado un momento (si estás "
                "por dictar, mejor después), se respalda el exe anterior "
                "y se vuelve a arrancar ya actualizado.")
            if answer != QMessageBox.Yes:
                return
            root = _workdir()
            script = os.path.join(root, "instant-update.bat")
            if not os.path.isfile(script):
                QMessageBox.warning(
                    self, "Actualizaciones",
                    "No encuentro instant-update.bat junto a la app "
                    "(instalación portable sin scripts).\n\n"
                    f"Instalá a mano: cerrá Instant por completo y copiá\n{target}\n"
                    f"sobre tu Instant.exe (SHA256 {expected[:16]}…).")
                return
            try:
                subprocess.Popen(["cmd", "/c", script, target, expected],
                                 cwd=root)
            except Exception as exc:
                QMessageBox.critical(
                    self, "Actualizaciones",
                    f"No pude lanzar el instalador:\n{exc}")
                return
            self.close()

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
            # El modelo interno de la tabla emite cellChanged al destruirse:
            # se desconecta acá, con el árbol vivo, para que esa señal no
            # llegue a un grafo a medio destruir (abortaba en offscreen).
            try:
                table = getattr(self, "vocab_table", None)
                if table is not None:
                    table.cellChanged.disconnect()
            except Exception:
                pass
            app = QApplication.instance()
            app.setQuitOnLastWindowClosed(False)
            if not self._pending_workers:
                app.quit()
            event.accept()

    return InstantWindow


STYLE = theme.stylesheet()


def run_gui(page="home", autostart_override=None, start_daemon_on_open=False):
    mutex = None
    try:
        if sys.platform == "win32":
            # Icono propio en la barra de tareas: sin AppUserModelID explícito,
            # Windows agrupa la ventana bajo el icono de Python (pythonw.exe).
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "getodevel-source.Instant.0.1")
            except Exception:
                log.warning("no pude fijar el AppUserModelID", exc_info=True)
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
        window.setWindowIcon(QIcon(pixmap))
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
