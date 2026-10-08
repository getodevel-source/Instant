"""Tokens de diseño de Instant: radios, tipografía, espaciado y tiempos.

Son la fuente de verdad del sistema visual. La UI web los repite a mano
(las páginas se sirven tal cual, sin motor de plantillas) y
`tests/test_panel_page.py` falla si se despegan. La paleta vive en
`branding.PALETTE`.
"""

# Radios: un poco más generoso que el estándar para que el vidrio se vea
# suave; los controles usan la mitad para no sentirse "duros".
RADIUS = {"card": 18, "control": 12, "small": 8, "rail": 12}

# Escala tipográfica en puntos. Un punto más chica y con pesos medios:
# el minimalismo susurra, no grita.
FONT = {
    "brand": 18, "display": 21, "title": 18, "heading": 12,
    "body": 9.5, "small": 8.5, "caption": 7.5, "key": 14,
}

# Entrada/salida apenas más largas: lo premium se mueve despacio.
MOTION = {
    "enter": 300, "exit": 200, "state": 280, "wave_up": 240, "wave_down": 520,
    "sweep": 1100, "breathe": 2600,
}

SPACE = {"xs": 4, "sm": 8, "md": 16, "lg": 26, "xl": 42}
