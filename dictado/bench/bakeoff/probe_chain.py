"""Sonda de la cadena v4: corre las 3 etapas y reporta alfa central de cada una."""
import json
import os
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    app = QGuiApplication(["bakeoff-chain-probe"])
    app.setQuitOnLastWindowClosed(False)
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda msgs: warnings.extend(w.toString() for w in msgs))
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "qml", "probe_chain.qml")))
    root = engine.rootObjects()[0]
    results = {}

    def sample(stage, tag):
        image = root.grabWindow()
        path = os.path.join(HERE, "out", f"probe_chain_{tag}.png")
        image.save(path)
        cx = image.width() // 2
        peak = 0
        for dy in range(-30, 31, 3):
            c = image.pixelColor(cx, cx + dy)
            peak = max(peak, c.alpha())
        results[tag] = {"peak_alpha_center": peak,
                        "center": [image.pixelColor(cx, cx).red(),
                                   image.pixelColor(cx, cx).green(),
                                   image.pixelColor(cx, cx).blue(),
                                   image.pixelColor(cx, cx).alpha()]}

    QTimer.singleShot(900, lambda: (sample(0, "directo")))
    QTimer.singleShot(1100, lambda: root.setProperty("stage", 2))
    QTimer.singleShot(1900, lambda: sample(2, "captura"))
    QTimer.singleShot(2100, lambda: root.setProperty("stage", 3))
    QTimer.singleShot(2900, lambda: (sample(3, "bloom"), finish()))

    def finish():
        print(json.dumps({"event": "chain", "results": results, "warnings": warnings}),
              flush=True)
        app.quit()

    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
