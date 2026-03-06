"""
Widget de gestión de Comentarios de WordPress.
Moderar, aprobar, rechazar y eliminar comentarios.
Todas las operaciones de red se ejecutan en hilos secundarios.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QComboBox, QLineEdit, QMessageBox,
    QHeaderView, QAbstractItemView, QTextEdit, QDialog,
    QGroupBox, QFormLayout, QDialogButtonBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from utils.helpers import format_date, strip_html, get_status_display, get_status_color
from utils.worker import WorkerThread
from utils.screen_utils import get_dialog_size


class CommentDetailDialog(QDialog):
    """Diálogo para ver/editar un comentario."""

    def __init__(self, comments_api, comment, parent=None):
        super().__init__(parent)
        self.comments_api = comments_api
        self.comment = comment
        self._threads = []
        self.setWindowTitle("Detalle del Comentario")
        dlg_size = get_dialog_size(0.30, 0.42)
        self.setMinimumSize(dlg_size)
        self.resize(dlg_size)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QGroupBox("Información")
        form_layout = QFormLayout(form)

        form_layout.addRow("ID:", QLabel(str(self.comment.get("id", ""))))
        form_layout.addRow("Post:", QLabel(str(self.comment.get("post", ""))))
        form_layout.addRow("Autor:", QLabel(self.comment.get("author_name", "")))
        form_layout.addRow("Email:", QLabel(self.comment.get("author_email", "")))
        form_layout.addRow("URL:", QLabel(self.comment.get("author_url", "")))
        form_layout.addRow("Fecha:", QLabel(format_date(self.comment.get("date", ""))))
        form_layout.addRow("Estado:", QLabel(get_status_display(self.comment.get("status", ""))))
        layout.addWidget(form)

        content_group = QGroupBox("Contenido")
        cl = QVBoxLayout(content_group)
        self.txt_content = QTextEdit()
        content = self.comment.get("content", {})
        if isinstance(content, dict):
            content = content.get("rendered", content.get("raw", ""))
        self.txt_content.setHtml(content)
        cl.addWidget(self.txt_content)
        layout.addWidget(content_group)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        btns = QHBoxLayout()

        btn_approve = QPushButton("Aprobar")
        btn_approve.setObjectName("btnSuccess")
        btn_approve.clicked.connect(lambda: self._set_status("approved"))
        btns.addWidget(btn_approve)

        btn_pending = QPushButton("Pendiente")
        btn_pending.clicked.connect(lambda: self._set_status("hold"))
        btns.addWidget(btn_pending)

        btn_spam = QPushButton("Spam")
        btn_spam.setObjectName("btnSecondary")
        btn_spam.clicked.connect(lambda: self._set_status("spam"))
        btns.addWidget(btn_spam)

        btn_update = QPushButton("Guardar")
        btn_update.clicked.connect(self._save_content)
        btns.addWidget(btn_update)

        btn_delete = QPushButton("Eliminar")
        btn_delete.setObjectName("btnDanger")
        btn_delete.clicked.connect(self._delete)
        btns.addWidget(btn_delete)

        layout.addLayout(btns)

    def _set_status(self, status):
        self.status_label.setText("Cambiando estado...")
        cid = self.comment["id"]
        t = WorkerThread(lambda: self.comments_api.update(cid, status=status))
        t.finished.connect(lambda _r, s=status: self._on_status_changed(s))
        t.error.connect(lambda e: self._on_action_error(e))
        self._threads.append(t)
        t.start()

    def _on_status_changed(self, status):
        self.status_label.setText("")
        QMessageBox.information(self, "Éxito", f"Estado cambiado a: {get_status_display(status)}")
        self.accept()

    def _save_content(self):
        self.status_label.setText("Guardando...")
        cid = self.comment["id"]
        new_content = self.txt_content.toPlainText()
        t = WorkerThread(lambda: self.comments_api.update(cid, content=new_content))
        t.finished.connect(lambda _r: self._on_content_saved())
        t.error.connect(lambda e: self._on_action_error(e))
        self._threads.append(t)
        t.start()

    def _on_content_saved(self):
        self.status_label.setText("")
        QMessageBox.information(self, "Éxito", "Comentario actualizado.")
        self.accept()

    def _delete(self):
        reply = QMessageBox.question(
            self, "Confirmar", "¿Eliminar este comentario?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status_label.setText("Eliminando...")
            cid = self.comment["id"]
            t = WorkerThread(lambda: self.comments_api.delete(cid))
            t.finished.connect(lambda _r: self._on_deleted())
            t.error.connect(lambda e: self._on_action_error(e))
            self._threads.append(t)
            t.start()

    def _on_deleted(self):
        self.status_label.setText("")
        QMessageBox.information(self, "Éxito", "Comentario eliminado.")
        self.done(2)

    def _on_action_error(self, error):
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", str(error))


class CommentsWidget(QWidget):
    """Widget para gestionar comentarios."""

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        from api.comments import CommentsAPI
        self.comments_api = CommentsAPI(api_client)
        self.current_page = 1
        self.total_pages = 1
        self._threads = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        header = QHBoxLayout()
        title = QLabel("Comentarios")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        filters = QHBoxLayout()
        self.filter_status = QComboBox()
        self.filter_status.addItems([
            "Todos", "Aprobados", "Pendientes", "Spam", "Papelera"
        ])
        self.filter_status.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(QLabel("Estado:"))
        filters.addWidget(self.filter_status)

        self.filter_search = QLineEdit()
        self.filter_search.setPlaceholderText("Buscar comentarios...")
        self.filter_search.returnPressed.connect(self._apply_filters)
        filters.addWidget(self.filter_search)

        btn_search = QPushButton("Buscar")
        btn_search.clicked.connect(self._apply_filters)
        filters.addWidget(btn_search)

        btn_refresh = QPushButton("Actualizar")
        btn_refresh.clicked.connect(self.load_comments)
        filters.addWidget(btn_refresh)
        layout.addLayout(filters)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Autor", "Comentario", "Post", "Fecha", "Estado", "Acciones"
        ])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            # Columna Acciones: ancho fijo para que los botones se lean
            header.setSectionResizeMode(5, QHeaderView.Fixed)
            self.table.setColumnWidth(5, 300)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v_header = self.table.verticalHeader()
        if v_header is not None:
            v_header.setDefaultSectionSize(80)
            v_header.setMinimumSectionSize(80)
        self.table.doubleClicked.connect(self._show_detail)
        layout.addWidget(self.table)

        bulk_layout = QHBoxLayout()
        self.bulk_action = QComboBox()
        self.bulk_action.addItems([
            "Acciones en lote", "Aprobar", "Pendiente", "Spam", "Papelera", "Eliminar"
        ])
        bulk_layout.addWidget(self.bulk_action)
        btn_apply = QPushButton("Aplicar")
        btn_apply.setObjectName("btnSecondary")
        btn_apply.clicked.connect(self._apply_bulk)
        bulk_layout.addWidget(btn_apply)
        bulk_layout.addStretch()

        self.lbl_pagination = QLabel("Página 1 de 1")
        bulk_layout.addWidget(self.lbl_pagination)
        self.btn_prev = QPushButton("◀")
        self.btn_prev.clicked.connect(self._prev_page)
        bulk_layout.addWidget(self.btn_prev)
        self.btn_next = QPushButton("▶")
        self.btn_next.clicked.connect(self._next_page)
        bulk_layout.addWidget(self.btn_next)
        layout.addLayout(bulk_layout)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

    def load_comments(self):
        self.status_label.setText("Cargando comentarios...")
        self.table.setRowCount(0)

        status_map = {
            0: "approve", 1: "approved", 2: "hold", 3: "spam", 4: "trash"
        }
        status = status_map.get(self.filter_status.currentIndex(), "approve")
        search = self.filter_search.text().strip() or None

        t = WorkerThread(
            lambda: self.comments_api.list(
                page=self.current_page, per_page=20,
                status=status, search=search
            )
        )
        t.finished.connect(self._on_comments_loaded)
        t.error.connect(self._on_load_error)
        self._threads.append(t)
        t.start()

    def _on_comments_loaded(self, result):
        items = result.get("data", []) if isinstance(result, dict) else result
        total = result.get("total", 0) if isinstance(result, dict) else len(items)
        self.total_pages = result.get("total_pages", 1) if isinstance(result, dict) else 1

        self.table.setRowCount(len(items))
        for row, comment in enumerate(items):
            author = comment.get("author_name", "Anónimo")
            self.table.setItem(row, 0, QTableWidgetItem(author))

            content = comment.get("content", {})
            if isinstance(content, dict):
                content = content.get("rendered", content.get("raw", ""))
            content_text = strip_html(content)[:80]
            ci = QTableWidgetItem(content_text)
            ci.setData(Qt.ItemDataRole.UserRole, comment)
            self.table.setItem(row, 1, ci)

            self.table.setItem(row, 2, QTableWidgetItem(str(comment.get("post", ""))))
            self.table.setItem(row, 3, QTableWidgetItem(format_date(comment.get("date", ""))))

            status_val = comment.get("status", "")
            si = QTableWidgetItem(get_status_display(status_val))
            si.setForeground(QColor(get_status_color(status_val)))
            self.table.setItem(row, 4, si)

            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(4, 4, 4, 4)
            al.setSpacing(6)

            cid = comment["id"]
            btn_style = "QPushButton { color: white; font-size: 13px; padding: 4px 10px; }"

            btn_approve = QPushButton("Aprobar")
            btn_approve.setMinimumHeight(28)
            btn_approve.setMinimumWidth(70)
            btn_approve.setStyleSheet(btn_style + "QPushButton { background-color: #0073aa; }")
            btn_approve.setToolTip("Aprobar")
            btn_approve.clicked.connect(lambda c, i=cid: self._quick_action(i, "approve"))
            al.addWidget(btn_approve)

            btn_spam = QPushButton("Spam")
            btn_spam.setMinimumHeight(28)
            btn_spam.setMinimumWidth(60)
            btn_spam.setStyleSheet(btn_style + "QPushButton { background-color: #555; }")
            btn_spam.setToolTip("Marcar como spam")
            btn_spam.clicked.connect(lambda c, i=cid: self._quick_action(i, "spam"))
            al.addWidget(btn_spam)

            btn_del = QPushButton("Borrar")
            btn_del.setMinimumHeight(28)
            btn_del.setMinimumWidth(65)
            btn_del.setStyleSheet(btn_style + "QPushButton { background-color: #dc3545; }")
            btn_del.setToolTip("Eliminar comentario")
            btn_del.clicked.connect(lambda c, i=cid: self._quick_action(i, "delete"))
            al.addWidget(btn_del)

            self.table.setCellWidget(row, 5, actions)

        self.lbl_pagination.setText(f"Página {self.current_page} de {self.total_pages} ({total})")
        self.btn_prev.setEnabled(self.current_page > 1)
        self.btn_next.setEnabled(self.current_page < self.total_pages)
        self.status_label.setText(f"{total} comentarios")

    def _on_load_error(self, error):
        self.status_label.setText(f"Error: {error}")

    def _apply_filters(self):
        self.current_page = 1
        self.load_comments()

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_comments()

    def _next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_comments()

    def _quick_action(self, comment_id, action):
        if action == "delete":
            reply = QMessageBox.question(
                self, "Confirmar", "¿Eliminar este comentario?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        self.status_label.setText("Procesando...")

        if action == "approve":
            fn = lambda: self.comments_api.approve(comment_id)
        elif action == "spam":
            fn = lambda: self.comments_api.spam(comment_id)
        else:
            fn = lambda: self.comments_api.delete(comment_id)

        t = WorkerThread(fn)
        t.finished.connect(lambda _r: self._on_quick_action_done())
        t.error.connect(lambda e: self._on_quick_action_error(e))
        self._threads.append(t)
        t.start()

    def _on_quick_action_done(self):
        self.load_comments()

    def _on_quick_action_error(self, error):
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", str(error))

    def _show_detail(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 1)
        if item is None:
            return
        comment = item.data(Qt.ItemDataRole.UserRole)
        if comment:
            dialog = CommentDetailDialog(self.comments_api, comment, self)
            result = dialog.exec_()
            if result >= 1:
                self.load_comments()

    def _apply_bulk(self):
        action_idx = self.bulk_action.currentIndex()
        if action_idx == 0:
            return

        sel_model = self.table.selectionModel()
        if sel_model is None:
            return
        selected = sel_model.selectedRows()
        if not selected:
            QMessageBox.warning(self, "Sin selección", "Selecciona comentarios primero.")
            return

        action_map = {1: "approve", 2: "unapprove", 3: "spam", 4: "trash", 5: "delete"}
        action = action_map.get(action_idx)

        ids = []
        for idx in selected:
            item = self.table.item(idx.row(), 1)
            if item is None:
                continue
            comment = item.data(Qt.ItemDataRole.UserRole)
            if comment:
                ids.append(comment["id"])

        if ids:
            self.status_label.setText("Procesando acción en lote...")
            t = WorkerThread(lambda: self.comments_api.bulk_action(ids, action))
            t.finished.connect(lambda _r: self._on_bulk_done())
            t.error.connect(lambda e: self._on_bulk_error(e))
            self._threads.append(t)
            t.start()

    def _on_bulk_done(self):
        self.load_comments()

    def _on_bulk_error(self, error):
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", str(error))

    def showEvent(self, a0):
        super().showEvent(a0)
        self.load_comments()
