from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogo.models import Producto
from comercios.models import Comercio
from cuentas.models import RegistroAuditoria, Usuario
from cuentas.permisos import comerciante_con_comercio, rol_requerido

from . import servicios
from .forms import ReservaForm
from .models import PERDIDAS, SIN_ATENDER, Reserva, monto


@rol_requerido(Usuario.Rol.CLIENTE)
def nueva(request, producto_pk):
    """HU-10/HU-11: reservar con cantidad y total referencial."""
    producto = get_object_or_404(
        Producto.objects.select_related("comercio"),
        pk=producto_pk,
        activo=True,
        comercio__estado=Comercio.Estado.APROBADA,
    )
    form = ReservaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            reserva = servicios.crear_reserva(request.user, producto.pk, form.cleaned_data["cantidad"])
        except servicios.ReservaError as e:
            form.add_error(None, str(e))
        else:
            return redirect("reservas:detalle", pk=reserva.pk)
    return render(request, "reservas/nueva.html", {"producto": producto, "form": form})


@rol_requerido(Usuario.Rol.CLIENTE)
def detalle(request, pk):
    reserva = get_object_or_404(
        Reserva.objects.select_related("producto", "comercio"), pk=pk, cliente=request.user
    )
    return render(request, "reservas/detalle.html", {"reserva": reserva})


@rol_requerido(Usuario.Rol.CLIENTE)
def mis_reservas(request):
    """HU-12: estado de mis reservas."""
    reservas = Reserva.objects.filter(cliente=request.user).select_related(
        "producto", "comercio", "valoracion"
    )
    return render(request, "reservas/mis_reservas.html", {"reservas": reservas[:50]})


@require_POST
@rol_requerido(Usuario.Rol.CLIENTE)
def anular(request, pk):
    try:
        reserva = servicios.anular_reserva(pk, request.user, por_cliente=True)
        messages.success(request, f"Reserva {reserva.codigo} anulada.")
    except servicios.ReservaError as e:
        messages.error(request, str(e))
    return redirect("reservas:mis_reservas")


def _resultado(reserva, anulo_el_cliente):
    """(clase de etiqueta, texto) de cómo terminó: lo que el comercio puede corregir va en rojo."""
    if reserva.estado == Reserva.Estado.RETIRADA:
        return "exito", "Retirada"
    if reserva.estado == Reserva.Estado.ANULADA:
        return ("neutra", "Anulada por el cliente") if anulo_el_cliente else ("peligro", "Anulada por ti")
    if reserva.atendida_en:
        return "advertencia", "Venció sin retirar"
    return "peligro", "Venció sin atender"


@comerciante_con_comercio
def panel(request):
    """HU-15: qué atender primero (vence antes), cuánto hay comprometido y qué stock frena reservas."""
    ahora = timezone.now()
    reservas = Reserva.objects.filter(comercio=request.comercio).select_related("producto", "cliente")
    activas = list(reservas.filter(estado__in=Reserva.ACTIVAS).order_by("vence_en"))
    espera = ahora - timedelta(minutes=settings.RESERVA_AVISO_SIN_ATENCION_MIN)
    for r in activas:
        r.urgente = r.vence_en - ahora < timedelta(hours=1)
        r.espera_larga = r.creada_en < espera  # solo se muestra en las pendientes
    pendientes = [r for r in activas if r.estado == Reserva.Estado.PENDIENTE]
    atendidas = [r for r in activas if r.estado == Reserva.Estado.ATENDIDA]
    cerradas = reservas.exclude(estado__in=Reserva.ACTIVAS).filter(cerrada_en__gte=ahora - timedelta(days=7))
    por_confirmar = request.comercio.productos.filter(
        activo=True, actualizado_en__lt=Producto.limite_frescura()
    )
    ultimas = list(cerradas.order_by("-cerrada_en")[:30])
    por_cliente = set(
        RegistroAuditoria.objects.filter(
            accion="anular_reserva_cliente", entidad="reserva", entidad_id__in=[str(r.pk) for r in ultimas]
        ).values_list("entidad_id", flat=True)
    )
    for r in ultimas:
        r.resultado = _resultado(r, str(r.pk) in por_cliente)
    hoy = reservas.filter(estado=Reserva.Estado.RETIRADA, cerrada_en__date=timezone.localdate())
    return render(
        request,
        "reservas/panel.html",
        {
            "pendientes": pendientes,
            "atendidas": atendidas,
            "cifras": {
                "espera_larga": sum(r.espera_larga for r in pendientes),
                "vencen_pronto": sum(r.urgente for r in activas),
                "comprometido": sum(r.total for r in activas),
                "aviso_min": settings.RESERVA_AVISO_SIN_ATENCION_MIN,
                **hoy.aggregate(retiradas_hoy=Count("id"), retirado_hoy=monto()),
            },
            "cerradas": ultimas,
            "semana": cerradas.aggregate(
                retiradas=Count("id", filter=Q(estado=Reserva.Estado.RETIRADA)),
                retirado=monto(Q(estado=Reserva.Estado.RETIRADA)),
                perdidas=Count("id", filter=PERDIDAS),
                perdido=monto(PERDIDAS),
                sin_atender=Count("id", filter=SIN_ATENDER),
            ),
            "desactualizados": por_confirmar.count(),
            "mas_atrasados": por_confirmar.order_by("actualizado_en")[:5],
        },
    )


@comerciante_con_comercio
def pendientes_json(request):
    """Consulta liviana del panel (cada 10 s y al volver a la pestaña): si llega otra pendiente, recarga."""
    datos = Reserva.objects.filter(comercio=request.comercio, estado=Reserva.Estado.PENDIENTE).aggregate(
        pendientes=Count("id"), ultima=Max("id")
    )
    return JsonResponse(datos)


ACCIONES = {
    "atender": servicios.atender_reserva,
    "entregar": servicios.confirmar_retiro,
    "anular": lambda pk, usuario: servicios.anular_reserva(pk, usuario, por_cliente=False),
}


@require_POST
@comerciante_con_comercio
def accion_comercio(request, pk, accion):
    if accion not in ACCIONES:
        return redirect("reservas:panel")
    try:
        reserva = ACCIONES[accion](pk, request.user)
        messages.success(request, f"Reserva {reserva.codigo}: {reserva.get_estado_display().lower()}.")
    except servicios.ReservaError as e:
        messages.error(request, str(e))
    return redirect("reservas:panel")
