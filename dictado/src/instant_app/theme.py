"""Tokens de diseño de Instant: una base para seguir ajustando la interfaz.

Los colores viven en `branding.PALETTE` (una sola fuente de verdad). Acá están
las medidas, la escala tipográfica y los tiempos de animación, más el armado de
la hoja de estilo de la ventana. Tocar un token cambia toda la aplicación.
"""
from instant_app.branding import PALETTE, rgba

# Radios: tarjetas amplias y controles contenidos dan el aire minimalista.
# Subidos un punto respecto a la versión anterior: el iOS moderno redondea
# generoso y funde los bordes con el fondo en vez de recortarlos.
RADIUS = {"card": 18, "control": 12, "small": 8, "rail": 12}

# Escala tipográfica en puntos (Qt usa pt en QSS). Un punto más chica y con
# pesos medios: el minimalismo iOS susurra, no grita.
FONT = {
    "brand": 18, "display": 21, "title": 18, "heading": 12,
    "body": 9.5, "small": 8.5, "caption": 7.5, "key": 14,
}

# Tiempos de animación en milisegundos (los usa también el overlay).
# Entrada/salida apenas más largas: lo premium se mueve despacio.
MOTION = {
    "enter": 300, "exit": 200, "state": 280, "wave_up": 240, "wave_down": 520,
    "sweep": 1100, "breathe": 2600,
}

SPACE = {"xs": 4, "sm": 8, "md": 16, "lg": 26, "xl": 42}


def stylesheet():
    """QSS de la ventana, armado desde la paleta y los tokens."""
    c = PALETTE
    r = RADIUS
    f = FONT
    return f"""
/* ---------- base ---------- */
QMainWindow, QDialog, QMessageBox, QWidget {{
    background:{c['background']}; color:{c['text']};
    font-family:'Segoe UI'; font-size:{f['body']}pt;
}}
QLabel {{ background:transparent; }}

/* ---------- marca ---------- */
QLabel#brand {{ color:{c['hero_text']}; font-size:{f['brand']}pt; font-weight:600; }}
QLabel#railCaption {{ color:{c['faint']}; font-size:{f['caption']}pt; }}

/* ---------- encabezado ---------- */
QFrame#rule {{ background:{rgba(c['line_soft'], 0.6)}; border:0; }}
QLabel#muted {{ color:{c['muted']}; }}
QLabel#statusDot {{
    background:transparent; border:0; color:{c['faint']};
    font-size:13pt; padding:0 2px;
}}
QLabel#statusDot[active="true"] {{ color:{c['green']}; }}

/* ---------- portada ---------- */
QFrame#hero {{
    background:qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {c['hero']}, stop:1 {c['hero_alt']});
    border:1px solid {rgba(c['accent'], 0.12)}; border-radius:{r['card'] + 2}px;
}}
QLabel#heroStatus {{ color:{c['accent_soft']}; font-size:{f['small'] + 1.5}pt; font-weight:600; }}
QLabel#heroTitle {{ color:{c['hero_text']}; font-size:{f['display']}pt; font-weight:600; }}
QLabel#heroDetail {{ color:{rgba(c['hero_text'], 0.72)}; }}
QLabel#keyBadge {{
    background:{rgba(c['accent'], 0.11)}; color:{c['hero_text']};
    border:1px solid {rgba(c['accent'], 0.25)}; border-radius:{r['control']}px;
    padding:8px 18px; font-size:{f['key']}pt; font-weight:600;
}}

/* ---------- tarjetas ---------- */
QFrame#card {{
    background:{c['surface']}; border:1px solid {rgba(c['line_soft'], 0.7)};
    border-radius:{r['card']}px;
}}
QLabel#cardTitle {{ font-size:{f['heading']}pt; font-weight:600; }}
QLabel#statusLine {{ color:{c['muted']}; }}

/* ---------- estado sin tarjeta: una línea tenue, sin cromo ---------- */
QLabel#softStatus {{ color:{c['faint']}; font-size:{f['small']}pt; }}

/* ---------- controles ---------- */
QPushButton {{
    background:{c['surface_alt']}; color:{c['text']};
    border:1px solid {rgba(c['line'], 0.8)}; border-radius:{r['control']}px;
    padding:12px 18px; font-weight:500;
}}
QPushButton:hover {{ background:{c['surface_high']}; border-color:{rgba(c['accent'], 0.30)}; }}
QPushButton:pressed {{ background:{c['surface']}; }}
QPushButton:focus {{ border-color:{rgba(c['accent'], 0.6)}; outline:none; }}
QPushButton:disabled {{ color:{c['faint']}; background:{rgba(c['surface_alt'], 0.55)}; border-color:{rgba(c['line_soft'], 0.6)}; }}
QPushButton#primaryButton {{
    background:{c['accent_button']}; color:white; border:1px solid transparent;
    padding:12px 20px; font-weight:600;
}}
QPushButton#ghostButton {{
    background:transparent; color:{c['muted']};
    border:1px solid transparent; border-radius:{r['control']}px;
    padding:8px 14px; font-weight:500;
}}
QPushButton#ghostButton:hover {{ background:{rgba(c['accent'], 0.08)}; color:{c['text']}; border-color:transparent; }}
QPushButton#primaryButton:hover {{ background:{c['accent_hover']}; border-color:transparent; }}
QPushButton#primaryButton:pressed {{ background:{c['accent_press']}; }}
QPushButton#primaryButton:disabled {{ background:{rgba(c['accent_button'], 0.38)}; color:{rgba('#ffffff', 0.55)}; }}

QComboBox, QPlainTextEdit, QLineEdit {{
    background:{c['bg_alt']}; color:{c['text']};
    border:1px solid {rgba(c['line'], 0.8)}; border-radius:{r['control']}px;
    padding:10px 12px;
    selection-color:white; selection-background-color:{c['accent_button']};
}}
QComboBox:hover, QPlainTextEdit:hover, QLineEdit:hover {{ border-color:{rgba(c['surface_high'], 0.9)}; }}
QComboBox:focus, QPlainTextEdit:focus, QLineEdit:focus {{ border-color:{rgba(c['accent'], 0.6)}; }}
QComboBox:disabled, QLineEdit:disabled {{ color:{c['faint']}; }}
QComboBox::drop-down {{ border:0; width:22px; }}
QComboBox QAbstractItemView {{
    background:{c['surface']}; color:{c['text']};
    border:1px solid {rgba(c['line'], 0.8)}; border-radius:{r['small']}px;
    padding:4px; outline:none;
    selection-color:{c['text']}; selection-background-color:{rgba(c['accent'], 0.16)};
}}

/* ---------- tabla de vocabulario ---------- */
QTableWidget {{
    background:{c['bg_alt']}; color:{c['text']};
    border:1px solid {rgba(c['line_soft'], 0.7)}; border-radius:{r['control']}px;
    gridline-color:transparent; outline:none;
}}
QHeaderView::section {{
    background:transparent; color:{c['muted']};
    border:0; padding:8px 10px; font-weight:600;
}}
QTableWidget::item {{ padding:6px 8px; border:0; }}
QTableWidget::item:selected {{ background:{rgba(c['accent'], 0.16)}; color:{c['text']}; }}
/* Envoltorios de los botones de cada fila: transparentes para no pintar
   un cuadrado detrás del pill / círculo (el fondo global de QWidget los
   tapaba con otro tono). */
QTableWidget QWidget#vocabCell {{ background:transparent; border:0; }}
QPushButton#rowDelete {{
    background:transparent; color:{c['muted']};
    border:1px solid {rgba(c['line'], 0.7)}; border-radius:15px;
    min-width:30px; max-width:30px; min-height:30px; max-height:30px;
    padding:0; font-size:10pt; font-weight:600;
}}
QPushButton#rowDelete:hover {{ color:{c['red']}; border-color:{rgba(c['red'], 0.5)}; background:transparent; }}
QPushButton#soundToggle {{
    background:transparent; color:{c['faint']};
    border:1px solid {rgba(c['line'], 0.7)}; border-radius:14px;
    min-width:56px; max-width:56px; min-height:28px; max-height:28px;
    padding:0; font-size:11pt; font-weight:600;
}}
QPushButton#soundToggle:hover {{ color:{c['muted']}; border-color:{rgba(c['accent'], 0.5)}; }}
QPushButton#soundToggle:checked {{
    background:{rgba(c['accent'], 0.14)}; color:{c['accent']};
    border-color:{rgba(c['accent'], 0.45)};
}}

QProgressBar {{
    min-height:6px; max-height:6px; border:0;
    background:{rgba(c['surface_alt'], 0.8)}; border-radius:3px;
}}
QProgressBar::chunk {{
    background:qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent_button']}, stop:1 {c['accent']});
    border-radius:3px;
}}

QCheckBox {{ spacing:12px; padding:6px 2px; background:transparent; }}
QCheckBox::indicator {{
    width:46px; height:26px; border:1px solid {rgba(c['line'], 0.9)};
    border-radius:13px; background:{c['surface_high']};
}}
QCheckBox::indicator:hover {{ border-color:{rgba(c['accent'], 0.5)}; }}
QCheckBox::indicator:checked {{
    background:{c['accent_button']}; border-color:transparent;
}}

/* ---------- detalles ---------- */
QScrollArea {{ background:transparent; border:0; }}
QScrollArea > QWidget > QWidget {{ background:transparent; }}
QScrollBar:vertical {{ background:transparent; width:8px; margin:2px; }}
QScrollBar::handle:vertical {{ background:{rgba(c['surface_high'], 0.9)}; border-radius:4px; min-height:28px; }}
QScrollBar::handle:vertical:hover {{ background:{rgba(c['accent'], 0.4)}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; width:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
QToolTip {{
    background:{c['surface_high']}; color:{c['text']};
    border:1px solid {c['line']}; border-radius:{r['small']}px; padding:6px 9px;
}}
QPlainTextEdit {{ selection-color:white; }}

/* ---------- toasts: avisos sin ventanas ---------- */
QWidget#toastHost {{ background:transparent; border:0; }}
QFrame#toast {{
    background:{c['surface']}; border:1px solid {rgba(c['line'], 0.9)};
    border-radius:{r['control']}px;
}}
QFrame#toast[level="info"] {{ border-color:{rgba(c['accent'], 0.55)}; }}
QFrame#toast[level="warn"] {{ border-color:{rgba(c['amber'], 0.55)}; }}
QFrame#toast[level="error"] {{ border-color:{rgba(c['red'], 0.55)}; }}
QLabel#toastTitle {{ font-weight:600; }}
QLabel#toastBody {{ color:{c['muted']}; }}
QPushButton#toastAction {{
    background:transparent; color:{c['text']};
    border:1px solid {rgba(c['line'], 0.9)}; border-radius:{r['small']}px;
    padding:6px 12px; font-weight:600;
}}
QPushButton#toastAction:hover {{ border-color:{rgba(c['accent'], 0.5)}; }}
"""
