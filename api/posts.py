"""
API de Posts de WordPress.
Gestiona todas las operaciones CRUD para entradas del blog.
"""


class PostsAPI:
    """Gestiona las operaciones con posts de WordPress."""

    def __init__(self, client):
        self.client = client

    def list(self, page=1, per_page=20, status="any", search=None,
             categories=None, tags=None, orderby="date", order="desc",
             author=None):
        """Lista los posts con filtros opcionales."""
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
        if categories:
            params["categories"] = ",".join(str(c) for c in categories)
        if tags:
            params["tags"] = ",".join(str(t) for t in tags)
        if author:
            params["author"] = author

        return self.client.get("posts", params=params)

    def get(self, post_id):
        """Obtiene un post por ID."""
        return self.client.get(f"posts/{post_id}?context=edit")

    def create(self, title, content="", status="draft", excerpt="",
               categories=None, tags=None, featured_media=0,
               comment_status="open", ping_status="open",
               format_type="standard", sticky=False, slug="",
               date=None, password="", author=None, template="",
               meta=None):
        """Crea un nuevo post."""
        data = {
            "title": title,
            "content": content,
            "status": status,
            "excerpt": excerpt,
            "featured_media": featured_media,
            "comment_status": comment_status,
            "ping_status": ping_status,
            "format": format_type,
            "sticky": sticky,
        }
        if categories:
            data["categories"] = categories
        if tags:
            data["tags"] = tags
        if slug:
            data["slug"] = slug
        if date:
            data["date"] = date
        if password:
            data["password"] = password
        if author:
            data["author"] = author
        if template:
            data["template"] = template
        if meta:
            data["meta"] = meta

        return self.client.post("posts", data=data)

    def update(self, post_id, **kwargs):
        """Actualiza un post existente."""
        # Mapear format_type a format si existe
        if "format_type"in kwargs:
            kwargs["format"] = kwargs.pop("format_type")
        return self.client.post(f"posts/{post_id}", data=kwargs)

    def delete(self, post_id, force=True):
        """Elimina un post."""
        params = {"force": force}
        return self.client.delete(f"posts/{post_id}", params=params)

    def trash(self, post_id):
        """Mueve un post a la papelera."""
        return self.client.delete(f"posts/{post_id}", params={"force": False})

    def get_revisions(self, post_id):
        """Obtiene las revisiones de un post."""
        return self.client.get(f"posts/{post_id}/revisions")

    def get_statuses(self):
        """Obtiene los estados disponibles para posts."""
        return self.client.get("statuses")

    def get_formats(self):
        """Obtiene los formatos de post disponibles."""
        # Los formatos se obtienen del endpoint de tipos de post
        return [
            "standard", "aside", "chat", "gallery", "link",
            "image", "quote", "status", "video", "audio"
        ]

    def bulk_delete(self, post_ids, force=True):
        """Elimina múltiples posts."""
        results = []
        for pid in post_ids:
            try:
                result = self.delete(pid, force=force)
                results.append({"id": pid, "success": True, "data": result})
            except Exception as e:
                results.append({"id": pid, "success": False, "error": str(e)})
        return results

    def bulk_update_status(self, post_ids, status):
        """Actualiza el estado de múltiples posts."""
        results = []
        for pid in post_ids:
            try:
                result = self.update(pid, status=status)
                results.append({"id": pid, "success": True, "data": result})
            except Exception as e:
                results.append({"id": pid, "success": False, "error": str(e)})
        return results
