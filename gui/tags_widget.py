"""
Widget de gestión de Etiquetas de WordPress.
Todas las operaciones de red se ejecutan en hilos secundarios.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QMessageBox, QFormLayout,
    QGroupBox, QHeaderView, QAbstractItemView, QTextEdit
)
from PyQt5.QtCore import Qt
from utils.helpers import extract_rendered, strip_html
from utils.worker import WorkerThread
from utils.screen_utils import get_scale_factor, scaled


class TagsWidget(QWidget):
    """Widget para gestionar etiquetas."""

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        from api.tags import TagsAPI
        self.tags_api = TagsAPI(api_client)
        self.tags = []
        self.editing_id = None
        self._threads = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        # Formulario
        left = QWidget()
        sf = get_scale_factor()
        left.setMaximumWidth(scaled(350, sf))
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Añadir nueva etiqueta"))

        form = QGroupBox()
        form_layout = QFormLayout(form)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Nombre de la etiqueta")
        form_layout.addRow("Nombre:", self.txt_name)

        self.txt_slug = QLineEdit()
        self.txt_slug.setPlaceholderText("slug-de-la-etiqueta")
        form_layout.addRow("Slug:", self.txt_slug)

        self.txt_description = QTextEdit()
        self.txt_description.setMaximumHeight(80)
        form_layout.addRow("Descripción:", self.txt_description)

        left_layout.addWidget(form)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("+ Añadir Etiqueta")
        self.btn_add.setObjectName("btnSuccess")
        self.btn_add.clicked.connect(self._add_tag)
        btn_layout.addWidget(self.btn_add)

        self.btn_update = QPushButton("Actualizar")
        self.btn_update.clicked.connect(self._update_tag)
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

        # Tabla
        right = QWidget()
        right_layout = QVBoxLayout(right)

        header = QHBoxLayout()
        header.addWidget(QLabel("Etiquetas"))
        header.addStretch()
        btn_refresh = QPushButton("Actualizar lista")
        btn_refresh.clicked.connect(self.load_tags)
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

    def load_tags(self):
        self.table.setRowCount(0)
        self.status_label.setText("Cargando etiquetas...")
        t = WorkerThread(lambda: self.tags_api.get_all())
        t.finished.connect(self._on_tags_loaded)
        t.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._threads.append(t)
        t.start()

    def _on_tags_loaded(self, tags):
        self.tags = tags
        self.table.setRowCount(len(self.tags))
        for row, tag in enumerate(self.tags):
            name = strip_html(extract_rendered(tag.get("name", "")))
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(tag.get("slug", "")))
            desc = strip_html(tag.get("description", ""))
            self.table.setItem(row, 2, QTableWidgetItem(desc[:80]))
            self.table.setItem(row, 3, QTableWidgetItem(str(tag.get("count", 0))))

            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(4, 4, 4, 4)
            al.setSpacing(6)
            tid = tag["id"]
            btn_style = "QPushButton { color: white; font-size: 13px; padding: 4px 10px; }"

            btn_edit = QPushButton("Editar")
            btn_edit.setMinimumHeight(28)
            btn_edit.setMinimumWidth(70)
            btn_edit.setStyleSheet(btn_style + "QPushButton { background-color: #0073aa; }")
            btn_edit.clicked.connect(lambda c, t=tid: self._edit_tag(t))
            al.addWidget(btn_edit)

            btn_del = QPushButton("Borrar")
            btn_del.setMinimumHeight(28)
            btn_del.setMinimumWidth(70)
            btn_del.setStyleSheet(btn_style + "QPushButton { background-color: #dc3545; }")
            btn_del.clicked.connect(lambda c, t=tid: self._delete_tag(t))
            al.addWidget(btn_del)

            self.table.setCellWidget(row, 4, actions)

        self.status_label.setText(f"{len(self.tags)} etiquetas cargadas")

    def _add_tag(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "El nombre es obligatorio.")
            return
        self.status_label.setText("Creando etiqueta...")
        slug = self.txt_slug.text().strip()
        desc = self.txt_description.toPlainText()
        t = WorkerThread(
            lambda: self.tags_api.create(name=name, slug=slug, description=desc)
        )
        t.finished.connect(lambda _r: self._on_tag_created())
        t.error.connect(lambda e: self._on_action_error(e))
        self._threads.append(t)
        t.start()

    def _on_tag_created(self):
        QMessageBox.information(self, "Éxito", "Etiqueta creada.")
        self._clear_form()
        self.load_tags()

    def _edit_tag(self, tag_id):
        tag = next((t for t in self.tags if t["id"] == tag_id), None)
        if not tag:
            return
        self.editing_id = tag_id
        self.txt_name.setText(strip_html(extract_rendered(tag.get("name", ""))))
        self.txt_slug.setText(tag.get("slug", ""))
        self.txt_description.setPlainText(tag.get("description", ""))
        self.btn_add.setVisible(False)
        self.btn_update.setVisible(True)
        self.btn_cancel.setVisible(True)

    def _update_tag(self):
        if not self.editing_id:
            return
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "El nombre es obligatorio.")
            return
        self.status_label.setText("Actualizando...")
        eid = self.editing_id
        slug = self.txt_slug.text().strip()
        desc = self.txt_description.toPlainText()
        t = WorkerThread(
            lambda: self.tags_api.update(eid, name=name, slug=slug, description=desc)
        )
        t.finished.connect(lambda _r: self._on_tag_updated())
        t.error.connect(lambda e: self._on_action_error(e))
        self._threads.append(t)
        t.start()

    def _on_tag_updated(self):
        QMessageBox.information(self, "Éxito", "Etiqueta actualizada.")
        self._cancel_edit()
        self.load_tags()

    def _delete_tag(self, tag_id):
        reply = QMessageBox.question(
            self, "Confirmar", "¿Eliminar esta etiqueta?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status_label.setText("Eliminando...")
            t = WorkerThread(lambda: self.tags_api.delete(tag_id))
            t.finished.connect(lambda _r: self.load_tags())
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

    def showEvent(self, a0):
        super().showEvent(a0)
        self.load_tags()
