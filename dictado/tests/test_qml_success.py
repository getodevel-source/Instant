"""Consumer-visible copy in the Windows Qt Quick overlay."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

try:
    import PySide6  # noqa: F401
except ImportError:
    print("SKIP Qt Quick overlay copy: PySide6 is not installed")
else:
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QGuiApplication

    from instant_app.overlay import _QtQuickOverlay

    class QtQuickSuccessCopyTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            cls.app = QGuiApplication.instance() or QGuiApplication(["Instant test"])

        def test_success_state_truthfully_confirms_copy_attempt(self):
            overlay = _QtQuickOverlay("F9")
            try:
                success = overlay.root.findChild(QObject, "successText")
                self.assertIsNotNone(success)
                self.assertEqual(overlay.root.property("title"), "Instant overlay")
                overlay.root.setProperty("mode", "success")
                self.app.processEvents()
                self.assertEqual(success.property("text"), "Copiado")
                self.assertTrue(overlay.root.property("visible"))
            finally:
                overlay.root.close()


if __name__ == "__main__":
    unittest.main()
