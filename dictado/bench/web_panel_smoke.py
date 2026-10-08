"""Smoke del panel web de producción: instancia `_WebPanel`, espera el canal,
ejercita ops reales por el bridge y captura la ventana.

Uso: python web_panel_smoke.py [--out RUTA.png]
"""
import argparse
import json
import logging
import os
import sys
import time
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "src")))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401  (wrapper de grabWindow)

from instant_app import gui  # noqa: E402


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(
        HERE, "bakeoff", "out", "web_panel.png"))
    parser.add_argument("--seconds", type=float, default=9.0)
    args = parser.parse_args()

    # Estado del usuario a resguardo: nada de este smoke escribe el config
    # real ni toca el autostart del sistema.
    with patch("instant_app.gui.config.save",
               side_effect=lambda cfg: "smoke-config.json") as save_cfg, \
            patch("instant_app.gui.autostart.is_enabled", return_value=False), \
            patch("instant_app.gui.autostart.enable") as autostart_enable, \
            patch("instant_app.gui.autostart.disable") as autostart_disable:
        run(args, save_cfg, autostart_enable, autostart_disable)
    return 0


def run(args, save_cfg, autostart_enable, autostart_disable):
    panel = gui._WebPanel(page="home", autostart_override=False)
    app = panel.application
    events = []

    def op(payload):
        events.append(payload)
        panel._handle_call(json.dumps(payload))

    def capture():
        image = panel.root.grabWindow()
        image.save(args.out)
        print(json.dumps({
            "event": "captured", "file": args.out,
            "size": [image.width(), image.height()],
            "title": panel.view.property("title"),
            "loadProgress": panel.view.property("loadProgress"),
            "ops": events,
            "settings_status": panel.logic.settings_status,
            "status_title": panel.logic.status_var,
            "vocab_rows": panel.logic.state_payload()["vocab"]["rows"][:3],
            "config_saved": save_cfg.call_count,
            "autostart_calls": [autostart_enable.call_count,
                                autostart_disable.call_count],
        }, ensure_ascii=False), flush=True)
        panel.logic.close()
        app.quit()

    # Secuencia: perfil desechable para editar sin tocar el vocabulario real.
    QTimer.singleShot(2500, lambda: op({"op": "navigate", "page": "settings"}))
    QTimer.singleShot(3000, lambda: op({"op": "context_add", "name": "Smoke"}))
    QTimer.singleShot(3200, lambda: op({"op": "vocab_add"}))
    QTimer.singleShot(3400, lambda: op({"op": "vocab_set", "row": 0, "col": "term",
                                        "value": "OpenAI"}))
    QTimer.singleShot(3600, lambda: op({"op": "vocab_toggle_sound", "row": 0}))
    QTimer.singleShot(3900, lambda: op({"op": "context_remove"}))
    QTimer.singleShot(4200, lambda: op({"op": "set_autostart", "value": False}))
    QTimer.singleShot(4500, lambda: op({"op": "save_config"}))
    QTimer.singleShot(4800, lambda: op({"op": "key_captured", "code": 13, "name": "enter"}))
    QTimer.singleShot(int(args.seconds * 1000), capture)

    panel.show()
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
