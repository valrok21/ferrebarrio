from datetime import timedelta

from django.contrib.gis.measure import D
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone

from busqueda.models import Busqueda
from comercios.models import Comercio
from cuentas.models import Usuario
from cuentas.permisos import comerciante_con_comercio, rol_requerido
from reservas.models import Aviso, Reserva
from reservas.servicios import diferencias_stock
from valoraciones.models import Valoracion

DIAS, RADIO_KM = 30, 3


def _tasa_retiro(reservas):
    c = reservas.aggregate(
        retiradas=Count("id", filter=Q(estado="retirada")),
        cerradas=Count("id", filter=Q(estado__in=["retirada", "anulada", "expirada"])),
    )
    return round(100 * c["retiradas"] / c["cerradas"]) if c["cerradas"] else None


@comerciante_con_comercio
def comerciante(request):
    """HU-24 más buscados, HU-25 demanda no cubierta, HU-26 desempeño de reservas (últimos 30 días)."""
    desde = timezone.now() - timedelta(days=DIAS)
    comercio = request.comercio
    zona = Busqueda.objects.none()
    if comercio.ubicacion:
        zona = Busqueda.objects.filter(
            fecha__gte=desde, ubicacion_aprox__dwithin=(comercio.ubicacion, D(km=RADIO_KM))
        )
    reservas = Reserva.objects.filter(comercio=comercio, creada_en__gte=desde)
    return render(
        request,
        "reportes/comerciante.html",
        {
            "dias": DIAS,
            "radio": RADIO_KM,
            "mas_buscados": zona.values("termino").annotate(n=Count("id")).order_by("-n", "termino")[:10],
            "sin_stock": zona.filter(n_con_stock=0)
            .values("termino")
            .annotate(n=Count("id"))
            .order_by("-n", "termino")[:10],
            "por_estado": reservas.values("estado").annotate(n=Count("id")).order_by("-n"),
            "tasa_retiro": _tasa_retiro(reservas),
            "quiebres": comercio.productos.filter(activo=True, stock_disponible=0),
        },
    )


@rol_requerido(Usuario.Rol.ADMIN)
def admin(request):
    """Indicadores de los objetivos específicos del piloto y alertas de operación."""
    desde = timezone.now() - timedelta(days=DIAS)
    aprobados = Comercio.objects.filter(estado=Comercio.Estado.APROBADA)
    busquedas = Busqueda.objects.filter(fecha__gte=desde)
    reservas = Reserva.objects.filter(creada_en__gte=desde)
    n_busq = busquedas.count()
    return render(
        request,
        "reportes/admin.html",
        {
            "dias": DIAS,
            "oe1": {
                "aprobados": aprobados.count(),
                "con_catalogo": aprobados.filter(productos__activo=True).distinct().count(),
            },
            "oe2": {
                "total": n_busq,
                "con_resultados": busquedas.filter(n_resultados__gt=0).count(),
                "pct": round(100 * busquedas.filter(n_resultados__gt=0).count() / n_busq) if n_busq else None,
            },
            "oe3": {"total": reservas.count(), "tasa_retiro": _tasa_retiro(reservas)},
            "diferencias": diferencias_stock(),
            "fallidos": Aviso.objects.filter(estado=Aviso.Estado.FALLIDO)[:20],
            "solicitudes": Comercio.objects.filter(estado__in=["pendiente", "observada"]).count(),
            "por_moderar": Valoracion.objects.filter(estado=Valoracion.Estado.PENDIENTE).count(),
        },
    )
