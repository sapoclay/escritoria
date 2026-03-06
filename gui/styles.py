"""
Estilos CSS para la aplicación ESCritORIA.
Tema oscuro inspirado en el panel de administración de WordPress.
Los tamaños se adaptan dinámicamente a la resolución de pantalla.
"""


def _get_sizes():
    """Obtiene los tamaños adaptados a la pantalla actual."""
    try:
        from utils.screen_utils import get_css_sizes
        return get_css_sizes()
    except Exception:
        # Valores por defecto si no se puede calcular
        return {
            "sidebar_width": 220,
            "font_size_base": 13,
            "font_size_sidebar": 13,
            "font_size_sidebar_header": 16,
            "font_size_site_info": 11,
            "font_size_toolbar": 15,
            "font_size_section_title": 18,
            "font_size_status": 11,
            "font_size_btn": 13,
            "font_size_input": 13,
            "font_size_tab": 12,
            "padding_sidebar_btn": "10px 15px",
            "padding_sidebar_header": 15,
            "padding_input": "6px 10px",
            "padding_btn": "6px 16px",
            "padding_header_section": "8px",
            "min_height_btn": 28,
            "min_height_toolbar": 40,
            "border_radius": 3,
            "scrollbar_width": 10,
        }


def _build_dark_theme(s):
    """Genera el tema oscuro con tamaños adaptados."""
    return f"""
/* ====== TEMA PRINCIPAL ====== */
QMainWindow {{
    background-color: #1e1e1e;
    color: #e0e0e0;
}}

QWidget {{
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: {s['font_size_base']}px;
}}

/* ====== BARRA LATERAL ====== */
#sidebar {{
    background-color: #23282d;
    min-width: {s['sidebar_width']}px;
    max-width: {s['sidebar_width']}px;
    border-right: 1px solid #32373c;
}}

#sidebar QPushButton {{
    background-color: transparent;
    color: #b4b9be;
    border: none;
    text-align: left;
    padding: {s['padding_sidebar_btn']};
    font-size: {s['font_size_sidebar']}px;
    border-left: 3px solid transparent;
}}

#sidebar QPushButton:hover {{
    background-color: #32373c;
    color: #00b9eb;
    border-left: 3px solid #00b9eb;
}}

#sidebar QPushButton:checked,
#sidebar QPushButton[active="true"] {{
    background-color: #0073aa;
    color: white;
    border-left: 3px solid #00b9eb;
}}

#sidebarHeader {{
    background-color: #1d2327;
    padding: {s['padding_sidebar_header']}px;
    border-bottom: 1px solid #32373c;
}}

#sidebarHeader QLabel {{
    color: #00b9eb;
    font-size: {s['font_size_sidebar_header']}px;
    font-weight: bold;
    background: transparent;
}}

#siteInfo {{
    color: #72aee6;
    font-size: {s['font_size_site_info']}px;
    background: transparent;
}}

/* ====== BARRA SUPERIOR ====== */
#toolbar {{
    background-color: #32373c;
    border-bottom: 1px solid #464b50;
    padding: 5px 15px;
    min-height: {s['min_height_toolbar']}px;
}}

#toolbar QLabel {{
    color: #e0e0e0;
    font-size: {s['font_size_toolbar']}px;
    font-weight: bold;
    background: transparent;
}}

/* ====== BOTONES ====== */
QPushButton {{
    background-color: #0073aa;
    color: white;
    border: 1px solid #006799;
    border-radius: {s['border_radius']}px;
    padding: {s['padding_btn']};
    font-size: {s['font_size_btn']}px;
    min-height: {s['min_height_btn']}px;
}}

QPushButton:hover {{
    background-color: #006799;
    border-color: #005177;
}}

QPushButton:pressed {{
    background-color: #005177;
}}

QPushButton:disabled {{
    background-color: #3c3c3c;
    color: #777;
    border-color: #555;
}}

QPushButton#btnDanger {{
    background-color: #dc3545;
    border-color: #bd2130;
}}

QPushButton#btnDanger:hover {{
    background-color: #bd2130;
}}

QPushButton#btnSecondary {{
    background-color: #555;
    border-color: #444;
}}

QPushButton#btnSecondary:hover {{
    background-color: #666;
}}

QPushButton#btnSuccess {{
    background-color: #28a745;
    border-color: #218838;
}}

QPushButton#btnSuccess:hover {{
    background-color: #218838;
}}

/* ====== INPUTS ====== */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background-color: #2c2c2c;
    color: #e0e0e0;
    border: 1px solid #464b50;
    border-radius: {s['border_radius']}px;
    padding: {s['padding_input']};
    font-size: {s['font_size_input']}px;
    selection-background-color: #0073aa;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: #0073aa;
    outline: none;
}}

QComboBox {{
    padding-right: 25px;
}}

QComboBox::drop-down {{
    border: none;
    width: 25px;
}}

QComboBox::down-arrow {{
    width: 12px;
    height: 12px;
}}

QComboBox QAbstractItemView {{
    background-color: #2c2c2c;
    color: #e0e0e0;
    border: 1px solid #464b50;
    selection-background-color: #0073aa;
}}

/* ====== TABLAS ====== */
QTableWidget, QTableView {{
    background-color: #1e1e1e;
    color: #e0e0e0;
    gridline-color: #32373c;
    border: 1px solid #32373c;
    selection-background-color: #0073aa;
    alternate-background-color: #232323;
}}

QTableWidget::item, QTableView::item {{
    padding: {s['padding_header_section']};
    border-bottom: 1px solid #32373c;
}}

QTableWidget::item:selected, QTableView::item:selected {{
    background-color: #0073aa;
    color: white;
}}

QHeaderView::section {{
    background-color: #32373c;
    color: #e0e0e0;
    padding: {s['padding_header_section']};
    border: none;
    border-bottom: 2px solid #0073aa;
    font-weight: bold;
    font-size: {s['font_size_tab']}px;
}}

/* ====== TABS ====== */
QTabWidget::pane {{
    border: 1px solid #32373c;
    background-color: #1e1e1e;
}}

QTabBar::tab {{
    background-color: #32373c;
    color: #b4b9be;
    padding: {s['padding_header_section']} 20px;
    border: 1px solid #464b50;
    border-bottom: none;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: #1e1e1e;
    color: #0073aa;
    border-bottom: 2px solid #0073aa;
}}

QTabBar::tab:hover {{
    color: #00b9eb;
}}

/* ====== SCROLLBARS ====== */
QScrollBar:vertical {{
    background-color: #1e1e1e;
    width: {s['scrollbar_width']}px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: #464b50;
    min-height: 30px;
    border-radius: {s['scrollbar_width'] // 2}px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #5a5f64;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background-color: #1e1e1e;
    height: {s['scrollbar_width']}px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background-color: #464b50;
    min-width: 30px;
    border-radius: {s['scrollbar_width'] // 2}px;
}}

/* ====== LABELS ====== */
QLabel {{
    color: #e0e0e0;
    background: transparent;
}}

QLabel#sectionTitle {{
    font-size: {s['font_size_section_title']}px;
    font-weight: bold;
    color: #e0e0e0;
    padding: 10px 0;
}}

QLabel#statusLabel {{
    color: #72aee6;
    font-size: {s['font_size_status']}px;
}}

/* ====== GROUP BOX ====== */
QGroupBox {{
    border: 1px solid #32373c;
    border-radius: 5px;
    margin-top: 10px;
    padding-top: 15px;
    font-weight: bold;
    color: #e0e0e0;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}}

/* ====== CHECKBOXES / RADIO ====== */
QCheckBox, QRadioButton {{
    color: #e0e0e0;
    spacing: 8px;
    background: transparent;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #464b50;
    background-color: #2c2c2c;
}}

QCheckBox::indicator:checked {{
    background-color: #0073aa;
    border-color: #0073aa;
}}

QRadioButton::indicator {{
    border-radius: 8px;
}}

QRadioButton::indicator:checked {{
    background-color: #0073aa;
    border-color: #0073aa;
}}

/* ====== PROGRESS BAR ====== */
QProgressBar {{
    border: 1px solid #464b50;
    border-radius: {s['border_radius']}px;
    text-align: center;
    background-color: #2c2c2c;
    color: white;
    height: 20px;
}}

QProgressBar::chunk {{
    background-color: #0073aa;
    border-radius: 2px;
}}

/* ====== MENÚ ====== */
QMenuBar {{
    background-color: #23282d;
    color: #e0e0e0;
    border-bottom: 1px solid #32373c;
}}

QMenuBar::item:selected {{
    background-color: #0073aa;
}}

QMenu {{
    background-color: #2c2c2c;
    color: #e0e0e0;
    border: 1px solid #464b50;
}}

QMenu::item:selected {{
    background-color: #0073aa;
}}

QMenu::separator {{
    height: 1px;
    background-color: #464b50;
    margin: 5px 10px;
}}

/* ====== DIÁLOGOS ====== */
QDialog {{
    background-color: #1e1e1e;
}}

/* ====== STATUS BAR ====== */
QStatusBar {{
    background-color: #23282d;
    color: #b4b9be;
    border-top: 1px solid #32373c;
    font-size: {s['font_size_status']}px;
}}

/* ====== SPLITTER ====== */
QSplitter::handle {{
    background-color: #32373c;
}}

QSplitter::handle:horizontal {{
    width: 2px;
}}

QSplitter::handle:vertical {{
    height: 2px;
}}

/* ====== TREE VIEW ====== */
QTreeWidget, QTreeView {{
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #32373c;
    alternate-background-color: #232323;
}}

QTreeWidget::item:selected, QTreeView::item:selected {{
    background-color: #0073aa;
}}

/* ====== LIST VIEW ====== */
QListWidget, QListView {{
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #32373c;
    alternate-background-color: #232323;
}}

QListWidget::item:selected, QListView::item:selected {{
    background-color: #0073aa;
}}

QListWidget::item {{
    padding: 5px;
}}

/* ====== TOOLTIP ====== */
QToolTip {{
    background-color: #32373c;
    color: #e0e0e0;
    border: 1px solid #464b50;
    padding: 4px 8px;
}}

/* ====== MESSAGE BOX ====== */
QMessageBox {{
    background-color: #1e1e1e;
}}

QMessageBox QLabel {{
    color: #e0e0e0;
}}
"""


def _build_light_theme(s):
    """Genera el tema claro con tamaños adaptados."""
    return f"""
QMainWindow {{
    background-color: #f1f1f1;
    color: #23282d;
}}

QWidget {{
    background-color: #f1f1f1;
    color: #23282d;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: {s['font_size_base']}px;
}}

#sidebar {{
    background-color: #23282d;
    min-width: {s['sidebar_width']}px;
    max-width: {s['sidebar_width']}px;
    border-right: 1px solid #32373c;
}}

#sidebar QPushButton {{
    background-color: transparent;
    color: #b4b9be;
    border: none;
    text-align: left;
    padding: {s['padding_sidebar_btn']};
    font-size: {s['font_size_sidebar']}px;
    border-left: 3px solid transparent;
}}

#sidebar QPushButton:hover {{
    background-color: #32373c;
    color: #00b9eb;
    border-left: 3px solid #00b9eb;
}}

#sidebar QPushButton:checked,
#sidebar QPushButton[active="true"] {{
    background-color: #0073aa;
    color: white;
    border-left: 3px solid #00b9eb;
}}

#sidebarHeader {{
    background-color: #1d2327;
    padding: {s['padding_sidebar_header']}px;
    border-bottom: 1px solid #32373c;
}}

#sidebarHeader QLabel {{
    color: #00b9eb;
    font-size: {s['font_size_sidebar_header']}px;
    font-weight: bold;
    background: transparent;
}}

#siteInfo {{
    color: #72aee6;
    font-size: {s['font_size_site_info']}px;
    background: transparent;
}}

QPushButton {{
    background-color: #0073aa;
    color: white;
    border: 1px solid #006799;
    border-radius: {s['border_radius']}px;
    padding: {s['padding_btn']};
    font-size: {s['font_size_btn']}px;
    min-height: {s['min_height_btn']}px;
}}

QPushButton:hover {{
    background-color: #006799;
}}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background-color: #ffffff;
    color: #23282d;
    border: 1px solid #7e8993;
    border-radius: {s['border_radius']}px;
    padding: {s['padding_input']};
    font-size: {s['font_size_input']}px;
}}

QLineEdit:focus, QTextEdit:focus {{
    border: 2px solid #0073aa;
}}

QTableWidget, QTableView {{
    background-color: #ffffff;
    color: #23282d;
    gridline-color: #e2e4e7;
    border: 1px solid #e2e4e7;
    selection-background-color: #0073aa;
    alternate-background-color: #f9f9f9;
}}

QHeaderView::section {{
    background-color: #f1f1f1;
    color: #23282d;
    padding: {s['padding_header_section']};
    border: none;
    border-bottom: 2px solid #0073aa;
    font-weight: bold;
}}

QLabel {{
    color: #23282d;
    background: transparent;
}}

QLabel#sectionTitle {{
    font-size: {s['font_size_section_title']}px;
    font-weight: bold;
    padding: 10px 0;
}}

#toolbar {{
    background-color: #ffffff;
    border-bottom: 1px solid #e2e4e7;
    padding: 5px 15px;
    min-height: {s['min_height_toolbar']}px;
}}

#toolbar QLabel {{
    color: #23282d;
    font-size: {s['font_size_toolbar']}px;
    font-weight: bold;
    background: transparent;
}}
"""


def get_theme(name="dark"):
    """Devuelve el tema CSS solicitado, adaptado a la pantalla actual."""
    s = _get_sizes()
    if name == "light":
        return _build_light_theme(s)
    return _build_dark_theme(s)
