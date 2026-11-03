from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cuentas.models import auditar, instantanea
from cuentas.permisos import comerciante_con_comercio

from .forms import PlanillaForm, ProductoForm
from .models import Producto
from .planilla import CAMPOS_AUDITADOS, PlanillaInvalida, cargar, plantilla


@comerciante_con_comercio
def lista(request):
    productos = request.comercio.productos.filter(activo=True).select_related("categoria")
    return render(
        request,
        "catalogo/lista.html",
        {
            "productos": productos,
            "form": PlanillaForm(),
            "carga": request.comercio.cargas.first(),
            "desactualizados": sum(p.desactualizado for p in productos),
        },
    )


@comerciante_con_comercio
def editar(request, pk=None):
    """HU-05: alta y edición; el producto se busca siempre dentro del comercio del usuario (CT-15)."""
    with transaction.atomic():
        if pk:
            producto = get_object_or_404(
                Producto.objects.select_for_update(), pk=pk, comercio=request.comercio, activo=True
            )
        else:
            producto = Producto(comercio=request.comercio)
        antes = instantanea(producto, CAMPOS_AUDITADOS) if pk else None
        form = ProductoForm(request.POST or None, instance=producto)
        if request.method == "POST" and form.is_valid():
            producto = form.save(commit=False)
            producto.actualizado_en = timezone.now()
            producto.save()
            request.comercio.catalogo_actualizado_en = producto.actualizado_en
            request.comercio.save(update_fields=["catalogo_actualizado_en"])
            auditar(
                request.user,
                "editar_producto" if pk else "crear_producto",
                producto,
                antes,
                instantanea(producto, CAMPOS_AUDITADOS),
            )
            messages.success(request, f"«{producto.nombre}» guardado.")
            return redirect("catalogo:lista")
    return render(request, "catalogo/producto_form.html", {"form": form, "producto": producto})


@require_POST
@comerciante_con_comercio
def eliminar(request, pk):
    with transaction.atomic():
        producto = get_object_or_404(
            Producto.objects.select_for_update(), pk=pk, comercio=request.comercio, activo=True
        )
        antes = instantanea(producto, CAMPOS_AUDITADOS)
        producto.activo = False
        producto.save(update_fields=["activo"])
        auditar(request.user, "eliminar_producto", producto, antes, instantanea(producto, CAMPOS_AUDITADOS))
    messages.success(request, f"«{producto.nombre}» quitado del catálogo.")
    return redirect("catalogo:lista")


@require_POST
@comerciante_con_comercio
def subir_planilla(request):
    form = PlanillaForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            carga = cargar(form.cleaned_data["archivo"], request.comercio, request.user)
        except PlanillaInvalida as e:
            messages.error(request, str(e))
        else:
            (messages.success if not carga.errores else messages.warning)(request, carga.resumen)
    else:
        messages.error(request, "Selecciona un archivo .xlsx.")
    return redirect("catalogo:lista")


@comerciante_con_comercio
def descargar_plantilla(request):
    respuesta = HttpResponse(
        plantilla(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    respuesta["Content-Disposition"] = 'attachment; filename="plantilla-catalogo-ferrebarrio.xlsx"'
    return respuesta
