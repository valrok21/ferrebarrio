import unicodedata


def normalizar_texto(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios simples: «Tornillo  Coche» → «tornillo coche»."""
    sin_tildes = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())
