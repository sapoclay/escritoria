"""
Utilidades para adaptar la interfaz al tamaño de pantalla.
Calcula factores de escala y dimensiones proporcionales a la resolución
para que la aplicación se vea bien en cualquier monitor.
"""
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSize

# Resolución de referencia (base del diseño original)
REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1080


def get_screen_geometry():
    """Obtiene la geometría disponible de la pantalla principal."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return None
    screen = app.primaryScreen()
    if screen is None:
        return None
    return screen.availableGeometry()


def get_scale_factor():
    """
    Calcula el factor de escala basado en la resolución de la pantalla.
    Retorna un float donde 1.0 = resolución de referencia (1920x1080).
    """
    geom = get_screen_geometry()
    if geom is None:
        return 1.0

    scale_w = geom.width() / REFERENCE_WIDTH
    scale_h = geom.height() / REFERENCE_HEIGHT

    # Promedio ponderado (más peso al menor para no desbordar)
    scale = min(scale_w, scale_h)

    # Limitar entre 0.6 y 2.0
    return max(0.6, min(2.0, scale))


def scaled(value, factor=None):
    """Escala un valor de píxeles según el factor de escala de pantalla."""
    if factor is None:
        factor = get_scale_factor()
    return max(1, int(value * factor))


def get_window_size(width_pct=0.75, height_pct=0.82):
    """
    Calcula el tamaño inicial de ventana como porcentaje de la pantalla.
    """
    geom = get_screen_geometry()
    if geom is None:
        return QSize(1400, 800)

    w = int(geom.width() * width_pct)
    h = int(geom.height() * height_pct)
    return QSize(w, h)


def get_min_window_size(width_pct=0.52, height_pct=0.52):
    """
    Calcula el tamaño mínimo de ventana como porcentaje de la pantalla.
    """
    geom = get_screen_geometry()
    if geom is None:
        return QSize(900, 550)

    w = max(800, int(geom.width() * width_pct))
    h = max(500, int(geom.height() * height_pct))
    return QSize(w, h)


def get_dialog_size(width_pct=0.40, height_pct=0.55):
    """
    Calcula el tamaño de un diálogo como porcentaje de la pantalla.
    """
    geom = get_screen_geometry()
    if geom is None:
        return QSize(700, 500)

    w = max(500, int(geom.width() * width_pct))
    h = max(400, int(geom.height() * height_pct))
    return QSize(w, h)


def get_sidebar_width():
    """Calcula el ancho del sidebar según la pantalla."""
    geom = get_screen_geometry()
    if geom is None:
        return 220

    # ~11.5% del ancho disponible, con límites razonables
    w = int(geom.width() * 0.115)
    return max(170, min(280, w))


def get_font_size():
    """Calcula el tamaño de fuente base óptimo según la pantalla."""
    geom = get_screen_geometry()
    if geom is None:
        return 10

    if geom.height() < 768:
        return 9
    elif geom.height() < 1080:
        return 10
    elif geom.height() < 1440:
        return 11
    else:
        return 12


def get_sidebar_font_size():
    """Tamaño de fuente para el sidebar."""
    base = get_font_size()
    return max(11, base + 1)


def get_css_sizes():
    """
    Devuelve un diccionario con todos los tamaños CSS calculados
    para la resolución actual. Usado por get_theme().
    """
    sf = get_scale_factor()
    sidebar_w = get_sidebar_width()
    font_base = get_font_size()

    return {
        "sidebar_width": sidebar_w,
        "font_size_base": max(12, scaled(13, sf)),
        "font_size_sidebar": max(12, scaled(13, sf)),
        "font_size_sidebar_header": max(14, scaled(16, sf)),
        "font_size_site_info": max(10, scaled(11, sf)),
        "font_size_toolbar": max(13, scaled(15, sf)),
        "font_size_section_title": max(16, scaled(18, sf)),
        "font_size_status": max(10, scaled(11, sf)),
        "font_size_btn": max(12, scaled(13, sf)),
        "font_size_input": max(12, scaled(13, sf)),
        "font_size_tab": max(11, scaled(12, sf)),
        "padding_sidebar_btn": f"{scaled(10, sf)}px {scaled(15, sf)}px",
        "padding_sidebar_header": scaled(15, sf),
        "padding_input": f"{scaled(6, sf)}px {scaled(10, sf)}px",
        "padding_btn": f"{scaled(6, sf)}px {scaled(16, sf)}px",
        "padding_header_section": f"{scaled(8, sf)}px",
        "min_height_btn": scaled(28, sf),
        "min_height_toolbar": scaled(40, sf),
        "border_radius": max(2, scaled(3, sf)),
        "scrollbar_width": max(8, scaled(10, sf)),
    }
