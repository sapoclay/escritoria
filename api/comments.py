"""
API de Comentarios de WordPress.
"""


class CommentsAPI:
    """Gestiona las operaciones con comentarios."""

    def __init__(self, client):
        self.client = client

    def list(self, page=1, per_page=20, status="approve", search=None,
             post=None, orderby="date_gmt", order="desc", author=None,
             parent=None):
        """Lista los comentarios."""
        params = {
            "page": page,
            "per_page": per_page,
            "status": status,
            "orderby": orderby,
            "order": order,
        }
        if search:
            params["search"] = search
        if post:
            params["post"] = post
        if author:
            params["author"] = author
        if parent is not None:
            params["parent"] = parent

        return self.client.get("comments", params=params)

    def get(self, comment_id):
        """Obtiene un comentario por ID."""
        return self.client.get(f"comments/{comment_id}?context=edit")

    def create(self, post, content, author_name="", author_email="",
               author_url="", parent=0, status="approve"):
        """Crea un nuevo comentario."""
        data = {
            "post": post,
            "content": content,
            "status": status,
            "parent": parent,
        }
        if author_name:
            data["author_name"] = author_name
        if author_email:
            data["author_email"] = author_email
        if author_url:
            data["author_url"] = author_url

        return self.client.post("comments", data=data)

    def update(self, comment_id, **kwargs):
        """Actualiza un comentario."""
        return self.client.post(f"comments/{comment_id}", data=kwargs)

    def delete(self, comment_id, force=True):
        """Elimina un comentario."""
        return self.client.delete(f"comments/{comment_id}", params={"force": force})

    def approve(self, comment_id):
        """Aprueba un comentario."""
        return self.update(comment_id, status="approved")

    def unapprove(self, comment_id):
        """Marca un comentario como pendiente."""
        return self.update(comment_id, status="hold")

    def spam(self, comment_id):
        """Marca un comentario como spam."""
        return self.update(comment_id, status="spam")

    def trash(self, comment_id):
        """Mueve un comentario a la papelera."""
        return self.update(comment_id, status="trash")

    def bulk_action(self, comment_ids, action):
        """Ejecuta una acción en lotes sobre comentarios."""
        results = []
        for cid in comment_ids:
            try:
                if action == "approve":
                    result = self.approve(cid)
                elif action == "unapprove":
                    result = self.unapprove(cid)
                elif action == "spam":
                    result = self.spam(cid)
                elif action == "trash":
                    result = self.trash(cid)
                elif action == "delete":
                    result = self.delete(cid)
                else:
                    continue
                results.append({"id": cid, "success": True, "data": result})
            except Exception as e:
                results.append({"id": cid, "success": False, "error": str(e)})
        return results
