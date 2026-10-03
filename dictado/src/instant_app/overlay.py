"""Cross-platform floating overlay: Qt Quick on Windows, Tk on Unix."""
import logging
import math
import os
import queue
import sys
import threading
import time

from instant_app.branding import PALETTE, blend

log = logging.getLogger("instant")

# Margen transparente que el QML reserva para dibujar su sombra (overlay.qml,
# `shadowMargin`). La ventana es mas grande que la pastilla, asi que al ubicarla
# hay que descontarlo.
_OVERLAY_SHADOW_MARGIN = 12
# La pastilla del dictado vive fija abajo al centro, estilo asistente de voz:
# siempre en el mismo lugar, sin tapar el campo donde se escribe.
_OVERLAY_BOTTOM_GAP = 60

# Geometria del overlay Tk: la linea base de las barras esta en y=29 y el
# lienzo del medidor mide 26 px de alto, asi que el semialto se queda en 13.
_TK_BAR_BASE = 29
_TK_BAR_MAX = 13
_TK_SPINNER_SEGMENTS = 8


def animation_frame(state, tick, level=0.0):
    """(alturas de barra, fase del spinner) para el renderer Tk.

    El overlay de Qt Quick anima con QML (una onda escalonada por indice al
    escuchar y un arco que barre en 1150 ms al transcribir). Tk no tiene ese
    motor, asi que la misma animacion se calcula por cuadro: las barras suben y
    bajan alternadas con un desfase por indice y el giro avanza en ocho
    segmentos con la cabeza en el color de la marca.

    `level` es el nivel de voz 0..1 del dictado (0 = silencio). Cuando sube,
    las barras centrales crecen hasta ~14 px extra: la pastilla respira con
    la voz en vez de moverse en falso. Con 0 el cuadro es idéntico al de
    antes, así que la regresión existente sigue verde.
    """
    level = max(0.0, min(1.0, float(level)))
    bars = [round(4 + (_TK_BAR_MAX - 4) * (
        0.5 + 0.5 * math.sin(tick * 0.45 - index * 0.75)))
        for index in range(5)]
    if level > 0.0:
        for index in range(5):
            weight = 1.0 - abs(index - 2) / 3.0
            bars[index] = min(_TK_BAR_MAX + 14, round(
                bars[index] + level * 14 * (0.45 + 0.55 * weight)))
    spinner = tick % _TK_SPINNER_SEGMENTS
    return bars, spinner


class OverlayTransitions:
    """Reject stale worker updates before they can replace newer visual states."""
    _RANK = {
        "starting": 0,
        "listening": 1,
        "processing": 2,
        "notice": 3,
        "success": 3,
        "error": 4,
        "idle": 5,
    }

    def __init__(self):
        self.session = -1
        self.rank = -1
        self.state = "idle"
        self.token = 0

    def accept(self, session, state):
        rank = self._RANK[state]
        if session < self.session:
            return None
        if session > self.session:
            self.session = session
            self.rank = -1
            self.state = "idle"
        if rank < self.rank:
            return None
        if self.state == "error" and state != "error":
            return None
        self.rank = rank
        self.state = state
        self.token += 1
        return self.token

    def hide(self):
        self.token += 1
        self.rank = self._RANK["idle"]
        self.state = "idle"
        return self.token


class Overlay:
    """Thread-safe semantic overlay API; platform renderer owns all UI objects."""
    def __init__(self, key_label="F9", style="classic"):
        self._transitions = OverlayTransitions()
        self._lock = threading.Lock()
        if sys.platform == "win32":
            self._renderer = _QtQuickOverlay(key_label, style=style)
        else:
            self._renderer = _TkOverlay(key_label)

    def _send(self, session, state, text="", color=None, milliseconds=0):
        color = color or PALETTE["amber"]
        with self._lock:
            token = self._transitions.accept(session, state)
            if token is None:
                return False
        self._renderer.dispatch((token, session, state, text, color, milliseconds))
        if state in ("processing", "success", "notice", "error", "idle"):
            try:
                self._renderer.set_level(session, 0.0)
            except Exception:
                pass
            try:
                clearer = getattr(self._renderer, "clear_bands", None)
                if clearer is not None:
                    clearer()
            except Exception:
                pass
        return True

    def set_level(self, session, value):
        """Nivel de voz 0..1 para la animación del dictado. No bloquea nunca."""
        try:
            value = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return False
        with self._lock:
            if session != self._transitions.session:
                return False
            if self._transitions.state not in ("starting", "listening"):
                return False
        try:
            self._renderer.set_level(session, value)
        except Exception:
            return False
        return True

    def set_bands(self, session, values):
        """Espectro en 9 bandas 0..1 (una por barra). No bloquea nunca."""
        try:
            bands = [max(0.0, min(1.0, float(v))) for v in values]
            if len(bands) != 9:
                return False
        except (TypeError, ValueError):
            return False
        with self._lock:
            if session != self._transitions.session:
                return False
            if self._transitions.state not in ("starting", "listening"):
                return False
        try:
            setter = getattr(self._renderer, "set_bands", None)
            if setter is None:
                return False
            setter(session, bands)
        except Exception:
            return False
        return True

    def set_pitch(self, session, value):
        """Tono 0..1 (grave->agudo) para teñir la onda. No bloquea nunca."""
        try:
            value = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return False
        with self._lock:
            if session != self._transitions.session:
                return False
            if self._transitions.state not in ("starting", "listening"):
                return False
        try:
            setter = getattr(self._renderer, "set_pitch", None)
            if setter is None:
                return False
            setter(session, value)
        except Exception:
            return False
        return True

    def starting(self, session):
        return self._send(session, "starting")

    def listening(self, session):
        return self._send(session, "listening")

    def processing(self, session):
        return self._send(session, "processing")

    def success_for(self, session, milliseconds=760):
        return self._send(session, "success", milliseconds=milliseconds)

    def show_notice_for(self, session, text, color=None, milliseconds=2000):
        return self._send(session, "notice", text, color or PALETTE["amber"], milliseconds)

    def show_error_for(self, session, text, color=None, milliseconds=3000):
        return self._send(session, "error", text, color or PALETTE["red"], milliseconds)

    def hide(self):
        with self._lock:
            token = self._transitions.hide()
            session = self._transitions.session
        self._renderer.dispatch((token, session, "idle", "", PALETTE["amber"], 0))

    def run_event_loop(self, shutdown, on_heartbeat):
        return self._renderer.run_event_loop(shutdown, on_heartbeat)


class _QtQuickOverlay:
    """Daemon-owned Qt/QML window; every QML object stays on the Qt main thread."""
    STYLES = {"classic": "overlay.qml", "orbital": "overlay_orbital.qml"}

    def __init__(self, key_label, style="classic"):
        import importlib
        qtcore = importlib.import_module("PySide6.QtCore")
        qtgui = importlib.import_module("PySide6.QtGui")
        qtqml = importlib.import_module("PySide6.QtQml")
        QObject, QPoint, QThread, QTimer, Qt, QUrl = (
            getattr(qtcore, name) for name in ("QObject", "QPoint", "QThread", "QTimer", "Qt", "QUrl"))
        Signal, Slot = qtcore.Signal, qtcore.Slot
        QCursor, QGuiApplication = qtgui.QCursor, qtgui.QGuiApplication
        QQmlApplicationEngine = qtqml.QQmlApplicationEngine

        self.application = QGuiApplication.instance() or QGuiApplication(["Instant"])
        if QThread.currentThread() != self.application.thread():
            raise RuntimeError("Qt Quick overlay must be created on the QApplication thread")
        self.application.setQuitOnLastWindowClosed(False)

        class EventBridge(QObject):
            event = Signal(object)
            level = Signal(float)
            bands = Signal(object)
            pitch = Signal(float)

        class Presenter(QObject):
            def __init__(presenter, root, owner):
                super().__init__()
                presenter.root = root
                presenter.owner = owner
                presenter.current_token = -1
                presenter.last_heartbeat = time.monotonic()

            @Slot(object)
            def render(presenter, event):
                token, _session, state, text, color, milliseconds = event
                if token < presenter.current_token:
                    return
                presenter.current_token = token
                if state == "idle":
                    presenter.root.setProperty("mode", "idle")
                    return
                presenter.root.setProperty("message", text)
                presenter.root.setProperty("messageColor", color)
                presenter.root.setProperty("mode", state)
                presenter.root.setProperty("visible", True)
                presenter._position()
                # El ancho anima en 240 ms: al terminar se recentra para que la
                # pastilla quede abajo al centro también con textos largos.
                QTimer.singleShot(
                    260, lambda t=token: presenter._reposition_if_current(t))
                if milliseconds:
                    QTimer.singleShot(
                        milliseconds,
                        lambda t=token: presenter._expire(t))

            def _position(presenter):
                cursor = QCursor.pos()
                screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
                bounds = screen.availableGeometry()
                # Fija abajo al centro del monitor donde se trabaja (el del
                # cursor): siempre el mismo lugar relativo, pero en la pantalla
                # del campo que se está dictando, no solo en la principal.
                # La ventana incluye el margen de la sombra, que se descuenta
                # para que la pastilla quede centrada de verdad.
                margin = _OVERLAY_SHADOW_MARGIN
                pill_width = max(1, presenter.root.width() - margin * 2)
                pill_height = max(1, presenter.root.height() - margin * 2)
                x = bounds.left() + (bounds.width() - pill_width) // 2 - margin
                y = bounds.bottom() - pill_height - _OVERLAY_BOTTOM_GAP - margin
                x = max(bounds.left() - margin, x)
                y = max(bounds.top() - margin, y)
                presenter.root.setPosition(QPoint(x, y))
                presenter.root.raise_()

            def _reposition_if_current(presenter, token):
                if (token == presenter.current_token
                        and presenter.owner._is_latest_token(token)):
                    presenter._position()

            def _expire(presenter, token):
                if (token == presenter.current_token
                        and presenter.owner._is_latest_token(token)):
                    presenter.root.setProperty("mode", "idle")

            @Slot(float)
            def setLevel(presenter, value):
                try:
                    presenter.root.setProperty(
                        "level", max(0.0, min(1.0, float(value))))
                except Exception:
                    pass

            @Slot(object)
            def setBands(presenter, values):
                try:
                    presenter.root.setProperty(
                        "bandLevels", [max(0.0, min(1.0, float(v))) for v in values])
                except Exception:
                    pass

            @Slot(float)
            def setPitch(presenter, value):
                try:
                    presenter.root.setProperty(
                        "pitch", max(0.0, min(1.0, float(value))))
                except Exception:
                    pass

        self.engine = QQmlApplicationEngine()
        qml_file = self.STYLES.get(style, self.STYLES["classic"])
        qml_path = os.path.join(os.path.dirname(__file__), "qml", qml_file)
        self.engine.load(QUrl.fromLocalFile(qml_path))
        roots = self.engine.rootObjects()
        if not roots:
            raise RuntimeError(f"Could not load Qt Quick overlay: {qml_path}")
        self.root = roots[0]
        self.root.setProperty("keyLabel", key_label)
        self._dispatch_lock = threading.Lock()
        self._latest_token = -1
        self.bridge = EventBridge(self.application)
        self.presenter = Presenter(self.root, self)
        self.bridge.event.connect(
            self.presenter.render, Qt.ConnectionType.QueuedConnection)
        self.bridge.level.connect(
            self.presenter.setLevel, Qt.ConnectionType.QueuedConnection)
        self.bridge.bands.connect(
            self.presenter.setBands, Qt.ConnectionType.QueuedConnection)
        self.bridge.pitch.connect(
            self.presenter.setPitch, Qt.ConnectionType.QueuedConnection)

    def set_level(self, session, value):
        del session
        try:
            self.bridge.level.emit(max(0.0, min(1.0, float(value))))
        except Exception:
            pass

    def set_bands(self, session, values):
        del session
        try:
            self.bridge.bands.emit([max(0.0, min(1.0, float(v))) for v in values])
        except Exception:
            pass

    def set_pitch(self, session, value):
        del session
        try:
            self.bridge.pitch.emit(max(0.0, min(1.0, float(value))))
        except Exception:
            pass

    def clear_bands(self):
        try:
            self.bridge.bands.emit([0.0] * 9)
        except Exception:
            pass

    def _is_latest_token(self, token):
        with self._dispatch_lock:
            return token == self._latest_token

    def dispatch(self, event):
        token = event[0]
        with self._dispatch_lock:
            self._latest_token = max(self._latest_token, token)
        self.bridge.event.emit(event)

    def run_event_loop(self, shutdown, on_heartbeat):
        from PySide6.QtCore import QTimer

        timer = QTimer(self.presenter)
        timer.setInterval(100)

        def poll():
            if shutdown.is_set():
                self.application.quit()
                return
            now = time.monotonic()
            if now - self.presenter.last_heartbeat >= 60:
                self.presenter.last_heartbeat = now
                on_heartbeat()

        timer.timeout.connect(poll)
        timer.start()
        self.application.exec()
        timer.stop()
        return True


class _TkOverlay:
    """Portable fallback kept for Linux/macOS CLI daemons."""
    _BG = PALETTE["background"]
    _PANEL = PALETTE["surface"]
    _RECORD = PALETTE["accent"]
    _TEXT = PALETTE["text"]
    _LINE = PALETTE["line"]

    def __init__(self, key_label):
        self.key_label = key_label
        self.q = queue.Queue()
        self._current_token = -1
        self._dispatch_lock = threading.Lock()
        self._latest_token = -1
        self.animation_generation = 0
        self._level = 0.0
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        try:
            import tkinter as tk
            self.root = tk.Tk()
            self.root.withdraw()
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            try:
                self.root.attributes("-alpha", 0.97)
            except Exception:
                pass
            self.canvas = tk.Canvas(
                self.root, width=184, height=58, bg=self._BG, bd=0,
                highlightthickness=0)
            self.canvas.pack()
            self._draw_overlay()
            self.root.after(50, self._poll)
            self.root.mainloop()
        except Exception:
            log.exception("overlay thread muerto (sin Tk? instala python3-tk en linux)")

    def _draw_overlay(self):
        c = self.canvas
        c.create_polygon(
            12, 1, 172, 1, 183, 12, 183, 46, 172, 57, 12, 57, 1, 46, 1, 12,
            smooth=True, fill=self._PANEL, outline=self._LINE, width=1, tags="panel")
        c.create_oval(13, 13, 45, 45, fill=PALETTE["surface_high"], outline="", tags="icon_bg")
        c.create_arc(7, 7, 51, 51, start=40, extent=80, style="arc",
                     outline=self._RECORD, width=2, tags="record_ring")
        c.create_arc(7, 7, 51, 51, start=220, extent=80, style="arc",
                     outline=self._RECORD, width=2, tags="record_ring")
        c.create_rectangle(26, 19, 32, 32, fill=self._TEXT, outline="", tags="mic")
        c.create_arc(22, 23, 36, 37, start=180, extent=180, style="arc",
                     outline=self._TEXT, width=2, tags="mic")
        c.create_line(29, 36, 29, 40, fill=self._TEXT, width=2, tags="mic")
        c.create_line(25, 40, 33, 40, fill=self._TEXT, width=2, tags="mic")
        self.bar_ids = [c.create_line(
            x, 29, x, 29, fill=self._RECORD, width=4, capstyle="round",
            tags="record_bar") for x in (75, 86, 97, 108, 119)]
        self.spinner_ids = []
        for i in range(8):
            angle = i * math.tau / 8
            x, y = 97 + math.cos(angle) * 13, 29 + math.sin(angle) * 13
            self.spinner_ids.append(c.create_oval(
                x - 2.5, y - 2.5, x + 2.5, y + 2.5,
                fill=PALETTE["surface_high"], outline="", tags="spinner"))
        self.message_id = c.create_text(
            60, 29, anchor="w", width=350, text="", font=("Segoe UI", 10, "bold"),
            fill=self._TEXT, tags="message")

    def dispatch(self, event):
        token = event[0]
        with self._dispatch_lock:
            self._latest_token = max(self._latest_token, token)
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass
        self.q.put(event)

    def set_level(self, session, value):
        del session
        try:
            level = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return
        with self._dispatch_lock:
            self._level = max(self._level, level)

    def set_bands(self, session, values):
        # El fallback Tk mueve sus 5 barras con el nivel global (set_level);
        # el espectro por banda es un lujo del renderer Qt Quick.
        del session, values

    def set_pitch(self, session, value):
        # Tono: también exclusivo del renderer Qt Quick.
        del session, value

    def clear_bands(self):
        pass

    def _poll(self):
        try:
            while True:
                token, _session, state, text, color, milliseconds = self.q.get_nowait()
                if token < self._current_token:
                    continue
                self._current_token = token
                if state == "idle":
                    self.animation_generation += 1
                    self.root.withdraw()
                    continue
                if state in ("starting", "listening"):
                    self._show_state("recording")
                elif state == "processing":
                    self._show_state("transcribing")
                else:
                    self._show_feedback("Listo" if state == "success" else text, color)
                # Posición fija abajo al centro, como en Qt: mismo lugar siempre.
                width, height = (430, 68) if self.state == "feedback" else (184, 58)
                sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                x, y = (sw - width) // 2, sh - height - 96
                # Nace 18 px abajo y sube, en espejo al overlay Qt.
                self.root.geometry(f"+{max(0, x)}+{max(0, y + 18)}")
                try:
                    self.root.attributes("-alpha", 0.0)
                except Exception:
                    pass
                self.root.deiconify()
                self.root.lift()
                generation = self.animation_generation
                self._fade_to(generation, 0.97)
                self._slide_to(generation, max(0, y))
                if milliseconds:
                    self.root.after(milliseconds, lambda t=token: self._expire(t))
        except queue.Empty:
            pass
        except Exception:
            log.exception("overlay poll fail")
        self.root.after(50, self._poll)

    def _show_state(self, state):
        self.state = state
        self.animation_generation += 1
        generation = self.animation_generation
        self.tick = 0
        with self._dispatch_lock:
            self._level = 0.0
        self.canvas.coords(
            "panel", 12, 1, 172, 1, 183, 12, 183, 46, 172, 57,
            12, 57, 1, 46, 1, 12)
        self.canvas.config(width=184, height=58, bg=self._BG)
        self.canvas.itemconfigure("panel", fill=self._PANEL, outline=self._LINE)
        self.canvas.itemconfigure("message", text="")
        self.canvas.itemconfigure("record_ring", state="normal" if state == "recording" else "hidden")
        self.canvas.itemconfigure("mic", state="normal" if state == "recording" else "hidden")
        self.canvas.itemconfigure("icon_bg", state="normal" if state == "recording" else "hidden")
        self.canvas.itemconfigure("record_bar", state="normal" if state == "recording" else "hidden")
        self.canvas.itemconfigure("spinner", state="normal" if state == "transcribing" else "hidden")
        self._animate(generation)

    def _show_feedback(self, text, color):
        self.animation_generation += 1
        self.state = "feedback"
        with self._dispatch_lock:
            self._level = 0.0
        self.canvas.config(width=430, height=68, bg=self._BG)
        self.canvas.itemconfigure("panel", fill=self._PANEL, outline=self._LINE)
        for tag in ("record_ring", "mic", "icon_bg", "record_bar", "spinner"):
            self.canvas.itemconfigure(tag, state="hidden")
        self.canvas.coords("panel", 12, 1, 418, 1, 429, 12, 429, 56, 418, 67, 12, 67, 1, 56, 1, 12)
        self.canvas.itemconfigure("message", text=text, fill=color, width=390)
        self.canvas.coords("message", 18, 34)

    def _animate(self, generation):
        if generation != self.animation_generation:
            return
        with self._dispatch_lock:
            level = self._level
            self._level *= 0.82
        bars, spinner = animation_frame(self.state, self.tick, level)
        if self.state == "recording":
            self.canvas.itemconfigure(
                "panel", outline=blend(self._LINE, PALETTE["accent"], 0.55))
            for item, height in zip(self.bar_ids, bars):
                x = self.canvas.coords(item)[0]
                self.canvas.coords(item, x, 29 - height, x, 29 + height)
        else:
            self.canvas.itemconfigure(
                "panel", outline=blend(self._LINE, PALETTE["working"], 0.55))
            # La cabeza del giro usa el acento y el resto se apaga hacia el fondo.
            for i, item in enumerate(self.spinner_ids):
                phase = ((i - spinner) % _TK_SPINNER_SEGMENTS) / (_TK_SPINNER_SEGMENTS - 1)
                self.canvas.itemconfigure(
                    item, fill=blend(PALETTE["accent"], PALETTE["surface_high"], phase))
        self.tick += 1
        self.root.after(90, lambda g=generation: self._animate(g))

    def _fade_to(self, generation, target):
        """Fundido de entrada/salida del fallback Tk."""
        if generation != self.animation_generation:
            return
        try:
            current = float(self.root.attributes("-alpha"))
        except Exception:
            return
        if abs(target - current) < 0.05:
            try:
                self.root.attributes("-alpha", target)
            except Exception:
                pass
            if target == 0.0:
                self.root.withdraw()
            return
        step = 0.2 if target > current else -0.2
        try:
            self.root.attributes("-alpha", max(0.0, min(0.97, current + step)))
        except Exception:
            return
        self.root.after(30, lambda g=generation: self._fade_to(g, target))

    def _expire(self, token):
        with self._dispatch_lock:
            current = token == self._current_token == self._latest_token
        if current:
            self._current_token += 1
            self.animation_generation += 1
            generation = self.animation_generation
            self._fade_to(generation, 0.0)
            try:
                self._slide_to(generation, self.root.winfo_y() + 14)
            except Exception:
                pass

    def _slide_to(self, generation, target_y):
        """Elevación de entrada/salida del fallback Tk (3 px por cuadro)."""
        if generation != self.animation_generation:
            return
        try:
            current_y = self.root.winfo_y()
        except Exception:
            return
        if abs(target_y - current_y) <= 3:
            try:
                x = self.root.winfo_x()
                self.root.geometry(f"+{x}+{target_y}")
            except Exception:
                pass
            return
        step = 3 if target_y > current_y else -3
        try:
            x = self.root.winfo_x()
            self.root.geometry(f"+{x}+{current_y + step}")
        except Exception:
            return
        self.root.after(30, lambda g=generation: self._slide_to(g, target_y))

    def run_event_loop(self, _shutdown, _on_heartbeat):
        return False
