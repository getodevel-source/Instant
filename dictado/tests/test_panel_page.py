"""Contrato del panel web: página, hosts QML y composición con qwebchannel.

Los hosts de QML ya se rompieron una vez por olvidar `webChannel: channel`
(el canal queda sin transporte y la página lo avisa con un título). Acá queda
anclado ese contrato, además de la paleta y las piezas puras de gui.py.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app.branding import PALETTE
from instant_app.gui import compose_panel_page

PACKAGE = os.path.join(os.path.dirname(__file__), "..", "src", "instant_app")
PANEL_PAGE = os.path.join(PACKAGE, "web", "panel.html")
OVERLAY_PAGE = os.path.join(PACKAGE, "web", "overlay.html")
HOSTS = {
    "panel_web_host.qml": os.path.join(PACKAGE, "qml", "panel_web_host.qml"),
    "overlay_web_host.qml": os.path.join(PACKAGE, "qml", "overlay_web_host.qml"),
}
ALLOWED_LITERALS = {"#ffffff", "#000000"}


class PanelPageContractTests(unittest.TestCase):
    def _source(self):
        with open(PANEL_PAGE, encoding="utf-8") as handle:
            return handle.read()

    def test_page_keeps_its_bridge_contract(self):
        source = self._source()
        for expected in ("<!--QWEBCHANNEL-->", "window.__panelReady",
                         "bridge.call", 'on("state", onState)',
                         'on("toast", onToast)', 'on("key_result", onKeyResult)',
                         'op:"ready"', 'op:"save_config"', 'op:"toggle_daemon"',
                         'op:"key_captured"', 'op:"diagnostics"'):
            self.assertIn(expected, source)

    def test_page_keeps_the_user_facing_copy(self):
        source = self._source()
        for expected in ("Hablá. Soltá. Listo.", "Iniciar dictado", "Detener",
                         "Guardar ajustes", "Añadir perfil", "Eliminar perfil",
                         "Añadir término", "Descargar voz", "Elegir tecla",
                         "Iniciar Instant con Windows", "Diagnóstico",
                         "Buscar actualizaciones", "La prueba no guarda audio."):
            self.assertIn(expected, source)

    def test_no_color_escapes_the_palette(self):
        found = {value.lower() for value in re.findall(r"#[0-9a-fA-F]{6}", self._source())}
        allowed = {value.lower() for value in PALETTE.values()} | ALLOWED_LITERALS
        self.assertEqual(found - allowed, set(), "panel.html: colores fuera de la paleta")

    def test_qwebchannel_is_injected_once(self):
        out = compose_panel_page("<html><!--QWEBCHANNEL--></html>", "window.qt=1;")
        self.assertIn("<script>", out)
        self.assertIn("window.qt=1;", out)
        self.assertNotIn("<!--QWEBCHANNEL-->", out)


class HostContractTests(unittest.TestCase):
    def test_hosts_bind_the_channel_and_register_the_bridge(self):
        for name, path in HOSTS.items():
            with self.subTest(host=name), open(path, encoding="utf-8") as handle:
                source = handle.read()
            self.assertIn("webChannel: channel", source,
                          f"{name}: el WebEngineView sin webChannel no inyecta "
                          "qt.webChannelTransport")
            self.assertIn("registerBridge", source, f"{name}: falta registerBridge")
            self.assertIn('objectName: "view"', source, f"{name}: falta el view")

    def test_pages_ship_with_the_package(self):
        self.assertTrue(os.path.isfile(PANEL_PAGE))
        self.assertTrue(os.path.isfile(OVERLAY_PAGE))


if __name__ == "__main__":
    unittest.main()
