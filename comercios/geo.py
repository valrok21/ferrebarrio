import json
import logging
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

from catalogo.texto import normalizar_texto

from .models import CacheGeocodificacion

log = logging.getLogger(__name__)


def dentro_de_chile(lat, lon):
    return -56.0 <= lat <= -17.4 and -76.0 <= lon <= -66.0


def geocodificar(direccion, comuna):
    """Devuelve (lat, lon) o None. Caché en BD (CT-17), 1 req/s y timeout 5 s (CT-13)."""
    clave = normalizar_texto(f"{direccion}, {comuna}, chile")
    guardada = CacheGeocodificacion.objects.filter(direccion=clave).first()
    if guardada:
        return guardada.lat, guardada.lon
    if not settings.NOMINATIM_URL.startswith("https://"):
        return None
    for _ in range(10):  # política de Nominatim: máximo 1 petición por segundo
        if cache.add("nominatim:turno", 1, timeout=1):
            break
        time.sleep(0.2)
    else:
        return None
    url = (
        settings.NOMINATIM_URL
        + "?"
        + urlencode(
            {"q": f"{direccion}, {comuna}, Chile", "format": "json", "limit": 1, "countrycodes": "cl"}
        )
    )
    try:
        # URL fija desde settings y validada como https arriba.
        with urlopen(Request(url, headers={"User-Agent": settings.NOMINATIM_USER_AGENT}), timeout=5) as r:  # nosec B310  # noqa: S310
            datos = json.load(r)
        lat, lon = float(datos[0]["lat"]), float(datos[0]["lon"])
    except (URLError, TimeoutError, OSError, ValueError, KeyError, IndexError) as e:
        log.warning("Geocodificación fallida para %r: %s", clave, e)
        return None
    if not dentro_de_chile(lat, lon):
        return None
    CacheGeocodificacion.objects.get_or_create(direccion=clave, defaults={"lat": lat, "lon": lon})
    return lat, lon
