from datetime import timedelta

from django.contrib.gis.measure import D
from django.db.models import Avg, Count, F, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from busqueda.models import Busqueda
from catalogo.texto import normalizar_texto
from comercios.models import Comercio
from cuentas.models import Usuario
from cuentas.permisos import comerciante_con_comercio, rol_requerido
from reservas.models import PERDIDAS, SIN_ATENDER, Aviso, Reserva, monto
from reservas.servicios import diferencias_stock
from valoraciones.models import Valoracion

DIAS, RADIO_KM = 30, 3


def _tasa_retiro(reservas):
    c = reservas.aggregate(
        retiradas=Count("id", filter=Q(estado="retirada")),
        cerradas=Count("id", filter=Q(estado__in=["retirada", "anulada", "expirada"])),
    )
    return round(100 * c["retiradas"] / c["cerradas"]) if c["cerradas"] else None


def _situacion(mios):
    """(orden, clave, texto) de lo que ve un cliente que busca esto en tu local; las oportunidades primero."""
    if not mios:
        return 1, "no", "No lo vendes"
    frescos = [p for p in mios if not p.desactualizado]
    if con_stock := sum(p.stock_disponible for p in frescos):
        return 3, "stock", f"Con stock ({con_stock})"
    if len(frescos) < len(mios):
        return 2, "confirmar", "Por confirmar"
    return 0, "sin", "Lo tienes sin stock"


def _coincide(termino, producto):
    # Mismo criterio que busqueda.views.buscar: cada palabra contenida en el nombre normalizado.
    return all(t in producto.nombre_normalizado for t in normalizar_texto(termino).split())


@comerciante_con_comercio
def comerciante(request):
    """HU-24/25/26: tu zona frente a tu catálogo, qué reponer y cómo rinden tus reservas (30 días)."""
    desde = timezone.now() - timedelta(days=DIAS)
    comercio = request.comercio
    zona = Busqueda.objects.none()
    if comercio.ubicacion:
        zona = Busqueda.objects.filter(
            fecha__gte=desde, ubicacion_aprox__dwithin=(comercio.ubicacion, D(km=RADIO_KM))
        )
    # ponytail: cruce en Python (términos × catálogo); si el catálogo pasa de miles, llevarlo a SQL.
    terminos = list(
        zona.values("termino")
        .annotate(n=Count("id"), sin_stock=Count("id", filter=Q(n_con_stock=0)))
        .order_by("-n", "termino")[:100]
    )
    productos = list(comercio.productos.filter(activo=True))
    demanda = []
    for t in terminos[:15]:
        mios = [p for p in productos if _coincide(t["termino"], p)]
        t["orden"], t["clave"], t["situacion"] = _situacion(mios)
        demanda.append(t)
    demanda.sort(key=lambda t: (t["orden"], -t["n"], t["termino"]))

    reservas = Reserva.objects.filter(comercio=comercio, creada_en__gte=desde)
    reservado = dict(reservas.values_list("producto").annotate(n=Count("id")))
    reponer = [p for p in productos if p.stock_disponible == 0 or p.desactualizado]
    for p in reponer:
        p.buscado = sum(t["n"] for t in terminos if _coincide(t["termino"], p))
        p.reservado = reservado.get(p.pk, 0)
    reponer.sort(key=lambda p: (-(p.buscado + p.reservado), p.nombre))

    atencion = reservas.filter(atendida_en__isnull=False).aggregate(
        media=Avg(F("atendida_en") - F("creada_en"))
    )
    return render(
        request,
        "reportes/comerciante.html",
        {
            "dias": DIAS,
            "radio": RADIO_KM,
            "resumen": {
                **reservas.aggregate(
                    total=Count("id"),
                    retiradas=Count("id", filter=Q(estado=Reserva.Estado.RETIRADA)),
                    retirado=monto(Q(estado=Reserva.Estado.RETIRADA)),
                    perdidas=Count("id", filter=PERDIDAS),
                    perdido=monto(PERDIDAS),
                    sin_atender=Count("id", filter=SIN_ATENDER),
                ),
                "tasa_retiro": _tasa_retiro(reservas),
                "atencion_min": round(atencion["media"].total_seconds() / 60) if atencion["media"] else None,
                **Valoracion.objects.filter(
                    comercio=comercio, estado=Valoracion.Estado.APROBADA, creada_en__gte=desde
                ).aggregate(nota=Avg("puntaje"), valoraciones=Count("id")),
            },
            "demanda": demanda,
            "mas_reservados": reservas.values("producto", "producto__nombre")
            .annotate(
                n=Count("id"),
                unidades=Sum("cantidad"),
                retiradas=Count("id", filter=Q(estado=Reserva.Estado.RETIRADA)),
                perdidas=Count("id", filter=PERDIDAS),
                retirado=monto(Q(estado=Reserva.Estado.RETIRADA)),
            )
            .order_by("-n", "producto__nombre")[:10],
            "reponer": reponer[:15],
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
