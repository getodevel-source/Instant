"""Selección del renderer del overlay: Qt Quick primero, Tk de respaldo.

Corre sin Qt ni Tk reales: los renderers se reemplazan por dobles, así que
verifica la decisión (y no el dibujo, que cubren test_qml_success y
test_regression).
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import overlay as overlay_module


class OverlayRendererSelectionTests(unittest.TestCase):
    def test_prefers_qt_quick_everywhere(self):
        with patch.object(overlay_module, "_QtQuickOverlay") as qml, \
                patch.object(overlay_module, "_TkOverlay") as tk:
            overlay = overlay_module.Overlay("F10", style="orbital")
        qml.assert_called_once_with("F10", style="orbital")
        tk.assert_not_called()
        self.assertIs(overlay._renderer, qml.return_value)

    def test_falls_back_to_tk_when_qt_quick_cannot_open(self):
        with patch.object(overlay_module, "_QtQuickOverlay",
                          side_effect=RuntimeError("could not load qml")), \
                patch.object(overlay_module, "_TkOverlay") as tk, \
                self.assertLogs("instant", level="WARNING") as logs:
            overlay = overlay_module.Overlay("F9")
        tk.assert_called_once_with("F9")
        self.assertIs(overlay._renderer, tk.return_value)
        self.assertIn("overlay de Qt Quick no abrió", logs.output[0])

    def test_fallback_also_covers_a_missing_pyside6(self):
        with patch.object(overlay_module, "_QtQuickOverlay",
                          side_effect=ImportError("No module named PySide6")), \
                patch.object(overlay_module, "_TkOverlay") as tk, \
                self.assertLogs("instant", level="WARNING"):
            overlay = overlay_module.Overlay("F9", style="classic")
        self.assertIs(overlay._renderer, tk.return_value)


if __name__ == "__main__":
    unittest.main()
