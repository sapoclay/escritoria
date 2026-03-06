"""
Editor de contenido enriquecido para WordPress.
Editor HTML con barra de herramientas, vista previa,
corrector ortográfico y contador de palabras.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPlainTextEdit,
    QPushButton, QTabWidget, QToolBar, QAction, QFontComboBox,
    QSpinBox, QColorDialog, QFileDialog, QLabel, QComboBox,
    QInputDialog, QMessageBox, QMenu
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QUrl as _QUrl, QThread
from PyQt5.QtGui import (
    QFont, QTextCharFormat, QColor, QTextCursor,
    QKeySequence, QIcon, QImage, QTextDocument
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from utils.screen_utils import get_scale_factor, scaled
from utils.word_counter import WordCounterBar
from utils.spell_checker import (
    SpellCheckHighlighter, SpellCheckMixin, HAS_SPELLCHECKER,
    get_available_languages, LANGUAGE_NAMES
)
import requests as _requests
import urllib3 as _urllib3
_urllib3.disable_warnings(_urllib3.exceptions.InsecureRequestWarning)


def _make_download_session() -> _requests.Session:
    """Crea una sesión HTTP robusta para descargar imágenes."""
    s = _requests.Session()
    s.verify = False
    s.headers.update({
        "User-Agent": "WP-Desktop-Editor/1.0",
        "Accept": "image/*, */*",
    })
    # Reintentos automáticos ante errores de conexión
    adapter = _requests.adapters.HTTPAdapter(
        max_retries=_urllib3.util.retry.Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        )
    )
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


class _ImageDownloadThread(QThread):
    """Hilo para descargar una imagen remota sin bloquear la UI."""
    finished = pyqtSignal(str, bytes)   # url, data
    error = pyqtSignal(str)             # url

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            session = _make_download_session()
            resp = session.get(self._url, timeout=20)
            if resp.status_code == 200 and resp.content:
                self.finished.emit(self._url, resp.content)
            else:
                self.error.emit(self._url)
        except Exception:
            self.error.emit(self._url)


class SpellCheckTextEdit(SpellCheckMixin, QTextEdit):
    """QTextEdit con corrección ortográfica e imágenes remotas (asíncronas)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_cache: dict[str, QImage] = {}
        self._pending_urls: set[str] = set()
        self._download_threads: list[_ImageDownloadThread] = []

    def loadResource(self, resource_type: int, url) -> object:  # type: ignore[override]
        """Devuelve imágenes remotas desde caché o lanza descarga asíncrona."""
        if resource_type == QTextDocument.ResourceType.ImageResource:
            qurl = url if isinstance(url, _QUrl) else _QUrl(url)
            url_str = qurl.toString()
            if qurl.scheme() in ("http", "https"):
                # Desde caché
                if url_str in self._image_cache:
                    return self._image_cache[url_str]
                # Lanzar descarga asíncrona (solo una vez por URL)
                if url_str not in self._pending_urls:
                    self._pending_urls.add(url_str)
                    t = _ImageDownloadThread(url_str, self)
                    t.finished.connect(self._on_image_downloaded)
                    t.error.connect(self._on_image_error)
                    self._download_threads.append(t)
                    t.start()
                # Devolver imagen transparente de 1×1 como placeholder
                placeholder = QImage(1, 1, QImage.Format.Format_ARGB32)
                placeholder.fill(QColor(0, 0, 0, 0))
                return placeholder
        return super().loadResource(resource_type, url)

    def _on_image_downloaded(self, url_str: str, data: bytes) -> None:
        """Inserta la imagen descargada en el documento y refresca."""
        self._pending_urls.discard(url_str)
        image = QImage()
        image.loadFromData(data)
        if image.isNull():
            return
        # Escalar si es más ancha que el editor
        max_w = self.viewport().width() - 20
        if max_w > 0 and image.width() > max_w:
            image = image.scaledToWidth(
                max_w, Qt.TransformationMode.SmoothTransformation
            )
        self._image_cache[url_str] = image
        doc = self.document()
        if doc is not None:
            doc.addResource(
                QTextDocument.ResourceType.ImageResource,
                _QUrl(url_str), image
            )
            # Refrescar cada vez que se descarga una imagen para mostrarla
            self._refresh_content()

    def _on_image_error(self, url_str: str) -> None:
        self._pending_urls.discard(url_str)

    def _refresh_content(self) -> None:
        """Fuerza un re-renderizado del documento para mostrar imágenes."""
        doc = self.document()
        if doc is None:
            return
        cursor = self.textCursor()
        pos = cursor.position()
        self.blockSignals(True)
        # Re-iterar todos los bloques: buscar imágenes y forzar su recarga
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    if fmt.isImageFormat():
                        img_fmt = fmt.toImageFormat()
                        url_str = img_fmt.name()
                        if url_str in self._image_cache:
                            doc.addResource(
                                QTextDocument.ResourceType.ImageResource,
                                _QUrl(url_str),
                                self._image_cache[url_str]
                            )
                it += 1
            block = block.next()
        # Señalar al layout que el contenido cambió para re-renderizar
        doc.markContentsDirty(0, doc.characterCount())
        self.viewport().update()
        cursor = self.textCursor()
        cursor.setPosition(min(pos, max(0, doc.characterCount() - 1)))
        self.setTextCursor(cursor)
        self.blockSignals(False)


class ContentEditor(QWidget):
    """Editor de contenido con soporte para HTML visual y código fuente."""

    content_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._is_updating = False
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(400)
        self._update_timer.timeout.connect(self._update_word_count)

    def _setup_ui(self):
        """Configura la interfaz del editor."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Barra de herramientas
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        self.toolbar.setStyleSheet("""
            QToolBar {
                background-color: #32373c;
                border: 1px solid #464b50;
                padding: 3px;
                spacing: 2px;
            }
            QToolBar QToolButton {
                background-color: transparent;
                color: #e0e0e0;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 13px;
                min-width: 28px;
            }
            QToolBar QToolButton:hover {
                background-color: #464b50;
                border: 1px solid #5a5f64;
            }
            QToolBar QToolButton:pressed {
                background-color: #0073aa;
            }
        """)
        self._setup_toolbar()
        layout.addWidget(self.toolbar)

        # Tabs: Visual / HTML / Vista previa
        self.tabs = QTabWidget()

        # Tab Visual (WYSIWYG) con corrector ortográfico
        sf = get_scale_factor()
        self.visual_editor = SpellCheckTextEdit()
        self.visual_editor.setAcceptRichText(True)
        self.visual_editor.setMinimumHeight(scaled(250, sf))
        self.visual_editor.textChanged.connect(self._on_visual_changed)

        # Inicializar corrector ortográfico
        if HAS_SPELLCHECKER:
            self.visual_editor.init_spell_check("es")
            self._spell_enabled = True
        else:
            self._spell_enabled = False

        self.tabs.addTab(self.visual_editor, "Visual")

        # Tab HTML
        self.html_editor = QPlainTextEdit()
        self.html_editor.setMinimumHeight(scaled(250, sf))
        font = QFont("Consolas, Monaco, monospace", 12)
        self.html_editor.setFont(font)
        self.html_editor.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        self.html_editor.textChanged.connect(self._on_html_changed)
        self.tabs.addTab(self.html_editor, "HTML")

        # Tab Vista previa
        try:
            self.preview = QWebEngineView()
            self.tabs.addTab(self.preview, "Vista previa")
            self._has_preview = True
        except Exception:
            self.preview_text = QTextEdit()
            self.preview_text.setReadOnly(True)
            self.tabs.addTab(self.preview_text, "Vista previa")
            self._has_preview = False

        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)

        # Barra de contador de palabras
        self.word_counter = WordCounterBar()
        layout.addWidget(self.word_counter)

    def _setup_toolbar(self):
        """Configura la barra de herramientas del editor."""
        # Negrita
        bold_action = QAction("B", self)
        bold_action.setToolTip("Negrita (Ctrl+B)")
        bold_action.setShortcut(QKeySequence.Bold)
        bold_action.triggered.connect(self._toggle_bold)
        f = bold_action.font()
        f.setBold(True)
        bold_action.setFont(f)
        self.toolbar.addAction(bold_action)

        # Cursiva
        italic_action = QAction("I", self)
        italic_action.setToolTip("Cursiva (Ctrl+I)")
        italic_action.setShortcut(QKeySequence.Italic)
        italic_action.triggered.connect(self._toggle_italic)
        f = italic_action.font()
        f.setItalic(True)
        italic_action.setFont(f)
        self.toolbar.addAction(italic_action)

        # Subrayado
        underline_action = QAction("U", self)
        underline_action.setToolTip("Subrayado (Ctrl+U)")
        underline_action.setShortcut(QKeySequence.Underline)
        underline_action.triggered.connect(self._toggle_underline)
        f = underline_action.font()
        f.setUnderline(True)
        underline_action.setFont(f)
        self.toolbar.addAction(underline_action)

        # Tachado
        strike_action = QAction("S̶", self)
        strike_action.setToolTip("Tachado")
        strike_action.triggered.connect(self._toggle_strikethrough)
        self.toolbar.addAction(strike_action)

        self.toolbar.addSeparator()

        # Encabezados
        self.heading_combo = QComboBox()
        self.heading_combo.addItems([
            "Párrafo", "Encabezado 1", "Encabezado 2", "Encabezado 3",
            "Encabezado 4", "Encabezado 5", "Encabezado 6"
        ])
        self.heading_combo.setMaximumWidth(140)
        self.heading_combo.currentIndexChanged.connect(self._set_heading)
        self.toolbar.addWidget(self.heading_combo)

        self.toolbar.addSeparator()

        # Listas
        ul_action = QAction("• Lista", self)
        ul_action.setToolTip("Lista con viñetas")
        ul_action.triggered.connect(self._insert_unordered_list)
        self.toolbar.addAction(ul_action)

        ol_action = QAction("1. Lista", self)
        ol_action.setToolTip("Lista numerada")
        ol_action.triggered.connect(self._insert_ordered_list)
        self.toolbar.addAction(ol_action)

        self.toolbar.addSeparator()

        # Enlace
        link_action = QAction("Enlace", self)
        link_action.setToolTip("Insertar enlace")
        link_action.triggered.connect(self._insert_link)
        self.toolbar.addAction(link_action)

        # Imagen
        img_action = QAction("Imagen", self)
        img_action.setToolTip("Insertar imagen")
        img_action.triggered.connect(self._insert_image)
        self.toolbar.addAction(img_action)

        self.toolbar.addSeparator()

        # Alinear
        align_left = QAction("Left", self)
        align_left.setToolTip("Alinear a la izquierda")
        align_left.triggered.connect(lambda: self._set_alignment(Qt.AlignmentFlag.AlignLeft))
        self.toolbar.addAction(align_left)

        align_center = QAction("Center", self)
        align_center.setToolTip("Centrar")
        align_center.triggered.connect(lambda: self._set_alignment(Qt.AlignmentFlag.AlignCenter))
        self.toolbar.addAction(align_center)

        align_right = QAction("Right", self)
        align_right.setToolTip("Alinear a la derecha")
        align_right.triggered.connect(lambda: self._set_alignment(Qt.AlignmentFlag.AlignRight))
        self.toolbar.addAction(align_right)

        self.toolbar.addSeparator()

        # Color de texto
        color_action = QAction("Color", self)
        color_action.setToolTip("Color de texto")
        color_action.triggered.connect(self._change_text_color)
        self.toolbar.addAction(color_action)

        # Cita
        quote_action = QAction("❝", self)
        quote_action.setToolTip("Insertar cita (blockquote)")
        quote_action.triggered.connect(self._insert_blockquote)
        self.toolbar.addAction(quote_action)

        # Código
        code_action = QAction("</>", self)
        code_action.setToolTip("Insertar código")
        code_action.triggered.connect(self._insert_code)
        self.toolbar.addAction(code_action)

        # Línea horizontal
        hr_action = QAction("—", self)
        hr_action.setToolTip("Línea horizontal")
        hr_action.triggered.connect(self._insert_hr)
        self.toolbar.addAction(hr_action)

        # Separador antes de herramientas adicionales
        self.toolbar.addSeparator()

        # Corrector ortográfico toggle
        if HAS_SPELLCHECKER:
            self.spell_action = QAction("✓ Abc", self)
            self.spell_action.setToolTip("Activar/Desactivar corrector ortográfico")
            self.spell_action.setCheckable(True)
            self.spell_action.setChecked(True)
            self.spell_action.triggered.connect(self._toggle_spell_check)
            self.toolbar.addAction(self.spell_action)

            # Selector de idioma del corrector
            self.spell_lang_combo = QComboBox()
            self.spell_lang_combo.setMaximumWidth(100)
            self.spell_lang_combo.setToolTip("Idioma del corrector ortográfico")
            langs = get_available_languages()
            for lang in langs:
                name = LANGUAGE_NAMES.get(lang, lang)
                self.spell_lang_combo.addItem(name, lang)
            # Seleccionar español por defecto
            idx = self.spell_lang_combo.findData("es")
            if idx >= 0:
                self.spell_lang_combo.setCurrentIndex(idx)
            self.spell_lang_combo.currentIndexChanged.connect(
                self._change_spell_language
            )
            self.toolbar.addWidget(self.spell_lang_combo)

    # ---- Acciones del editor ----

    def _toggle_spell_check(self, checked):
        """Activa o desactiva el corrector ortográfico."""
        if hasattr(self.visual_editor, 'spell_highlighter'):
            self.visual_editor.spell_highlighter.enabled = checked
            self._spell_enabled = checked

    def _change_spell_language(self, index):
        """Cambia el idioma del corrector ortográfico."""
        if not hasattr(self, 'spell_lang_combo'):
            return
        lang = self.spell_lang_combo.itemData(index)
        if lang and hasattr(self.visual_editor, 'spell_highlighter'):
            self.visual_editor.spell_highlighter.language = lang

    def _update_word_count(self):
        """Actualiza el contador de palabras."""
        content = self.get_content()
        self.word_counter.update_stats(content)

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        cursor = self.visual_editor.textCursor()
        current = cursor.charFormat()
        weight = QFont.Normal if current.fontWeight() == QFont.Bold else QFont.Bold
        fmt.setFontWeight(weight)
        cursor.mergeCharFormat(fmt)
        self.visual_editor.setTextCursor(cursor)

    def _toggle_italic(self):
        fmt = QTextCharFormat()
        cursor = self.visual_editor.textCursor()
        fmt.setFontItalic(not cursor.charFormat().fontItalic())
        cursor.mergeCharFormat(fmt)
        self.visual_editor.setTextCursor(cursor)

    def _toggle_underline(self):
        fmt = QTextCharFormat()
        cursor = self.visual_editor.textCursor()
        fmt.setFontUnderline(not cursor.charFormat().fontUnderline())
        cursor.mergeCharFormat(fmt)
        self.visual_editor.setTextCursor(cursor)

    def _toggle_strikethrough(self):
        fmt = QTextCharFormat()
        cursor = self.visual_editor.textCursor()
        fmt.setFontStrikeOut(not cursor.charFormat().fontStrikeOut())
        cursor.mergeCharFormat(fmt)
        self.visual_editor.setTextCursor(cursor)

    def _set_heading(self, index):
        cursor = self.visual_editor.textCursor()
        if index == 0:
            # Párrafo normal
            block_fmt = cursor.blockFormat()
            block_fmt.setHeadingLevel(0)
            cursor.setBlockFormat(block_fmt)
            fmt = QTextCharFormat()
            fmt.setFontPointSize(13)
            fmt.setFontWeight(QFont.Normal)
            cursor.mergeCharFormat(fmt)
        else:
            sizes = {1: 24, 2: 20, 3: 16, 4: 14, 5: 12, 6: 11}
            block_fmt = cursor.blockFormat()
            block_fmt.setHeadingLevel(index)
            cursor.setBlockFormat(block_fmt)
            fmt = QTextCharFormat()
            fmt.setFontPointSize(sizes.get(index, 13))
            fmt.setFontWeight(QFont.Bold)
            cursor.mergeCharFormat(fmt)
        self.visual_editor.setTextCursor(cursor)

    def _insert_unordered_list(self):
        cursor = self.visual_editor.textCursor()
        cursor.insertHtml("<ul><li>&nbsp;</li></ul>")

    def _insert_ordered_list(self):
        cursor = self.visual_editor.textCursor()
        cursor.insertHtml("<ol><li>&nbsp;</li></ol>")

    def _insert_link(self):
        url, ok = QInputDialog.getText(self, "Insertar Enlace", "URL:")
        if ok and url:
            text, ok2 = QInputDialog.getText(
                self, "Texto del Enlace",
                "Texto a mostrar:", text=url
            )
            if ok2:
                cursor = self.visual_editor.textCursor()
                cursor.insertHtml(f'<a href="{url}">{text}</a>')

    def _insert_image(self):
        url, ok = QInputDialog.getText(self, "Insertar Imagen", "URL de la imagen:")
        if ok and url:
            alt, ok2 = QInputDialog.getText(
                self, "Texto Alternativo",
                "Texto alt:"
            )
            if ok2:
                cursor = self.visual_editor.textCursor()
                cursor.insertHtml(f'<img src="{url}"alt="{alt}" />')

    def _set_alignment(self, alignment):
        cursor = self.visual_editor.textCursor()
        block_fmt = cursor.blockFormat()
        block_fmt.setAlignment(alignment)
        cursor.mergeBlockFormat(block_fmt)
        self.visual_editor.setTextCursor(cursor)

    def _change_text_color(self):
        color = QColorDialog.getColor(QColor("#ffffff"), self, "Color de Texto")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            cursor = self.visual_editor.textCursor()
            cursor.mergeCharFormat(fmt)
            self.visual_editor.setTextCursor(cursor)

    def _insert_blockquote(self):
        cursor = self.visual_editor.textCursor()
        selected = cursor.selectedText()
        if selected:
            cursor.insertHtml(f'<blockquote>{selected}</blockquote>')
        else:
            cursor.insertHtml('<blockquote>Cita...</blockquote>')

    def _insert_code(self):
        cursor = self.visual_editor.textCursor()
        selected = cursor.selectedText()
        if selected:
            cursor.insertHtml(f'<code>{selected}</code>')
        else:
            cursor.insertHtml('<code>código</code>')

    def _insert_hr(self):
        cursor = self.visual_editor.textCursor()
        cursor.insertHtml('<hr />')

    # ---- Sincronización de tabs ----

    def _on_visual_changed(self):
        if not self._is_updating:
            self.content_changed.emit()
            self._update_timer.start()

    def _on_html_changed(self):
        if not self._is_updating:
            self.content_changed.emit()
            self._update_timer.start()

    def _on_tab_changed(self, index):
        self._is_updating = True
        try:
            if index == 0:
                # Cambiando a Visual desde HTML
                html_content = self.html_editor.toPlainText()
                if html_content:
                    self.visual_editor.setHtml(html_content)
            elif index == 1:
                # Cambiando a HTML desde Visual: mantener el HTML limpio
                # No sobrescribir con toHtml() de Qt que añade estilos inline
                pass
            elif index == 2:
                # Vista previa
                html_content = self.get_content()
                preview_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body {{
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                            max-width: 800px; margin: 20px auto; padding: 20px;
                            background: #fff; color: #333; line-height: 1.6;
                        }}
                        img {{ max-width: 100%; height: auto; }}
                        blockquote {{
                            border-left: 4px solid #0073aa; margin: 1em 0;
                            padding: 0.5em 1em; background: #f9f9f9;
                        }}
                        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
                        pre {{ background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }}
                        a {{ color: #0073aa; }}
                        table {{ border-collapse: collapse; width: 100%; }}
                        td, th {{ border: 1px solid #ddd; padding: 8px; }}
                    </style>
                </head>
                <body>{html_content}</body>
                </html>
                """
                if self._has_preview:
                    self.preview.setHtml(preview_html)
                else:
                    self.preview_text.setHtml(html_content)
        finally:
            self._is_updating = False

    # ---- API Pública ----

    def get_content(self):
        """Obtiene el contenido HTML del editor.

        Siempre devuelve el HTML limpio (del editor de código).
        Así se preserva el formato original de WordPress y se evita
        enviar el HTML enriquecido que genera Qt (con doctype e inline styles).
        """
        current_tab = self.tabs.currentIndex()
        if current_tab == 0:
            # Si estamos en Visual, sincronizar primero al editor HTML
            # pero usar el raw html almacenado que es el original de WordPress
            pass
        # Siempre devolver el HTML limpio
        return self.html_editor.toPlainText()

    def set_content(self, html_content):
        """Establece el contenido HTML en el editor."""
        self._is_updating = True
        try:
            self.html_editor.setPlainText(html_content or "")
            self.visual_editor.setHtml(html_content or "")
        finally:
            self._is_updating = False
        self._update_timer.start()

    def get_raw_html(self):
        """Obtiene el HTML directamente del editor HTML."""
        return self.html_editor.toPlainText()

    def set_raw_html(self, html_content):
        """Establece HTML directamente en el editor HTML."""
        self._is_updating = True
        try:
            self.html_editor.setPlainText(html_content or "")
            self.visual_editor.setHtml(html_content or "")
        finally:
            self._is_updating = False
        self._update_timer.start()

    def clear(self):
        """Limpia el editor."""
        self._is_updating = True
        try:
            self.visual_editor.clear()
            self.html_editor.clear()
        finally:
            self._is_updating = False
        self.word_counter.update_stats("")
