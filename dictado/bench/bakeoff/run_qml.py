"""Runner del prototipo QML v2 del bake-off: carga overlay_v2.qml, reproduce
frames.jsonl a sus timestamps y emite metricas JSON por stdout.

Eventos por stdout (una linea JSON cada uno):
    {"event": "first_frame", "ms": ...}
    {"event": "fps", "t": s, "fps": n, "p95_ms": ms}
    {"event": "shot", "t": ms, "file": ...}
    {"event": "summary", "frames": n, "duration_s": s}

Uso: python run_qml.py [--frames frames.jsonl] [--shots 1200,2500,6500,9200]
                       [--out out] [--label qml] [--tail-ms 1200]
"""
import argparse
import json
import os
import sys
import time

from PySide6.QtCore import QPoint, QTimer, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (wrapper antes de rootObjects)

HERE = os.path.dirname(os.path.abspath(__file__))


def load_frames(path):
    frames = []
    with open(path, encoding="utf-8") as fh:
        meta = json.loads(fh.readline())
        for line in fh:
            line = line.strip()
            if line:
                frames.append(json.loads(line))
    return meta, frames


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", default=os.path.join(HERE, "frames.jsonl"))
    parser.add_argument("--shots", default="1200,2500,6500,9200")
    parser.add_argument("--out", default=os.path.join(HERE, "out"))
    parser.add_argument("--label", default="qml")
    parser.add_argument("--variant", choices=["v2", "v3", "v4"], default="v2")
    parser.add_argument("--tail-ms", type=int, default=1200)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    qml_file = {"v2": "overlay_v2.qml", "v3": "overlay_v3.qml", "v4": "overlay_v4.qml"}[args.variant]

    meta, frames = load_frames(args.frames)
    last_t = frames[-1]["t"] if frames else 0
    shots = [int(s) for s in args.shots.split(",") if s.strip()]

    app = QGuiApplication(["instant-bakeoff-qml"])
    app.setQuitOnLastWindowClosed(False)

    engine = QQmlApplicationEngine()
    t_load0 = time.monotonic()
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "qml", qml_file)))
    if not engine.rootObjects():
        print(json.dumps({"event": "fatal", "reason": "qml load failed"}))
        return 1
    root = engine.rootObjects()[0]

    screen = QGuiApplication.primaryScreen().availableGeometry()
    root.setPosition(QPoint(
        screen.left() + (screen.width() - root.width()) // 2,
        screen.bottom() - root.height() - 60))

    t_start = time.monotonic()  # reloj del replay: mismo en el runner web
    state = {"idx": 0, "shot_i": 0, "shot_at": {}, "done": False}

    def elapsed_ms():
        return (time.monotonic() - t_start) * 1000.0

    def on_first_frame():
        print(json.dumps({"event": "first_frame",
                          "ms": round((time.monotonic() - t_load0) * 1000, 1)}), flush=True)

    def on_fps(fps, p95):
        print(json.dumps({"event": "fps", "t": round(elapsed_ms() / 1000.0, 2),
                          "fps": int(fps), "p95_ms": int(p95)}), flush=True)

    root.firstFrame.connect(on_first_frame)
    root.reportFps.connect(on_fps)

    def tick():
        if state["done"]:
            return
        now = elapsed_ms()
        while state["idx"] < len(frames) and frames[state["idx"]]["t"] <= now:
            frame = frames[state["idx"]]
            root.setProperty("level", frame["level"])
            root.setProperty("bandLevels", frame["bands"])
            root.setProperty("pitch", frame["pitch"])
            if "message" in frame:
                root.setProperty("message", frame["message"])
            if root.property("mode") != frame["mode"]:
                root.setProperty("mode", frame["mode"])
            state["idx"] += 1
        while state["shot_i"] < len(shots) and now >= shots[state["shot_i"]]:
            shot_t = shots[state["shot_i"]]
            state["shot_i"] += 1
            image = root.grabWindow()
            path = os.path.join(args.out, f"{args.label}_{shot_t}.png")
            image.save(path)
            print(json.dumps({"event": "shot", "t": shot_t, "file": path}), flush=True)
        if state["idx"] >= len(frames) and now >= last_t + args.tail_ms:
            image = root.grabWindow()
            image.save(os.path.join(args.out, f"{args.label}_final.png"))
            print(json.dumps({
                "event": "summary", "frames": int(root.property("frames") or 0),
                "duration_s": round(now / 1000.0, 2)}), flush=True)
            state["done"] = True
            app.quit()

    pump = QTimer()
    pump.setTimerType(Qt.PreciseTimer)
    pump.setInterval(4)
    pump.timeout.connect(tick)
    pump.start()

    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
