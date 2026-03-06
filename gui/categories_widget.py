"""
Widget de gestión de Categorías de WordPress.
Todas las operaciones de red se ejecutan en hilos secundarios.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QMessageBox, QFormLayout,
    QGroupBox, QHeaderView, QAbstractItemView, QComboBox, QTextEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from utils.helpers import extract_rendered, strip_html
from utils.worker import WorkerThread
from utils.screen_utils import get_scale_factor, scaled


class CategoriesWidget(QWidget):
    """Widget para gestionar categorías."""

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        from api.categories import CategoriesAPI
        self.categories_api = CategoriesAPI(api_client)
        self.categories = []
        self._threads = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        # Panel izquierdo: formulario
        left = QWidget()
        sf = get_scale_factor()
        left.setMaximumWidth(scaled(350, sf))
        left_layout = QVBoxLayout(left)

        left_layout.addWidget(QLabel("Añadir nueva categoría"))

        form = QGroupBox()
        form_layout = QFormLayout(form)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Nombre de la categoría")
        form_layout.addRow("Nombre:", self.txt_name)

        self.txt_slug = QLineEdit()
        self.txt_slug.setPlaceholderText("slug-de-la-categoria")
        form_layout.addRow("Slug:", self.txt_slug)

        self.combo_parent = QComboBox()
        self.combo_parent.addItem("Ninguna", 0)
        form_layout.addRow("Categoría superior:", self.combo_parent)

        self.txt_description = QTextEdit()
        self.txt_description.setMaximumHeight(80)
        self.txt_description.setPlaceholderText("Descripción de la categoría...")
        form_layout.addRow("Descripción:", self.txt_description)

        left_layout.addWidget(form)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("+ Añadir Categoría")
        self.btn_add.setObjectName("btnSuccess")
        self.btn_add.clicked.connect(self._add_category)
        btn_layout.addWidget(self.btn_add)

        self.btn_update = QPushButton("Actualizar")
        self.btn_update.clicked.connect(self._update_category)
        self.btn_update.setVisible(False)
        btn_layout.addWidget(self.btn_update)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("btnSecondary")
        self.btn_cancel.clicked.connect(self._cancel_edit)
        self.btn_cancel.setVisible(False)
        btn_layout.addWidget(self.btn_cancel)
        left_layout.addLayout(btn_layout)

        left_layout.addStretch()
        layout.addWidget(left)

        # Panel derecho: tabla
        right = QWidget()
        right_layout = QVBoxLayout(right)

        header = QHBoxLayout()
        header.addWidget(QLabel("Categorías"))
        header.addStretch()
        btn_refresh = QPushButton("Actualizar lista")
        btn_refresh.clicked.connect(self.load_categories)
        header.addWidget(btn_refresh)
        right_layout.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Nombre", "Slug", "Descripción", "Nº Posts", "Acciones"
        ])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.Stretch)
            header.setSectionResizeMode(4, QHeaderView.Fixed)
            self.table.setColumnWidth(4, 220)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v_header = self.table.verticalHeader()
        if v_header is not None:
            v_header.setDefaultSectionSize(80)
            v_header.setMinimumSectionSize(80)
        right_layout.addWidget(self.table)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        right_layout.addWidget(self.status_label)

        layout.addWidget(right, stretch=1)

        self.editing_id = None

    def load_categories(self):
        self.table.setRowCount(0)
        self.status_label.setText("Cargando categorías...")
        t = WorkerThread(lambda: self.categories_api.get_all())
        t.finished.connect(self._on_categories_loaded)
        t.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._threads.append(t)
        t.start()

    def _on_categories_loaded(self, cats):
        self.categories = cats
        self._refresh_parent_combo()
        self.table.setRowCount(len(self.categories))
        for row, cat in enumerate(self.categories):
            name = strip_html(extract_rendered(cat.get("name", "")))
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(cat.get("slug", "")))
            desc = strip_html(cat.get("description", ""))
            self.table.setItem(row, 2, QTableWidgetItem(desc[:80]))
            self.table.setItem(row, 3, QTableWidgetItem(str(cat.get("count", 0))))

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(6)

            cat_id = cat["id"]
            btn_style = "QPushButton { color: white; font-size: 13px; padding: 4px 10px; }"

            btn_edit = QPushButton("Editar")
            btn_edit.setMinimumHeight(28)
            btn_edit.setMinimumWidth(70)
            btn_edit.setStyleSheet(btn_style + "QPushButton { background-color: #0073aa; }")
            btn_edit.setToolTip("Editar categoría")
            btn_edit.clicked.connect(lambda checked, cid=cat_id: self._edit_category(cid))
            actions_layout.addWidget(btn_edit)

            btn_del = QPushButton("Borrar")
            btn_del.setMinimumHeight(28)
            btn_del.setMinimumWidth(70)
            btn_del.setStyleSheet(btn_style + "QPushButton { background-color: #dc3545; }")
            btn_del.setToolTip("Eliminar categoría")
            btn_del.clicked.connect(lambda checked, cid=cat_id: self._delete_category(cid))
            actions_layout.addWidget(btn_del)

            self.table.setCellWidget(row, 4, actions)

        self.status_label.setText(f"{len(self.categories)} categorías cargadas")

    def _refresh_parent_combo(self):
        current_data = self.combo_parent.currentData()
        self.combo_parent.clear()
        self.combo_parent.addItem("Ninguna", 0)
        for cat in self.categories:
            name = strip_html(extract_rendered(cat.get("name", "")))
            self.combo_parent.addItem(name, cat["id"])
        for i in range(self.combo_parent.count()):
            if self.combo_parent.itemData(i) == current_data:
                self.combo_parent.setCurrentIndex(i)
                break

    def _add_category(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "El nombre es obligatorio.")
            return
        self.status_label.setText("Creando categoría...")
        slug = self.txt_slug.text().strip()
        parent = self.combo_parent.currentData() or 0
        desc = self.txt_description.toPlainText()
        t = WorkerThread(
            lambda: self.categories_api.create(
                name=name, slug=slug, parent=parent, description=desc
            )
        )
        t.finished.connect(lambda _r: self._on_category_created())
        t.error.connect(lambda e: self._on_action_error(e))
        self._threads.append(t)
        t.start()

    def _on_category_created(self):
        QMessageBox.information(self, "Éxito", "Categoría creada correctamente.")
        self._clear_form()
        self.load_categories()

    def _edit_category(self, cat_id):
        cat = next((c for c in self.categories if c["id"] == cat_id), None)
        if not cat:
            return
        self.editing_id = cat_id
        self.txt_name.setText(strip_html(extract_rendered(cat.get("name", ""))))
        self.txt_slug.setText(cat.get("slug", ""))
        self.txt_description.setPlainText(cat.get("description", ""))
        parent = cat.get("parent", 0)
        for i in range(self.combo_parent.count()):
            if self.combo_parent.itemData(i) == parent:
                self.combo_parent.setCurrentIndex(i)
                break
        self.btn_add.setVisible(False)
        self.btn_update.setVisible(True)
        self.btn_cancel.setVisible(True)

    def _update_category(self):
        if not self.editing_id:
            return
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "El nombre es obligatorio.")
            return
        self.status_label.setText("Actualizando categoría...")
        eid = self.editing_id
        slug = self.txt_slug.text().strip()
        parent = self.combo_parent.currentData() or 0
        desc = self.txt_description.toPlainText()
        t = WorkerThread(
            lambda: self.categories_api.update(
                eid, name=name, slug=slug, parent=parent, description=desc
            )
        )
        t.finished.connect(lambda _r: self._on_category_updated())
        t.error.connect(lambda e: self._on_action_error(e))
        self._threads.append(t)
        t.start()

    def _on_category_updated(self):
        QMessageBox.information(self, "Éxito", "Categoría actualizada.")
        self._cancel_edit()
        self.load_categories()

    def _delete_category(self, cat_id):
        reply = QMessageBox.question(
            self, "Confirmar", "¿Eliminar esta categoría?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status_label.setText("Eliminando...")
            t = WorkerThread(lambda: self.categories_api.delete(cat_id))
            t.finished.connect(lambda _r: self.load_categories())
            t.error.connect(lambda e: self._on_action_error(e))
            self._threads.append(t)
            t.start()

    def _on_action_error(self, error):
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", str(error))

    def _cancel_edit(self):
        self.editing_id = None
        self._clear_form()
        self.btn_add.setVisible(True)
        self.btn_update.setVisible(False)
        self.btn_cancel.setVisible(False)

    def _clear_form(self):
        self.txt_name.clear()
        self.txt_slug.clear()
        self.txt_description.clear()
        self.combo_parent.setCurrentIndex(0)

    def showEvent(self, a0):
        super().showEvent(a0)
        self.load_categories()
