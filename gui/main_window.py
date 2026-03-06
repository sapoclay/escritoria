"""
Ventana principal de ESCritORIA.
Combina la barra lateral de navegación con los widgets de gestión.
"""
import os

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QStackedWidget, QStatusBar, QMessageBox, QAction, QMenu,
    QMenuBar, QFrame, QScrollArea, QApplication, QSplitter,
    QSystemTrayIcon, QDialog, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QFont, QIcon, QPixmap, QDesktopServices

from api.client import WordPressClient
from gui.styles import get_theme
from gui.connection_dialog import ConnectionDialog
from gui.posts_widget import PostsWidget
from gui.pages_widget import PagesWidget
from gui.categories_widget import CategoriesWidget
from gui.tags_widget import TagsWidget
from gui.media_widget import MediaWidget
from gui.comments_widget import CommentsWidget
from gui.users_widget import UsersWidget
from gui.settings_widget import SettingsWidget
from config.settings import load_config, save_config, APP_NAME, APP_VERSION
from utils.worker import WorkerThread
from utils.screen_utils import (
    get_min_window_size, get_window_size, get_scale_factor, scaled,
    get_dialog_size
)
from utils.offline_manager import (
    OfflineManager, OfflineStatusWidget, OfflineDraftsDialog, SyncThread
)


class ConnectionCheckThread(QThread):
    """Verifica la conexión al iniciar."""
    result = pyqtSignal(dict)

    def __init__(self, client):
        super().__init__()
        self.client = client

    def run(self):
        result = self.client.test_connection()
        if result.get("success"):
            try:
                user = self.client.get_current_user()
                result["user"] = user
            except Exception:
                pass
        self.result.emit(result)


class MainWindow(QMainWindow):
    """Ventana principal de la aplicación."""

    def __init__(self):
        super().__init__()
        self.client = None
        self.site_info = {}
        self.current_user = {}
        self._check_thread = None
        self._sidebar_buttons = []
        self._sync_threads = []

        # Offline Manager
        self.offline_manager = OfflineManager(self)
        self.offline_manager.connection_changed.connect(self._on_connection_state_changed)

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        min_size = get_min_window_size()
        self.setMinimumSize(min_size)
        win_size = get_window_size()
        self.resize(win_size)

        # Ruta del logo
        self._logo_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "img", "logo.png"
        )

        # Icono de la ventana
        if os.path.exists(self._logo_path):
            self.setWindowIcon(QIcon(self._logo_path))

        # Aplicar tema
        config = load_config()
        theme = get_theme(config.get("theme", "dark"))
        self.setStyleSheet(theme)

        self._setup_menubar()
        self._setup_ui()
        self._setup_statusbar()
        self._setup_tray()

        # Mostrar diálogo de conexión al inicio
        self._show_connection_dialog()

    def _status_message(self, msg: str):
        """Muestra un mensaje en la barra de estado de forma segura."""
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(msg)

    def _setup_menubar(self):
        """Configura la barra de menú."""
        menubar = self.menuBar()
        if menubar is None:
            return

        # Menú Archivo
        file_menu = menubar.addMenu("&Archivo")
        if file_menu is None:
            return

        action_connect = QAction("Nueva Conexión...", self)
        action_connect.setShortcut("Ctrl+N")
        action_connect.triggered.connect(self._show_connection_dialog)
        file_menu.addAction(action_connect)

        action_disconnect = QAction("Desconectar", self)
        action_disconnect.triggered.connect(self._disconnect)
        file_menu.addAction(action_disconnect)

        file_menu.addSeparator()

        action_offline_drafts = QAction("Borradores Offline...", self)
        action_offline_drafts.triggered.connect(self._show_offline_drafts)
        file_menu.addAction(action_offline_drafts)

        file_menu.addSeparator()

        action_quit = QAction("Salir", self)
        action_quit.setShortcut("Ctrl+Q")
        action_quit.triggered.connect(lambda: self.close() and None)  # type: ignore[arg-type]
        file_menu.addAction(action_quit)

        # Menú Ver
        view_menu = menubar.addMenu("&Ver")
        if view_menu is None:
            return

        action_dark = QAction("Tema Oscuro", self)
        action_dark.triggered.connect(lambda: self._change_theme("dark"))
        view_menu.addAction(action_dark)

        action_light = QAction("Tema Claro", self)
        action_light.triggered.connect(lambda: self._change_theme("light"))
        view_menu.addAction(action_light)

        view_menu.addSeparator()

        action_refresh = QAction("Actualizar", self)
        action_refresh.setShortcut("F5")
        action_refresh.triggered.connect(self._refresh_current)
        view_menu.addAction(action_refresh)

        # Menú Ayuda
        help_menu = menubar.addMenu("A&yuda")
        if help_menu is None:
            return

        action_about = QAction("Acerca de...", self)
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

    def _setup_ui(self):
        """Configura la interfaz principal."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- Barra lateral ----
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Header del sidebar
        header = QWidget()
        header.setObjectName("sidebarHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(15, 12, 15, 12)

        self.lbl_site_name = QLabel("WordPress")
        self.lbl_site_name.setObjectName("sidebarHeader")
        header_layout.addWidget(self.lbl_site_name)

        self.lbl_site_info = QLabel("Sin conexión")
        self.lbl_site_info.setObjectName("siteInfo")
        header_layout.addWidget(self.lbl_site_info)

        sidebar_layout.addWidget(header)

        # Botones de navegación
        nav_items = [
            ("Escritorio", 0),
            ("Entradas", 1),
            ("Páginas", 2),
            ("Categorías", 3),
            ("Etiquetas", 4),
            ("Medios", 5),
            ("Comentarios", 6),
            ("Usuarios", 7),
            ("Ajustes", 8),
        ]

        for text, index in nav_items:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, idx=index: self._navigate(idx))
            sidebar_layout.addWidget(btn)
            self._sidebar_buttons.append(btn)

        sidebar_layout.addStretch()

        # Botón de conexión en la parte inferior
        self.btn_connection = QPushButton("Conexión")
        self.btn_connection.clicked.connect(self._show_connection_dialog)
        sidebar_layout.addWidget(self.btn_connection)

        # Info del usuario
        self.lbl_user = QLabel("")
        self.lbl_user.setObjectName("siteInfo")
        self.lbl_user.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_user.setStyleSheet("padding: 10px; color: #72aee6;")
        sidebar_layout.addWidget(self.lbl_user)

        main_layout.addWidget(sidebar)

        # ---- Área de contenido ----
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Barra superior
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(15, 5, 15, 5)

        self.lbl_page_title = QLabel("Escritorio")
        self.lbl_page_title.setObjectName("toolbar")
        toolbar_layout.addWidget(self.lbl_page_title)
        toolbar_layout.addStretch()

        self.lbl_connection_status = QLabel("Desconectado")
        toolbar_layout.addWidget(self.lbl_connection_status)

        # Widget de estado offline
        self.offline_status = OfflineStatusWidget(self.offline_manager)
        self.offline_status.sync_requested.connect(self._sync_offline_drafts)
        toolbar_layout.addWidget(self.offline_status)

        content_layout.addWidget(toolbar)

        # Stack de widgets
        self.content_stack = QStackedWidget()

        # 0 - Dashboard
        self.dashboard = self._create_dashboard()
        self.content_stack.addWidget(self.dashboard)

        # Placeholders para los widgets (se crean al conectarse)
        self.posts_widget = None
        self.pages_widget = None
        self.categories_widget = None
        self.tags_widget = None
        self.media_widget = None
        self.comments_widget = None
        self.users_widget = None
        self.settings_widget = None

        # Añadir placeholders
        for i in range(8):
            placeholder = QLabel("Conéctate a un servidor WordPress para comenzar.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #777; font-size: 16px;")
            self.content_stack.addWidget(placeholder)

        content_layout.addWidget(self.content_stack)

        main_layout.addWidget(content_area, stretch=1)

        # Seleccionar dashboard por defecto
        self._navigate(0)

    def _create_dashboard(self):
        """Crea el widget del escritorio/dashboard."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel(f"Bienvenido a {APP_NAME}")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel("Gestiona tu sitio WordPress desde el escritorio")
        subtitle.setStyleSheet("font-size: 14px; color: #72aee6; margin-bottom: 20px;")
        layout.addWidget(subtitle)

        # Cards resumen
        cards = QHBoxLayout()
        cards.setSpacing(15)

        self.card_posts = self._create_card("", "Entradas", "—", "Posts publicados")
        cards.addWidget(self.card_posts)

        self.card_pages = self._create_card("", "Páginas", "—", "Páginas del sitio")
        cards.addWidget(self.card_pages)

        self.card_comments = self._create_card("", "Comentarios", "—", "Comentarios pendientes")
        cards.addWidget(self.card_comments)

        self.card_users = self._create_card("", "Usuarios", "—", "Usuarios registrados")
        cards.addWidget(self.card_users)

        layout.addLayout(cards)

        # Info del sitio
        self.dashboard_info = QGroupBox("Información del Sitio")
        info_layout = QVBoxLayout(self.dashboard_info)

        self.lbl_dashboard_site = QLabel("Sin conexión")
        self.lbl_dashboard_site.setStyleSheet("font-size: 14px; padding: 10px;")
        info_layout.addWidget(self.lbl_dashboard_site)

        layout.addWidget(self.dashboard_info)
        layout.addStretch()

        return widget

    def _create_card(self, icon, title, value, description):
        """Crea una tarjeta resumen para el dashboard."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #2c2c2c;
                border: 1px solid #32373c;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        layout = QVBoxLayout(card)

        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 32px;")
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #0073aa;")
        value_label.setObjectName("cardValue")
        layout.addWidget(value_label)

        desc_label = QLabel(description)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("font-size: 11px; color: #999;")
        layout.addWidget(desc_label)

        return card

    def _setup_statusbar(self):
        """Configura la barra de estado."""
        self._status_message("Listo")

    # ---- Navegación ----

    def _navigate(self, index):
        """Navega a una sección."""
        titles = [
            "Escritorio", "Entradas", "Páginas", "Categorías",
            "Etiquetas", "Medios", "Comentarios", "Usuarios", "Ajustes"
        ]
        if index < len(titles):
            self.lbl_page_title.setText(titles[index])

        # Actualizar botones
        for i, btn in enumerate(self._sidebar_buttons):
            btn.setChecked(i == index)
            btn.setProperty("active", "true"if i == index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self.content_stack.setCurrentIndex(index)

    # ---- Conexión ----

    def _show_connection_dialog(self):
        """Muestra el diálogo de conexión."""
        dialog = ConnectionDialog(self)
        if dialog.exec_():
            conn = dialog.get_connection()
            if conn:
                self._connect(conn)

    def _connect(self, connection):
        """Establece la conexión al servidor WordPress."""
        self.client = WordPressClient(
            connection["url"],
            connection["username"],
            connection["app_password"]
        )

        self.lbl_connection_status.setText("Conectando...")
        self._status_message("Conectando al servidor...")

        self._check_thread = ConnectionCheckThread(self.client)
        self._check_thread.result.connect(
            lambda result: self._on_connected(result, connection)
        )
        self._check_thread.start()

    def _on_connected(self, result, connection):
        """Maneja el resultado de la conexión."""
        if result.get("success"):
            self.site_info = result
            self.current_user = result.get("user", {})

            site_name = result.get("name", "WordPress")
            self.lbl_site_name.setText(site_name)
            self.lbl_site_info.setText(connection["url"])
            self.lbl_connection_status.setText(f"{site_name}")

            # Info del usuario
            username = self.current_user.get("username",
                        self.current_user.get("name", connection["username"]))
            self.lbl_user.setText(f"{username}")

            self._status_message(f"Conectado a {site_name}")
            self.setWindowTitle(f"{APP_NAME} — {site_name}")

            # Dashboard info
            self.lbl_dashboard_site.setText(
                f"Sitio: {site_name}\n"
                f"URL: {connection['url']}\n"
                f"Usuario: {username}\n"
                f"Zona horaria: {result.get('timezone_string', 'N/A')}"
            )

            # Crear widgets de gestión
            self._create_widgets()

            # Iniciar monitoreo offline
            self.offline_manager.set_api_client(self.client)
            self.offline_status.refresh()

            # Cargar conteos del dashboard
            self._load_dashboard_counts()
        else:
            error = result.get("error", "Error desconocido")
            self.lbl_connection_status.setText("Error de conexión")
            self._status_message(f"Error: {error}")
            QMessageBox.critical(
                self, "Error de Conexión",
                f"No se pudo conectar al servidor:\n{error}"
            )

    def _create_widgets(self):
        """Crea los widgets de gestión tras conectarse."""
        if not self.client:
            return

        # Eliminar placeholders y crear widgets reales
        # Posts (index 1)
        self.posts_widget = PostsWidget(self.client, offline_manager=self.offline_manager)
        self.content_stack.removeWidget(self.content_stack.widget(1))
        self.content_stack.insertWidget(1, self.posts_widget)

        # Pages (index 2)
        self.pages_widget = PagesWidget(self.client, offline_manager=self.offline_manager)
        self.content_stack.removeWidget(self.content_stack.widget(2))
        self.content_stack.insertWidget(2, self.pages_widget)

        # Categories (index 3)
        self.categories_widget = CategoriesWidget(self.client)
        self.content_stack.removeWidget(self.content_stack.widget(3))
        self.content_stack.insertWidget(3, self.categories_widget)

        # Tags (index 4)
        self.tags_widget = TagsWidget(self.client)
        self.content_stack.removeWidget(self.content_stack.widget(4))
        self.content_stack.insertWidget(4, self.tags_widget)

        # Media (index 5)
        self.media_widget = MediaWidget(self.client)
        self.content_stack.removeWidget(self.content_stack.widget(5))
        self.content_stack.insertWidget(5, self.media_widget)

        # Comments (index 6)
        self.comments_widget = CommentsWidget(self.client)
        self.content_stack.removeWidget(self.content_stack.widget(6))
        self.content_stack.insertWidget(6, self.comments_widget)

        # Users (index 7)
        self.users_widget = UsersWidget(self.client)
        self.content_stack.removeWidget(self.content_stack.widget(7))
        self.content_stack.insertWidget(7, self.users_widget)

        # Settings (index 8)
        self.settings_widget = SettingsWidget(self.client)
        self.content_stack.removeWidget(self.content_stack.widget(8))
        self.content_stack.insertWidget(8, self.settings_widget)

    def _load_dashboard_counts(self):
        """Carga los conteos para las tarjetas del dashboard en hilos."""
        try:
            from api.posts import PostsAPI
            from api.pages import PagesAPI
            from api.comments import CommentsAPI
            from api.users import UsersAPI

            posts_api = PostsAPI(self.client)
            pages_api = PagesAPI(self.client)
            comments_api = CommentsAPI(self.client)
            users_api = UsersAPI(self.client)

            self._dashboard_threads = []

            def _make_count_handler(card, label_name):
                def handler(result):
                    if isinstance(result, dict):
                        count = result.get("total", 0)
                        label = card.findChild(QLabel, label_name)
                        if label:
                            label.setText(str(count))
                return handler

            configs = [
                (lambda: posts_api.list(per_page=1, status="publish"), self.card_posts),
                (lambda: pages_api.list(per_page=1, status="publish"), self.card_pages),
                (lambda: comments_api.list(per_page=1, status="hold"), self.card_comments),
                (lambda: users_api.list(per_page=1), self.card_users),
            ]

            for fn, card in configs:
                t = WorkerThread(fn)
                t.finished.connect(_make_count_handler(card, "cardValue"))
                self._dashboard_threads.append(t)
                t.start()

        except Exception:
            pass

    def _disconnect(self):
        """Desconecta del servidor."""
        self.offline_manager.stop_monitoring()
        self.client = None
        self.lbl_site_name.setText("WordPress")
        self.lbl_site_info.setText("Sin conexión")
        self.lbl_connection_status.setText("Desconectado")
        self.lbl_user.setText("")
        self.lbl_dashboard_site.setText("Sin conexión")
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self._status_message("Desconectado")

        # Limpiar tarjetas
        for card in [self.card_posts, self.card_pages, self.card_comments, self.card_users]:
            label = card.findChild(QLabel, "cardValue")
            if label:
                label.setText("—")

    def _change_theme(self, theme_name):
        """Cambia el tema de la aplicación."""
        theme = get_theme(theme_name)
        self.setStyleSheet(theme)

        config = load_config()
        config["theme"] = theme_name
        save_config(config)

        self._status_message(f"Tema cambiado a: {theme_name}")

    def _on_connection_state_changed(self, is_online):
        """Maneja cambios en el estado de la conexión (online/offline)."""
        if is_online:
            self._status_message("Conexión restablecida")
            # Auto-sincronizar si hay borradores pendientes
            if self.offline_manager.pending_count > 0:
                self._status_message(
                    f"Conexión restablecida. "
                    f"{self.offline_manager.pending_count} borrador(es) pendiente(s)."
                )
        else:
            self._status_message("Sin conexión — Modo offline activo")

    def _show_offline_drafts(self):
        """Muestra el diálogo de borradores offline."""
        dlg = OfflineDraftsDialog(self.offline_manager, self)
        if dlg.exec_():
            # Si se pidió sincronizar
            self._sync_offline_drafts()

    def _sync_offline_drafts(self):
        """Sincroniza todos los borradores offline."""
        if not self.offline_manager.is_online:
            QMessageBox.warning(
                self, "Sin Conexión",
                "No se puede sincronizar sin conexión al servidor."
            )
            return

        if self.offline_manager.pending_count == 0:
            self._status_message("No hay borradores pendientes")
            return

        self._status_message("Sincronizando borradores offline...")

        # Obtener APIs para la sincronización
        posts_api = None
        pages_api = None
        if self.posts_widget:
            posts_api = self.posts_widget.posts_api
        if self.pages_widget:
            pages_api = self.pages_widget.pages_api

        thread = SyncThread(self.offline_manager, posts_api, pages_api)
        thread.finished.connect(self._on_sync_finished)
        thread.error.connect(self._on_sync_error)
        self._sync_threads.append(thread)
        thread.start()

    def _on_sync_finished(self, success, errors):
        """Maneja el resultado de la sincronización."""
        self.offline_status.refresh()
        if errors == 0:
            self._status_message(
                f"Sincronización completada: {success} borrador(es) sincronizado(s)"
            )
            QMessageBox.information(
                self, "Sincronización",
                f"Se sincronizaron {success} borrador(es) correctamente."
            )
        else:
            self._status_message(
                f"Sincronización: {success} exitoso(s), {errors} error(es)"
            )
            QMessageBox.warning(
                self, "Sincronización parcial",
                f"Se sincronizaron {success} borrador(es).\n"
                f"{errors} borrador(es) tuvieron errores."
            )

    def _on_sync_error(self, error):
        """Maneja errores de sincronización."""
        self._status_message(f"Error de sincronización: {error}")
        QMessageBox.critical(
            self, "Error de Sincronización",
            f"Error al sincronizar borradores:\n{error}"
        )

    def _refresh_current(self):
        """Actualiza el widget actual."""
        idx = self.content_stack.currentIndex()
        widget = self.content_stack.widget(idx)
        if widget is None:
            return
        for method_name in ('load_posts', 'load_pages', 'load_categories',
                            'load_tags', 'load_media', 'load_comments',
                            'load_users', 'load_settings'):
            method = getattr(widget, method_name, None)
            if callable(method):
                method()
                return
        if idx == 0 and self.client:
            self._load_dashboard_counts()

    def _show_about(self):
        """Muestra el diálogo Acerca de con logo."""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Acerca de {APP_NAME}")
        about_size = get_dialog_size(0.30, 0.60)
        dlg.setMinimumSize(about_size)
        dlg.resize(about_size)
        layout = QVBoxLayout(dlg)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Logo
        if os.path.exists(self._logo_path):
            lbl_logo = QLabel()
            pixmap = QPixmap(self._logo_path).scaled(
                128, 128, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            lbl_logo.setPixmap(pixmap)
            lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl_logo)

        # Área de scroll para la información
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        lbl_info = QLabel(
            f"<p>Version {APP_VERSION}</p>"
            f"<p>Cliente de escritorio para gestionar sitios WordPress "
            f"de forma remota a traves de la API REST.</p>"
            f"<p><b>Caracteristicas:</b></p>"
            f"<ul>"
            f"<li>Gestion de Entradas y Paginas</li>"
            f"<li>Editor visual y HTML</li>"
            f"<li>Corrector ortografico integrado</li>"
            f"<li>Contador de palabras en tiempo real</li>"
            f"<li>Modo offline con sincronizacion</li>"
            f"<li>Categorias y Etiquetas</li>"
            f"<li>Biblioteca de Medios</li>"
            f"<li>Moderacion de Comentarios</li>"
            f"<li>Gestion de Usuarios</li>"
            f"<li>Ajustes del Sitio</li>"
            f"<li>Integracion Yoast SEO</li>"
            f"</ul>"
            f"<p>Desarrollado con Python y PyQt5.</p>"
        )
        lbl_info.setWordWrap(True)
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_layout.addWidget(lbl_info)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        # Botón para abrir el repositorio en GitHub
        btn_github = QPushButton("  Abrir en GitHub")
        btn_github.setIcon(self.style().standardIcon(
            self.style().StandardPixmap.SP_DriveNetIcon
        ))
        btn_github.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_github.setStyleSheet(
            "QPushButton { background-color: #24292e; color: white; "
            "border: none; border-radius: 4px; padding: 8px 16px; "
            "font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #3a3f44; }"
        )
        btn_github.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/sapoclay/escritoria"))
        )
        layout.addWidget(btn_github, alignment=Qt.AlignmentFlag.AlignCenter)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)

        dlg.exec_()

    # ---- Bandeja del sistema ----

    def _setup_tray(self):
        """Configura el icono de la bandeja del sistema."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(self._logo_path):
            self.tray_icon.setIcon(QIcon(self._logo_path))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(
                self.style().StandardPixmap.SP_ComputerIcon
            ))
        self.tray_icon.setToolTip(f"{APP_NAME} v{APP_VERSION}")

        tray_menu = QMenu(self)

        action_show = tray_menu.addAction("Mostrar ventana")
        action_show.triggered.connect(self._tray_show_window)

        tray_menu.addSeparator()

        # Secciones de navegacion
        nav_names = [
            "Escritorio", "Entradas", "Paginas", "Categorias",
            "Etiquetas", "Medios", "Comentarios", "Usuarios", "Ajustes",
        ]
        for i, name in enumerate(nav_names):
            act = tray_menu.addAction(name)
            act.triggered.connect(lambda checked, idx=i: self._tray_navigate(idx))

        tray_menu.addSeparator()

        action_connect = tray_menu.addAction("Nueva Conexion...")
        action_connect.triggered.connect(self._show_connection_dialog)

        action_about = tray_menu.addAction("Acerca de...")
        action_about.triggered.connect(self._show_about)

        tray_menu.addSeparator()

        action_quit = tray_menu.addAction("Salir")
        action_quit.triggered.connect(self._tray_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _tray_activated(self, reason):
        """Doble clic en el icono de la bandeja muestra la ventana."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_show_window()

    def _tray_show_window(self):
        """Muestra y activa la ventana principal."""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _tray_navigate(self, index):
        """Navega a una seccion desde la bandeja."""
        self._tray_show_window()
        self._navigate(index)

    def _tray_quit(self):
        """Cierra la aplicacion completamente."""
        self._force_quit = True
        self.close()

    def closeEvent(self, a0):
        """Minimiza a la bandeja o cierra la aplicacion."""
        config = load_config()
        config["window_geometry"] = {
            "x": self.x(), "y": self.y(),
            "width": self.width(), "height": self.height()
        }
        save_config(config)

        # Si existe bandeja y no se pidio salir, minimizar
        if (
            hasattr(self, "tray_icon")
            and self.tray_icon.isVisible()
            and not getattr(self, "_force_quit", False)
        ):
            if a0:
                a0.ignore()
            self.hide()
            self.tray_icon.showMessage(
                APP_NAME,
                "La aplicacion sigue en la bandeja del sistema.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            return

        # Limpiar bandeja al salir
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()
        if a0:
            a0.accept()


# Necesario importar QGroupBox
from PyQt5.QtWidgets import QGroupBox
