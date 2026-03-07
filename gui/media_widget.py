"""
Widget de gestión de Medios (Biblioteca de Medios) de WordPress.
Subida, visualización y eliminación de archivos multimedia.
Todas las operaciones de red se ejecutan en hilos secundarios.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QMessageBox, QComboBox,
    QHeaderView, QAbstractItemView, QFileDialog, QProgressBar,
    QGroupBox, QFormLayout, QTextEdit, QDialog, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap
from utils.helpers import format_date, strip_html, extract_rendered, is_valid_image_data
from utils.worker import WorkerThread
from utils.screen_utils import get_scale_factor, scaled, get_dialog_size
from gui.media_picker import MediaUploadDialog
import os
import requests
from io import BytesIO


class UploadThread(QThread):
    """Hilo para subir archivos."""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, media_api, file_path, title, caption, alt_text, description):
        super().__init__()
        self.media_api = media_api
        self.file_path = file_path
        self.title = title
        self.caption = caption
        self.alt_text = alt_text
        self.description = description

    def run(self):
        try:
            result = self.media_api.upload(
                self.file_path,
                title=self.title,
                caption=self.caption,
                alt_text=self.alt_text,
                description=self.description
            )
            # Asegurar que alt_text se guarda (algunos WP lo ignoran en upload)
            media_id = result.get("id", 0)
            if media_id and self.alt_text:
                try:
                    self.media_api.update(media_id, alt_text=self.alt_text)
                except Exception:
                    pass  # no crítico
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ImageLoaderThread(QThread):
    """Hilo para cargar una imagen desde URL sin bloquear la UI."""
    finished = pyqtSignal(bytes)
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            headers = {"User-Agent": "WP-Desktop-Editor/1.0"}
            resp = requests.get(
                self.url, timeout=20, headers=headers,
                verify=True, allow_redirects=True
            )
            if resp.status_code == 200 and is_valid_image_data(resp.content):
                self.finished.emit(resp.content)
            else:
                self.error.emit(f"HTTP {resp.status_code}")
        except requests.exceptions.SSLError:
            # Reintentar sin verificación SSL
            try:
                resp = requests.get(
                    self.url, timeout=20, headers=headers,
                    verify=False, allow_redirects=True
                )
                if resp.status_code == 200 and is_valid_image_data(resp.content):
                    self.finished.emit(resp.content)
                else:
                    self.error.emit(f"HTTP {resp.status_code} (sin SSL)")
            except Exception as e2:
                self.error.emit(f"SSL: {e2}")
        except Exception as e:
            self.error.emit(str(e))


class MediaDetailDialog(QDialog):
    """Diálogo de detalles de un medio."""

    def __init__(self, media_api, media_data, parent=None):
        super().__init__(parent)
        self.media_api = media_api
        self.media = media_data
        self._threads = []
        self.setWindowTitle("Detalles del Medio")
        dlg_size = get_dialog_size(0.38, 0.52)
        self.setMinimumSize(dlg_size)
        self.resize(dlg_size)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        source_url = self.media.get("source_url", "")
        mime = self.media.get("mime_type", "")

        self.preview_label = None
        if mime.startswith("image/") and source_url:
            self.preview_label = QLabel("Cargando imagen...")
            self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview_label.setMinimumHeight(100)
            self.preview_label.setMaximumHeight(350)
            layout.addWidget(self.preview_label)
            # Cargar imagen en hilo separado
            loader = ImageLoaderThread(source_url)
            loader.finished.connect(self._on_image_loaded)
            loader.error.connect(self._on_image_error)
            self._threads.append(loader)
            loader.start()
        elif source_url:
            # Para archivos no-imagen, mostrar un enlace a la URL
            link_label = QLabel(f'<a href="{source_url}">Abrir archivo en navegador</a>')
            link_label.setOpenExternalLinks(True)
            link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(link_label)

        form = QGroupBox("Información del Medio")
        form_layout = QFormLayout(form)

        self.txt_title = QLineEdit(strip_html(extract_rendered(self.media.get("title", ""))))
        form_layout.addRow("Título:", self.txt_title)

        self.txt_caption = QTextEdit()
        self.txt_caption.setMaximumHeight(60)
        self.txt_caption.setPlainText(strip_html(extract_rendered(self.media.get("caption", ""))))
        form_layout.addRow("Leyenda:", self.txt_caption)

        self.txt_alt = QLineEdit(self.media.get("alt_text", ""))
        form_layout.addRow("Texto alt:", self.txt_alt)

        self.txt_description = QTextEdit()
        self.txt_description.setMaximumHeight(60)
        self.txt_description.setPlainText(strip_html(extract_rendered(self.media.get("description", ""))))
        form_layout.addRow("Descripción:", self.txt_description)

        url_label = QLabel(source_url)
        url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        url_label.setWordWrap(True)
        form_layout.addRow("URL:", url_label)

        form_layout.addRow("Tipo:", QLabel(mime))
        form_layout.addRow("Fecha:", QLabel(format_date(self.media.get("date", ""))))
        form_layout.addRow("ID:", QLabel(str(self.media.get("id", ""))))

        layout.addWidget(form)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        btns = QHBoxLayout()
        btn_save = QPushButton("Guardar cambios")
        btn_save.setObjectName("btnSuccess")
        btn_save.clicked.connect(self._save)
        btns.addWidget(btn_save)

        btn_delete = QPushButton("Eliminar")
        btn_delete.setObjectName("btnDanger")
        btn_delete.clicked.connect(self._delete)
        btns.addWidget(btn_delete)

        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.reject)
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def _on_image_loaded(self, data):
        if not self.preview_label:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data) or pixmap.isNull():
            self.preview_label.setText("No se pudo decodificar la imagen")
            return
        # Escalar al ancho disponible del diálogo
        max_w = max(self.width() - 40, 200)
        max_h = 350
        scaled = pixmap.scaled(
            max_w, max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.preview_label.setPixmap(scaled)

    def _on_image_error(self, error_msg):
        if self.preview_label:
            self.preview_label.setText(
                f"No se pudo cargar la vista previa.\n{error_msg}"
            )

    def _save(self):
        self.status_label.setText("Guardando...")
        mid = self.media["id"]
        title = self.txt_title.text()
        caption = self.txt_caption.toPlainText()
        alt_text = self.txt_alt.text()
        description = self.txt_description.toPlainText()
        t = WorkerThread(
            lambda: self.media_api.update(
                mid, title=title, caption=caption,
                alt_text=alt_text, description=description
            )
        )
        t.finished.connect(lambda _r: self._on_saved())
        t.error.connect(lambda e: self._on_error(e))
        self._threads.append(t)
        t.start()

    def _on_saved(self):
        self.status_label.setText("")
        QMessageBox.information(self, "Éxito", "Medio actualizado.")
        self.accept()

    def _delete(self):
        reply = QMessageBox.question(
            self, "Confirmar", "¿Eliminar este medio permanentemente?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status_label.setText("Eliminando...")
            mid = self.media["id"]
            t = WorkerThread(lambda: self.media_api.delete(mid))
            t.finished.connect(lambda _r: self._on_deleted())
            t.error.connect(lambda e: self._on_error(e))
            self._threads.append(t)
            t.start()

    def _on_deleted(self):
        self.status_label.setText("")
        QMessageBox.information(self, "Éxito", "Medio eliminado.")
        self.done(2)

    def _on_error(self, error):
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", str(error))


class MediaWidget(QWidget):
    """Widget para gestionar la biblioteca de medios."""

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api = api_client
        from api.media import MediaAPI
        self.media_api = MediaAPI(api_client)
        self.current_page = 1
        self.total_pages = 1
        self._threads = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        header = QHBoxLayout()
        title = QLabel("Biblioteca de Medios")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()

        self.btn_upload = QPushButton("Subir Archivo")
        self.btn_upload.setObjectName("btnSuccess")
        self.btn_upload.clicked.connect(self._upload_file)
        header.addWidget(self.btn_upload)
        layout.addLayout(header)

        filters = QHBoxLayout()
        self.filter_type = QComboBox()
        self.filter_type.addItems(["Todos", "Imágenes", "Vídeos", "Audio", "Documentos"])
        self.filter_type.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(QLabel("Tipo:"))
        filters.addWidget(self.filter_type)

        self.filter_search = QLineEdit()
        self.filter_search.setPlaceholderText("Buscar medios...")
        self.filter_search.returnPressed.connect(self._apply_filters)
        filters.addWidget(self.filter_search)

        btn_search = QPushButton("Buscar")
        btn_search.clicked.connect(self._apply_filters)
        filters.addWidget(btn_search)

        btn_refresh = QPushButton("Actualizar")
        btn_refresh.clicked.connect(self.load_media)
        filters.addWidget(btn_refresh)
        layout.addLayout(filters)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Archivo", "Tipo", "Autor", "Fecha", "Tamaño", "Acciones"
        ])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            for i in range(1, 5):
                header.setSectionResizeMode(
                    i, QHeaderView.ResizeToContents
                )
            # Columna Acciones: ancho fijo suficiente para los botones
            header.setSectionResizeMode(5, QHeaderView.Fixed)
            self.table.setColumnWidth(5, 160)
        # Altura de fila por defecto suficiente para botones
        v_header = self.table.verticalHeader()
        if v_header is not None:
            v_header.setDefaultSectionSize(80)
            v_header.setMinimumSectionSize(80)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self._show_details)
        layout.addWidget(self.table)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.lbl_pagination = QLabel("Página 1 de 1")
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

    def load_media(self):
        self.status_label.setText("Cargando medios...")
        self.table.setRowCount(0)

        type_map = {0: None, 1: "image", 2: "video", 3: "audio", 4: "application"}
        media_type = type_map.get(self.filter_type.currentIndex())
        search = self.filter_search.text().strip() or None

        t = WorkerThread(
            lambda: self.media_api.list(
                page=self.current_page, per_page=20,
                search=search, media_type=media_type
            )
        )
        t.finished.connect(self._on_media_loaded)
        t.error.connect(self._on_load_error)
        self._threads.append(t)
        t.start()

    def _on_media_loaded(self, result):
        items = result.get("data", []) if isinstance(result, dict) else result
        total = result.get("total", 0) if isinstance(result, dict) else len(items)
        self.total_pages = result.get("total_pages", 1) if isinstance(result, dict) else 1

        self.table.setRowCount(len(items))
        for row, media in enumerate(items):
            title = strip_html(extract_rendered(media.get("title", "")))
            filename = media.get("source_url", "").split("/")[-1] if media.get("source_url") else title
            name_item = QTableWidgetItem(filename)
            name_item.setData(Qt.ItemDataRole.UserRole, media)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(media.get("mime_type", "")))
            self.table.setItem(row, 2, QTableWidgetItem(str(media.get("author", ""))))
            self.table.setItem(row, 3, QTableWidgetItem(format_date(media.get("date", ""))))

            details = media.get("media_details", {})
            size = details.get("filesize", 0)
            if size:
                if size > 1048576:
                    size_str = f"{size / 1048576:.1f} MB"
                elif size > 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size} B"
            else:
                size_str = "-"
            self.table.setItem(row, 4, QTableWidgetItem(size_str))

            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(4, 4, 4, 4)
            al.setSpacing(6)
            btn_view = QPushButton("Ver")
            btn_view.setMinimumHeight(28)
            btn_view.clicked.connect(lambda c, m=media: self._show_media_detail(m))
            al.addWidget(btn_view)
            btn_del = QPushButton("Borrar")
            btn_del.setMinimumHeight(28)
            btn_del.setObjectName("btnDanger")
            mid = media.get("id")
            btn_del.clicked.connect(lambda c, m=mid: self._delete_media(m))
            al.addWidget(btn_del)
            self.table.setCellWidget(row, 5, actions)

        self.lbl_pagination.setText(f"Página {self.current_page} de {self.total_pages} ({total} archivos)")
        self.btn_prev.setEnabled(self.current_page > 1)
        self.btn_next.setEnabled(self.current_page < self.total_pages)
        self.status_label.setText(f"{total} archivos cargados")

    def _on_load_error(self, error):
        self.status_label.setText(f"Error: {error}")

    def _apply_filters(self):
        self.current_page = 1
        self.load_media()

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_media()

    def _next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_media()

    def _upload_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Archivo",
            "", "Todos los archivos (*);;Imágenes (*.jpg *.jpeg *.png *.gif *.webp);;Documentos (*.pdf *.doc *.docx);;Vídeos (*.mp4 *.avi *.mov)"
        )
        if not file_path:
            return

        # Mostrar diálogo de metadatos SEO antes de subir
        seo_dlg = MediaUploadDialog(file_path, parent=self)
        if seo_dlg.exec_() != QDialog.Accepted:
            return

        filename = os.path.basename(file_path)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status_label.setText(f"Subiendo {filename}...")

        thread = UploadThread(
            self.media_api, file_path,
            title=seo_dlg.get_title(),
            caption=seo_dlg.get_caption(),
            alt_text=seo_dlg.get_alt_text(),
            description=seo_dlg.get_description(),
        )
        thread.finished.connect(self._on_upload_finished)
        thread.error.connect(self._on_upload_error)
        self._threads.append(thread)
        thread.start()

    def _on_upload_finished(self, result):
        self.progress.setVisible(False)
        title = strip_html(extract_rendered(result.get("title", "")))
        self.status_label.setText(f"Archivo \'{title}\' subido correctamente")
        QMessageBox.information(self, "Éxito", f"Archivo subido:\n{title}")
        self.load_media()

    def _on_upload_error(self, error):
        self.progress.setVisible(False)
        self.status_label.setText(f"Error al subir: {error}")
        QMessageBox.critical(self, "Error", f"Error al subir archivo:\n{error}")

    def _show_details(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        media = item.data(Qt.ItemDataRole.UserRole)
        if media:
            self._show_media_detail(media)

    def _show_media_detail(self, media):
        dialog = MediaDetailDialog(self.media_api, media, self)
        result = dialog.exec_()
        if result in (1, 2):
            self.load_media()

    def _delete_media(self, media_id):
        reply = QMessageBox.question(
            self, "Confirmar", "¿Eliminar este archivo permanentemente?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status_label.setText("Eliminando...")
            t = WorkerThread(lambda: self.media_api.delete(media_id))
            t.finished.connect(lambda _r: self._on_delete_done())
            t.error.connect(lambda e: self._on_delete_error(e))
            self._threads.append(t)
            t.start()

    def _on_delete_done(self):
        self.load_media()

    def _on_delete_error(self, error):
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", str(error))

    def showEvent(self, a0):
        super().showEvent(a0)
        self.load_media()
