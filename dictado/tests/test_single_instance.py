"""Canal de instancia única del panel (QLocalServer/QLocalSocket).

En Linux/macOS una segunda apertura no crea otra ventana: escribe el pedido
por el canal y sale. En Windows ese rol lo cumple el mutex + FindWindow
(test_app_lifecycle.py); acá se cubre el mecanismo portable, que corre en
los tres sistemas.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import PySide6  # noqa: F401
except ImportError:
    print("SKIP canal de instancia única: PySide6 no está instalado")
else:
    from PySide6.QtCore import QEventLoop, QObject, QTimer
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication

    from instant_app import gui

    class _WindowStub(QObject):
        """Ventana mínima: solo recibe la acción que llegue por el canal."""

        def __init__(self):
            super().__init__()
            self.actions = []

        def apply_gui_action(self, page=None, start_daemon=False):
            self.actions.append((page, start_daemon))

    class SingleInstanceChannelTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            cls.app = QApplication.instance() or QApplication([])

        def setUp(self):
            QLocalServer.removeServer(gui._gui_server_name())
            self.server = None

        def tearDown(self):
            if self.server is not None:
                self.server.close()
                self.server = None
            QLocalServer.removeServer(gui._gui_server_name())

        def _send_raw(self, raw):
            """Escribe bytes crudos y espera el acuse del panel."""
            from PySide6.QtNetwork import QLocalSocket

            socket = QLocalSocket()
            socket.connectToServer(gui._gui_server_name())
            self.assertTrue(socket.waitForConnected(500))
            socket.write(raw)
            socket.flush()
            loop = QEventLoop()
            socket.disconnected.connect(loop.quit)
            QTimer.singleShot(3000, loop.quit)
            loop.exec()

        def test_forwarding_reaches_the_listening_window(self):
            window = _WindowStub()
            self.server = gui._install_gui_server(window)
            self.assertIsNotNone(self.server)
            self.assertTrue(gui._forward_to_existing_gui("setup", True))
            # El forward espera el acuse: al volver, la acción ya se aplicó.
            self.assertEqual(window.actions, [("setup", True)])

        def test_forwarding_without_server_is_false(self):
            self.assertFalse(gui._forward_to_existing_gui("home", False))

        def test_garbage_payload_does_not_break_the_channel(self):
            window = _WindowStub()
            self.server = gui._install_gui_server(window)
            self._send_raw(b"\xff\x00 not json")
            self.assertTrue(gui._forward_to_existing_gui("diagnostics", False))
            self.assertEqual(window.actions, [("diagnostics", False)])

        @unittest.skipIf(sys.platform == "win32",
                         "la rama unix de run_gui solo corre en Linux/macOS")
        def test_run_gui_installs_the_channel(self):
            """La ventana real atiende el canal: integración de punta a punta."""
            from unittest.mock import patch

            from PySide6.QtCore import QTimer

            results = []

            def probe():
                results.append(gui._forward_to_existing_gui(None, False))
                self.app.quit()

            QTimer.singleShot(700, probe)
            with patch.dict(os.environ, {"DISPLAY": os.environ.get("DISPLAY", ":0")}):
                rc = gui.run_gui("setup")
            self.assertEqual(rc, 0)
            self.assertEqual(results, [True],
                             "el canal no respondió al pedido de otra instancia")


if __name__ == "__main__":
    unittest.main()
