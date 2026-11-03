from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.core.cache import cache
from django.db.models import Avg
from django.shortcuts import render
from django.utils import timezone

from catalogo.models import Producto
from catalogo.texto import normalizar_texto
from comercios.models import Comercio
from valoraciones.models import Valoracion

from .forms import BusquedaForm
from .models import Busqueda

MAX_RESULTADOS = 50


def buscar(termino, lat, lon, radio_km, categoria=None):
    """Productos activos de comercios aprobados dentro del radio, más cercanos primero (HU-07..09)."""
    punto = Point(lon, lat, srid=4326)
    productos = Producto.objects.filter(
        activo=True,
        comercio__estado=Comercio.Estado.APROBADA,
        comercio__ubicacion__dwithin=(punto, D(km=radio_km)),
    )
    for token in normalizar_texto(termino).split():
        productos = productos.filter(nombre_normalizado__contains=token)
    if categoria:
        productos = productos.filter(categoria=categoria)
    return list(
        productos.annotate(distancia=Distance("comercio__ubicacion", punto))
        .select_related("comercio", "categoria")
        .order_by("distancia", "precio_referencial")[:MAX_RESULTADOS]
    )


def _excede_limite(request):
    # ponytail: 30/min por sesión (diseño) y 4x por IP para quien descarta la cookie; sin bloqueo persistente.
    if not request.session.session_key:
        request.session.save()
    minuto = timezone.now().strftime("%Y%m%d%H%M")
    # ponytail: REMOTE_ADDR, igual que el bloqueo de ingreso; detrás de un proxy, la IP que fije ese proxy.
    claves = [
        (f"busq:s:{request.session.session_key}:{minuto}", settings.BUSQUEDA_POR_MINUTO),
        (f"busq:ip:{request.META.get('REMOTE_ADDR', '')}:{minuto}", settings.BUSQUEDA_POR_MINUTO * 4),
    ]
    excedido = False
    for clave, tope in claves:
        cache.add(clave, 0, timeout=90)
        excedido |= cache.incr(clave) > tope
    return excedido


def inicio(request):
    form = BusquedaForm(request.GET or None)
    contexto = {"form": form}
    if request.GET and form.is_valid():
        if _excede_limite(request):
            form.add_error(None, "Hiciste muchas búsquedas en poco tiempo. Espera un minuto.")
        else:
            d = form.cleaned_data
            lat, lon = d["punto"]
            resultados = buscar(d["q"], lat, lon, d["radio"], d["categoria"])
            promedios = dict(
                Valoracion.objects.filter(
                    estado=Valoracion.Estado.APROBADA, comercio__in={p.comercio_id for p in resultados}
                )
                .values_list("comercio")
                .annotate(Avg("puntaje"))
            )
            for p in resultados:
                p.promedio = promedios.get(p.comercio_id)
            Busqueda.objects.create(
                termino=normalizar_texto(d["q"]),
                categoria=d["categoria"],
                ubicacion_aprox=Point(round(lon, 3), round(lat, 3), srid=4326),
                comuna=d["comuna"] or "",
                radio_km=d["radio"],
                n_resultados=len(resultados),
                n_con_stock=sum(p.marca[0] == "stock" for p in resultados),
            )
            comercios = {p.comercio_id: p.comercio for p in resultados}.values()
            contexto.update(
                resultados=resultados,
                lat=lat,
                lon=lon,
                radio_m=d["radio"] * 1000,
                marcadores=[
                    {
                        "lat": c.ubicacion.y,
                        "lon": c.ubicacion.x,
                        "nombre": c.nombre,
                        "url": f"/comercios/{c.pk}/",
                    }
                    for c in comercios
                ],
            )
    return render(request, "busqueda/inicio.html", contexto)
