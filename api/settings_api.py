"""
API de Ajustes de WordPress.
Gestiona la configuración general del sitio.
"""


class SettingsAPI:
    """Gestiona los ajustes del sitio WordPress."""

    def __init__(self, client):
        self.client = client

    def get(self):
        """Obtiene todos los ajustes del sitio."""
        return self.client.get("settings")

    def update(self, **kwargs):
        """Actualiza los ajustes del sitio."""
        return self.client.post("settings", data=kwargs)

    def get_title(self):
        """Obtiene el título del sitio."""
        settings = self.get()
        return settings.get("title", "")

    def set_title(self, title):
        """Establece el título del sitio."""
        return self.update(title=title)

    def get_description(self):
        """Obtiene la descripción del sitio."""
        settings = self.get()
        return settings.get("description", "")

    def set_description(self, description):
        """Establece la descripción del sitio."""
        return self.update(description=description)

    def get_site_info(self):
        """Obtiene información general del sitio vía wp-json root."""
        try:
            url = f"{self.client.site_url}/wp-json"
            response = self.client.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception:
            return {}

    def get_post_types(self):
        """Obtiene los tipos de contenido disponibles."""
        return self.client.get("types")

    def get_taxonomies(self):
        """Obtiene las taxonomías disponibles."""
        return self.client.get("taxonomies")

    def get_plugins(self):
        """Obtiene la lista de plugins (requiere permisos de admin)."""
        try:
            url = f"{self.client.site_url}/wp-json/wp/v2/plugins"
            response = self.client.session.get(url, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception:
            return []

    def get_themes(self):
        """Obtiene la lista de temas (requiere permisos de admin)."""
        try:
            url = f"{self.client.site_url}/wp-json/wp/v2/themes"
            response = self.client.session.get(url, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception:
            return []
