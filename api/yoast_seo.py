"""
API de Yoast SEO para WordPress.
Lee y escribe los campos SEO de Yoast a través de la API REST.

Yoast SEO expone datos SEO en los posts/páginas mediante:
- Lectura: campo 'yoast_head_json' en la respuesta del post
- Escritura: campos meta en el body de la petición POST/PUT
"""


# Claves meta de Yoast SEO que se envían al guardar un post/página
YOAST_META_KEYS = {
    "seo_title": "_yoast_wpseo_title",
    "meta_description": "_yoast_wpseo_metadesc",
    "focus_keyword": "_yoast_wpseo_focuskw",
    "canonical_url": "_yoast_wpseo_canonical",
    "og_title": "_yoast_wpseo_opengraph-title",
    "og_description": "_yoast_wpseo_opengraph-description",
    "og_image": "_yoast_wpseo_opengraph-image",
    "twitter_title": "_yoast_wpseo_twitter-title",
    "twitter_description": "_yoast_wpseo_twitter-description",
    "twitter_image": "_yoast_wpseo_twitter-image",
    "meta_robots_noindex": "_yoast_wpseo_meta-robots-noindex",
    "meta_robots_nofollow": "_yoast_wpseo_meta-robots-nofollow",
}


def extract_yoast_data(post_data):
    """
    Extrae los datos SEO de Yoast de la respuesta de un post/página.

    Yoast expone los datos en 'yoast_head_json' y en 'meta'.
    Devuelve un diccionario con claves amigables.
    """
    result = {
        "seo_title": "",
        "meta_description": "",
        "focus_keyword": "",
        "canonical_url": "",
        "og_title": "",
        "og_description": "",
        "og_image": "",
        "twitter_title": "",
        "twitter_description": "",
        "twitter_image": "",
        "meta_robots_noindex": False,
        "meta_robots_nofollow": False,
    }

    if not isinstance(post_data, dict):
        return result

    # Intentar leer desde meta (contexto edit)
    meta = post_data.get("meta", {})
    if isinstance(meta, dict):
        for friendly_key, meta_key in YOAST_META_KEYS.items():
            value = meta.get(meta_key, "")
            if friendly_key in ("meta_robots_noindex", "meta_robots_nofollow"):
                result[friendly_key] = bool(value and str(value) == "1")
            else:
                result[friendly_key] = str(value) if value else ""

    # Complementar con yoast_head_json si los campos meta están vacíos
    yoast_json = post_data.get("yoast_head_json", {})
    if isinstance(yoast_json, dict):
        if not result["seo_title"]:
            result["seo_title"] = yoast_json.get("title", "")
        if not result["meta_description"]:
            result["meta_description"] = yoast_json.get("description", "")
        if not result["canonical_url"]:
            result["canonical_url"] = yoast_json.get("canonical", "")

        # Open Graph
        og = yoast_json.get("og_title", "")
        if og and not result["og_title"]:
            result["og_title"] = og
        og_desc = yoast_json.get("og_description", "")
        if og_desc and not result["og_description"]:
            result["og_description"] = og_desc
        og_images = yoast_json.get("og_image", [])
        if og_images and not result["og_image"]:
            if isinstance(og_images, list) and len(og_images) > 0:
                result["og_image"] = og_images[0].get("url", "")
            elif isinstance(og_images, str):
                result["og_image"] = og_images

        # Twitter
        tw_card = yoast_json.get("twitter_misc", {})
        tw_title = yoast_json.get("twitter_card", "")
        # Twitter fields are less commonly exposed in yoast_head_json

        # Robots
        robots = yoast_json.get("robots", {})
        if isinstance(robots, dict):
            index_val = robots.get("index", "index")
            follow_val = robots.get("follow", "follow")
            if not result["meta_robots_noindex"]:
                result["meta_robots_noindex"] = (index_val == "noindex")
            if not result["meta_robots_nofollow"]:
                result["meta_robots_nofollow"] = (follow_val == "nofollow")

    return result


def build_yoast_meta(seo_data):
    """
    Construye el diccionario meta para enviar a la API al guardar.

    Recibe un dict con claves amigables y devuelve el dict
    listo para incluir en 'meta' del body de la petición.

    Args:
        seo_data: dict con claves como 'seo_title', 'meta_description', etc.

    Returns:
        dict con las claves meta de Yoast (_yoast_wpseo_*)
    """
    meta = {}
    if not isinstance(seo_data, dict):
        return meta

    for friendly_key, meta_key in YOAST_META_KEYS.items():
        value = seo_data.get(friendly_key, "")
        if friendly_key in ("meta_robots_noindex", "meta_robots_nofollow"):
            meta[meta_key] = "1" if value else ""
        else:
            if value:  # Solo enviar campos con valor
                meta[meta_key] = str(value)

    return meta


def has_yoast_seo(post_data):
    """
    Detecta si el post/página tiene datos de Yoast SEO.
    Útil para saber si el plugin está activo en el servidor.
    """
    if not isinstance(post_data, dict):
        return False
    return (
        "yoast_head_json" in post_data
        or "yoast_head" in post_data
        or any(
            k.startswith("_yoast_wpseo_")
            for k in (post_data.get("meta", {}) or {})
        )
    )
