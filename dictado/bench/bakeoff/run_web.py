"""Runner del prototipo web (QtWebEngine) del bake-off: misma ventana y mismo
replay que run_qml.py. Los frames van al canvas via runJavaScript y todo lo que
Python necesita leer vuelve por QWebChannel: el costo del IPC queda dentro de
las metricas (a proposito: es parte del precio de la ruta web).

Eventos por stdout: identicos a run_qml.py.
Uso: python run_web.py [--frames frames.jsonl] [--shots 2500,7600,9200]
                       [--out out] [--label web] [--tail-ms 1200]
"""
import argparse
import base64
import json
import os
import sys
import time

from PySide6.QtCore import QObject, QPoint, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (wrapper antes de rootObjects)
from PySide6.QtWebEngineQuick import QtWebEngineQuick

HERE = os.path.dirname(os.path.abspath(__file__))


def load_frames(path):
    frames = []
    with open(path, encoding="utf-8") as fh:
        fh.readline()
        for line in fh:
            line = line.strip()
            if line:
                frames.append(json.loads(line))
    return frames


class Bridge(QObject):
    """Puente QWebChannel bidireccional: frames y comandos van como señales
    (Python->JS), los resultados vuelven por el slot event() (JS->Python)."""

    frame = Signal(str)
    command = Signal(str)

    def __init__(self, on_event):
        super().__init__()
        self._on_event = on_event

    @Slot(str)
    def event(self, payload):
        self._on_event(payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", default=os.path.join(HERE, "frames.jsonl"))
    parser.add_argument("--shots", default="2500,7600,9200")
    parser.add_argument("--out", default=os.path.join(HERE, "out"))
    parser.add_argument("--label", default="web")
    parser.add_argument("--variant", choices=["v2", "v3", "v4"], default="v2")
    parser.add_argument("--tail-ms", type=int, default=1200)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    html_file = {"v2": "overlay.html", "v3": "overlay_v3.html", "v4": "overlay_v4.html"}[args.variant]

    frames = load_frames(args.frames)
    last_t = frames[-1]["t"] if frames else 0
    shots = [int(s) for s in args.shots.split(",") if s.strip()]

    QtWebEngineQuick.initialize()
    app = QGuiApplication(["instant-bakeoff-web"])
    app.setQuitOnLastWindowClosed(False)

    engine = QQmlApplicationEngine()
    t_load0 = time.monotonic()
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "web", "host.qml")))
    if not engine.rootObjects():
        print(json.dumps({"event": "fatal", "reason": "qml load failed"}))
        return 1
    root = engine.rootObjects()[0]

    screen = QGuiApplication.primaryScreen().availableGeometry()
    root.setPosition(QPoint(
        screen.left() + (screen.width() - root.width()) // 2,
        screen.bottom() - root.height() - 60))

    view = root.findChild(QObject, "view")
    if view is None:
        print(json.dumps({"event": "fatal", "reason": "WebEngineView not found"}))
        return 1

    state = {"ready": False, "idx": 0, "shot_i": 0, "done": False,
             "first": False, "t_replay0": 0.0, "t_page0": 0.0}

    def elapsed_ms():
        if not state["ready"]:
            return 0.0
        return (time.monotonic() - state["t_replay0"]) * 1000.0

    def emit_first(page_ms):
        if state["first"] or page_ms is None or page_ms < 0:
            return
        state["first"] = True
        total_ms = (state["t_page0"] + page_ms / 1000.0 - t_load0) * 1000.0
        print(json.dumps({"event": "first_frame", "ms": round(total_ms, 1)}), flush=True)

    def on_bridge(payload):
        try:
            ev = json.loads(payload)
        except ValueError:
            return
        kind = ev.get("kind")
        if kind == "ready" and not state["ready"]:
            state["ready"] = True
            print(json.dumps({"event": "ready", "webgl": ev.get("webgl"),
                              "program": ev.get("program")}), flush=True)
            state["t_page0"] = time.monotonic() - ev.get("now", 0.0) / 1000.0
            state["t_replay0"] = time.monotonic()
            emit_first(ev.get("first", -1))
            pump.start()
            fps_timer.start()
        elif kind == "first":
            emit_first(ev.get("t"))
        elif kind == "fps":
            times = ev.get("times", [])
            p95 = 0
            if len(times) > 1:
                deltas = sorted(times[i] - times[i - 1] for i in range(1, len(times)))
                p95 = deltas[min(len(deltas) - 1, int(len(deltas) * 0.95))]
            print(json.dumps({"event": "fps", "t": round(elapsed_ms() / 1000.0, 2),
                              "fps": len(times), "p95_ms": round(p95, 1)}), flush=True)
        elif kind == "shot":
            shot_t = ev.get("t")
            data = ev.get("data") or ""
            if data and shot_t is not None:
                path = os.path.join(args.out, f"{args.label}_{shot_t}.png")
                with open(path, "wb") as fh:
                    fh.write(base64.b64decode(data.split(",", 1)[1]))
                print(json.dumps({"event": "shot", "t": shot_t, "file": path}), flush=True)
        elif kind == "summary":
            print(json.dumps({"event": "summary", "frames": int(ev.get("frames", 0)),
                              "duration_s": round(elapsed_ms() / 1000.0, 2)}), flush=True)
            state["done"] = True
            app.quit()

    bridge = Bridge(on_bridge)
    # El canal vive en host.qml (la propiedad webChannel del view es
    # QQmlWebChannel, sin binding PySide): registramos el bridge por la funcion
    # QML, y recien despues navegamos, asi qt.webChannelTransport ya existe.
    root.registerBridge(bridge)
    root.setProperty("page", QUrl.fromLocalFile(os.path.join(HERE, "web", html_file)))

    def tick():
        if state["done"] or not state["ready"]:
            return
        now = elapsed_ms()
        while state["idx"] < len(frames) and frames[state["idx"]]["t"] <= now:
            bridge.frame.emit(json.dumps(frames[state["idx"]], separators=(",", ":")))
            state["idx"] += 1
        while state["shot_i"] < len(shots) and now >= shots[state["shot_i"]]:
            shot_t = shots[state["shot_i"]]
            state["shot_i"] += 1
            bridge.command.emit(f"shot:{shot_t}")
            if shot_t == shots[0]:
                grab = root.grabWindow()
                grab.save(os.path.join(args.out, f"{args.label}_grab_{shot_t}.png"))
        if state["idx"] >= len(frames) and now >= last_t + args.tail_ms and not state["done"]:
            bridge.command.emit("summary")

    pump = QTimer()
    pump.setTimerType(Qt.PreciseTimer)
    pump.setInterval(4)
    pump.timeout.connect(tick)

    fps_timer = QTimer()
    fps_timer.setInterval(1000)
    fps_timer.timeout.connect(lambda: bridge.command.emit("fps"))

    def on_guard():
        grab = root.grabWindow()
        grab.save(os.path.join(args.out, f"{args.label}_timeout_grab.png"))
        print(json.dumps({"event": "fatal", "reason": "page never ready"}), flush=True)
        app.quit()

    guard = QTimer()
    guard.setInterval(15000)
    guard.setSingleShot(True)
    guard.timeout.connect(on_guard)
    guard.start()

    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
