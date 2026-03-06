"""
Widget de gestión de Usuarios de WordPress.
Todas las operaciones de red se ejecutan en hilos secundarios.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QComboBox, QLineEdit, QMessageBox,
    QHeaderView, QAbstractItemView, QDialog, QFormLayout,
    QGroupBox, QTextEdit, QDialogButtonBox
)
from PyQt5.QtCore import Qt
from utils.helpers import format_date, extract_rendered, strip_html
from utils.worker import WorkerThread
from utils.screen_utils import get_dialog_size


class UserDialog(QDialog):
    """Diálogo para crear/editar un usuario."""

    def __init__(self, users_api, user=None, roles=None, parent=None):
        super().__init__(parent)
        self.users_api = users_api
        self.user = user
        self.roles = roles or []
        self._threads = []
        self.setWindowTitle("Editar Usuario" if user else "Nuevo Usuario")
        dlg_size = get_dialog_size(0.28, 0.50)
        self.setMinimumSize(dlg_size)
        self.resize(dlg_size)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QGroupBox("Datos del Usuario")
        fl = QFormLayout(form)

        self.txt_username = QLineEdit()
        if self.user:
            self.txt_username.setText(self.user.get("username", ""))
            self.txt_username.setReadOnly(True)
        fl.addRow("Usuario:", self.txt_username)

        self.txt_email = QLineEdit()
        if self.user:
            self.txt_email.setText(self.user.get("email", ""))
        fl.addRow("Email:", self.txt_email)

        self.txt_first_name = QLineEdit()
        if self.user:
            self.txt_first_name.setText(self.user.get("first_name", ""))
        fl.addRow("Nombre:", self.txt_first_name)

        self.txt_last_name = QLineEdit()
        if self.user:
            self.txt_last_name.setText(self.user.get("last_name", ""))
        fl.addRow("Apellido:", self.txt_last_name)

        self.txt_nickname = QLineEdit()
        if self.user:
            self.txt_nickname.setText(self.user.get("nickname", ""))
        fl.addRow("Apodo:", self.txt_nickname)

        self.txt_url = QLineEdit()
        if self.user:
            self.txt_url.setText(self.user.get("url", ""))
        fl.addRow("Sitio web:", self.txt_url)

        self.txt_description = QTextEdit()
        self.txt_description.setMaximumHeight(80)
        if self.user:
            self.txt_description.setPlainText(self.user.get("description", ""))
        fl.addRow("Biografía:", self.txt_description)

        self.combo_role = QComboBox()
        # Cargar roles ya obtenidos previamente
        for role in self.roles:
            self.combo_role.addItem(role["name"], role["slug"])
        if self.user:
            user_roles = self.user.get("roles", [])
            for i in range(self.combo_role.count()):
                if self.combo_role.itemData(i) in user_roles:
                    self.combo_role.setCurrentIndex(i)
                    break
        fl.addRow("Rol:", self.combo_role)

        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setPlaceholderText(
            "Dejar vacío para no cambiar" if self.user else "Contraseña"
        )
        fl.addRow("Contraseña:", self.txt_password)

        layout.addWidget(form)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        btns = QHBoxLayout()
        btn_save = QPushButton("Guardar")
        btn_save.setObjectName("btnSuccess")
        btn_save.clicked.connect(self._save)
        btns.addWidget(btn_save)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _save(self):
        email = self.txt_email.text().strip()
        if not email:
            QMessageBox.warning(self, "Error", "El email es obligatorio.")
            return

        self.status_label.setText("Guardando...")

        if self.user:
            data = {
                "email": email,
                "first_name": self.txt_first_name.text().strip(),
                "last_name": self.txt_last_name.text().strip(),
                "nickname": self.txt_nickname.text().strip(),
                "url": self.txt_url.text().strip(),
                "description": self.txt_description.toPlainText(),
                "roles": [self.combo_role.currentData()],
            }
            password = self.txt_password.text()
            if password:
                data["password"] = password
            uid = self.user["id"]
            t = WorkerThread(lambda: self.users_api.update(uid, **data))
        else:
            username = self.txt_username.text().strip()
            password = self.txt_password.text()
            if not username or not password:
                QMessageBox.warning(self, "Error", "Usuario y contraseña son obligatorios.")
                return
            t = WorkerThread(
                lambda: self.users_api.create(
                    username=username,
                    email=email,
                    password=password,
                    first_name=self.txt_first_name.text().strip(),
                    last_name=self.txt_last_name.text().strip(),
                    nickname=self.txt_nickname.text().strip(),
                    url=self.txt_url.text().strip(),
                    description=self.txt_description.toPlainText(),
                    roles=[self.combo_role.currentData()],
                )
            )
        t.finished.connect(lambda _r: self._on_saved())
        t.error.connect(lambda e: self._on_save_error(e))
        self._threads.append(t)
        t.start()

    def _on_saved(self):
        self.status_label.setText("")
        QMessageBox.information(self, "Éxito", "Usuario guardado correctamente.")
        self.accept()

    def _on_save_error(self, error):
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", str(error))


class UsersWidget(QWidget):
    """Widget para gestionar usuarios."""

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        from api.users import UsersAPI
        self.users_api = UsersAPI(api_client)
        self.current_page = 1
        self.total_pages = 1
        self._threads = []
        self._cached_roles = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        header = QHBoxLayout()
        title = QLabel("Usuarios")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()

        self.btn_new = QPushButton("+ Añadir Usuario")
        self.btn_new.setObjectName("btnSuccess")
        self.btn_new.clicked.connect(self._new_user)
        header.addWidget(self.btn_new)
        layout.addLayout(header)

        filters = QHBoxLayout()
        self.filter_role = QComboBox()
        self.filter_role.addItems([
            "Todos", "Administrador", "Editor", "Autor", "Colaborador", "Suscriptor"
        ])
        self.filter_role.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(QLabel("Rol:"))
        filters.addWidget(self.filter_role)

        self.filter_search = QLineEdit()
        self.filter_search.setPlaceholderText("Buscar usuarios...")
        self.filter_search.returnPressed.connect(self._apply_filters)
        filters.addWidget(self.filter_search)

        btn_search = QPushButton("Buscar")
        btn_search.clicked.connect(self._apply_filters)
        filters.addWidget(btn_search)

        btn_refresh = QPushButton("Actualizar")
        btn_refresh.clicked.connect(self.load_users)
        filters.addWidget(btn_refresh)
        layout.addLayout(filters)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Usuario", "Nombre", "Email", "Rol", "Nº Posts", "Acciones"
        ])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.Stretch)
            for i in range(3, 5):
                header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
            # Columna Acciones: ancho fijo para que los botones se vean
            header.setSectionResizeMode(5, QHeaderView.Fixed)
            self.table.setColumnWidth(5, 180)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v_header = self.table.verticalHeader()
        if v_header is not None:
            v_header.setDefaultSectionSize(80)
            v_header.setMinimumSectionSize(80)
        self.table.doubleClicked.connect(self._edit_selected)
        layout.addWidget(self.table)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.lbl_pagination = QLabel("")
        bottom.addWidget(self.lbl_pagination)
        self.btn_prev = QPushButton("◀")
        self.btn_prev.clicked.connect(self._prev_page)
        bottom.addWidget(self.btn_prev)
        self.btn_next = QPushButton("▶")
        self.btn_next.clicked.connect(self._next_page)
        bottom.addWidget(self.btn_next)
        layout.addLayout(bottom)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

    def load_users(self):
        self.status_label.setText("Cargando usuarios...")
        self.table.setRowCount(0)

        role_map = {
            0: None, 1: "administrator", 2: "editor",
            3: "author", 4: "contributor", 5: "subscriber"
        }
        roles = role_map.get(self.filter_role.currentIndex())
        search = self.filter_search.text().strip() or None

        t = WorkerThread(
            lambda: self.users_api.list(
                page=self.current_page,
                per_page=20,
                search=search if search else "",
                roles=roles if roles else "",
            )
        )
        t.finished.connect(self._on_users_loaded)
        t.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._threads.append(t)
        t.start()

    def _on_users_loaded(self, result):
        users = result.get("data", []) if isinstance(result, dict) else result
        total = result.get("total", 0) if isinstance(result, dict) else len(users)
        self.total_pages = result.get("total_pages", 1) if isinstance(result, dict) else 1

        self.table.setRowCount(len(users))
        for row, user in enumerate(users):
            username = user.get("username", user.get("slug", ""))
            ui = QTableWidgetItem(username)
            ui.setData(Qt.ItemDataRole.UserRole, user)
            self.table.setItem(row, 0, ui)

            name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            if not name:
                name = strip_html(extract_rendered(user.get("name", "")))
            self.table.setItem(row, 1, QTableWidgetItem(name))

            self.table.setItem(row, 2, QTableWidgetItem(user.get("email", "")))

            roles_list = user.get("roles", [])
            self.table.setItem(row, 3, QTableWidgetItem(", ".join(roles_list)))

            self.table.setItem(row, 4, QTableWidgetItem("-"))

            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(4, 4, 4, 4)
            al.setSpacing(6)
            uid = user["id"]

            btn_edit = QPushButton("Editar")
            btn_edit.setMinimumHeight(28)
            btn_edit.clicked.connect(lambda c, u=user: self._edit_user(u))
            al.addWidget(btn_edit)

            btn_del = QPushButton("Borrar")
            btn_del.setMinimumHeight(28)
            btn_del.setObjectName("btnDanger")
            btn_del.clicked.connect(lambda c, u=uid: self._delete_user(u))
            al.addWidget(btn_del)

            self.table.setCellWidget(row, 5, actions)

        self.lbl_pagination.setText(f"Página {self.current_page} de {self.total_pages} ({total})")
        self.btn_prev.setEnabled(self.current_page > 1)
        self.btn_next.setEnabled(self.current_page < self.total_pages)
        self.status_label.setText(f"{total} usuarios")

    def _apply_filters(self):
        self.current_page = 1
        self.load_users()

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_users()

    def _next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_users()

    def _load_roles_then_open_dialog(self, user=None):
        """Carga roles en hilo y luego abre el diálogo de usuario."""
        if self._cached_roles:
            self._open_user_dialog(user, self._cached_roles)
            return
        self.status_label.setText("Cargando roles...")
        t = WorkerThread(lambda: self.users_api.get_roles())
        t.finished.connect(lambda roles: self._on_roles_loaded(roles, user))
        t.error.connect(lambda e: self._on_roles_error(e))
        self._threads.append(t)
        t.start()

    def _on_roles_loaded(self, roles, user):
        self._cached_roles = roles
        self.status_label.setText("")
        self._open_user_dialog(user, roles)

    def _on_roles_error(self, error):
        self.status_label.setText("")
        QMessageBox.warning(
            self, "Aviso",
            f"No se pudieron cargar los roles: {error}\nSe usarán roles por defecto."
        )
        default_roles = [
            {"name": "Administrador", "slug": "administrator"},
            {"name": "Editor", "slug": "editor"},
            {"name": "Autor", "slug": "author"},
            {"name": "Colaborador", "slug": "contributor"},
            {"name": "Suscriptor", "slug": "subscriber"},
        ]
        self._open_user_dialog(user, default_roles)

    def _open_user_dialog(self, user, roles):
        dialog = UserDialog(self.users_api, user=user, roles=roles, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_users()

    def _new_user(self):
        self._load_roles_then_open_dialog(user=None)

    def _edit_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        user = item.data(Qt.ItemDataRole.UserRole)
        if user:
            self._edit_user(user)

    def _edit_user(self, user):
        self._load_roles_then_open_dialog(user=user)

    def _delete_user(self, user_id):
        reply = QMessageBox.question(
            self, "Confirmar",
            "¿Eliminar este usuario?\nSus contenidos serán reasignados al administrador.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status_label.setText("Eliminando usuario...")
            t = WorkerThread(lambda: self.users_api.delete(user_id, reassign_to=1))
            t.finished.connect(lambda _r: self.load_users())
            t.error.connect(lambda e: self._on_delete_error(e))
            self._threads.append(t)
            t.start()

    def _on_delete_error(self, error):
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", str(error))

    def showEvent(self, a0):
        super().showEvent(a0)
        self.load_users()
