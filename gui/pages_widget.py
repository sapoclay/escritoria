"""
Widget de gestión de Páginas de WordPress.
Lista, crea, edita, publica y elimina páginas.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QComboBox, QLineEdit, QMessageBox,
    QFormLayout, QGroupBox, QCheckBox, QDateTimeEdit,
    QHeaderView, QAbstractItemView, QSpinBox,
    QStackedWidget, QTextEdit, QInputDialog, QListWidget, QListWidgetItem,
    QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QDateTime
from PyQt5.QtGui import QColor, QPixmap

from gui.editor_widget import ContentEditor
from utils.worker import WorkerThread
from utils.helpers import (
    format_date, strip_html, truncate, get_status_display,
    get_status_color, extract_rendered
)
from api.yoast_seo import extract_yoast_data, build_yoast_meta, has_yoast_seo
from utils.screen_utils import get_scale_factor, scaled
from utils.offline_manager import OfflineManager


class LoadPagesThread(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, pages_api, **kwargs):
        super().__init__()
        self.pages_api = pages_api
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.pages_api.list(**self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class PagesWidget(QWidget):
    """Widget principal para gestión de páginas."""

    def __init__(self, api_client, parent=None, offline_manager=None):
        super().__init__(parent)
        self.api = api_client
        self.offline_manager = offline_manager
        from api.pages import PagesAPI
        from api.media import MediaAPI
        self.pages_api = PagesAPI(api_client)
        self.media_api = MediaAPI(api_client)
        self.current_page_num = 1
        self.total_pages = 1
        self.current_page_data = None
        self.all_pages = []  # Para el selector de padre
        self._threads = []
        self._loaded_offline_draft_id = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.list_view = self._create_list_view()
        self.stack.addWidget(self.list_view)
        self.edit_view = self._create_edit_view()
        self.stack.addWidget(self.edit_view)
        layout.addWidget(self.stack)

    def _create_list_view(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)

        header = QHBoxLayout()
        title = QLabel("Páginas")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()
        self.btn_new_page = QPushButton("+ Añadir Nueva")
        self.btn_new_page.setObjectName("btnSuccess")
        self.btn_new_page.clicked.connect(self._new_page)
        header.addWidget(self.btn_new_page)
        layout.addLayout(header)

        filters = QHBoxLayout()
        self.filter_status = QComboBox()
        self.filter_status.addItems([
            "Todos", "Publicados", "Borradores", "Pendientes", "Privados", "Papelera"
        ])
        self.filter_status.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(QLabel("Estado:"))
        filters.addWidget(self.filter_status)

        self.filter_search = QLineEdit()
        self.filter_search.setPlaceholderText("Buscar páginas...")
        self.filter_search.returnPressed.connect(self._apply_filters)
        filters.addWidget(self.filter_search)

        btn_search = QPushButton("Buscar")
        btn_search.clicked.connect(self._apply_filters)
        filters.addWidget(btn_search)

        btn_refresh = QPushButton("Actualizar")
        btn_refresh.clicked.connect(self.load_pages)
        filters.addWidget(btn_refresh)
        layout.addLayout(filters)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Título", "Autor", "Plantilla", "Fecha", "Estado"
        ])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            for i in range(1, 5):
                header.setSectionResizeMode(
                    i, QHeaderView.ResizeToContents
                )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self._edit_selected_page)
        layout.addWidget(self.table)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.lbl_pagination = QLabel("Página 1 de 1")
        bottom.addWidget(self.lbl_pagination)
        self.btn_prev = QPushButton("◀ Anterior")
        self.btn_prev.clicked.connect(self._prev_page)
        bottom.addWidget(self.btn_prev)
        self.btn_next = QPushButton("Siguiente ▶")
        self.btn_next.clicked.connect(self._next_page)
        bottom.addWidget(self.btn_next)
        layout.addLayout(bottom)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        return widget

    def _create_edit_view(self):
        widget = QWidget()
        main_layout = QHBoxLayout(widget)
        main_layout.setContentsMargins(15, 15, 15, 15)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 10, 0)

        back_layout = QHBoxLayout()
        btn_back = QPushButton("← Volver a la lista")
        btn_back.setObjectName("btnSecondary")
        btn_back.clicked.connect(self._back_to_list)
        back_layout.addWidget(btn_back)
        back_layout.addStretch()
        self.edit_title_label = QLabel("Nueva Página")
        self.edit_title_label.setObjectName("sectionTitle")
        back_layout.addWidget(self.edit_title_label)
        back_layout.addStretch()
        left_layout.addLayout(back_layout)

        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("Título de la página...")
        self.txt_title.setStyleSheet("font-size: 18px; padding: 10px;")
        left_layout.addWidget(self.txt_title)

        slug_layout = QHBoxLayout()
        slug_layout.addWidget(QLabel("Slug:"))
        self.txt_slug = QLineEdit()
        self.txt_slug.setPlaceholderText("url-de-la-pagina")
        slug_layout.addWidget(self.txt_slug)
        left_layout.addLayout(slug_layout)

        self.editor = ContentEditor(media_api=self.media_api)
        left_layout.addWidget(self.editor, stretch=1)

        excerpt_group = QGroupBox("Extracto")
        excerpt_layout = QVBoxLayout(excerpt_group)
        self.txt_excerpt = QTextEdit()
        self.txt_excerpt.setMaximumHeight(80)
        excerpt_layout.addWidget(self.txt_excerpt)
        left_layout.addWidget(excerpt_group)

        main_layout.addWidget(left, stretch=2)

        # Panel derecho con scroll
        sf = get_scale_factor()
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setMaximumWidth(scaled(320, sf))
        right_scroll.setMinimumWidth(scaled(250, sf))
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 0, 0, 0)

        # Publicar
        pub_group = QGroupBox("Publicar")
        pub_layout = QVBoxLayout(pub_group)

        row = QHBoxLayout()
        row.addWidget(QLabel("Estado:"))
        self.combo_status = QComboBox()
        self.combo_status.addItems(["Borrador", "Pendiente", "Publicado", "Privado"])
        row.addWidget(self.combo_status)
        pub_layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Fecha:"))
        self.date_edit = QDateTimeEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDateTime(QDateTime.currentDateTime())
        row2.addWidget(self.date_edit)
        pub_layout.addLayout(row2)

        pass_row = QHBoxLayout()
        pass_row.addWidget(QLabel("Contraseña:"))
        self.txt_password = QLineEdit()
        self.txt_password.setPlaceholderText("Opcional")
        pass_row.addWidget(self.txt_password)
        pub_layout.addLayout(pass_row)

        btns = QHBoxLayout()
        self.btn_save_draft = QPushButton("Borrador")
        self.btn_save_draft.clicked.connect(lambda: self._save_page("draft"))
        btns.addWidget(self.btn_save_draft)
        self.btn_publish = QPushButton("Publicar")
        self.btn_publish.setObjectName("btnSuccess")
        self.btn_publish.clicked.connect(lambda: self._save_page("publish"))
        btns.addWidget(self.btn_publish)
        pub_layout.addLayout(btns)

        self.btn_delete = QPushButton("Eliminar")
        self.btn_delete.setObjectName("btnDanger")
        self.btn_delete.clicked.connect(self._delete_current_page)
        pub_layout.addWidget(self.btn_delete)
        right_layout.addWidget(pub_group)

        # Atributos de página
        attr_group = QGroupBox("Atributos de Página")
        attr_layout = QVBoxLayout(attr_group)

        attr_layout.addWidget(QLabel("Página superior:"))
        self.combo_parent = QComboBox()
        self.combo_parent.addItem("(sin padre)", 0)
        attr_layout.addWidget(self.combo_parent)

        order_row = QHBoxLayout()
        order_row.addWidget(QLabel("Orden:"))
        self.spin_order = QSpinBox()
        self.spin_order.setRange(0, 999)
        order_row.addWidget(self.spin_order)
        attr_layout.addLayout(order_row)

        attr_layout.addWidget(QLabel("Plantilla:"))
        self.combo_template = QComboBox()
        self.combo_template.addItem("Predeterminada", "")
        attr_layout.addWidget(self.combo_template)

        right_layout.addWidget(attr_group)

        # Imagen destacada
        feat_group = QGroupBox("Imagen Destacada")
        feat_layout = QVBoxLayout(feat_group)
        self.lbl_featured = QLabel("Sin imagen destacada")
        self.lbl_featured.setAlignment(Qt.AlignmentFlag.AlignCenter)
        feat_layout.addWidget(self.lbl_featured)
        self.featured_media_id = 0
        feat_btns = QHBoxLayout()
        btn_set = QPushButton("Seleccionar")
        btn_set.clicked.connect(self._set_featured_image)
        feat_btns.addWidget(btn_set)
        btn_remove = QPushButton("Quitar")
        btn_remove.setObjectName("btnSecondary")
        btn_remove.clicked.connect(self._remove_featured_image)
        feat_btns.addWidget(btn_remove)
        feat_layout.addLayout(feat_btns)
        right_layout.addWidget(feat_group)

        # Discusión
        disc_group = QGroupBox("Discusión")
        disc_layout = QVBoxLayout(disc_group)
        self.chk_comments = QCheckBox("Permitir comentarios")
        disc_layout.addWidget(self.chk_comments)
        right_layout.addWidget(disc_group)

        # SEO (Yoast)
        self.seo_group = QGroupBox("SEO (Yoast)")
        seo_layout = QFormLayout(self.seo_group)
        seo_layout.setSpacing(6)

        self.txt_seo_title = QLineEdit()
        self.txt_seo_title.setPlaceholderText("Titulo SEO personalizado")
        self.txt_seo_title.setMinimumHeight(32)
        seo_layout.addRow("Titulo SEO:", self.txt_seo_title)

        self.txt_seo_description = QTextEdit()
        self.txt_seo_description.setMinimumHeight(80)
        self.txt_seo_description.setMaximumHeight(100)
        self.txt_seo_description.setPlaceholderText("Meta descripcion para buscadores (max 160 chars)")
        seo_layout.addRow("Meta descripcion:", self.txt_seo_description)

        self.txt_seo_keyword = QLineEdit()
        self.txt_seo_keyword.setPlaceholderText("Palabra clave principal")
        self.txt_seo_keyword.setMinimumHeight(32)
        seo_layout.addRow("Keyword:", self.txt_seo_keyword)

        self.txt_seo_canonical = QLineEdit()
        self.txt_seo_canonical.setPlaceholderText("https://...")
        self.txt_seo_canonical.setMinimumHeight(32)
        seo_layout.addRow("URL canonica:", self.txt_seo_canonical)

        self.txt_seo_og_title = QLineEdit()
        self.txt_seo_og_title.setPlaceholderText("Titulo para redes sociales")
        self.txt_seo_og_title.setMinimumHeight(32)
        seo_layout.addRow("OG Title:", self.txt_seo_og_title)

        self.txt_seo_og_desc = QLineEdit()
        self.txt_seo_og_desc.setPlaceholderText("Descripcion para redes sociales")
        self.txt_seo_og_desc.setMinimumHeight(32)
        seo_layout.addRow("OG Desc:", self.txt_seo_og_desc)

        self.txt_seo_og_image = QLineEdit()
        self.txt_seo_og_image.setPlaceholderText("URL de la imagen OG")
        self.txt_seo_og_image.setMinimumHeight(32)
        seo_layout.addRow("OG Imagen:", self.txt_seo_og_image)

        self.chk_seo_noindex = QCheckBox("noindex (ocultar de buscadores)")
        seo_layout.addRow("", self.chk_seo_noindex)

        self.chk_seo_nofollow = QCheckBox("nofollow (no seguir enlaces)")
        seo_layout.addRow("", self.chk_seo_nofollow)

        self.seo_group.setVisible(True)
        right_layout.addWidget(self.seo_group)

        right_layout.addStretch()
        right_scroll.setWidget(right)
        main_layout.addWidget(right_scroll, stretch=0)

        return widget

    def load_pages(self):
        self.status_label.setText("Cargando páginas...")
        self.table.setRowCount(0)

        status_map = {
            0: "any", 1: "publish", 2: "draft", 3: "pending",
            4: "private", 5: "trash"
        }
        status = status_map.get(self.filter_status.currentIndex(), "any")
        search = self.filter_search.text().strip() or None

        thread = LoadPagesThread(
            self.pages_api,
            page=self.current_page_num, per_page=20,
            status=status, search=search
        )
        thread.finished.connect(self._on_pages_loaded)
        thread.error.connect(self._on_pages_error)
        self._threads.append(thread)
        thread.start()

    def _on_pages_loaded(self, result):
        pages = result.get("data", []) if isinstance(result, dict) else result
        total = result.get("total", 0) if isinstance(result, dict) else len(pages)
        self.total_pages = result.get("total_pages", 1) if isinstance(result, dict) else 1
        self.all_pages = pages

        self.table.setRowCount(len(pages))
        for row, page in enumerate(pages):
            title = extract_rendered(page.get("title", ""))
            title_item = QTableWidgetItem(strip_html(title))
            title_item.setData(Qt.ItemDataRole.UserRole, page)
            self.table.setItem(row, 0, title_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(page.get("author", ""))))
            self.table.setItem(row, 2, QTableWidgetItem(page.get("template", "default")))
            self.table.setItem(row, 3, QTableWidgetItem(format_date(page.get("date", ""))))
            status = page.get("status", "")
            si = QTableWidgetItem(get_status_display(status))
            si.setForeground(QColor(get_status_color(status)))
            self.table.setItem(row, 4, si)

        self.lbl_pagination.setText(
            f"Página {self.current_page_num} de {self.total_pages} ({total} páginas)"
        )
        self.btn_prev.setEnabled(self.current_page_num > 1)
        self.btn_next.setEnabled(self.current_page_num < self.total_pages)
        self.status_label.setText(f"{total} páginas cargadas")

    def _on_pages_error(self, error):
        self.status_label.setText(f"Error: {error}")
        QMessageBox.warning(self, "Error", f"Error al cargar páginas:\n{error}")

    def _apply_filters(self):
        self.current_page_num = 1
        self.load_pages()

    def _prev_page(self):
        if self.current_page_num > 1:
            self.current_page_num -= 1
            self.load_pages()

    def _next_page(self):
        if self.current_page_num < self.total_pages:
            self.current_page_num += 1
            self.load_pages()

    def _new_page(self):
        self.current_page_data = None
        self.edit_title_label.setText("Nueva Página")
        self.txt_title.clear()
        self.txt_slug.clear()
        self.editor.clear()
        self.txt_excerpt.clear()
        self.combo_status.setCurrentIndex(0)
        self.date_edit.setDateTime(QDateTime.currentDateTime())
        self.txt_password.clear()
        self.chk_comments.setChecked(False)
        self.featured_media_id = 0
        self.lbl_featured.setText("Sin imagen destacada")
        self.spin_order.setValue(0)
        self._clear_seo_fields()
        self._load_parent_pages()
        self.btn_delete.setVisible(False)
        self.stack.setCurrentIndex(1)

    def _edit_selected_page(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        page = item.data(Qt.ItemDataRole.UserRole)
        self._load_page_into_editor(page)

    def _load_page_into_editor(self, page):
        self.current_page_data = page
        self.edit_title_label.setText("Editar Página")
        self.txt_title.setText(strip_html(extract_rendered(page.get("title", ""))))
        self.txt_slug.setText(page.get("slug", ""))
        self.editor.set_raw_html(extract_rendered(page.get("content", "")))
        self.txt_excerpt.setPlainText(strip_html(extract_rendered(page.get("excerpt", ""))))

        status_map = {"draft": 0, "pending": 1, "publish": 2, "private": 3}
        self.combo_status.setCurrentIndex(status_map.get(page.get("status"), 0))

        date = page.get("date", "")
        if date:
            from dateutil import parser as dp
            try:
                dt = dp.parse(date)
                self.date_edit.setDateTime(QDateTime(
                    dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second
                ))
            except Exception:
                pass

        self.txt_password.setText(page.get("password", ""))
        self.chk_comments.setChecked(page.get("comment_status") == "open")
        self.featured_media_id = page.get("featured_media", 0)
        self.lbl_featured.setText(
            f"ID: {self.featured_media_id}"if self.featured_media_id else "Sin imagen"
        )
        self.spin_order.setValue(page.get("menu_order", 0))
        self._load_parent_pages(page.get("parent", 0), page.get("id"))

        # Cargar datos SEO (Yoast)
        self._load_seo_fields(page)

        self.btn_delete.setVisible(True)
        self.stack.setCurrentIndex(1)

    def _load_parent_pages(self, selected_parent=0, exclude_id=None):
        self.combo_parent.clear()
        self.combo_parent.addItem("(sin padre)", 0)
        for p in self.all_pages:
            pid = p.get("id")
            if exclude_id and pid == exclude_id:
                continue
            title = strip_html(extract_rendered(p.get("title", "")))
            self.combo_parent.addItem(f"{title} (ID: {pid})", pid)
            if pid == selected_parent:
                self.combo_parent.setCurrentIndex(self.combo_parent.count() - 1)

    def _save_page(self, status=None):
        title = self.txt_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Error", "El título es obligatorio.")
            return

        if status is None:
            status_map = {0: "draft", 1: "pending", 2: "publish", 3: "private"}
            status = status_map.get(self.combo_status.currentIndex(), "draft")

        parent_idx = self.combo_parent.currentIndex()
        parent = self.combo_parent.itemData(parent_idx) or 0

        data = {
            "title": title,
            "content": self.editor.get_content(),
            "status": status,
            "excerpt": self.txt_excerpt.toPlainText(),
            "slug": self.txt_slug.text().strip(),
            "parent": parent,
            "menu_order": self.spin_order.value(),
            "featured_media": self.featured_media_id,
            "comment_status": "open"if self.chk_comments.isChecked() else "closed",
        }

        # Agregar campos SEO (Yoast) al meta
        seo_meta = self._get_seo_data()
        yoast_meta = build_yoast_meta(seo_meta)
        if yoast_meta:
            data["meta"] = yoast_meta

        password = self.txt_password.text()
        if password:
            data["password"] = password

        dt = self.date_edit.dateTime()
        data["date"] = dt.toString(Qt.DateFormat.ISODate)

        try:
            if self.current_page_data:
                page_id = self.current_page_data["id"]
                t = WorkerThread(lambda: self.pages_api.update(page_id, **data))
            else:
                t = WorkerThread(lambda: self.pages_api.create(**data))
            self.status_label.setText("Guardando página...")
            t.finished.connect(self._on_page_saved)
            t.error.connect(lambda e: self._on_page_save_error(e))
            self._threads.append(t)
            t.start()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al guardar:\n{e}")

    def _on_page_saved(self, result):
        self.current_page_data = result

        # Eliminar borrador offline si se cargó desde uno
        if self._loaded_offline_draft_id and self.offline_manager:
            self.offline_manager.delete_draft(self._loaded_offline_draft_id)
            self._loaded_offline_draft_id = None

        QMessageBox.information(self, "Éxito", "Página guardada correctamente.")
        self.status_label.setText("Página guardada")

    def _on_page_save_error(self, error):
        self.status_label.setText("")
        # Ofrecer guardar offline si no hay conexión
        if self.offline_manager and not self.offline_manager.is_online:
            reply = QMessageBox.question(
                self, "Sin Conexión",
                f"Error al guardar:\n{error}\n\n"
                "¿Deseas guardar un borrador offline para sincronizarlo más tarde?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._save_offline_draft()
                return
        QMessageBox.critical(self, "Error", f"Error al guardar:\n{error}")

    def _delete_current_page(self):
        if not self.current_page_data:
            return
        title = strip_html(extract_rendered(self.current_page_data.get("title", "")))
        reply = QMessageBox.question(
            self, "Confirmar",
            f"¿Eliminar la página '{title}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status_label.setText("Eliminando página...")
            page_id = self.current_page_data["id"]
            t = WorkerThread(lambda: self.pages_api.delete(page_id))
            t.finished.connect(lambda _r: self._on_page_deleted())
            t.error.connect(lambda e: self._on_page_delete_error(e))
            self._threads.append(t)
            t.start()

    def _on_page_deleted(self):
        QMessageBox.information(self, "Éxito", "Página eliminada.")
        self._back_to_list()

    def _on_page_delete_error(self, error):
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", str(error))

    def _back_to_list(self):
        self.stack.setCurrentIndex(0)
        self.load_pages()

    def _set_featured_image(self):
        """Abre el selector visual de la biblioteca de medios."""
        from gui.media_picker import MediaPickerDialog
        dialog = MediaPickerDialog(self.media_api, parent=self)
        if dialog.exec_() == MediaPickerDialog.Accepted:
            media_id = dialog.get_selected_media_id()
            if media_id > 0:
                self.featured_media_id = media_id
                self.lbl_featured.setText(f"Seleccionada (ID: {media_id})")
                self._load_featured_thumbnail(media_id)

    def _remove_featured_image(self):
        self.featured_media_id = 0
        self.lbl_featured.setPixmap(QPixmap())
        self.lbl_featured.setText("Sin imagen destacada")

    def _load_featured_thumbnail(self, media_id):
        """Carga la miniatura de la imagen destacada en un hilo."""
        from gui.posts_widget import _FeaturedImageThread
        t = _FeaturedImageThread(self.media_api, media_id)
        t.finished.connect(self._on_featured_thumbnail_loaded)
        t.error.connect(self._on_featured_thumbnail_error)
        self._threads.append(t)
        t.start()

    def _on_featured_thumbnail_loaded(self, image_data, media_id):
        """Callback cuando la miniatura se descarg\u00f3."""
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(
                200, 150, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_featured.setPixmap(scaled_pixmap)
            self.lbl_featured.setToolTip(f"ID: {media_id}")
        else:
            self.lbl_featured.setText(f"ID: {media_id} (sin vista previa)")

    def _on_featured_thumbnail_error(self, error):
        """Callback si falla la carga de la miniatura."""
        self.lbl_featured.setText(f"ID: {self.featured_media_id} (error: {error})")

    # --- Métodos SEO (Yoast) ---

    def _clear_seo_fields(self):
        """Limpia todos los campos SEO."""
        self.txt_seo_title.clear()
        self.txt_seo_description.clear()
        self.txt_seo_keyword.clear()
        self.txt_seo_canonical.clear()
        self.txt_seo_og_title.clear()
        self.txt_seo_og_desc.clear()
        self.txt_seo_og_image.clear()
        self.chk_seo_noindex.setChecked(False)
        self.chk_seo_nofollow.setChecked(False)

    def _load_seo_fields(self, page: dict):
        """Carga los datos SEO de Yoast desde una página."""
        seo = extract_yoast_data(page)
        self.txt_seo_title.setText(seo.get("seo_title", ""))
        self.txt_seo_description.setPlainText(seo.get("meta_description", ""))
        self.txt_seo_keyword.setText(seo.get("focus_keyword", ""))
        self.txt_seo_canonical.setText(seo.get("canonical_url", ""))
        self.txt_seo_og_title.setText(seo.get("og_title", ""))
        self.txt_seo_og_desc.setText(seo.get("og_description", ""))
        self.txt_seo_og_image.setText(seo.get("og_image", ""))
        self.chk_seo_noindex.setChecked(bool(seo.get("meta_robots_noindex", False)))
        self.chk_seo_nofollow.setChecked(bool(seo.get("meta_robots_nofollow", False)))
        self.seo_group.setVisible(has_yoast_seo(page))

    def _get_seo_data(self) -> dict:
        """Obtiene los datos SEO de los campos del formulario."""
        data: dict = {}
        val = self.txt_seo_title.text().strip()
        if val:
            data["seo_title"] = val
        val = self.txt_seo_description.toPlainText().strip()
        if val:
            data["meta_description"] = val
        val = self.txt_seo_keyword.text().strip()
        if val:
            data["focus_keyword"] = val
        val = self.txt_seo_canonical.text().strip()
        if val:
            data["canonical_url"] = val
        val = self.txt_seo_og_title.text().strip()
        if val:
            data["og_title"] = val
        val = self.txt_seo_og_desc.text().strip()
        if val:
            data["og_description"] = val
        val = self.txt_seo_og_image.text().strip()
        if val:
            data["og_image"] = val
        if self.chk_seo_noindex.isChecked():
            data["meta_robots_noindex"] = True
        if self.chk_seo_nofollow.isChecked():
            data["meta_robots_nofollow"] = True
        return data

    def _save_offline_draft(self):
        """Guarda el contenido actual como borrador offline."""
        if not self.offline_manager:
            return

        title = self.txt_title.text().strip()
        if not title:
            title = "Sin título"

        data = {
            "title": title,
            "content": self.editor.get_content(),
            "status": "draft",
            "excerpt": self.txt_excerpt.toPlainText(),
            "slug": self.txt_slug.text().strip(),
        }

        page_id = self.current_page_data.get("id") if self.current_page_data else None
        draft_id = self.offline_manager.save_draft("page", data, page_id)
        self.status_label.setText(f"Borrador offline guardado: {draft_id}")
        QMessageBox.information(
            self, "Borrador Offline",
            f"La página «{title}» se ha guardado localmente.\n"
            "Se sincronizará automáticamente cuando se restablezca la conexión."
        )

    def showEvent(self, a0):
        super().showEvent(a0)
        if self.stack.currentIndex() == 0:
            self.load_pages()

    def load_from_draft(self, draft):
        """Carga un borrador offline en el editor para continuar editándolo.

        Args:
            draft: dict con la estructura del borrador offline
                   {"id", "type", "post_id", "data": {...}, ...}
        """
        data = draft.get("data", {})
        page_id = draft.get("post_id")

        if page_id:
            self.current_page_data = {"id": page_id}
            self.edit_title_label.setText("Editar Página (borrador offline)")
            self.btn_delete.setVisible(True)
        else:
            self.current_page_data = None
            self.edit_title_label.setText("Nueva Página (borrador offline)")
            self.btn_delete.setVisible(False)

        self.txt_title.setText(data.get("title", ""))
        self.txt_slug.setText(data.get("slug", ""))

        content = data.get("content", "")
        self.editor.set_raw_html(content)

        self.txt_excerpt.setPlainText(data.get("excerpt", ""))

        status_map = {"draft": 0, "pending": 1, "publish": 2, "private": 3}
        self.combo_status.setCurrentIndex(
            status_map.get(data.get("status", "draft"), 0)
        )

        self.date_edit.setDateTime(QDateTime.currentDateTime())
        self.txt_password.setText(data.get("password", ""))
        self.chk_comments.setChecked(
            data.get("comment_status", "open") == "open"
        )
        self.featured_media_id = data.get("featured_media", 0)
        self.lbl_featured.setText("Sin imagen destacada")
        self.spin_order.setValue(data.get("menu_order", 0))

        self._load_parent_pages()
        self.stack.setCurrentIndex(1)

        self._loaded_offline_draft_id = draft.get("id")
        self.status_label.setText("Borrador offline cargado en el editor")
