"""
Configuración de la aplicación ESCritORIA.
Gestiona las conexiones guardadas y preferencias del usuario.
"""
import json
import os
from pathlib import Path


APP_NAME = "ESCritORIA"
APP_VERSION = "1.0.0"
CONFIG_DIR = Path.home() / ".escritoria"
CONFIG_FILE = CONFIG_DIR / "config.json"
CONNECTIONS_FILE = CONFIG_DIR / "connections.json"


DEFAULT_CONFIG = {
    "theme": "dark",
    "language": "es",
    "editor_font_size": 14,
    "posts_per_page": 20,
    "auto_save_interval": 60,
    "last_connection": None,
    "window_geometry": None,
}


def ensure_config_dir():
    """Crea el directorio de configuración si no existe."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    """Carga la configuración de la aplicación."""
    ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                merged = {**DEFAULT_CONFIG, **config}
                return merged
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config):
    """Guarda la configuración de la aplicación."""
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def load_connections():
    """Carga las conexiones guardadas."""
    ensure_config_dir()
    if CONNECTIONS_FILE.exists():
        try:
            with open(CONNECTIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def save_connections(connections):
    """Guarda las conexiones."""
    ensure_config_dir()
    with open(CONNECTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(connections, f, indent=2, ensure_ascii=False)


def add_connection(name, url, username, app_password):
    """Añade una nueva conexión."""
    connections = load_connections()
    url = url.rstrip("/")
    connection = {
        "name": name,
        "url": url,
        "username": username,
        "app_password": app_password,
    }
    # Evitar duplicados por nombre
    connections = [c for c in connections if c["name"] != name]
    connections.append(connection)
    save_connections(connections)
    return connection


def remove_connection(name):
    """Elimina una conexión por nombre."""
    connections = load_connections()
    connections = [c for c in connections if c["name"] != name]
    save_connections(connections)


def get_connection(name):
    """Obtiene una conexión por nombre."""
    connections = load_connections()
    for conn in connections:
        if conn["name"] == name:
            return conn
    return None
