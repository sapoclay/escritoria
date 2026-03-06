"""
API de Páginas de WordPress.
Gestiona todas las operaciones CRUD para páginas.
"""


class PagesAPI:
    """Gestiona las operaciones con páginas de WordPress."""

    def __init__(self, client):
        self.client = client

    def list(self, page=1, per_page=20, status="any", search=None,
             parent=None, orderby="date", order="desc", author=None):
        """Lista las páginas con filtros opcionales."""
        params = {
            "page": page,
            "per_page": per_page,
            "status": status,
            "orderby": orderby,
            "order": order,
            "context": "edit",
        }
        if search:
            params["search"] = search
        if parent is not None:
            params["parent"] = parent
        if author:
            params["author"] = author

        return self.client.get("pages", params=params)

    def get(self, page_id):
        """Obtiene una página por ID."""
        return self.client.get(f"pages/{page_id}?context=edit")

    def create(self, title, content="", status="draft", excerpt="",
               parent=0, menu_order=0, featured_media=0,
               comment_status="closed", template="",
               slug="", date=None, password="", author=None):
        """Crea una nueva página."""
        data = {
            "title": title,
            "content": content,
            "status": status,
            "excerpt": excerpt,
            "parent": parent,
            "menu_order": menu_order,
            "featured_media": featured_media,
            "comment_status": comment_status,
        }
        if template:
            data["template"] = template
        if slug:
            data["slug"] = slug
        if date:
            data["date"] = date
        if password:
            data["password"] = password
        if author:
            data["author"] = author

        return self.client.post("pages", data=data)

    def update(self, page_id, **kwargs):
        """Actualiza una página existente."""
        return self.client.post(f"pages/{page_id}", data=kwargs)

    def delete(self, page_id, force=True):
        """Elimina una página."""
        params = {"force": force}
        return self.client.delete(f"pages/{page_id}", params=params)

    def trash(self, page_id):
        """Mueve una página a la papelera."""
        return self.client.delete(f"pages/{page_id}", params={"force": False})

    def get_revisions(self, page_id):
        """Obtiene las revisiones de una página."""
        return self.client.get(f"pages/{page_id}/revisions")

    def get_templates(self):
        """Obtiene las plantillas de página disponibles."""
        try:
            # Intentar obtener del API de tipos
            result = self.client.get("types/page")
            if isinstance(result, dict) and "template"in result:
                return result["template"]
        except Exception:
            pass
        return []

    def get_hierarchy(self):
        """Obtiene las páginas organizadas jerárquicamente."""
        all_pages = []
        page = 1
        while True:
            result = self.list(page=page, per_page=100, status="any")
            if isinstance(result, dict) and "data"in result:
                all_pages.extend(result["data"])
                if page >= result.get("total_pages", 1):
                    break
            else:
                break
            page += 1

        # Organizar jerárquicamente
        tree = self._build_tree(all_pages)
        return tree

    def _build_tree(self, pages, parent_id=0):
        """Construye un árbol jerárquico de páginas."""
        tree = []
        for page in pages:
            pid = page.get("parent", 0)
            if pid == parent_id:
                children = self._build_tree(pages, page["id"])
                page["children"] = children
                tree.append(page)
        return tree
