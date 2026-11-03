from django import forms
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cuentas.models import Usuario, auditar
from cuentas.permisos import rol_requerido
from reservas.models import Reserva

from .models import Valoracion


class ValoracionForm(forms.ModelForm):
    puntaje = forms.TypedChoiceField(choices=[(i, "★" * i) for i in range(5, 0, -1)], coerce=int)

    class Meta:
        model = Valoracion
        fields = ["puntaje", "comentario"]
        widgets = {"comentario": forms.Textarea(attrs={"rows": 3, "maxlength": 500})}
        help_texts = {"comentario": "Opcional. Los comentarios se publican tras revisión."}


@rol_requerido(Usuario.Rol.CLIENTE)
def valorar(request, reserva_pk):
    reserva = get_object_or_404(
        Reserva.objects.select_related("comercio"),
        pk=reserva_pk,
        cliente=request.user,
        estado=Reserva.Estado.RETIRADA,
    )
    if Valoracion.objects.filter(reserva=reserva).exists():
        messages.info(request, "Ya valoraste esta reserva.")
        return redirect("reservas:mis_reservas")
    form = ValoracionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        valoracion = form.save(commit=False)
        valoracion.reserva, valoracion.comercio, valoracion.cliente = reserva, reserva.comercio, request.user
        valoracion.comentario = valoracion.comentario.strip()
        valoracion.estado = (
            Valoracion.Estado.PENDIENTE if valoracion.comentario else Valoracion.Estado.APROBADA
        )
        try:
            with transaction.atomic():
                valoracion.save()
        except IntegrityError:
            messages.info(request, "Ya valoraste esta reserva.")
            return redirect("reservas:mis_reservas")
        messages.success(
            request,
            "¡Gracias por tu valoración!"
            + (" Tu comentario se publicará tras revisión." if valoracion.comentario else ""),
        )
        return redirect("reservas:mis_reservas")
    return render(request, "valoraciones/valorar.html", {"form": form, "reserva": reserva})


@rol_requerido(Usuario.Rol.ADMIN)
def moderar(request):
    pendientes = Valoracion.objects.filter(estado=Valoracion.Estado.PENDIENTE).select_related("comercio")
    return render(request, "valoraciones/moderar.html", {"pendientes": pendientes})


@require_POST
@rol_requerido(Usuario.Rol.ADMIN)
def resolver(request, pk):
    valoracion = get_object_or_404(Valoracion, pk=pk, estado=Valoracion.Estado.PENDIENTE)
    aprobar = request.POST.get("accion") == "aprobar"
    valoracion.estado = Valoracion.Estado.APROBADA if aprobar else Valoracion.Estado.RECHAZADA
    valoracion.moderada_por = request.user
    valoracion.save(update_fields=["estado", "moderada_por"])
    auditar(request.user, "moderar_valoracion", valoracion, None, {"estado": valoracion.estado})
    messages.success(request, f"Valoración {valoracion.get_estado_display().lower()}.")
    return redirect("valoraciones:moderar")
