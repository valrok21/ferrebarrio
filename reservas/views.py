from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogo.models import Producto
from comercios.models import Comercio
from cuentas.models import Usuario
from cuentas.permisos import comerciante_con_comercio, rol_requerido

from . import servicios
from .forms import ReservaForm
from .models import Reserva


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


@comerciante_con_comercio
def panel(request):
    """HU-15: cola de reservas del comercio."""
    reservas = Reserva.objects.filter(comercio=request.comercio).select_related("producto", "cliente")
    semana = timezone.now() - timedelta(days=7)
    return render(
        request,
        "reservas/panel.html",
        {
            "pendientes": reservas.filter(estado=Reserva.Estado.PENDIENTE).order_by("creada_en"),
            "atendidas": reservas.filter(estado=Reserva.Estado.ATENDIDA).order_by("vence_en"),
            "cerradas": reservas.exclude(estado__in=Reserva.ACTIVAS).filter(creada_en__gte=semana)[:30],
            "semana": reservas.filter(creada_en__gte=semana).aggregate(
                total=Count("id"), retiradas=Count("id", filter=Q(estado=Reserva.Estado.RETIRADA))
            ),
            "desactualizados": sum(p.desactualizado for p in request.comercio.productos.filter(activo=True)),
        },
    )


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
