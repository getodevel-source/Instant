"""Sonda Quick3D: valida View3D + ExtendedSceneEnvironment (glow) en ventana
transparente. Muestrea alphas radiales: glow = alpha > 0 fuera de la silueta."""
import json
import os
import sys
import time

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    app = QGuiApplication(["bakeoff-q3d-probe"])
    app.setQuitOnLastWindowClosed(False)
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda msgs: warnings.extend(w.toString() for w in msgs))
    t0 = time.monotonic()
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "qml", "probe_q3d.qml")))
    if not engine.rootObjects():
        print(json.dumps({"event": "fatal", "warnings": warnings}))
        return 1
    root = engine.rootObjects()[0]

    def shoot():
        image = root.grabWindow()
        path = os.path.join(HERE, "out", "probe_q3d.png")
        image.save(path)
        cx = image.width() // 2
        samples = {}
        profile = []
        for dy in range(20, 84, 4):
            c = image.pixelColor(cx, cx + dy)
            profile.append([dy, c.alpha()])
        for name, dy in (("center", 0), ("r30", 30), ("r48", 48)):
            c = image.pixelColor(cx, cx + dy)
            samples[name] = [c.red(), c.green(), c.blue(), c.alpha()]
        print(json.dumps({
            "event": "q3d", "ms_to_load": round((time.monotonic() - t0) * 1000, 1),
            "samples": samples, "alpha_profile": profile,
            "png": path, "warnings": warnings}), flush=True)
        app.quit()

    QTimer.singleShot(1200, shoot)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
