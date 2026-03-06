"""
Widget de Ajustes del sitio WordPress.
Configuración general, lectura, escritura y discusión.
Todas las operaciones de red se ejecutan en hilos secundarios.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QLabel, QMessageBox, QGroupBox, QComboBox,
    QSpinBox, QCheckBox, QTabWidget, QTextEdit, QScrollArea
)
from PyQt5.QtCore import Qt
from utils.worker import WorkerThread


class SettingsWidget(QWidget):
    """Widget para gestionar los ajustes del sitio."""

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        from api.settings_api import SettingsAPI
        self.settings_api = SettingsAPI(api_client)
        self.settings_data = {}
        self._threads = []
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        header = QHBoxLayout()
        title = QLabel("Ajustes del Sitio")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()

        self.btn_save = QPushButton("Guardar Cambios")
        self.btn_save.setObjectName("btnSuccess")
        self.btn_save.clicked.connect(self._save_settings)
        header.addWidget(self.btn_save)

        btn_refresh = QPushButton("Recargar")
        btn_refresh.clicked.connect(self.load_settings)
        header.addWidget(btn_refresh)
        main_layout.addLayout(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # Generales
        general_group = QGroupBox("General")
        gen_layout = QFormLayout(general_group)

        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("Título del sitio")
        gen_layout.addRow("Título del sitio:", self.txt_title)

        self.txt_description = QLineEdit()
        self.txt_description.setPlaceholderText("Descripción corta")
        gen_layout.addRow("Descripción:", self.txt_description)

        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("https://misitio.com")
        gen_layout.addRow("Dirección de WordPress (URL):", self.txt_url)

        self.txt_site_url = QLineEdit()
        self.txt_site_url.setPlaceholderText("https://misitio.com")
        gen_layout.addRow("Dirección del sitio (URL):", self.txt_site_url)

        self.txt_email = QLineEdit()
        self.txt_email.setPlaceholderText("admin@misitio.com")
        gen_layout.addRow("Dirección de correo:", self.txt_email)

        self.combo_timezone = QLineEdit()
        self.combo_timezone.setPlaceholderText("Europe/Madrid")
        gen_layout.addRow("Zona horaria:", self.combo_timezone)

        self.combo_date_format = QComboBox()
        self.combo_date_format.addItems([
            "j \\d\\e F \\d\\e Y", "Y-m-d", "m/d/Y", "d/m/Y", "F j, Y"
        ])
        self.combo_date_format.setEditable(True)
        gen_layout.addRow("Formato de fecha:", self.combo_date_format)

        self.combo_time_format = QComboBox()
        self.combo_time_format.addItems(["H:i", "g:i a", "g:i A"])
        self.combo_time_format.setEditable(True)
        gen_layout.addRow("Formato de hora:", self.combo_time_format)

        self.combo_start_of_week = QComboBox()
        self.combo_start_of_week.addItems([
            "Domingo", "Lunes", "Martes", "Miércoles",
            "Jueves", "Viernes", "Sábado"
        ])
        gen_layout.addRow("La semana comienza:", self.combo_start_of_week)

        self.combo_language = QLineEdit()
        self.combo_language.setPlaceholderText("es_ES")
        gen_layout.addRow("Idioma del sitio:", self.combo_language)

        scroll_layout.addWidget(general_group)

        # Escritura
        writing_group = QGroupBox("Escritura")
        write_layout = QFormLayout(writing_group)

        self.combo_default_category = QComboBox()
        self.combo_default_category.addItem("Sin categoría", 1)
        write_layout.addRow("Categoría predeterminada:", self.combo_default_category)

        self.combo_default_format = QComboBox()
        self.combo_default_format.addItems([
            "Estándar", "Cita", "Estado", "Chat", "Galería",
            "Enlace", "Imagen", "Vídeo", "Audio"
        ])
        write_layout.addRow("Formato de entrada:", self.combo_default_format)

        scroll_layout.addWidget(writing_group)

        # Lectura
        reading_group = QGroupBox("Lectura")
        read_layout = QFormLayout(reading_group)

        self.combo_show_on_front = QComboBox()
        self.combo_show_on_front.addItems(["Últimas entradas", "Página estática"])
        read_layout.addRow("Portada muestra:", self.combo_show_on_front)

        self.spin_posts_per_page = QSpinBox()
        self.spin_posts_per_page.setRange(1, 100)
        self.spin_posts_per_page.setValue(10)
        read_layout.addRow("Nº de entradas por página:", self.spin_posts_per_page)

        self.spin_posts_per_rss = QSpinBox()
        self.spin_posts_per_rss.setRange(1, 100)
        self.spin_posts_per_rss.setValue(10)
        read_layout.addRow("Nº de entradas en RSS:", self.spin_posts_per_rss)

        scroll_layout.addWidget(reading_group)

        # Comentarios
        comments_group = QGroupBox("Comentarios")
        comm_layout = QVBoxLayout(comments_group)

        self.chk_default_comment = QCheckBox(
            "Permitir que se publiquen comentarios en las nuevas entradas"
        )
        self.chk_default_comment.setChecked(True)
        comm_layout.addWidget(self.chk_default_comment)

        self.chk_default_pingback = QCheckBox(
            "Intentar notificar a los sitios web enlazados (pings)"
        )
        comm_layout.addWidget(self.chk_default_pingback)

        self.chk_require_name_email = QCheckBox(
            "El autor debe indicar nombre y email para comentar"
        )
        comm_layout.addWidget(self.chk_require_name_email)

        self.chk_comment_registration = QCheckBox(
            "Los usuarios deben estar registrados para comentar"
        )
        comm_layout.addWidget(self.chk_comment_registration)

        scroll_layout.addWidget(comments_group)

        # Información del Sitio
        info_group = QGroupBox("Información del Sistema")
        info_layout = QFormLayout(info_group)

        self.lbl_wp_version = QLabel("")
        info_layout.addRow("WordPress:", self.lbl_wp_version)

        self.lbl_php_version = QLabel("")
        info_layout.addRow("PHP:", self.lbl_php_version)

        self.lbl_theme = QLabel("")
        info_layout.addRow("Tema activo:", self.lbl_theme)

        scroll_layout.addWidget(info_group)
        scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        main_layout.addWidget(self.status_label)

    def load_settings(self):
        self.status_label.setText("Cargando ajustes...")
        # Cargar ajustes en hilo
        t = WorkerThread(lambda: self.settings_api.get())
        t.finished.connect(self._on_settings_loaded)
        t.error.connect(lambda e: self._on_load_error(e))
        self._threads.append(t)
        t.start()

    def _on_settings_loaded(self, settings_data):
        self.settings_data = settings_data
        self._populate_form()
        self.status_label.setText("Ajustes cargados")
        # Cargar info del sitio en paralelo
        t1 = WorkerThread(lambda: self.settings_api.get_site_info())
        t1.finished.connect(self._on_site_info_loaded)
        t1.error.connect(lambda _e: None)
        self._threads.append(t1)
        t1.start()

        t2 = WorkerThread(lambda: self.settings_api.get_themes())
        t2.finished.connect(self._on_themes_loaded)
        t2.error.connect(lambda _e: self.lbl_theme.setText("No disponible"))
        self._threads.append(t2)
        t2.start()

    def _on_site_info_loaded(self, site_info):
        self.lbl_wp_version.setText(site_info.get("description", "WordPress"))

    def _on_themes_loaded(self, themes):
        active_themes = [t for t in themes if t.get("status") == "active"]
        if active_themes:
            theme_name = active_themes[0].get("name", {})
            if isinstance(theme_name, dict):
                theme_name = theme_name.get("rendered", theme_name.get("raw", ""))
            self.lbl_theme.setText(str(theme_name))
        else:
            self.lbl_theme.setText("No disponible")

    def _on_load_error(self, error):
        self.status_label.setText(f"Error: {error}")
        QMessageBox.warning(self, "Error", f"Error al cargar ajustes:\n{error}")

    def _populate_form(self):
        s = self.settings_data
        self.txt_title.setText(s.get("title", ""))
        self.txt_description.setText(s.get("description", ""))
        self.txt_url.setText(s.get("url", ""))
        self.txt_site_url.setText(s.get("url", ""))
        self.txt_email.setText(s.get("email", ""))
        self.combo_timezone.setText(s.get("timezone_string", ""))

        date_format = s.get("date_format", "")
        idx = self.combo_date_format.findText(date_format)
        if idx >= 0:
            self.combo_date_format.setCurrentIndex(idx)
        else:
            self.combo_date_format.setEditText(date_format)

        time_format = s.get("time_format", "")
        idx = self.combo_time_format.findText(time_format)
        if idx >= 0:
            self.combo_time_format.setCurrentIndex(idx)
        else:
            self.combo_time_format.setEditText(time_format)

        self.combo_start_of_week.setCurrentIndex(s.get("start_of_week", 1))
        self.combo_language.setText(s.get("language", ""))
        self.spin_posts_per_page.setValue(s.get("posts_per_page", 10))
        self.spin_posts_per_rss.setValue(s.get("posts_per_rss", 10))
        show_on_front = s.get("show_on_front", "posts")
        self.combo_show_on_front.setCurrentIndex(0 if show_on_front == "posts" else 1)
        self.chk_default_comment.setChecked(
            s.get("default_comment_status", "open") == "open"
        )
        self.chk_default_pingback.setChecked(
            s.get("default_ping_status", "open") == "open"
        )

    def _save_settings(self):
        self.status_label.setText("Guardando ajustes...")
        self.btn_save.setEnabled(False)
        data = {
            "title": self.txt_title.text(),
            "description": self.txt_description.text(),
            "email": self.txt_email.text(),
            "timezone_string": self.combo_timezone.text(),
            "date_format": self.combo_date_format.currentText(),
            "time_format": self.combo_time_format.currentText(),
            "start_of_week": self.combo_start_of_week.currentIndex(),
            "language": self.combo_language.text(),
            "posts_per_page": self.spin_posts_per_page.value(),
            "posts_per_rss": self.spin_posts_per_rss.value(),
            "default_comment_status": "open" if self.chk_default_comment.isChecked() else "closed",
            "default_ping_status": "open" if self.chk_default_pingback.isChecked() else "closed",
        }

        t = WorkerThread(lambda: self.settings_api.update(**data))
        t.finished.connect(lambda _r: self._on_settings_saved())
        t.error.connect(lambda e: self._on_save_error(e))
        self._threads.append(t)
        t.start()

    def _on_settings_saved(self):
        self.btn_save.setEnabled(True)
        self.status_label.setText("Ajustes guardados")
        QMessageBox.information(self, "Éxito", "Ajustes guardados correctamente.")

    def _on_save_error(self, error):
        self.btn_save.setEnabled(True)
        self.status_label.setText(f"Error: {error}")
        QMessageBox.critical(self, "Error", f"Error al guardar ajustes:\n{error}")

    def showEvent(self, a0):
        super().showEvent(a0)
        self.load_settings()
