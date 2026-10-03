"""La paleta del overlay QML tiene que seguir a branding.PALETTE.

El QML se carga sin motor de plantillas, así que repite los colores a mano. Este
test es la red que evita que un cambio de marca deje la pastilla flotante con
los colores viejos (o con un literal suelto que nadie sabe de dónde salió).
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app.branding import PALETTE

QML_PATHS = [
    os.path.join(
        os.path.dirname(__file__), "..", "src", "instant_app", "qml", name)
    for name in ("overlay.qml", "overlay_orbital.qml")
]

# Token del QML -> clave de la paleta.
TOKENS = {
    "brandAccent": "accent",
    "brandWorking": "working",
    "brandGreen": "green",
    "brandAmber": "amber",
    "brandRed": "red",
    "ink": "text",
    "inkDim": "muted",
    "glassTop": "glass",
    "glassBottom": "glass_alt",
}

# Únicos colores que pueden escribirse a mano: blanco y negro puros se usan con
# alfa para la luz de canto y la sombra, no como color de marca.
ALLOWED_LITERALS = {"#ffffff"}


def qml_sources():
    for path in QML_PATHS:
        with open(path, encoding="utf-8") as handle:
            yield os.path.basename(path), handle.read()


class OverlayPaletteTests(unittest.TestCase):
    def test_declared_tokens_mirror_python_palette(self):
        for name, source in qml_sources():
            declared = {
                token: value.lower()
                for token, value in re.findall(
                    r'readonly property color (\w+):\s*"(#[0-9a-fA-F]{6})"', source)
            }
            for token, key in TOKENS.items():
                self.assertIn(token, declared, f"falta el token {token} en {name}")
                self.assertEqual(
                    declared[token], PALETTE[key].lower(),
                    f"{name}: {token} debe seguir a PALETTE['{key}']")

    def test_no_color_escapes_the_palette(self):
        for name, source in qml_sources():
            found = {value.lower() for value in re.findall(r"#[0-9a-fA-F]{6}", source)}
            allowed = {value.lower() for value in PALETTE.values()} | ALLOWED_LITERALS
            self.assertEqual(found - allowed, set(), f"{name}: colores fuera de la paleta")

    def test_default_message_color_is_the_amber_token(self):
        for name, source in qml_sources():
            default = re.search(r'property color messageColor:\s*"(#[0-9a-fA-F]{6})"', source)
            self.assertIsNotNone(default, f"{name}: sin messageColor")
            self.assertEqual(default.group(1).lower(), PALETTE["amber"].lower())


if __name__ == "__main__":
    unittest.main()
