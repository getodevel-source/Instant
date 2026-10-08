"""Sonda 6: QWebChannel creado en QML + bridge Python registrado por funcion
QML. Prueba tambien el canal de vuelta (la pagina hace ping)."""
import json
import os
import sys

from PySide6.QtCore import QMetaObject, QObject, QTimer, QUrl, Qt, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWebEngineQuick import QtWebEngineQuick

HERE = os.path.dirname(os.path.abspath(__file__))


class Bridge(QObject):
    @Slot(str)
    def ping(self, payload):
        print(json.dumps({"event": "bridge", "payload": payload}), flush=True)


def main():
    QtWebEngineQuick.initialize()
    app = QGuiApplication(["webengine-probe6"])
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda msgs: warnings.extend(w.toString() for w in msgs))
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "web", "host.qml")))
    if not engine.rootObjects():
        print(json.dumps({"event": "qml-failed", "warnings": warnings}), flush=True)
        return 1
    root = engine.rootObjects()[0]
    root.setProperty("page", QUrl("about:blank"))
    view = root.findChild(QObject, "view")

    bridge = Bridge()
    # Registro del bridge por la funcion QML (dos variantes: atributo directo
    # y QMetaObject.invokeMethod).
    try:
        root.registerBridge(bridge)
        print(json.dumps({"event": "register", "how": "attribute"}), flush=True)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"event": "register", "how": "attribute-failed",
                          "error": str(exc)}), flush=True)
        try:
            ok = QMetaObject.invokeMethod(
                root, "registerBridge", Qt.ConnectionType.DirectConnection,
                *[QMetaObject.FromPythonArg(QObject, bridge)]
                if hasattr(QMetaObject, "FromPythonArg") else [])
            print(json.dumps({"event": "register", "how": "invokeMethod", "ok": bool(ok)}),
                  flush=True)
        except Exception as exc2:  # noqa: BLE001
            print(json.dumps({"event": "register", "how": "invokeMethod-failed",
                              "error": str(exc2)}), flush=True)

    page = os.path.join(HERE, "web", "probe_channel.html")
    QTimer.singleShot(300, lambda: root.setProperty("page", QUrl.fromLocalFile(page)))

    def report():
        print(json.dumps({"event": "state", "title": str(view.property("title")),
                          "progress": view.property("loadProgress")}), flush=True)

    QTimer.singleShot(3500, report)
    QTimer.singleShot(6000, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
