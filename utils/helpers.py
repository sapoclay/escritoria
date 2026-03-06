"""
Utilidades comunes para la aplicación.
"""
from datetime import datetime
from dateutil import parser as dateutil_parser
import html
import re


def format_date(date_string, fmt="%d/%m/%Y %H:%M"):
    """Formatea una fecha de WordPress a formato legible."""
    if not date_string:
        return ""
    try:
        dt = dateutil_parser.parse(date_string)
        return dt.strftime(fmt)
    except (ValueError, TypeError):
        return date_string


def strip_html(text):
    """Elimina las etiquetas HTML de un texto."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    return html.unescape(clean).strip()


def truncate(text, max_length=100):
    """Trunca un texto a una longitud máxima."""
    if not text or len(text) <= max_length:
        return text or ""
    return text[:max_length].rsplit(" ", 1)[0] + "..."


def get_status_display(status):
    """Devuelve el nombre de estado legible."""
    statuses = {
        "publish": "Publicado",
        "draft": "Borrador",
        "pending": "Pendiente",
        "private": "Privado",
        "future": "Programado",
        "trash": "Papelera",
        "inherit": "Heredado",
        "approved": "Aprobado",
        "hold": "Pendiente",
        "spam": "Spam",
    }
    return statuses.get(status, status.capitalize() if status else "")


def get_status_color(status):
    """Devuelve un color para el estado."""
    colors = {
        "publish": "#28a745",
        "draft": "#6c757d",
        "pending": "#ffc107",
        "private": "#6f42c1",
        "future": "#17a2b8",
        "trash": "#dc3545",
        "approved": "#28a745",
        "hold": "#ffc107",
        "spam": "#dc3545",
    }
    return colors.get(status, "#6c757d")


def extract_rendered(obj, field="rendered"):
    """Extrae el valor rendered de un campo de la API de WP."""
    if isinstance(obj, dict):
        if field in obj:
            return obj[field]
        if "raw"in obj:
            return obj["raw"]
    return str(obj) if obj else ""


def wp_date_to_iso(date_string):
    """Convierte una fecha a formato ISO para la API de WP."""
    if not date_string:
        return None
    try:
        dt = dateutil_parser.parse(date_string)
        return dt.isoformat()
    except (ValueError, TypeError):
        return None


def build_excerpt(content, max_length=200):
    """Crea un extracto a partir del contenido."""
    text = strip_html(content)
    return truncate(text, max_length)
