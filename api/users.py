"""
API de Usuarios de WordPress.
"""


class UsersAPI:
    """Gestiona las operaciones con usuarios."""

    def __init__(self, client):
        self.client = client

    def list(self, page=1, per_page=20, search=None, roles=None,
             orderby="name", order="asc"):
        """Lista los usuarios."""
        params = {
            "page": page,
            "per_page": per_page,
            "orderby": orderby,
            "order": order,
            "context": "edit",
        }
        if search:
            params["search"] = search
        if roles:
            params["roles"] = ",".join(roles) if isinstance(roles, list) else roles

        return self.client.get("users", params=params)

    def get(self, user_id):
        """Obtiene un usuario por ID."""
        return self.client.get(f"users/{user_id}?context=edit")

    def get_me(self):
        """Obtiene el usuario actual."""
        return self.client.get("users/me?context=edit")

    def create(self, username, email, password, first_name="",
               last_name="", nickname="", roles=None, description="",
               url=""):
        """Crea un nuevo usuario."""
        data = {
            "username": username,
            "email": email,
            "password": password,
            "first_name": first_name,
            "last_name": last_name,
        }
        if nickname:
            data["nickname"] = nickname
        if roles:
            data["roles"] = roles
        if description:
            data["description"] = description
        if url:
            data["url"] = url

        return self.client.post("users", data=data)

    def update(self, user_id, **kwargs):
        """Actualiza un usuario."""
        return self.client.post(f"users/{user_id}", data=kwargs)

    def delete(self, user_id, reassign_to=None):
        """Elimina un usuario."""
        params = {"force": True}
        if reassign_to:
            params["reassign"] = reassign_to
        return self.client.delete(f"users/{user_id}", params=params)

    def get_roles(self):
        """Devuelve los roles disponibles en WordPress."""
        return [
            {"slug": "administrator", "name": "Administrador"},
            {"slug": "editor", "name": "Editor"},
            {"slug": "author", "name": "Autor"},
            {"slug": "contributor", "name": "Colaborador"},
            {"slug": "subscriber", "name": "Suscriptor"},
        ]
