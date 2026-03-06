"""
API de Categorías de WordPress.
"""


class CategoriesAPI:
    """Gestiona las operaciones con categorías."""

    def __init__(self, client):
        self.client = client

    def list(self, page=1, per_page=100, search=None, parent=None,
             orderby="name", order="asc", hide_empty=False):
        """Lista las categorías."""
        params = {
            "page": page,
            "per_page": per_page,
            "orderby": orderby,
            "order": order,
            "hide_empty": hide_empty,
        }
        if search:
            params["search"] = search
        if parent is not None:
            params["parent"] = parent

        return self.client.get("categories", params=params)

    def get(self, category_id):
        """Obtiene una categoría por ID."""
        return self.client.get(f"categories/{category_id}?context=edit")

    def create(self, name, description="", parent=0, slug=""):
        """Crea una nueva categoría."""
        data = {
            "name": name,
            "description": description,
            "parent": parent,
        }
        if slug:
            data["slug"] = slug
        return self.client.post("categories", data=data)

    def update(self, category_id, **kwargs):
        """Actualiza una categoría."""
        return self.client.post(f"categories/{category_id}", data=kwargs)

    def delete(self, category_id, force=True):
        """Elimina una categoría."""
        return self.client.delete(f"categories/{category_id}", params={"force": force})

    def get_all(self):
        """Obtiene todas las categorías (sin paginación)."""
        all_cats = []
        page = 1
        while True:
            result = self.list(page=page, per_page=100)
            if isinstance(result, dict) and "data"in result:
                all_cats.extend(result["data"])
                if page >= result.get("total_pages", 1):
                    break
            else:
                break
            page += 1
        return all_cats
