"""
Cliente base para la API REST de WordPress.
Maneja autenticación, peticiones HTTP y manejo de errores.
"""
import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import urljoin
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class WordPressAPIError(Exception):
    """Error personalizado para errores de la API de WordPress."""
    def __init__(self, message, status_code=None, response_data=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class WordPressClient:
    """Cliente base para comunicarse con la API REST de WordPress."""

    def __init__(self, site_url, username, app_password):
        self.site_url = site_url.rstrip("/")
        self.api_base = f"{self.site_url}/wp-json/wp/v2"
        self.username = username
        self.app_password = app_password
        self.session = requests.Session()
        self.session.verify = False
        self.session.auth = HTTPBasicAuth(username, app_password)
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "WP-Desktop-Editor/1.0",
        })
        self.timeout = 30

    def _build_url(self, endpoint):
        """Construye la URL completa para un endpoint."""
        endpoint = endpoint.lstrip("/")
        return f"{self.api_base}/{endpoint}"

    def _handle_response(self, response):
        """Procesa la respuesta de la API."""
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            error_data = None
            try:
                error_data = response.json()
                message = error_data.get("message", str(response.status_code))
            except (ValueError, KeyError):
                message = f"Error HTTP {response.status_code}"
            raise WordPressAPIError(
                message,
                status_code=response.status_code,
                response_data=error_data,
            )

        if response.status_code == 204:
            return None

        try:
            data = response.json()
        except ValueError:
            data = response.text

        # Extraer información de paginación de los headers
        total = response.headers.get("X-WP-Total")
        total_pages = response.headers.get("X-WP-TotalPages")

        if total is not None:
            return {
                "data": data,
                "total": int(total),
                "total_pages": int(total_pages) if total_pages else 1,
            }

        return data

    def get(self, endpoint, params=None):
        """Realiza una petición GET."""
        url = self._build_url(endpoint)
        response = self.session.get(url, params=params, timeout=self.timeout)
        return self._handle_response(response)

    def post(self, endpoint, data=None, files=None):
        """Realiza una petición POST."""
        url = self._build_url(endpoint)
        if files:
            # Para subida de archivos, no usar JSON
            headers = {k: v for k, v in self.session.headers.items()
                       if k != "Content-Type"}
            response = self.session.post(
                url, data=data, files=files,
                headers=headers, timeout=self.timeout
            )
        else:
            response = self.session.post(url, json=data, timeout=self.timeout)
        return self._handle_response(response)

    def put(self, endpoint, data=None):
        """Realiza una petición PUT."""
        url = self._build_url(endpoint)
        response = self.session.put(url, json=data, timeout=self.timeout)
        return self._handle_response(response)

    def delete(self, endpoint, params=None):
        """Realiza una petición DELETE."""
        url = self._build_url(endpoint)
        if params is None:
            params = {}
        params["force"] = True
        response = self.session.delete(url, params=params, timeout=self.timeout)
        return self._handle_response(response)

    def test_connection(self):
        """Prueba la conexión al sitio WordPress."""
        try:
            url = f"{self.site_url}/wp-json"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            site_info = response.json()
            return {
                "success": True,
                "name": site_info.get("name", ""),
                "description": site_info.get("description", ""),
                "url": site_info.get("url", ""),
                "gmt_offset": site_info.get("gmt_offset", 0),
                "timezone_string": site_info.get("timezone_string", ""),
            }
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "No se puede conectar al servidor"}
        except requests.exceptions.Timeout:
            return {"success": False, "error": "Tiempo de espera agotado"}
        except requests.exceptions.HTTPError as e:
            return {"success": False, "error": f"Error HTTP: {e.response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_current_user(self):
        """Obtiene la información del usuario actual autenticado."""
        return self.get("users/me?context=edit")
