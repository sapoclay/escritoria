"""
Widget de gestión de Posts de WordPress.
Lista, crea, edita, publica y elimina entradas.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QComboBox, QLineEdit, QMessageBox,
    QSplitter, QFormLayout, QGroupBox, QCheckBox, QDateTimeEdit,
    QHeaderView, QAbstractItemView, QDialog, QDialogButtonBox,
    QTextEdit, QSpinBox, QListWidget, QListWidgetItem, QStackedWidget,
    QInputDialog, QScrollArea, QTreeWidget, QTreeWidgetItem
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QDateTime, QTimer
from PyQt5.QtGui import QFont, QColor, QPixmap

from gui.editor_widget import ContentEditor
from utils.worker import WorkerThread
from utils.helpers import (
    format_date, strip_html, truncate, get_status_display,
    get_status_color, extract_rendered, is_valid_image_data
)
from api.yoast_seo import extract_yoast_data, build_yoast_meta, has_yoast_seo
from utils.screen_utils import get_scale_factor, scaled
from utils.offline_manager import OfflineManager, save_autosave, get_autosave, clear_autosave


class LoadPostsThread(QThread):
    """Hilo para cargar posts sin bloquear la UI."""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, posts_api, **kwargs):
        super().__init__()
        self.posts_api = posts_api
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.posts_api.list(**self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class SavePostThread(QThread):
    """Hilo para guardar un post."""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, posts_api, post_id=None, data=None):
        super().__init__()
        self.posts_api = posts_api
        self.post_id = post_id
        self.data = data or {}

    def run(self):
        try:
            if self.post_id:
                result = self.posts_api.update(self.post_id, **self.data)
            else:
                result = self.posts_api.create(**self.data)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class _FeaturedImageThread(QThread):
    """Hilo para obtener la URL y descargar la miniatura de la imagen destacada."""
    finished = pyqtSignal(bytes, int)  # image_data, media_id
    error = pyqtSignal(str)

    def __init__(self, media_api, media_id):
        super().__init__()
        self.media_api = media_api
        self.media_id = media_id

    def run(self):
        import requests as _req
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            media = self.media_api.get(self.media_id)
            # Intentar obtener thumbnail, luego medium, luego source_url
            sizes = media.get("media_details", {}).get("sizes", {})
            url = None
            for size_key in ("thumbnail", "medium", "medium_large"):
                if size_key in sizes:
                    url = sizes[size_key].get("source_url")
                    if url:
                        break
            if not url:
                url = media.get("source_url", "")
            if not url:
                self.error.emit("No se encontró URL de imagen")
                return
            # Descargar con sesión robusta (User-Agent + reintentos + SSL tolerante)
            session = _req.Session()
            session.verify = False
            session.headers.update({
                "User-Agent": "WP-Desktop-Editor/1.0",
                "Accept": "image/*, */*",
            })
            adapter = _req.adapters.HTTPAdapter(
                max_retries=urllib3.util.retry.Retry(
                    total=3,
                    backoff_factor=0.5,
                    status_forcelist=[500, 502, 503, 504],
                    allowed_methods=["GET"],
                )
            )
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            resp = session.get(url, timeout=20)
            if resp.status_code == 200 and is_valid_image_data(resp.content):
                self.finished.emit(resp.content, self.media_id)
            else:
                self.error.emit(f"HTTP {resp.status_code}")
        except Exception as e:
            self.error.emit(str(e))


class PostsWidget(QWidget):
    """Widget principal para gestión de posts."""

    def __init__(self, api_client, parent=None, offline_manager=None):
        super().__init__(parent)
        self.api = api_client
        self.offline_manager = offline_manager
        from api.posts import PostsAPI
        from api.categories import CategoriesAPI
        from api.tags import TagsAPI
        from api.media import MediaAPI
        self.posts_api = PostsAPI(api_client)
        self.categories_api = CategoriesAPI(api_client)
        self.tags_api = TagsAPI(api_client)
        self.media_api = MediaAPI(api_client)
        self.current_page = 1
        self.total_pages = 1
        self.current_post = None
        self.categories = []
        self.tags = []
        self._tag_map: dict[int, str] = {}
        self._cat_map: dict[int, str] = {}
        self._threads = []
        self._loaded_offline_draft_id = None
        self._setup_ui()

        # Auto-guardado local periódico (cada 60 s por defecto)
        from config.settings import load_config
        _cfg = load_config()
        interval_secs = _cfg.get("auto_save_interval", 60)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._do_autosave)
        self._autosave_interval = max(interval_secs, 10) * 1000  # mínimo 10 s

    def _setup_ui(self):
        """Configura la interfaz."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()

        # Vista de lista
        self.list_view = self._create_list_view()
        self.stack.addWidget(self.list_view)

        # Vista de edición
        self.edit_view = self._create_edit_view()
        self.stack.addWidget(self.edit_view)

        layout.addWidget(self.stack)

    def _create_list_view(self):
        """Crea la vista de lista de posts."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)

        # Cabecera
        header = QHBoxLayout()
        title = QLabel("Entradas")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()

        self.btn_new_post = QPushButton("+ Añadir Nueva")
        self.btn_new_post.setObjectName("btnSuccess")
        self.btn_new_post.clicked.connect(self._new_post)
        header.addWidget(self.btn_new_post)
        layout.addLayout(header)

        # Filtros
        filters_layout = QHBoxLayout()

        self.filter_status = QComboBox()
        self.filter_status.addItems([
            "Todos", "Publicados", "Borradores", "Pendientes", "Privados",
            "Programados", "Papelera"
        ])
        self.filter_status.currentIndexChanged.connect(self._apply_filters)
        filters_layout.addWidget(QLabel("Estado:"))
        filters_layout.addWidget(self.filter_status)

        self.filter_search = QLineEdit()
        self.filter_search.setPlaceholderText("Buscar entradas...")
        self.filter_search.returnPressed.connect(self._apply_filters)
        filters_layout.addWidget(self.filter_search)

        self.btn_search = QPushButton("Buscar")
        self.btn_search.clicked.connect(self._apply_filters)
        filters_layout.addWidget(self.btn_search)

        self.btn_refresh = QPushButton("Actualizar")
        self.btn_refresh.setToolTip("Actualizar lista")
        self.btn_refresh.clicked.connect(self.load_posts)
        filters_layout.addWidget(self.btn_refresh)

        layout.addLayout(filters_layout)

        # Tabla de posts
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Título", "Autor", "Categorías", "Etiquetas", "Fecha", "Estado"
        ])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self._edit_selected_post)
        layout.addWidget(self.table)

        # Paginación y acciones de lotes
        bottom_layout = QHBoxLayout()

        self.bulk_action = QComboBox()
        self.bulk_action.addItems(["Acciones en lote", "Publicar", "Borrador", "Papelera", "Eliminar"])
        bottom_layout.addWidget(self.bulk_action)

        self.btn_apply_bulk = QPushButton("Aplicar")
        self.btn_apply_bulk.setObjectName("btnSecondary")
        self.btn_apply_bulk.clicked.connect(self._apply_bulk_action)
        bottom_layout.addWidget(self.btn_apply_bulk)

        bottom_layout.addStretch()

        self.lbl_pagination = QLabel("Página 1 de 1")
        bottom_layout.addWidget(self.lbl_pagination)

        self.btn_prev = QPushButton("◀ Anterior")
        self.btn_prev.clicked.connect(self._prev_page)
        bottom_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("Siguiente ▶")
        self.btn_next.clicked.connect(self._next_page)
        bottom_layout.addWidget(self.btn_next)

        layout.addLayout(bottom_layout)

        # Status bar
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        return widget

    def _create_edit_view(self):
        """Crea la vista de edición de posts."""
        widget = QWidget()
        main_layout = QHBoxLayout(widget)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Contenido principal (izquierda)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 10, 0)

        # Botón volver
        back_layout = QHBoxLayout()
        self.btn_back = QPushButton("← Volver a la lista")
        self.btn_back.setObjectName("btnSecondary")
        self.btn_back.clicked.connect(self._back_to_list)
        back_layout.addWidget(self.btn_back)
        back_layout.addStretch()

        self.edit_title_label = QLabel("Nueva Entrada")
        self.edit_title_label.setObjectName("sectionTitle")
        back_layout.addWidget(self.edit_title_label)
        back_layout.addStretch()
        left_layout.addLayout(back_layout)

        # Título
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("Introduce el título aquí...")
        self.txt_title.setStyleSheet("font-size: 18px; padding: 10px;")
        left_layout.addWidget(self.txt_title)

        # Slug
        slug_layout = QHBoxLayout()
        slug_layout.addWidget(QLabel("Slug:"))
        self.txt_slug = QLineEdit()
        self.txt_slug.setPlaceholderText("url-del-post")
        slug_layout.addWidget(self.txt_slug)
        left_layout.addLayout(slug_layout)

        # Editor de contenido
        self.editor = ContentEditor(media_api=self.media_api)
        left_layout.addWidget(self.editor, stretch=1)

        # Extracto
        excerpt_group = QGroupBox("Extracto")
        excerpt_layout = QVBoxLayout(excerpt_group)
        self.txt_excerpt = QTextEdit()
        self.txt_excerpt.setMaximumHeight(80)
        self.txt_excerpt.setPlaceholderText("Escribe un extracto opcional...")
        excerpt_layout.addWidget(self.txt_excerpt)
        left_layout.addWidget(excerpt_group)

        main_layout.addWidget(left, stretch=2)

        # Panel lateral (derecha) con scroll
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
        publish_group = QGroupBox("Publicar")
        publish_layout = QVBoxLayout(publish_group)

        # Estado
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Estado:"))
        self.combo_status = QComboBox()
        self.combo_status.addItems(["Borrador", "Pendiente", "Publicado", "Privado"])
        status_row.addWidget(self.combo_status)
        publish_layout.addLayout(status_row)

        # Fecha
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Fecha:"))
        self.date_edit = QDateTimeEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDateTime(QDateTime.currentDateTime())
        date_row.addWidget(self.date_edit)
        publish_layout.addLayout(date_row)

        # Visibilidad
        self.chk_sticky = QCheckBox("Entrada fija (sticky)")
        publish_layout.addWidget(self.chk_sticky)

        # Contraseña
        pass_row = QHBoxLayout()
        pass_row.addWidget(QLabel("Contraseña:"))
        self.txt_password = QLineEdit()
        self.txt_password.setPlaceholderText("Opcional")
        pass_row.addWidget(self.txt_password)
        publish_layout.addLayout(pass_row)

        # Botones de publicación
        pub_btns = QHBoxLayout()
        self.btn_save_draft = QPushButton("Guardar Borrador")
        self.btn_save_draft.clicked.connect(lambda: self._save_post("draft"))
        pub_btns.addWidget(self.btn_save_draft)

        self.btn_publish = QPushButton("Publicar")
        self.btn_publish.setObjectName("btnSuccess")
        self.btn_publish.clicked.connect(lambda: self._save_post("publish"))
        pub_btns.addWidget(self.btn_publish)
        publish_layout.addLayout(pub_btns)

        # Botón eliminar
        self.btn_delete_post = QPushButton("Eliminar")
        self.btn_delete_post.setObjectName("btnDanger")
        self.btn_delete_post.clicked.connect(self._delete_current_post)
        publish_layout.addWidget(self.btn_delete_post)

        right_layout.addWidget(publish_group)

        # Formato
        format_group = QGroupBox("Formato")
        format_layout = QVBoxLayout(format_group)
        self.combo_format = QComboBox()
        self.combo_format.addItems([
            "Estándar", "Cita", "Estado", "Chat", "Galería",
            "Enlace", "Imagen", "Vídeo", "Audio"
        ])
        format_layout.addWidget(self.combo_format)
        right_layout.addWidget(format_group)

        # Categorías (árbol jerárquico)
        cat_group = QGroupBox("Categorías")
        cat_layout = QVBoxLayout(cat_group)
        self.cat_tree = QTreeWidget()
        self.cat_tree.setHeaderHidden(True)
        self.cat_tree.setMinimumHeight(250)
        self.cat_tree.setStyleSheet(
            "QTreeWidget { background-color: #2b2b2b; border: 1px solid #444; }"
            "QTreeWidget::item { padding: 2px 0; }"
        )
        cat_layout.addWidget(self.cat_tree)
        right_layout.addWidget(cat_group)

        # Etiquetas
        tag_group = QGroupBox("Etiquetas")
        tag_layout = QVBoxLayout(tag_group)
        self.txt_tags = QLineEdit()
        self.txt_tags.setPlaceholderText("Separar con comas...")
        tag_layout.addWidget(self.txt_tags)
        self.lbl_tags_info = QLabel("")
        self.lbl_tags_info.setObjectName("statusLabel")
        self.lbl_tags_info.setWordWrap(True)
        tag_layout.addWidget(self.lbl_tags_info)
        right_layout.addWidget(tag_group)

        # Imagen destacada
        featured_group = QGroupBox("Imagen Destacada")
        featured_layout = QVBoxLayout(featured_group)
        self.lbl_featured = QLabel("Sin imagen destacada")
        self.lbl_featured.setAlignment(Qt.AlignmentFlag.AlignCenter)
        featured_layout.addWidget(self.lbl_featured)
        self.featured_media_id = 0
        feat_btns = QHBoxLayout()
        self.btn_set_featured = QPushButton("Seleccionar")
        self.btn_set_featured.clicked.connect(self._set_featured_image)
        feat_btns.addWidget(self.btn_set_featured)
        self.btn_remove_featured = QPushButton("Quitar")
        self.btn_remove_featured.setObjectName("btnSecondary")
        self.btn_remove_featured.clicked.connect(self._remove_featured_image)
        feat_btns.addWidget(self.btn_remove_featured)
        featured_layout.addLayout(feat_btns)
        right_layout.addWidget(featured_group)

        # Comentarios
        discussion_group = QGroupBox("Discusión")
        discussion_layout = QVBoxLayout(discussion_group)
        self.chk_comments = QCheckBox("Permitir comentarios")
        self.chk_comments.setChecked(True)
        discussion_layout.addWidget(self.chk_comments)
        self.chk_pings = QCheckBox("Permitir pings y trackbacks")
        self.chk_pings.setChecked(True)
        discussion_layout.addWidget(self.chk_pings)
        right_layout.addWidget(discussion_group)

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

    # ---- Carga de datos ----

    def load_posts(self):
        """Carga la lista de posts."""
        self.status_label.setText("Cargando entradas...")
        self.table.setRowCount(0)
        self._load_taxonomy_maps()

        status_map = {
            0: "any", 1: "publish", 2: "draft", 3: "pending",
            4: "private", 5: "future", 6: "trash"
        }
        status = status_map.get(self.filter_status.currentIndex(), "any")
        search = self.filter_search.text().strip() or None

        thread = LoadPostsThread(
            self.posts_api,
            page=self.current_page,
            per_page=20,
            status=status,
            search=search
        )
        thread.finished.connect(self._on_posts_loaded)
        thread.error.connect(self._on_posts_error)
        self._threads.append(thread)
        thread.start()

    def _load_taxonomy_maps(self):
        """Carga mapas id->nombre de categorías y etiquetas en segundo plano."""
        if not self._tag_map:
            t = WorkerThread(lambda: self.tags_api.get_all())
            t.finished.connect(self._on_tag_map_loaded)
            self._threads.append(t)
            t.start()
        if not self._cat_map:
            t = WorkerThread(lambda: self.categories_api.get_all())
            t.finished.connect(self._on_cat_map_loaded)
            self._threads.append(t)
            t.start()

    def _on_tag_map_loaded(self, tags):
        self.tags = tags
        self._tag_map = {
            tag["id"]: strip_html(extract_rendered(tag.get("name", "")))
            for tag in tags
        }
        self._refresh_taxonomy_columns()

    def _on_cat_map_loaded(self, cats):
        self._cat_map = {
            cat["id"]: strip_html(extract_rendered(cat.get("name", "")))
            for cat in cats
        }
        self._refresh_taxonomy_columns()

    def _refresh_taxonomy_columns(self):
        """Actualiza las columnas de categorías y etiquetas con nombres."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            post = item.data(Qt.ItemDataRole.UserRole)
            if not post:
                continue
            if self._cat_map:
                cats = post.get("categories", [])
                cat_names = [self._cat_map.get(c, str(c)) for c in cats[:3]]
                cat_text = ", ".join(cat_names)
                if len(cats) > 3:
                    cat_text += f" (+{len(cats)-3})"
                self.table.setItem(row, 2, QTableWidgetItem(cat_text))
            if self._tag_map:
                tags = post.get("tags", [])
                tag_names = [self._tag_map.get(t, str(t)) for t in tags[:3]]
                tag_text = ", ".join(tag_names)
                if len(tags) > 3:
                    tag_text += f" (+{len(tags)-3})"
                self.table.setItem(row, 3, QTableWidgetItem(tag_text))

    def _on_posts_loaded(self, result):
        """Maneja los posts cargados."""
        posts = result.get("data", []) if isinstance(result, dict) else result
        total = result.get("total", 0) if isinstance(result, dict) else len(posts)
        self.total_pages = result.get("total_pages", 1) if isinstance(result, dict) else 1

        self.table.setRowCount(len(posts))

        for row, post in enumerate(posts):
            # Título
            title = extract_rendered(post.get("title", ""))
            title_item = QTableWidgetItem(strip_html(title))
            title_item.setData(Qt.ItemDataRole.UserRole, post)
            self.table.setItem(row, 0, title_item)

            # Autor (ID)
            author_id = post.get("author", "")
            self.table.setItem(row, 1, QTableWidgetItem(str(author_id)))

            # Categorías (nombres si el mapa está listo)
            cats = post.get("categories", [])
            cat_names = [self._cat_map.get(c, str(c)) for c in cats[:3]]
            cat_text = ", ".join(cat_names)
            if len(cats) > 3:
                cat_text += f" (+{len(cats)-3})"
            self.table.setItem(row, 2, QTableWidgetItem(cat_text))

            # Etiquetas (nombres si el mapa está listo)
            tags = post.get("tags", [])
            tag_names = [self._tag_map.get(t, str(t)) for t in tags[:3]]
            tag_text = ", ".join(tag_names)
            if len(tags) > 3:
                tag_text += f" (+{len(tags)-3})"
            self.table.setItem(row, 3, QTableWidgetItem(tag_text))

            # Fecha
            date = format_date(post.get("date", ""))
            self.table.setItem(row, 4, QTableWidgetItem(date))

            # Estado
            status = post.get("status", "")
            status_item = QTableWidgetItem(get_status_display(status))
            color = get_status_color(status)
            status_item.setForeground(QColor(color))
            self.table.setItem(row, 5, status_item)

        self.lbl_pagination.setText(
            f"Página {self.current_page} de {self.total_pages} "
            f"({total} entradas)"
        )
        self.btn_prev.setEnabled(self.current_page > 1)
        self.btn_next.setEnabled(self.current_page < self.total_pages)
        self.status_label.setText(f"{total} entradas cargadas")

    def _on_posts_error(self, error):
        """Maneja errores al cargar posts."""
        self.status_label.setText(f"Error: {error}")
        QMessageBox.warning(self, "Error", f"Error al cargar entradas:\n{error}")

    def _apply_filters(self):
        """Aplica los filtros de búsqueda."""
        self.current_page = 1
        self.load_posts()

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_posts()

    def _next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_posts()

    # ---- Edición de posts ----

    def _new_post(self):
        """Abre el editor para un nuevo post."""
        self.current_post = None
        self.edit_title_label.setText("Nueva Entrada")
        self.txt_title.clear()
        self.txt_slug.clear()
        self.editor.clear()
        self.txt_excerpt.clear()
        self.combo_status.setCurrentIndex(0)  # Borrador
        self.combo_format.setCurrentIndex(0)  # Estándar
        self.date_edit.setDateTime(QDateTime.currentDateTime())
        self.chk_sticky.setChecked(False)
        self.txt_password.clear()
        self.chk_comments.setChecked(True)
        self.chk_pings.setChecked(True)
        self.featured_media_id = 0
        self.lbl_featured.setPixmap(QPixmap())
        self.lbl_featured.setText("Sin imagen destacada")
        self.txt_tags.clear()
        self._clear_seo_fields()
        self.btn_delete_post.setVisible(False)
        self._load_categories()
        self.stack.setCurrentIndex(1)
        self._autosave_timer.start(self._autosave_interval)

    def _edit_selected_post(self):
        """Abre el editor con el post seleccionado."""
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        post = item.data(Qt.ItemDataRole.UserRole)
        self._load_post_into_editor(post)

    def _load_post_into_editor(self, post):
        """Carga un post en el editor."""
        self.current_post = post
        self.edit_title_label.setText("Editar Entrada")

        title = extract_rendered(post.get("title", ""))
        self.txt_title.setText(strip_html(title))

        self.txt_slug.setText(post.get("slug", ""))

        content = extract_rendered(post.get("content", ""))
        self.editor.set_raw_html(content)

        excerpt = extract_rendered(post.get("excerpt", ""))
        self.txt_excerpt.setPlainText(strip_html(excerpt))

        # Estado
        status_map = {"draft": 0, "pending": 1, "publish": 2, "private": 3}
        self.combo_status.setCurrentIndex(
            status_map.get(post.get("status", "draft"), 0)
        )

        # Formato
        format_map = {
            "standard": 0, "quote": 1, "status": 2, "chat": 3,
            "gallery": 4, "link": 5, "image": 6, "video": 7, "audio": 8
        }
        self.combo_format.setCurrentIndex(
            format_map.get(post.get("format", "standard"), 0)
        )

        # Fecha
        date = post.get("date", "")
        if date:
            from dateutil import parser as dateutil_parser
            try:
                dt = dateutil_parser.parse(date)
                self.date_edit.setDateTime(QDateTime(
                    dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second
                ))
            except Exception:
                self.date_edit.setDateTime(QDateTime.currentDateTime())

        self.chk_sticky.setChecked(post.get("sticky", False))
        self.txt_password.setText(post.get("password", ""))
        self.chk_comments.setChecked(
            post.get("comment_status", "open") == "open"
        )
        self.chk_pings.setChecked(
            post.get("ping_status", "open") == "open"
        )

        self.featured_media_id = post.get("featured_media", 0)
        if self.featured_media_id:
            self.lbl_featured.setText(f"Imagen destacada (ID: {self.featured_media_id}) — cargando miniatura...")
            self._load_featured_thumbnail(self.featured_media_id)
        else:
            self.lbl_featured.setText("Sin imagen destacada")
            self.lbl_featured.setPixmap(QPixmap())

        # Etiquetas (mostrar nombres en lugar de IDs)
        tag_ids = post.get("tags", [])
        if self._tag_map:
            tag_names = [self._tag_map.get(t, str(t)) for t in tag_ids]
        else:
            tag_names = [str(t) for t in tag_ids]
        self.txt_tags.setText(", ".join(tag_names))

        # Cargar datos SEO (Yoast)
        self._load_seo_fields(post)

        self.btn_delete_post.setVisible(True)
        self._load_categories(post.get("categories", []))
        self.stack.setCurrentIndex(1)
        self._autosave_timer.start(self._autosave_interval)

    def _load_categories(self, selected_ids=None):
        """Carga las categorías disponibles en hilo secundario."""
        self.cat_tree.clear()
        placeholder = QTreeWidgetItem(self.cat_tree, ["Cargando categorías..."])
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        self._pending_cat_ids = selected_ids
        t = WorkerThread(lambda: self.categories_api.get_all())
        t.finished.connect(self._on_categories_loaded)
        t.error.connect(lambda e: self._on_categories_error(e))
        self._threads.append(t)
        t.start()

    def _on_categories_loaded(self, cats):
        """Rellena el árbol de categorías jerárquicamente."""
        self.cat_tree.clear()
        self.categories = cats
        selected_ids = self._pending_cat_ids or []

        # Construir mapa id -> categoría y agrupar por parent
        cat_map: dict[int, dict] = {}
        children_map: dict[int, list] = {}  # parent_id -> [cat, ...]
        for cat in cats:
            cid = cat.get("id", 0)
            parent = cat.get("parent", 0)
            cat_map[cid] = cat
            children_map.setdefault(parent, []).append(cat)

        # Ordenar hijos alfabéticamente por nombre
        for kids in children_map.values():
            kids.sort(key=lambda c: strip_html(extract_rendered(c.get("name", ""))).lower())

        # Crear ítems del árbol, devolviendo el QTreeWidgetItem creado
        def _add_children(parent_widget, parent_id: int):
            for cat in children_map.get(parent_id, []):
                cid = cat["id"]
                name = strip_html(extract_rendered(cat.get("name", "")))
                tree_item = QTreeWidgetItem(parent_widget, [name])
                tree_item.setData(0, Qt.ItemDataRole.UserRole, cid)
                tree_item.setFlags(
                    tree_item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsAutoTristate
                )
                if cid in selected_ids:
                    tree_item.setCheckState(0, Qt.CheckState.Checked)
                else:
                    tree_item.setCheckState(0, Qt.CheckState.Unchecked)
                # Recursión para hijos
                _add_children(tree_item, cid)

        _add_children(self.cat_tree, 0)
        self.cat_tree.expandAll()

    def _on_categories_error(self, error):
        self.cat_tree.clear()
        err_item = QTreeWidgetItem(self.cat_tree, [f"Error: {error}"])
        err_item.setFlags(Qt.ItemFlag.NoItemFlags)

    def _save_post(self, status=None):
        """Guarda el post actual."""
        title = self.txt_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Error", "El título es obligatorio.")
            return

        # Mapear estado
        if status is None:
            status_map = {0: "draft", 1: "pending", 2: "publish", 3: "private"}
            status = status_map.get(self.combo_status.currentIndex(), "draft")

        # Mapear formato
        format_map = {
            0: "standard", 1: "quote", 2: "status", 3: "chat",
            4: "gallery", 5: "link", 6: "image", 7: "video", 8: "audio"
        }
        post_format = format_map.get(self.combo_format.currentIndex(), "standard")

        # Obtener categorías seleccionadas (recorrido recursivo del árbol)
        selected_cats = []

        def _collect_checked(parent_item):
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                if child.checkState(0) == Qt.CheckState.Checked:
                    cid = child.data(0, Qt.ItemDataRole.UserRole)
                    if cid is not None:
                        selected_cats.append(cid)
                _collect_checked(child)

        root = self.cat_tree.invisibleRootItem()
        _collect_checked(root)

        data = {
            "title": title,
            "content": self.editor.get_content(),
            "status": status,
            "excerpt": self.txt_excerpt.toPlainText(),
            "slug": self.txt_slug.text().strip(),
            "format_type": post_format,
            "sticky": self.chk_sticky.isChecked(),
            "password": self.txt_password.text(),
            "comment_status": "open"if self.chk_comments.isChecked() else "closed",
            "ping_status": "open"if self.chk_pings.isChecked() else "closed",
            "featured_media": self.featured_media_id,
        }

        # Agregar campos SEO (Yoast) al meta
        seo_meta = self._get_seo_data()
        yoast_meta = build_yoast_meta(seo_meta)
        if yoast_meta:
            data["meta"] = yoast_meta

        if selected_cats:
            data["categories"] = selected_cats

        # Etiquetas: resolver nombres a IDs
        tags_text = self.txt_tags.text().strip()
        if tags_text:
            tag_names_list = [t.strip() for t in tags_text.split(",") if t.strip()]
            tag_ids = []
            name_to_id = {v.lower(): k for k, v in self._tag_map.items()}
            for tn in tag_names_list:
                tid = name_to_id.get(tn.lower())
                if tid:
                    tag_ids.append(tid)
                else:
                    try:
                        tag_ids.append(int(tn))
                    except ValueError:
                        pass
            if tag_ids:
                data["tags"] = tag_ids

        # Fecha
        dt = self.date_edit.dateTime()
        data["date"] = dt.toString(Qt.DateFormat.ISODate)

        self.status_label.setText("Guardando entrada...")

        thread = SavePostThread(
            self.posts_api,
            post_id=self.current_post.get("id") if self.current_post else None,
            data=data
        )
        thread.finished.connect(self._on_post_saved)
        thread.error.connect(self._on_post_save_error)
        self._threads.append(thread)
        thread.start()

    def _on_post_saved(self, result):
        """Maneja el guardado exitoso del post."""
        title = extract_rendered(result.get("title", ""))
        status = get_status_display(result.get("status", ""))
        self.current_post = result

        # Eliminar borrador offline si se cargó desde uno
        if self._loaded_offline_draft_id and self.offline_manager:
            self.offline_manager.delete_draft(self._loaded_offline_draft_id)
            self._loaded_offline_draft_id = None

        QMessageBox.information(
            self, "Éxito",
            f"Entrada guardada correctamente.\n"
            f"Título: {strip_html(title)}\n"
            f"Estado: {status}"
        )
        self.status_label.setText("Entrada guardada")

    def _on_post_save_error(self, error):
        """Maneja errores al guardar el post. Ofrece guardar offline."""
        self.status_label.setText(f"Error al guardar: {error}")

        # Si hay offline manager, ofrecer guardar localmente
        if self.offline_manager and not self.offline_manager.is_online:
            reply = QMessageBox.question(
                self, "Sin Conexión",
                f"Error al guardar la entrada:\n{error}\n\n"
                "¿Deseas guardar un borrador offline para sincronizarlo más tarde?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._save_offline_draft()
                return

        QMessageBox.critical(self, "Error", f"Error al guardar la entrada:\n{error}")

    def _delete_current_post(self):
        """Elimina el post actual en hilo secundario."""
        if not self.current_post:
            return

        title = extract_rendered(self.current_post.get("title", ""))
        reply = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Estás seguro de eliminar la entrada '{strip_html(title)}'?\n"
            "Esta acción no se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status_label.setText("Eliminando entrada...")
            post_id = self.current_post["id"]
            t = WorkerThread(lambda: self.posts_api.delete(post_id))
            t.finished.connect(lambda _r: self._on_post_deleted())
            t.error.connect(lambda e: self._on_post_delete_error(e))
            self._threads.append(t)
            t.start()

    def _on_post_deleted(self):
        QMessageBox.information(self, "Éxito", "Entrada eliminada correctamente.")
        self._back_to_list()
        self.load_posts()

    def _on_post_delete_error(self, error):
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", f"Error al eliminar la entrada:\n{error}")

    def _back_to_list(self):
        """Vuelve a la vista de lista."""
        self._autosave_timer.stop()
        clear_autosave("post")
        self.stack.setCurrentIndex(0)
        self.load_posts()

    def _apply_bulk_action(self):
        """Aplica una acción en lote."""
        action_idx = self.bulk_action.currentIndex()
        if action_idx == 0:
            return

        sel_model = self.table.selectionModel()
        if sel_model is None:
            return
        selected = sel_model.selectedRows()
        if not selected:
            QMessageBox.warning(
                self, "Sin selección",
                "Selecciona al menos una entrada."
            )
            return

        post_ids = []
        for idx in selected:
            item = self.table.item(idx.row(), 0)
            if item is None:
                continue
            post = item.data(Qt.ItemDataRole.UserRole)
            if post:
                post_ids.append(post["id"])

        action_map = {1: "publish", 2: "draft", 3: "trash", 4: "delete"}
        action = action_map.get(action_idx)

        reply = QMessageBox.question(
            self, "Confirmar acción",
            f"¿Aplicar '{self.bulk_action.currentText()}' a {len(post_ids)} entradas?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status_label.setText("Procesando acción en lote...")
            if action == "delete":
                t = WorkerThread(lambda: self.posts_api.bulk_delete(post_ids))
            else:
                t = WorkerThread(lambda: self.posts_api.bulk_update_status(post_ids, action))
            t.finished.connect(self._on_bulk_done)
            t.error.connect(lambda e: QMessageBox.critical(self, "Error", str(e)))
            self._threads.append(t)
            t.start()

    def _on_bulk_done(self, results):
        success = sum(1 for r in results if r["success"])
        errors = len(results) - success
        self.status_label.setText(f"{success} procesados, {errors} errores")
        self.load_posts()

    def _load_featured_thumbnail(self, media_id):
        """Carga la miniatura de la imagen destacada en un hilo."""
        t = _FeaturedImageThread(self.media_api, media_id)
        t.finished.connect(self._on_featured_thumbnail_loaded)
        t.error.connect(self._on_featured_thumbnail_error)
        self._threads.append(t)
        t.start()

    def _on_featured_thumbnail_loaded(self, image_data, media_id):
        """Callback cuando la miniatura se descargó (crea QPixmap en hilo principal)."""
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

    def _set_featured_image(self):
        """Abre el selector visual de la biblioteca de medios."""
        from gui.media_picker import MediaPickerDialog
        dialog = MediaPickerDialog(self.media_api, parent=self)
        if dialog.exec_() == MediaPickerDialog.Accepted:
            media_id = dialog.get_selected_media_id()
            if media_id > 0:
                self.featured_media_id = media_id
                self.lbl_featured.setText("Cargando miniatura...")
                self._load_featured_thumbnail(media_id)

    def _remove_featured_image(self):
        """Quita la imagen destacada."""
        self.featured_media_id = 0
        self.lbl_featured.setPixmap(QPixmap())
        self.lbl_featured.setText("Sin imagen destacada")

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

    def _load_seo_fields(self, post: dict):
        """Carga los datos SEO de Yoast desde un post."""
        seo = extract_yoast_data(post)
        self.txt_seo_title.setText(seo.get("seo_title", ""))
        self.txt_seo_description.setPlainText(seo.get("meta_description", ""))
        self.txt_seo_keyword.setText(seo.get("focus_keyword", ""))
        self.txt_seo_canonical.setText(seo.get("canonical_url", ""))
        self.txt_seo_og_title.setText(seo.get("og_title", ""))
        self.txt_seo_og_desc.setText(seo.get("og_description", ""))
        self.txt_seo_og_image.setText(seo.get("og_image", ""))
        self.chk_seo_noindex.setChecked(bool(seo.get("meta_robots_noindex", False)))
        self.chk_seo_nofollow.setChecked(bool(seo.get("meta_robots_nofollow", False)))

        # Mostrar/ocultar grupo SEO según Yoast esté activo
        self.seo_group.setVisible(has_yoast_seo(post))

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
        """Guarda el contenido actual como borrador offline (todos los campos)."""
        if not self.offline_manager:
            return

        data = self._gather_editor_data()
        post_id = self.current_post.get("id") if self.current_post else None
        draft_id = self.offline_manager.save_draft("post", data, post_id)
        title = data.get("title", "Sin título")
        self.status_label.setText(f"Borrador offline guardado: {draft_id}")
        QMessageBox.information(
            self, "Borrador Offline",
            f"La entrada «{title}» se ha guardado localmente.\n"
            "Se sincronizará automáticamente cuando se restablezca la conexión."
        )

    def _gather_editor_data(self):
        """Recopila TODOS los campos del editor en un dict serializable."""
        title = self.txt_title.text().strip() or "Sin título"

        # Estado
        status_map = {0: "draft", 1: "pending", 2: "publish", 3: "private"}
        status = status_map.get(self.combo_status.currentIndex(), "draft")

        # Formato
        format_map = {
            0: "standard", 1: "quote", 2: "status", 3: "chat",
            4: "gallery", 5: "link", 6: "image", 7: "video", 8: "audio"
        }
        post_format = format_map.get(self.combo_format.currentIndex(), "standard")

        # Categorías seleccionadas
        selected_cats = []
        def _collect_checked(parent_item):
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                if child.checkState(0) == Qt.CheckState.Checked:
                    cid = child.data(0, Qt.ItemDataRole.UserRole)
                    if cid is not None:
                        selected_cats.append(cid)
                _collect_checked(child)
        root = self.cat_tree.invisibleRootItem()
        _collect_checked(root)

        # Etiquetas (texto tal como está)
        tags_text = self.txt_tags.text().strip()

        # Fecha
        dt = self.date_edit.dateTime()
        date_str = dt.toString(Qt.DateFormat.ISODate)

        # SEO
        seo_data = self._get_seo_data()

        data = {
            "title": title,
            "content": self.editor.get_content(),
            "status": status,
            "excerpt": self.txt_excerpt.toPlainText(),
            "slug": self.txt_slug.text().strip(),
            "format_type": post_format,
            "sticky": self.chk_sticky.isChecked(),
            "password": self.txt_password.text(),
            "comment_status": "open" if self.chk_comments.isChecked() else "closed",
            "ping_status": "open" if self.chk_pings.isChecked() else "closed",
            "featured_media": self.featured_media_id,
            "categories": selected_cats,
            "tags_text": tags_text,
            "date": date_str,
        }
        if seo_data:
            data["seo"] = seo_data
        return data

    def _do_autosave(self):
        """Callback del timer: guarda el estado del editor localmente."""
        # Solo autoguardar si estamos en la vista de edición
        if self.stack.currentIndex() != 1:
            return
        title = self.txt_title.text().strip()
        content = self.editor.get_content()
        # No autoguardar si no hay título ni contenido
        if not title and not content:
            return
        try:
            data = self._gather_editor_data()
            post_id = self.current_post.get("id") if self.current_post else None
            save_autosave("post", data, post_id)
        except Exception:
            pass  # no interrumpir al usuario si falla el autosave

    def check_and_recover_autosave(self):
        """Comprueba si hay un autoguardado pendiente y ofrece recuperarlo.

        Debe llamarse después de que el widget esté listo (tras conectar).
        Returns:
            bool: True si se recuperó un borrador.
        """
        autosave = get_autosave("post")
        if not autosave:
            return False

        data = autosave.get("data", {})
        title = data.get("title", "Sin título")
        saved_at = autosave.get("saved_at", "")[:19].replace("T", " ")
        post_id = autosave.get("post_id")
        action = "edición" if post_id else "nueva entrada"

        reply = QMessageBox.question(
            self, "Recuperar borrador",
            f"Se encontró un borrador autoguardado:\n\n"
            f"  Título: {title}\n"
            f"  Tipo: {action}\n"
            f"  Guardado: {saved_at}\n\n"
            "¿Deseas recuperarlo para seguir editándolo?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # Construir un dict compatible con load_from_draft
            draft_compat = {
                "type": "post",
                "post_id": post_id,
                "data": data,
            }
            self.load_from_draft(draft_compat)
            clear_autosave("post")
            return True
        # Si el usuario declina, NO borramos el autoguardado para que
        # pueda recuperarlo después desde Archivo > Borradores Offline.
        return False

    def showEvent(self, a0):
        """Se ejecuta al mostrar el widget."""
        super().showEvent(a0)
        if self.stack.currentIndex() == 0:
            self.load_posts()

    def load_from_draft(self, draft):
        """Carga un borrador offline en el editor para continuar editándolo.

        Args:
            draft: dict con la estructura del borrador offline
                   {"id", "type", "post_id", "data": {...}, ...}
        """
        data = draft.get("data", {})
        post_id = draft.get("post_id")

        # Si es una edición de un post existente, guardamos la referencia mínima
        if post_id:
            self.current_post = {"id": post_id}
            self.edit_title_label.setText("Editar Entrada (borrador recuperado)")
            self.btn_delete_post.setVisible(True)
        else:
            self.current_post = None
            self.edit_title_label.setText("Nueva Entrada (borrador recuperado)")
            self.btn_delete_post.setVisible(False)

        self.txt_title.setText(data.get("title", ""))
        self.txt_slug.setText(data.get("slug", ""))

        content = data.get("content", "")
        self.editor.set_raw_html(content)

        self.txt_excerpt.setPlainText(data.get("excerpt", ""))

        # Estado
        status_map = {"draft": 0, "pending": 1, "publish": 2, "private": 3}
        self.combo_status.setCurrentIndex(
            status_map.get(data.get("status", "draft"), 0)
        )

        # Formato
        format_map = {
            "standard": 0, "quote": 1, "status": 2, "chat": 3,
            "gallery": 4, "link": 5, "image": 6, "video": 7, "audio": 8
        }
        self.combo_format.setCurrentIndex(
            format_map.get(data.get("format_type", "standard"), 0)
        )

        # Fecha: usar la guardada si existe, si no la actual
        date_str = data.get("date", "")
        if date_str:
            try:
                from dateutil import parser as dateutil_parser
                dt = dateutil_parser.parse(date_str)
                self.date_edit.setDateTime(QDateTime(
                    dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second
                ))
            except Exception:
                self.date_edit.setDateTime(QDateTime.currentDateTime())
        else:
            self.date_edit.setDateTime(QDateTime.currentDateTime())

        self.chk_sticky.setChecked(data.get("sticky", False))
        self.txt_password.setText(data.get("password", ""))
        self.chk_comments.setChecked(
            data.get("comment_status", "open") == "open"
        )
        self.chk_pings.setChecked(
            data.get("ping_status", "open") == "open"
        )

        # Imagen destacada
        self.featured_media_id = data.get("featured_media", 0)
        if self.featured_media_id:
            self.lbl_featured.setText(f"Imagen destacada (ID: {self.featured_media_id}) — cargando miniatura...")
            try:
                self._load_featured_thumbnail(self.featured_media_id)
            except Exception:
                self.lbl_featured.setText(f"Imagen destacada (ID: {self.featured_media_id})")
        else:
            self.lbl_featured.setText("Sin imagen destacada")
            self.lbl_featured.setPixmap(QPixmap())

        # Etiquetas: restaurar texto guardado
        tags_text = data.get("tags_text", "")
        self.txt_tags.setText(tags_text)

        # SEO: restaurar si hay datos guardados
        seo_data = data.get("seo", {})
        if seo_data:
            self.txt_seo_title.setText(seo_data.get("seo_title", ""))
            self.txt_seo_description.setPlainText(seo_data.get("meta_description", ""))
            self.txt_seo_keyword.setText(seo_data.get("focus_keyword", ""))
            self.txt_seo_canonical.setText(seo_data.get("canonical_url", ""))
            self.txt_seo_og_title.setText(seo_data.get("og_title", ""))
            self.txt_seo_og_desc.setText(seo_data.get("og_description", ""))
            self.txt_seo_og_image.setText(seo_data.get("og_image", ""))
            self.chk_seo_noindex.setChecked(bool(seo_data.get("meta_robots_noindex", False)))
            self.chk_seo_nofollow.setChecked(bool(seo_data.get("meta_robots_nofollow", False)))
        else:
            self._clear_seo_fields()

        self._load_categories(data.get("categories", []))
        self.stack.setCurrentIndex(1)

        # Iniciar autoguardado para el borrador recuperado
        self._autosave_timer.start(self._autosave_interval)

        # Guardar referencia al borrador offline para poder eliminarlo tras publicar
        self._loaded_offline_draft_id = draft.get("id")
        self.status_label.setText("Borrador recuperado y cargado en el editor")
