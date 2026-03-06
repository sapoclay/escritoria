#!/usr/bin/env python3
"""
ESCritORIA - Punto de entrada principal.
Cliente de escritorio para gestionar sitios WordPress.
"""
import sys
import os

# Añadir directorio del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from gui.main_window import MainWindow
from config.settings import load_config, APP_NAME
from utils.screen_utils import get_font_size, get_window_size


def main():
    """Función principal de la aplicación."""
    # Habilitar High DPI
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("ESCritORIA")

    # Fuente global adaptada a la pantalla
    font_size = get_font_size()
    font = QFont("Segoe UI", font_size)
    if not font.exactMatch():
        font = QFont("Ubuntu", font_size)
        if not font.exactMatch():
            font = QFont("Sans Serif", font_size)
    app.setFont(font)

    # Crear y mostrar ventana principal
    window = MainWindow()

    # Restaurar geometría o usar tamaño proporcional a la pantalla
    config = load_config()
    geom = config.get("window_geometry")
    if geom:
        window.setGeometry(
            geom.get("x", 100), geom.get("y", 100),
            geom.get("width", 1400), geom.get("height", 800)
        )
    else:
        # Tamaño proporcional a la pantalla disponible
        size = get_window_size()
        window.resize(size)

    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
