"""Sonda: verifica que ShaderEffect (GLSL inline) y MultiEffect funcionan en
este PySide6 antes de comprometer el diseño del overlay v2 del bake-off.

Corre una ventana transparente de 240x120 con un orbe por fragment shader y un
glow por MultiEffect, la captura y valida pixeles. No forma parte de la app.
"""
import json
import os
import sys
import time

os.environ.setdefault("QT_LOGGING_RULES", "qt.qml.binding.removal.info=false")

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
# Registrar el wrapper de QQuickWindow ANTES de rootObjects(): si no, el root
# QML queda envuelto como QWindow base y grabWindow() no existe (gotcha PySide).
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    app = QGuiApplication(["bakeoff-probe"])
    app.setQuitOnLastWindowClosed(False)

    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda msgs: warnings.extend(str(w.toString()) for w in msgs))
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "qml", "probe.qml")))
    if not engine.rootObjects():
        print(json.dumps({"event": "fatal", "reason": "qml load failed", "warnings": warnings}))
        return 1

    root = engine.rootObjects()[0]
    result = {"event": "probe"}
    result["shader_error"] = [w for w in warnings if "shader" in w.lower() or "effect" in w.lower()]

    def shoot():
        image = root.grabWindow()
        path = os.path.join(HERE, "out", "probe.png")
        image.save(path)
        # Pixels: centro (orbe) debe tener alpha y color; esquina debe ser transparente.
        center = image.pixelColor(image.width() // 2, 60)
        corner = image.pixelColor(4, 4)
        result["size"] = [image.width(), image.height()]
        result["center_rgba"] = [center.red(), center.green(), center.blue(), center.alpha()]
        result["corner_alpha"] = corner.alpha()
        result["png"] = path
        result["warnings"] = warnings
        print(json.dumps(result))
        app.quit()

    QTimer.singleShot(900, shoot)
    code = app.exec()
    return code or 0


if __name__ == "__main__":
    sys.exit(main())
