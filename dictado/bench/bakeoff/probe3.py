"""Sonda 3: encuentra la sintaxis de fragmentShader inline que pinta en este
Qt 6.11 (PySide6, backend D3D11). Muestrea el centro de cada variante."""
import json
import os
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (wrapper antes de rootObjects)

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    app = QGuiApplication(["bakeoff-probe3"])
    app.setQuitOnLastWindowClosed(False)
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda msgs: warnings.extend(str(w.toString()) for w in msgs))
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "qml", "probe3.qml")))
    if not engine.rootObjects():
        print(json.dumps({"event": "fatal", "warnings": warnings}))
        return 1
    root = engine.rootObjects()[0]

    def shoot():
        image = root.grabWindow()
        path = os.path.join(HERE, "out", "probe3.png")
        image.save(path)
        names = ["legacy", "es3_in_out", "es3_const", "macros_main", "rect_control", "qt5compat"]
        samples = {}
        for i, name in enumerate(names):
            x = int(75 + i * 70)  # fila de 6x60 con 10 de separacion, centrada
            c = image.pixelColor(x, 80)
            samples[name] = [c.red(), c.green(), c.blue(), c.alpha()]
        try:
            api = str(QQuickWindow.graphicsApi())
        except Exception as exc:  # noqa: BLE001
            api = f"? {exc}"
        print(json.dumps({"event": "probe3", "graphics_api": api, "samples": samples,
                          "warnings": warnings, "png": path}))
        app.quit()

    QTimer.singleShot(900, shoot)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
