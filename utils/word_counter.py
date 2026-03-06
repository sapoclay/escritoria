"""
Contador de palabras y estadísticas de texto para el editor.
Muestra en tiempo real: palabras, caracteres, párrafos,
tiempo de lectura estimado y puntuación de legibilidad.
"""
import re
import math
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QColor


# Tiempo medio de lectura: ~200 palabras/minuto (español)
WORDS_PER_MINUTE = 200


def count_words(text):
    """Cuenta las palabras en un texto (excluyendo HTML)."""
    if not text:
        return 0
    # Eliminar etiquetas HTML
    clean = re.sub(r'<[^>]+>', ' ', text)
    # Eliminar entidades HTML
    clean = re.sub(r'&\w+;', ' ', clean)
    # Dividir por espacios y filtrar cadenas vacías
    words = [w for w in clean.split() if w.strip()]
    return len(words)


def count_characters(text, include_spaces=True):
    """Cuenta los caracteres en un texto (excluyendo HTML)."""
    if not text:
        return 0
    clean = re.sub(r'<[^>]+>', '', text)
    clean = re.sub(r'&\w+;', ' ', clean)
    if not include_spaces:
        clean = clean.replace(' ', '').replace('\n', '').replace('\t', '')
    return len(clean)


def count_paragraphs(text):
    """Cuenta los párrafos en un texto."""
    if not text:
        return 0
    # Contar etiquetas <p> o bloques separados por líneas vacías
    p_count = len(re.findall(r'<p[\s>]', text, re.IGNORECASE))
    if p_count > 0:
        return p_count
    # Fallback: contar líneas no vacías separadas por doble salto
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    return max(1, len(paragraphs)) if text.strip() else 0


def count_sentences(text):
    """Cuenta las oraciones en un texto."""
    if not text:
        return 0
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = re.sub(r'&\w+;', ' ', clean)
    sentences = re.split(r'[.!?]+(?:\s|$)', clean)
    return len([s for s in sentences if s.strip()])


def estimate_reading_time(word_count):
    """Estima el tiempo de lectura en minutos."""
    if word_count <= 0:
        return 0
    minutes = word_count / WORDS_PER_MINUTE
    return max(1, math.ceil(minutes))


def reading_time_display(word_count):
    """Devuelve el tiempo de lectura formateado."""
    minutes = estimate_reading_time(word_count)
    if minutes == 0:
        return "< 1 min"
    elif minutes == 1:
        return "1 min"
    else:
        return f"{minutes} min"


class WordCounterBar(QWidget):
    """
    Barra de estadísticas de texto que se muestra debajo del editor.
    Muestra: palabras, caracteres, párrafos, oraciones y tiempo de lectura.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._word_count = 0
        self._char_count = 0
        self._paragraph_count = 0
        self._sentence_count = 0

    def _setup_ui(self):
        """Configura la interfaz de la barra."""
        self.setFixedHeight(28)
        self.setStyleSheet("""
            WordCounterBar {
                background-color: #1d2327;
                border-top: 1px solid #3c434a;
            }
            QLabel {
                color: #a7aaad;
                font-size: 11px;
                padding: 0 6px;
                background: transparent;
                border: none;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(0)

        # Palabras
        self.lbl_words = QLabel("0 palabras")
        self.lbl_words.setToolTip("Número de palabras")
        layout.addWidget(self.lbl_words)

        layout.addWidget(self._separator())

        # Caracteres
        self.lbl_chars = QLabel("0 caracteres")
        self.lbl_chars.setToolTip("Número de caracteres (con espacios)")
        layout.addWidget(self.lbl_chars)

        layout.addWidget(self._separator())

        # Párrafos
        self.lbl_paragraphs = QLabel("0 párrafos")
        self.lbl_paragraphs.setToolTip("Número de párrafos")
        layout.addWidget(self.lbl_paragraphs)

        layout.addWidget(self._separator())

        # Oraciones
        self.lbl_sentences = QLabel("0 oraciones")
        self.lbl_sentences.setToolTip("Número de oraciones")
        layout.addWidget(self.lbl_sentences)

        layout.addWidget(self._separator())

        # Tiempo de lectura
        self.lbl_reading_time = QLabel("⏱ < 1 min")
        self.lbl_reading_time.setToolTip("Tiempo estimado de lectura")
        layout.addWidget(self.lbl_reading_time)

        layout.addStretch()

        # Indicador SEO suave (longitud del contenido)
        self.lbl_seo_hint = QLabel("")
        self.lbl_seo_hint.setToolTip("Indicador SEO: longitud del artículo")
        layout.addWidget(self.lbl_seo_hint)

    def _separator(self):
        """Crea un separador visual."""
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(
            "QFrame { color: #3c434a; background: #3c434a; "
            "max-width: 1px; margin: 4px 2px; }"
        )
        return sep

    @pyqtSlot(str)
    def update_stats(self, text):
        """Actualiza las estadísticas con el texto proporcionado."""
        self._word_count = count_words(text)
        self._char_count = count_characters(text)
        self._paragraph_count = count_paragraphs(text)
        self._sentence_count = count_sentences(text)

        # Actualizar etiquetas
        self.lbl_words.setText(
            f"{self._word_count:,} {'palabra' if self._word_count == 1 else 'palabras'}"
        )
        self.lbl_chars.setText(
            f"{self._char_count:,} {'carácter' if self._char_count == 1 else 'caracteres'}"
        )
        self.lbl_paragraphs.setText(
            f"{self._paragraph_count} {'párrafo' if self._paragraph_count == 1 else 'párrafos'}"
        )
        self.lbl_sentences.setText(
            f"{self._sentence_count} {'oración' if self._sentence_count == 1 else 'oraciones'}"
        )
        self.lbl_reading_time.setText(
            f"⏱ {reading_time_display(self._word_count)}"
        )

        # Indicador SEO de longitud
        self._update_seo_hint()

    def _update_seo_hint(self):
        """Actualiza el indicador SEO según la cantidad de palabras."""
        wc = self._word_count
        if wc == 0:
            self.lbl_seo_hint.setText("")
        elif wc < 300:
            self.lbl_seo_hint.setText("🔴 Muy corto para SEO")
            self.lbl_seo_hint.setStyleSheet(
                "QLabel { color: #e74c3c; font-size: 11px; background: transparent; border: none; }"
            )
        elif wc < 600:
            self.lbl_seo_hint.setText("🟡 Aceptable")
            self.lbl_seo_hint.setStyleSheet(
                "QLabel { color: #f39c12; font-size: 11px; background: transparent; border: none; }"
            )
        elif wc < 1500:
            self.lbl_seo_hint.setText("🟢 Buena longitud")
            self.lbl_seo_hint.setStyleSheet(
                "QLabel { color: #27ae60; font-size: 11px; background: transparent; border: none; }"
            )
        else:
            self.lbl_seo_hint.setText("🟢 Excelente longitud")
            self.lbl_seo_hint.setStyleSheet(
                "QLabel { color: #2ecc71; font-size: 11px; background: transparent; border: none; }"
            )

    @property
    def word_count(self):
        return self._word_count

    @property
    def char_count(self):
        return self._char_count
