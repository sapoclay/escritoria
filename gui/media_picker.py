"""
Selector visual de imágenes de la biblioteca de medios de WordPress.
Muestra una cuadrícula de miniaturas y permite elegir una imagen
para usarla como imagen destacada u otro propósito.
"""
import requests as _requests
import urllib3 as _urllib3
_urllib3.disable_warnings(_urllib3.exceptions.InsecureRequestWarning)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QScrollArea, QWidget, QLineEdit, QMessageBox,
    QDialogButtonBox, QFrame, QFileDialog, QApplication,
    QGroupBox, QFormLayout, QTextEdit, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QImage, QCursor

from utils.screen_utils import get_dialog_size, scaled, get_scale_factor
from utils.helpers import strip_html, extract_rendered, is_valid_image_data


class _ThumbnailLoaderThread(QThread):
    """Descarga una miniatura en segundo plano."""
    finished = pyqtSignal(int, bytes)   # media_id, image_data
    error = pyqtSignal(int, str)        # media_id, error_msg

    def __init__(self, media_id: int, url: str, parent=None):
        super().__init__(parent)
        self.media_id = media_id
        self.url = url

    def run(self):
        try:
            session = _requests.Session()
            session.verify = False
            session.headers.update({
                "User-Agent": "WP-Desktop-Editor/1.0",
                "Accept": "image/*, */*",
            })
            resp = session.get(self.url, timeout=15)
            if resp.status_code == 200 and is_valid_image_data(resp.content):
                self.finished.emit(self.media_id, resp.content)
            else:
                self.error.emit(self.media_id, f"HTTP {resp.status_code}")
        except Exception as e:
            self.error.emit(self.media_id, str(e))


class _MediaListThread(QThread):
    """Carga la lista de medios (imágenes) desde la API."""
    finished = pyqtSignal(list, int)    # items, total_pages
    error = pyqtSignal(str)

    def __init__(self, media_api, page=1, per_page=18, search=None, parent=None):
        super().__init__(parent)
        self.media_api = media_api
        self.page = page
        self.per_page = per_page
        self.search = search

    def run(self):
        try:
            result = self.media_api.list(
                page=self.page,
                per_page=self.per_page,
                media_type="image",
                search=self.search or None,
            )
            if isinstance(result, dict) and "data" in result:
                items = result["data"]
                total_pages = result.get("total_pages", 1)
            elif isinstance(result, list):
                items = result
                total_pages = 1
            else:
                items = []
                total_pages = 1
            self.finished.emit(items, total_pages)
        except Exception as e:
            self.error.emit(str(e))


class _UploadThread(QThread):
    """Sube una imagen desde el disco local con metadatos SEO."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, media_api, file_path, title="", alt_text="",
                 caption="", description="", parent=None):
        super().__init__(parent)
        self.media_api = media_api
        self.file_path = file_path
        self.title = title
        self.alt_text = alt_text
        self.caption = caption
        self.description = description

    def run(self):
        try:
            result = self.media_api.upload(
                self.file_path,
                title=self.title or None,
                alt_text=self.alt_text,
                caption=self.caption,
                description=self.description,
            )
            # WordPress no siempre acepta alt_text en el upload;
            # lo aseguramos con un update posterior
            media_id = result.get("id", 0)
            if media_id and self.alt_text:
                try:
                    self.media_api.update(media_id, alt_text=self.alt_text)
                except Exception:
                    pass  # no crítico
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class MediaUploadDialog(QDialog):
    """Diálogo para rellenar metadatos SEO antes de subir una imagen."""

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Metadatos SEO de la imagen")
        self.setMinimumWidth(480)
        self._file_path = file_path
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        import os
        filename = os.path.basename(self._file_path)
        default_title = os.path.splitext(filename)[0].replace("-", " ").replace("_", " ")

        info = QLabel(f"Archivo: <b>{filename}</b>")
        info.setWordWrap(True)
        layout.addWidget(info)

        hint = QLabel(
            "Completa estos campos para mejorar el posicionamiento SEO de la imagen. "
            "El texto alternativo (ALT) es el más importante para la accesibilidad y el SEO."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa; font-size: 12px; margin-bottom: 4px;")
        layout.addWidget(hint)

        form = QGroupBox("Metadatos SEO")
        form_layout = QFormLayout(form)
        form_layout.setSpacing(6)

        # Título
        self.txt_title = QLineEdit(default_title)
        self.txt_title.setPlaceholderText("Título descriptivo de la imagen")
        self.txt_title.setToolTip(
            "Título de la imagen en la biblioteca de medios. "
            "Úsalo para describir brevemente el contenido."
        )
        form_layout.addRow("Título:", self.txt_title)

        # Texto alternativo (ALT) — el más importante para SEO
        self.txt_alt = QLineEdit()
        self.txt_alt.setPlaceholderText("Describe la imagen para buscadores y lectores de pantalla")
        self.txt_alt.setToolTip(
            "Texto alternativo (atributo ALT). Es el campo MÁS importante para SEO.\n"
            "Describe lo que muestra la imagen de forma concisa.\n"
            "Los buscadores y los lectores de pantalla para personas con\n"
            "discapacidad visual lo utilizan para entender la imagen."
        )
        alt_hint = QLabel("⚡ Campo clave para SEO y accesibilidad")
        alt_hint.setStyleSheet("color: #f0ad4e; font-size: 11px;")
        form_layout.addRow("Texto ALT:", self.txt_alt)
        form_layout.addRow("", alt_hint)

        # Leyenda (caption)
        self.txt_caption = QTextEdit()
        self.txt_caption.setMaximumHeight(60)
        self.txt_caption.setPlaceholderText("Leyenda visible bajo la imagen (opcional)")
        self.txt_caption.setToolTip(
            "Texto que se muestra debajo de la imagen en el artículo.\n"
            "Puede contener HTML básico. Ayuda a contextualizarla."
        )
        form_layout.addRow("Leyenda:", self.txt_caption)

        # Descripción
        self.txt_description = QTextEdit()
        self.txt_description.setMaximumHeight(60)
        self.txt_description.setPlaceholderText("Descripción larga de la imagen (opcional)")
        self.txt_description.setToolTip(
            "Descripción detallada del medio. Se usa como contenido de\n"
            "la página de adjunto en WordPress y puede ayudar al SEO."
        )
        form_layout.addRow("Descripción:", self.txt_description)

        layout.addWidget(form)

        # Botones
        btns = QHBoxLayout()
        btns.addStretch()
        btn_upload = QPushButton("⬆ Subir imagen")
        btn_upload.setStyleSheet(
            "QPushButton { background-color: #0073aa; color: white; "
            "padding: 6px 20px; border-radius: 3px; font-weight: bold; }"
            "QPushButton:hover { background-color: #005f8c; }"
        )
        btn_upload.clicked.connect(self.accept)
        btns.addWidget(btn_upload)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    # ── Getters ──

    def get_title(self) -> str:
        return self.txt_title.text().strip()

    def get_alt_text(self) -> str:
        return self.txt_alt.text().strip()

    def get_caption(self) -> str:
        return self.txt_caption.toPlainText().strip()

    def get_description(self) -> str:
        return self.txt_description.toPlainText().strip()


class _ImageLabel(QFrame):
    """Widget clickeable que muestra una miniatura con borde de selección."""
    clicked = pyqtSignal(int, str)  # media_id, title

    def __init__(self, media_id: int, title: str, thumb_size: int, parent=None):
        super().__init__(parent)
        self.media_id = media_id
        self.title = title
        self._selected = False
        self._thumb_size = thumb_size

        self.setFixedSize(thumb_size + 8, thumb_size + 30)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)

        self.img_label = QLabel()
        self.img_label.setFixedSize(thumb_size, thumb_size)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background-color: #2a2a2a; border-radius: 3px;")
        self.img_label.setText("⏳")
        layout.addWidget(self.img_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.name_label = QLabel(title[:20] + "…" if len(title) > 20 else title)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("font-size: 11px; color: #aaa;")
        self.name_label.setMaximumWidth(thumb_size)
        layout.addWidget(self.name_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self._update_style()

    def set_pixmap(self, pixmap: QPixmap):
        scaled_px = pixmap.scaled(
            self._thumb_size, self._thumb_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.img_label.setPixmap(scaled_px)

    def set_error(self):
        self.img_label.setText("❌")

    @property
    def selected(self):
        return self._selected

    @selected.setter
    def selected(self, value: bool):
        self._selected = value
        self._update_style()

    def _update_style(self):
        if self._selected:
            self.setStyleSheet(
                "QFrame { border: 2px solid #0073aa; border-radius: 5px; "
                "background-color: #1a3a4a; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { border: 2px solid transparent; border-radius: 5px; "
                "background-color: transparent; }"
                "QFrame:hover { border: 2px solid #464b50; background-color: #252525; }"
            )

    def mousePressEvent(self, event):  # type: ignore[override]
        self.clicked.emit(self.media_id, self.title)
        super().mousePressEvent(event)


class MediaPickerDialog(QDialog):
    """Diálogo para seleccionar una imagen de la biblioteca de medios de WordPress."""

    def __init__(self, media_api, parent=None):
        super().__init__(parent)
        self.media_api = media_api
        self._threads: list[QThread] = []
        self._image_labels: dict[int, _ImageLabel] = {}
        self._selected_id = 0
        self._selected_title = ""
        self._current_page = 1
        self._total_pages = 1

        self.setWindowTitle("Seleccionar imagen de la biblioteca")
        dlg_size = get_dialog_size(0.50, 0.65)
        self.setMinimumSize(dlg_size)
        self.resize(dlg_size)

        self._setup_ui()
        self._load_media()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Barra superior: búsqueda + subir ──
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar imágenes…")
        self.search_input.returnPressed.connect(self._on_search)
        top_bar.addWidget(self.search_input)

        self.btn_search = QPushButton("Buscar")
        self.btn_search.clicked.connect(self._on_search)
        top_bar.addWidget(self.btn_search)

        self.btn_upload = QPushButton("⬆ Subir imagen")
        self.btn_upload.setToolTip("Subir una imagen desde el disco")
        self.btn_upload.clicked.connect(self._upload_image)
        top_bar.addWidget(self.btn_upload)

        layout.addLayout(top_bar)

        # ── Estado ──
        self.status_label = QLabel("Cargando biblioteca de medios…")
        self.status_label.setStyleSheet("color: #aaa; font-size: 12px;")
        layout.addWidget(self.status_label)

        # ── Área de scroll con cuadrícula de imágenes ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; }")
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(8)
        self.scroll_area.setWidget(self.grid_container)
        layout.addWidget(self.scroll_area, stretch=1)

        # ── Paginación ──
        nav_bar = QHBoxLayout()
        self.btn_prev = QPushButton("← Anterior")
        self.btn_prev.clicked.connect(self._prev_page)
        self.btn_prev.setEnabled(False)
        nav_bar.addWidget(self.btn_prev)

        self.lbl_page = QLabel("Página 1")
        self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_bar.addWidget(self.lbl_page)

        self.btn_next = QPushButton("Siguiente →")
        self.btn_next.clicked.connect(self._next_page)
        self.btn_next.setEnabled(False)
        nav_bar.addWidget(self.btn_next)
        layout.addLayout(nav_bar)

        # ── Info de selección + botones aceptar/cancelar ──
        bottom = QHBoxLayout()
        self.lbl_selection = QLabel("Ninguna imagen seleccionada")
        self.lbl_selection.setStyleSheet("color: #ccc;")
        bottom.addWidget(self.lbl_selection, stretch=1)

        self.btn_ok = QPushButton("Aceptar")
        self.btn_ok.setEnabled(False)
        self.btn_ok.setStyleSheet(
            "QPushButton { background-color: #0073aa; color: white; "
            "padding: 6px 20px; border-radius: 3px; font-weight: bold; }"
            "QPushButton:hover { background-color: #005f8c; }"
            "QPushButton:disabled { background-color: #444; color: #888; }"
        )
        self.btn_ok.clicked.connect(self.accept)
        bottom.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(self.btn_cancel)

        layout.addLayout(bottom)

    # ── Carga de medios ──

    def _load_media(self, search=None):
        self.status_label.setText("Cargando imágenes…")
        self._clear_grid()
        t = _MediaListThread(
            self.media_api,
            page=self._current_page,
            per_page=18,
            search=search,
            parent=self,
        )
        t.finished.connect(self._on_media_loaded)
        t.error.connect(self._on_media_error)
        self._threads.append(t)
        t.start()

    def _on_media_loaded(self, items: list, total_pages: int):
        self._total_pages = total_pages
        self._update_nav()

        if not items:
            self.status_label.setText("No se encontraron imágenes.")
            return

        self.status_label.setText(f"{len(items)} imágenes — Página {self._current_page}/{total_pages}")

        sf = get_scale_factor()
        thumb_size = scaled(120, sf)
        viewport = self.scroll_area.viewport()
        vp_width = viewport.width() if viewport else 600
        cols = max(1, (vp_width - 20) // (thumb_size + 16))

        for idx, media in enumerate(items):
            media_id = media.get("id", 0)
            raw_title = media.get("title", {})
            if isinstance(raw_title, dict):
                title = raw_title.get("rendered", raw_title.get("raw", f"ID {media_id}"))
            else:
                title = str(raw_title) if raw_title else f"ID {media_id}"
            # Limpiar tags HTML del título
            import re
            title = re.sub(r'<[^>]+>', '', title).strip() or f"ID {media_id}"

            img_label = _ImageLabel(media_id, title, thumb_size)
            img_label.clicked.connect(self._on_image_clicked)
            self._image_labels[media_id] = img_label

            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(img_label, row, col, alignment=Qt.AlignmentFlag.AlignTop)

            # Buscar URL de miniatura
            sizes = media.get("media_details", {}).get("sizes", {})
            thumb_url = None
            for size_key in ("thumbnail", "medium", "medium_large"):
                if size_key in sizes:
                    thumb_url = sizes[size_key].get("source_url")
                    if thumb_url:
                        break
            if not thumb_url:
                thumb_url = media.get("source_url", "")

            if thumb_url:
                t = _ThumbnailLoaderThread(media_id, thumb_url, parent=self)
                t.finished.connect(self._on_thumb_loaded)
                t.error.connect(self._on_thumb_error)
                self._threads.append(t)
                t.start()
            else:
                img_label.set_error()

    def _on_media_error(self, error: str):
        self.status_label.setText(f"Error: {error}")

    def _on_thumb_loaded(self, media_id: int, data: bytes):
        label = self._image_labels.get(media_id)
        if label is None:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if not pixmap.isNull():
            label.set_pixmap(pixmap)
        else:
            label.set_error()

    def _on_thumb_error(self, media_id: int, error: str):
        label = self._image_labels.get(media_id)
        if label:
            label.set_error()

    # ── Selección ──

    def _on_image_clicked(self, media_id: int, title: str):
        # Deseleccionar anterior
        for lbl in self._image_labels.values():
            lbl.selected = False
        # Seleccionar nuevo
        if media_id in self._image_labels:
            self._image_labels[media_id].selected = True
        self._selected_id = media_id
        self._selected_title = title
        self.lbl_selection.setText(f"Seleccionada: {title} (ID: {media_id})")
        self.btn_ok.setEnabled(True)

    # ── Paginación ──

    def _update_nav(self):
        self.lbl_page.setText(f"Página {self._current_page}/{self._total_pages}")
        self.btn_prev.setEnabled(self._current_page > 1)
        self.btn_next.setEnabled(self._current_page < self._total_pages)

    def _prev_page(self):
        if self._current_page > 1:
            self._current_page -= 1
            self._load_media(search=self.search_input.text().strip() or None)

    def _next_page(self):
        if self._current_page < self._total_pages:
            self._current_page += 1
            self._load_media(search=self.search_input.text().strip() or None)

    # ── Búsqueda ──

    def _on_search(self):
        self._current_page = 1
        self._load_media(search=self.search_input.text().strip() or None)

    # ── Subida ──

    def _upload_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen para subir", "",
            "Imágenes (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.svg);;Todos (*)"
        )
        if not file_path:
            return

        # Mostrar diálogo de metadatos SEO antes de subir
        seo_dlg = MediaUploadDialog(file_path, parent=self)
        if seo_dlg.exec_() != QDialog.Accepted:
            return

        self.status_label.setText("Subiendo imagen…")
        self.btn_upload.setEnabled(False)
        t = _UploadThread(
            self.media_api, file_path,
            title=seo_dlg.get_title(),
            alt_text=seo_dlg.get_alt_text(),
            caption=seo_dlg.get_caption(),
            description=seo_dlg.get_description(),
            parent=self,
        )
        t.finished.connect(self._on_upload_done)
        t.error.connect(self._on_upload_error)
        self._threads.append(t)
        t.start()

    def _on_upload_done(self, result: dict):
        self.btn_upload.setEnabled(True)
        media_id = result.get("id", 0)
        self.status_label.setText(f"Imagen subida (ID: {media_id}). Recargando…")
        # Seleccionar automáticamente la imagen subida
        self._selected_id = media_id
        raw_title = result.get("title", {})
        if isinstance(raw_title, dict):
            self._selected_title = raw_title.get("rendered", f"ID {media_id}")
        else:
            self._selected_title = str(raw_title) or f"ID {media_id}"
        # Recargar la cuadrícula para que aparezca
        self._current_page = 1
        self._load_media()

    def _on_upload_error(self, error: str):
        self.btn_upload.setEnabled(True)
        self.status_label.setText(f"Error al subir: {error}")
        QMessageBox.warning(self, "Error de subida", error)

    # ── Utilidades ──

    def _clear_grid(self):
        self._image_labels.clear()
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

    # ── Limpieza segura de hilos ──

    def _stop_all_threads(self):
        """Desconecta señales y espera a que todos los hilos terminen."""
        for t in self._threads:
            # Desconectar todas las señales para evitar callbacks tardíos
            try:
                t.disconnect()
            except TypeError:
                pass
            # Esperar a que termine (máx 2 s por hilo)
            if t.isRunning():
                t.quit()
                t.wait(2000)
                if t.isRunning():
                    t.terminate()
                    t.wait(1000)
        self._threads.clear()

    def reject(self):
        """Sobrescribe reject para limpiar hilos antes de cerrar."""
        self._stop_all_threads()
        super().reject()

    def accept(self):
        """Sobrescribe accept para limpiar hilos antes de cerrar."""
        self._stop_all_threads()
        super().accept()

    def closeEvent(self, a0):
        """Limpieza de hilos al cerrar la ventana."""
        self._stop_all_threads()
        super().closeEvent(a0)

    def get_selected_media_id(self) -> int:
        """Devuelve el ID del medio seleccionado (0 si ninguno)."""
        return self._selected_id

    def get_selected_title(self) -> str:
        """Devuelve el título del medio seleccionado."""
        return self._selected_title
