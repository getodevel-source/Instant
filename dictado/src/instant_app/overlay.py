"""Cross-platform floating overlay: Qt Quick on Windows, Tk on Unix."""
import logging
import math
import os
import queue
import sys
import threading
import time

log = logging.getLogger("instant")


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
    def __init__(self, key_label="F9"):
        self._transitions = OverlayTransitions()
        self._lock = threading.Lock()
        if sys.platform == "win32":
            self._renderer = _QtQuickOverlay(key_label)
        else:
            self._renderer = _TkOverlay(key_label)

    def _send(self, session, state, text="", color="#f2c36a", milliseconds=0):
        with self._lock:
            token = self._transitions.accept(session, state)
            if token is None:
                return False
        self._renderer.dispatch((token, session, state, text, color, milliseconds))
        return True

    def starting(self, session):
        return self._send(session, "starting")

    def listening(self, session):
        return self._send(session, "listening")

    def processing(self, session):
        return self._send(session, "processing")

    def success_for(self, session, milliseconds=760):
        return self._send(session, "success", milliseconds=milliseconds)

    def show_notice_for(self, session, text, color="#f2c36a", milliseconds=2000):
        return self._send(session, "notice", text, color, milliseconds)

    def show_error_for(self, session, text, color="#ff908b", milliseconds=3000):
        return self._send(session, "error", text, color, milliseconds)

    def hide(self):
        with self._lock:
            token = self._transitions.hide()
            session = self._transitions.session
        self._renderer.dispatch((token, session, "idle", "", "#f2c36a", 0))

    def run_event_loop(self, shutdown, on_heartbeat):
        return self._renderer.run_event_loop(shutdown, on_heartbeat)


class _QtQuickOverlay:
    """Daemon-owned Qt/QML window; every QML object stays on the Qt main thread."""
    def __init__(self, key_label):
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
                if milliseconds:
                    QTimer.singleShot(
                        milliseconds,
                        lambda t=token: presenter._expire(t))

            def _position(presenter):
                cursor = QCursor.pos()
                screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
                bounds = screen.availableGeometry()
                x = min(max(cursor.x() + 18, bounds.left()),
                        bounds.right() - presenter.root.width() + 1)
                y = min(max(cursor.y() + 18, bounds.top()),
                        bounds.bottom() - presenter.root.height() + 1)
                presenter.root.setPosition(QPoint(x, y))
                presenter.root.raise_()

            def _expire(presenter, token):
                if (token == presenter.current_token
                        and presenter.owner._is_latest_token(token)):
                    presenter.root.setProperty("mode", "idle")

        self.engine = QQmlApplicationEngine()
        qml_path = os.path.join(os.path.dirname(__file__), "qml", "overlay.qml")
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
    _BG = "#111827"
    _PANEL = "#1f2937"
    _RECORD = "#34d399"
    _TEXT = "#f3f4f6"

    def __init__(self, key_label):
        self.key_label = key_label
        self.q = queue.Queue()
        self._current_token = -1
        self._dispatch_lock = threading.Lock()
        self._latest_token = -1
        self.animation_generation = 0
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
            smooth=True, fill=self._PANEL, outline="#374151", width=1, tags="panel")
        c.create_oval(13, 13, 45, 45, fill="#263548", outline="", tags="icon_bg")
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
                fill="#4b5563", outline="", tags="spinner"))
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
                x, y = self.root.winfo_pointerx() + 16, self.root.winfo_pointery() + 16
                self.root.geometry(f"+{x}+{y}")
                self.root.deiconify()
                self.root.lift()
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
        self.canvas.coords(
            "panel", 12, 1, 172, 1, 183, 12, 183, 46, 172, 57,
            12, 57, 1, 46, 1, 12)
        self.canvas.config(width=184, height=58, bg=self._BG)
        self.canvas.itemconfigure("panel", fill=self._PANEL, outline="#374151")
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
        self.canvas.config(width=430, height=68, bg=self._BG)
        self.canvas.itemconfigure("panel", fill=self._PANEL, outline="#374151")
        for tag in ("record_ring", "mic", "icon_bg", "record_bar", "spinner"):
            self.canvas.itemconfigure(tag, state="hidden")
        self.canvas.coords("panel", 12, 1, 418, 1, 429, 12, 429, 56, 418, 67, 12, 67, 1, 56, 1, 12)
        self.canvas.itemconfigure("message", text=text, fill=color, width=390)
        self.canvas.coords("message", 18, 34)

    def _animate(self, generation):
        if generation != self.animation_generation:
            return
        bars, spinner = animation_frame(self.state, self.tick)
        if self.state == "recording":
            self.canvas.itemconfigure("panel", outline="#236b59")
            for item, height in zip(self.bar_ids, bars):
                x = self.canvas.coords(item)[0]
                self.canvas.coords(item, x, 29 - height, x, 29 + height)
        else:
            self.canvas.itemconfigure("panel", outline="#66519a")
            for i, item in enumerate(self.spinner_ids):
                shade = 255 - ((i - spinner) % 8) * 25
                self.canvas.itemconfigure(
                    item, fill=f"#{shade:02x}{int(shade * .82):02x}{int(shade * .95):02x}")
        self.tick += 1
        self.root.after(90, lambda g=generation: self._animate(g))

    def _expire(self, token):
        with self._dispatch_lock:
            current = token == self._current_token == self._latest_token
        if current:
            self._current_token += 1
            self.animation_generation += 1
            self.root.withdraw()

    def run_event_loop(self, _shutdown, _on_heartbeat):
        return False
