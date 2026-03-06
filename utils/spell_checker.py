"""
Corrector ortográfico para el editor de contenido.
Usa pyspellchecker para detectar palabras mal escritas y ofrecer sugerencias.
Soporta múltiples idiomas (español, inglés, etc.).
"""
import re
from PyQt5.QtCore import Qt
from PyQt5.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextCursor
)
from PyQt5.QtWidgets import QMenu, QAction

try:
    from spellchecker import SpellChecker as PySpellChecker
    HAS_SPELLCHECKER = True
except ImportError:
    PySpellChecker = None  # type: ignore[misc]
    HAS_SPELLCHECKER = False


# Patrón para extraer palabras (ignora HTML, URLs, números)
WORD_PATTERN = re.compile(
    r'(?<![<\w/="\':])(?<!\w[:/])(?<![&])'  # No dentro de HTML / URL
    r'\b([a-záàâãéèêíïóôõöúüçñA-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÜÇÑ]{2,})\b'
    r'(?![^<]*>)',  # No dentro de etiquetas HTML
    re.UNICODE
)

# Patrones a ignorar (URLs, emails, HTML tags)
IGNORE_PATTERNS = [
    re.compile(r'https?://\S+'),
    re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),
    re.compile(r'<[^>]+>'),
    re.compile(r'&\w+;'),  # HTML entities
    re.compile(r'#[0-9a-fA-F]{3,8}'),  # Colores hex
]


class SpellCheckHighlighter(QSyntaxHighlighter):
    """
    Resaltador de sintaxis que subraya palabras con errores ortográficos.
    Se usa sobre un QTextEdit para marcar las palabras mal escritas.
    """

    def __init__(self, parent=None, language="es"):
        super().__init__(parent)
        self._enabled = True
        self._language = language
        self._custom_words = set()
        self._spell = None
        self._ignored_ranges = []

        # Formato de subrayado ondulado rojo
        self._error_format = QTextCharFormat()
        self._error_format.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.SpellCheckUnderline
        )
        self._error_format.setUnderlineColor(QColor("#e74c3c"))

        self._init_checker(language)

    def _init_checker(self, language):
        """Inicializa el corrector para el idioma dado."""
        if not HAS_SPELLCHECKER:
            self._enabled = False
            return

        try:
            self._spell = PySpellChecker(language=language)  # type: ignore[misc]
            self._language = language
        except Exception:
            # Fallback a inglés si el idioma no está disponible
            try:
                self._spell = PySpellChecker(language="en")  # type: ignore[misc]
                self._language = "en"
            except Exception:
                self._enabled = False

    @property
    def enabled(self):
        return self._enabled and self._spell is not None

    @enabled.setter
    def enabled(self, value):
        self._enabled = value
        self.rehighlight()

    @property
    def language(self):
        return self._language

    @language.setter
    def language(self, lang):
        self._init_checker(lang)
        self.rehighlight()

    def add_word(self, word):
        """Añade una palabra al diccionario personalizado."""
        word_lower = word.lower()
        self._custom_words.add(word_lower)
        if self._spell:
            self._spell.word_frequency.load_words([word_lower])
        self.rehighlight()

    def remove_word(self, word):
        """Elimina una palabra del diccionario personalizado."""
        self._custom_words.discard(word.lower())
        self.rehighlight()

    def is_misspelled(self, word):
        """Comprueba si una palabra está mal escrita."""
        if not self.enabled or not self._spell or not word or len(word) < 2:
            return False

        word_lower = word.lower()

        # No marcar palabras del diccionario personalizado
        if word_lower in self._custom_words:
            return False

        # No marcar palabras que son solo mayúsculas (acrónimos)
        if word.isupper():
            return False

        # Consultar el corrector
        misspelled = self._spell.unknown([word_lower])
        return word_lower in misspelled

    def get_suggestions(self, word, max_suggestions=7):
        """Obtiene sugerencias de corrección para una palabra."""
        if not self.enabled or not self._spell or not word:
            return []

        candidates = self._spell.candidates(word.lower())
        if not candidates:
            return []

        # Ordenar por probabilidad/distancia
        suggestions = list(candidates)[:max_suggestions]

        # Mantener capitalización original
        if word[0].isupper():
            suggestions = [s.capitalize() for s in suggestions]

        return suggestions

    def highlightBlock(self, text):
        """Resalta las palabras mal escritas en un bloque de texto."""
        if not self.enabled or not text:
            return

        # Encontrar rangos a ignorar (URLs, HTML, etc.)
        ignore_ranges = set()
        for pattern in IGNORE_PATTERNS:
            for match in pattern.finditer(text):
                for i in range(match.start(), match.end()):
                    ignore_ranges.add(i)

        # Buscar y verificar cada palabra
        for match in WORD_PATTERN.finditer(text):
            start = match.start(1)
            word = match.group(1)

            # Saltar si está en rango ignorado
            if start in ignore_ranges:
                continue

            if self.is_misspelled(word):
                self.setFormat(start, len(word), self._error_format)


class SpellCheckMixin:
    """
    Mixin para añadir corrección ortográfica a un QTextEdit.
    Agrega menú contextual con sugerencias y opciones de diccionario.
    Debe mezclarse con QTextEdit.
    """

    def init_spell_check(self, language="es"):
        """Inicializa la corrección ortográfica."""
        self._spell_highlighter = SpellCheckHighlighter(
            self.document(), language  # type: ignore[attr-defined]
        )
        # Guardar referencia para acceder desde fuera
        self.spell_highlighter = self._spell_highlighter

    def contextMenuEvent(self, event):
        """Menú contextual con sugerencias ortográficas."""
        menu = self.createStandardContextMenu()  # type: ignore[attr-defined]

        cursor = self.cursorForPosition(event.pos())  # type: ignore[attr-defined]
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText().strip()

        if (
            word
            and hasattr(self, '_spell_highlighter')
            and self._spell_highlighter.enabled
            and self._spell_highlighter.is_misspelled(word)
        ):
            # Separador antes de las sugerencias
            menu.insertSeparator(menu.actions()[0] if menu.actions() else None)

            # Sugerencias
            suggestions = self._spell_highlighter.get_suggestions(word)
            if suggestions:
                spell_menu = QMenu(f"📝 Sugerencias para «{word}»", menu)
                spell_menu.setStyleSheet(
                    "QMenu { background-color: #2c3e50; color: #ecf0f1; }"
                    "QMenu::item:selected { background-color: #0073aa; }"
                )
                for suggestion in suggestions:
                    action = spell_menu.addAction(suggestion)
                    # Captura por defecto
                    if action is not None:
                        action.triggered.connect(
                            lambda checked, s=suggestion, c=cursor:
                                self._replace_word(c, s)
                        )
                menu.insertMenu(menu.actions()[0], spell_menu)
            else:
                no_sugg = QAction("❌ Sin sugerencias", menu)
                no_sugg.setEnabled(False)
                menu.insertAction(menu.actions()[0], no_sugg)

            # Añadir al diccionario
            add_action = QAction(f"➕ Añadir «{word}» al diccionario", menu)
            add_action.triggered.connect(
                lambda: self._spell_highlighter.add_word(word)
            )
            menu.insertAction(menu.actions()[0], add_action)

            menu.insertSeparator(menu.actions()[0])

        menu.exec_(event.globalPos())

    def _replace_word(self, cursor, replacement):
        """Reemplaza la palabra seleccionada por la sugerencia."""
        cursor.beginEditBlock()
        cursor.removeSelectedText()
        cursor.insertText(replacement)
        cursor.endEditBlock()


def get_available_languages():
    """Devuelve los idiomas disponibles para el corrector."""
    if not HAS_SPELLCHECKER:
        return []

    # Idiomas soportados por pyspellchecker
    available = []
    test_langs = ["es", "en", "fr", "de", "pt", "it"]
    for lang in test_langs:
        try:
            PySpellChecker(language=lang)  # type: ignore[misc]
            available.append(lang)
        except Exception:
            pass
    return available


LANGUAGE_NAMES = {
    "es": "Español",
    "en": "English",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
    "it": "Italiano",
}
