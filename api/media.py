"""
API de Medios de WordPress.
Gestiona la biblioteca de medios: subida, listado y eliminación de archivos.
"""
import os
import mimetypes


class MediaAPI:
    """Gestiona las operaciones con medios (archivos multimedia)."""

    def __init__(self, client):
        self.client = client

    def list(self, page=1, per_page=20, search=None, media_type=None,
             mime_type=None, orderby="date", order="desc", author=None):
        """Lista los medios."""
        params = {
            "page": page,
            "per_page": per_page,
            "orderby": orderby,
            "order": order,
        }
        if search:
            params["search"] = search
        if media_type:
            params["media_type"] = media_type  # image, video, audio, application
        if mime_type:
            params["mime_type"] = mime_type
        if author:
            params["author"] = author

        return self.client.get("media", params=params)

    def get(self, media_id):
        """Obtiene un medio por ID."""
        return self.client.get(f"media/{media_id}?context=edit")

    def upload(self, file_path, title=None, caption="", alt_text="",
               description=""):
        """Sube un archivo de medio."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        filename = os.path.basename(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        with open(file_path, "rb") as f:
            files = {
                "file": (filename, f, mime_type),
            }
            data = {}
            if title:
                data["title"] = title
            if caption:
                data["caption"] = caption
            if alt_text:
                data["alt_text"] = alt_text
            if description:
                data["description"] = description

            return self.client.post("media", data=data, files=files)

    def update(self, media_id, **kwargs):
        """Actualiza los datos de un medio."""
        return self.client.post(f"media/{media_id}", data=kwargs)

    def delete(self, media_id, force=True):
        """Elimina un medio."""
        return self.client.delete(f"media/{media_id}", params={"force": force})

    def get_by_type(self, media_type, page=1, per_page=20):
        """Obtiene medios filtrados por tipo."""
        return self.list(page=page, per_page=per_page, media_type=media_type)
