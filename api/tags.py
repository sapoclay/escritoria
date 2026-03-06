"""
API de Etiquetas de WordPress.
"""


class TagsAPI:
    """Gestiona las operaciones con etiquetas."""

    def __init__(self, client):
        self.client = client

    def list(self, page=1, per_page=100, search=None,
             orderby="name", order="asc", hide_empty=False):
        """Lista las etiquetas."""
        params = {
            "page": page,
            "per_page": per_page,
            "orderby": orderby,
            "order": order,
            "hide_empty": hide_empty,
        }
        if search:
            params["search"] = search

        return self.client.get("tags", params=params)

    def get(self, tag_id):
        """Obtiene una etiqueta por ID."""
        return self.client.get(f"tags/{tag_id}?context=edit")

    def create(self, name, description="", slug=""):
        """Crea una nueva etiqueta."""
        data = {
            "name": name,
            "description": description,
        }
        if slug:
            data["slug"] = slug
        return self.client.post("tags", data=data)

    def update(self, tag_id, **kwargs):
        """Actualiza una etiqueta."""
        return self.client.post(f"tags/{tag_id}", data=kwargs)

    def delete(self, tag_id, force=True):
        """Elimina una etiqueta."""
        return self.client.delete(f"tags/{tag_id}", params={"force": force})

    def get_all(self):
        """Obtiene todas las etiquetas (sin paginación)."""
        all_tags = []
        page = 1
        while True:
            result = self.list(page=page, per_page=100)
            if isinstance(result, dict) and "data"in result:
                all_tags.extend(result["data"])
                if page >= result.get("total_pages", 1):
                    break
            else:
                break
            page += 1
        return all_tags
