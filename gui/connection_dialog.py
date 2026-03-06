"""
Diálogo de conexión al servidor WordPress.
Permite configurar, probar y gestionar conexiones a servidores WordPress.
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QGroupBox, QWidget, QStackedWidget, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon

from api.client import WordPressClient
from config.settings import (
    load_connections, save_connections, add_connection,
    remove_connection, load_config, save_config
)
from utils.screen_utils import get_dialog_size, get_scale_factor, scaled


class ConnectionTestThread(QThread):
    """Hilo para probar la conexión sin bloquear la UI."""
    result = pyqtSignal(dict)

    def __init__(self, url, username, password):
        super().__init__()
        self.url = url
        self.username = username
        self.password = password

    def run(self):
        client = WordPressClient(self.url, self.username, self.password)
        result = client.test_connection()
        self.result.emit(result)


class ConnectionDialog(QDialog):
    """Diálogo para gestionar las conexiones a servidores WordPress."""

    connection_selected = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conexión al Servidor WordPress")
        dlg_size = get_dialog_size(0.42, 0.55)
        self.setMinimumSize(dlg_size)
        self.resize(dlg_size)
        self.selected_connection = None
        self._test_thread = None
        self._setup_ui()
        self._load_saved_connections()

    def _setup_ui(self):
        """Configura la interfaz del diálogo."""
        layout = QHBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Panel izquierdo: Lista de conexiones
        left_panel = QWidget()
        sf = get_scale_factor()
        left_w = scaled(250, sf)
        left_panel.setMaximumWidth(left_w)
        left_panel.setMinimumWidth(max(180, scaled(200, sf)))
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)

        lbl_title = QLabel("Conexiones Guardadas")
        lbl_title.setObjectName("sectionTitle")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        lbl_title.setFont(font)
        left_layout.addWidget(lbl_title)

        self.connections_list = QListWidget()
        self.connections_list.currentRowChanged.connect(self._on_connection_selected)
        left_layout.addWidget(self.connections_list)

        btn_layout = QHBoxLayout()
        self.btn_new = QPushButton("+ Nueva")
        self.btn_new.clicked.connect(self._new_connection)
        btn_layout.addWidget(self.btn_new)

        self.btn_remove = QPushButton("Eliminar")
        self.btn_remove.setObjectName("btnDanger")
        self.btn_remove.clicked.connect(self._remove_connection)
        btn_layout.addWidget(self.btn_remove)
        left_layout.addLayout(btn_layout)

        layout.addWidget(left_panel)

        # Separador
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Panel derecho: Formulario de conexión
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 15, 20, 15)

        lbl_form_title = QLabel("Configuración de Conexión")
        lbl_form_title.setObjectName("sectionTitle")
        lbl_form_title.setFont(font)
        right_layout.addWidget(lbl_form_title)

        # Formulario
        form_group = QGroupBox("Datos del Servidor")
        form_layout = QFormLayout(form_group)
        form_layout.setSpacing(10)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Mi sitio WordPress")
        form_layout.addRow("Nombre:", self.txt_name)

        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("https://misitio.com")
        form_layout.addRow("URL del sitio:", self.txt_url)

        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("admin")
        form_layout.addRow("Usuario:", self.txt_username)

        self.txt_password = QLineEdit()
        self.txt_password.setPlaceholderText("xxxx xxxx xxxx xxxx xxxx xxxx")
        self.txt_password.setEchoMode(QLineEdit.Password)
        form_layout.addRow("Contraseña de\nAplicación:", self.txt_password)

        right_layout.addWidget(form_group)

        # Info
        info_label = QLabel(
            "(i) Para obtener la contraseña de aplicación:\n"
            "WordPress Admin → Usuarios → Perfil → Contraseñas de Aplicación"
        )
        info_label.setObjectName("statusLabel")
        info_label.setWordWrap(True)
        right_layout.addWidget(info_label)

        # Estado de la conexión
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

        right_layout.addStretch()

        # Botones de acción
        actions_layout = QHBoxLayout()

        self.btn_test = QPushButton("Probar Conexión")
        self.btn_test.setObjectName("btnSecondary")
        self.btn_test.clicked.connect(self._test_connection)
        actions_layout.addWidget(self.btn_test)

        self.btn_save = QPushButton("Guardar")
        self.btn_save.clicked.connect(self._save_connection)
        actions_layout.addWidget(self.btn_save)

        self.btn_connect = QPushButton("Conectar")
        self.btn_connect.setObjectName("btnSuccess")
        self.btn_connect.clicked.connect(self._connect)
        actions_layout.addWidget(self.btn_connect)

        right_layout.addLayout(actions_layout)

        layout.addWidget(right_panel)

    def _load_saved_connections(self):
        """Carga las conexiones guardadas en la lista."""
        self.connections_list.clear()
        connections = load_connections()
        for conn in connections:
            item = QListWidgetItem(f" {conn['name']}")
            item.setData(Qt.ItemDataRole.UserRole, conn)
            self.connections_list.addItem(item)

        # Seleccionar la última conexión usada
        config = load_config()
        last = config.get("last_connection")
        if last:
            for i in range(self.connections_list.count()):
                item = self.connections_list.item(i)
                if item is None:
                    continue
                conn = item.data(Qt.ItemDataRole.UserRole)
                if conn and conn.get("name") == last:
                    self.connections_list.setCurrentRow(i)
                    break

    def _on_connection_selected(self, row):
        """Se ejecuta cuando se selecciona una conexión de la lista."""
        if row < 0:
            return
        item = self.connections_list.item(row)
        if item:
            conn = item.data(Qt.ItemDataRole.UserRole)
            if conn:
                self.txt_name.setText(conn.get("name", ""))
                self.txt_url.setText(conn.get("url", ""))
                self.txt_username.setText(conn.get("username", ""))
                self.txt_password.setText(conn.get("app_password", ""))
                self.status_label.setText("")

    def _new_connection(self):
        """Limpia el formulario para una nueva conexión."""
        self.connections_list.clearSelection()
        self.txt_name.clear()
        self.txt_url.clear()
        self.txt_username.clear()
        self.txt_password.clear()
        self.status_label.setText("")
        self.txt_name.setFocus()

    def _remove_connection(self):
        """Elimina la conexión seleccionada."""
        row = self.connections_list.currentRow()
        if row < 0:
            return
        item = self.connections_list.item(row)
        if item is None:
            return
        conn = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Eliminar la conexión '{conn['name']}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            remove_connection(conn["name"])
            self._load_saved_connections()
            self._new_connection()

    def _validate_form(self):
        """Valida el formulario."""
        if not self.txt_name.text().strip():
            QMessageBox.warning(self, "Error", "Introduce un nombre para la conexión.")
            return False
        if not self.txt_url.text().strip():
            QMessageBox.warning(self, "Error", "Introduce la URL del sitio WordPress.")
            return False
        if not self.txt_username.text().strip():
            QMessageBox.warning(self, "Error", "Introduce el nombre de usuario.")
            return False
        if not self.txt_password.text().strip():
            QMessageBox.warning(self, "Error", "Introduce la contraseña de aplicación.")
            return False
        return True

    def _test_connection(self):
        """Prueba la conexión al servidor."""
        if not self._validate_form():
            return

        self.status_label.setText("Probando conexión...")
        self.status_label.setStyleSheet("color: #72aee6;")
        self.btn_test.setEnabled(False)

        self._test_thread = ConnectionTestThread(
            self.txt_url.text().strip(),
            self.txt_username.text().strip(),
            self.txt_password.text().strip()
        )
        self._test_thread.result.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, result):
        """Maneja el resultado de la prueba de conexión."""
        self.btn_test.setEnabled(True)
        if result.get("success"):
            name = result.get("name", "")
            desc = result.get("description", "")
            self.status_label.setText(
                f"Conexión exitosa\n"
                f"Sitio: {name}\n"
                f"Descripción: {desc}"
            )
            self.status_label.setStyleSheet("color: #28a745;")
        else:
            error = result.get("error", "Error desconocido")
            self.status_label.setText(f"Error: {error}")
            self.status_label.setStyleSheet("color: #dc3545;")

    def _save_connection(self):
        """Guarda la conexión actual."""
        if not self._validate_form():
            return

        add_connection(
            self.txt_name.text().strip(),
            self.txt_url.text().strip(),
            self.txt_username.text().strip(),
            self.txt_password.text().strip()
        )
        self._load_saved_connections()
        self.status_label.setText("Conexión guardada correctamente.")
        self.status_label.setStyleSheet("color: #28a745;")

    def _connect(self):
        """Establece la conexión y cierra el diálogo."""
        if not self._validate_form():
            return

        self.selected_connection = {
            "name": self.txt_name.text().strip(),
            "url": self.txt_url.text().strip(),
            "username": self.txt_username.text().strip(),
            "app_password": self.txt_password.text().strip(),
        }

        # Guardar como última conexión
        config = load_config()
        config["last_connection"] = self.selected_connection["name"]
        save_config(config)

        # Guardar la conexión
        add_connection(
            self.selected_connection["name"],
            self.selected_connection["url"],
            self.selected_connection["username"],
            self.selected_connection["app_password"]
        )

        self.accept()

    def get_connection(self):
        """Devuelve los datos de la conexión seleccionada."""
        return self.selected_connection
