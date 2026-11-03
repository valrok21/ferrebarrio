from django.contrib import messages
from django.contrib.gis.geos import Point
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cuentas.models import Usuario, auditar, instantanea
from cuentas.permisos import rol_requerido
from reservas.avisos import programar_aviso

from .forms import ComercioForm, FichaAprobadaForm, VerificacionForm
from .geo import geocodificar
from .models import Comercio

CAMPOS_AUDITADOS = [
    "nombre",
    "rut",
    "direccion",
    "comuna",
    "ubicacion",
    "origen_ubicacion",
    "horario",
    "telefono",
    "estado",
    "motivo",
]


@rol_requerido(Usuario.Rol.COMERCIANTE)
def registrar(request):
    """HU-01/HU-02: alta y edición de la ficha del comercio por su propietario."""
    comercio = Comercio.objects.filter(propietario=request.user).first()
    if comercio and comercio.estado == Comercio.Estado.RECHAZADA:
        return render(request, "comercios/registrar.html", {"comercio": comercio})
    if comercio and comercio.estado == Comercio.Estado.APROBADA:
        form = FichaAprobadaForm(request.POST or None, instance=comercio)
        if request.method == "POST" and form.is_valid():
            antes = instantanea(comercio, CAMPOS_AUDITADOS)
            form.save()
            auditar(request.user, "editar_ficha", comercio, antes, instantanea(comercio, CAMPOS_AUDITADOS))
            messages.success(request, "Ficha actualizada.")
            return redirect("comercios:registrar")
        return render(request, "comercios/registrar.html", {"comercio": comercio, "form": form})

    form = ComercioForm(request.POST or None, instance=comercio or Comercio(propietario=request.user))
    if request.method == "POST" and form.is_valid():
        nuevo = form.save(commit=False)
        antes = instantanea(comercio, CAMPOS_AUDITADOS) if comercio else None
        datos = form.cleaned_data
        if datos["marcador_movido"]:
            nuevo.ubicacion, nuevo.origen_ubicacion = Point(datos["lon"], datos["lat"], srid=4326), "manual"
        elif not nuevo.ubicacion or {"direccion", "comuna"} & set(form.changed_data):
            coords = geocodificar(nuevo.direccion, nuevo.comuna)
            if coords is None:
                form.add_error(
                    None, "No pudimos ubicar la dirección automáticamente. Marca tu local en el mapa."
                )
                return render(
                    request,
                    "comercios/registrar.html",
                    {"comercio": comercio, "form": form, "sin_ubicacion": True},
                )
            nuevo.ubicacion, nuevo.origen_ubicacion = Point(coords[1], coords[0], srid=4326), "geocodificada"
        if not comercio:
            nuevo.acepto_terminos_en = timezone.now()
        nuevo.estado = Comercio.Estado.PENDIENTE
        nuevo.save()
        auditar(
            request.user,
            "alta_comercio" if not comercio else "editar_ficha",
            nuevo,
            antes,
            instantanea(nuevo, CAMPOS_AUDITADOS),
        )
        messages.success(
            request, "Datos enviados. Un administrador verificará tu ferretería antes de publicarla."
        )
        return redirect("comercios:registrar")
    return render(request, "comercios/registrar.html", {"comercio": comercio, "form": form})


def ficha(request, pk):
    """HU-17: ficha pública, solo de comercios aprobados."""
    from valoraciones.models import Valoracion

    comercio = get_object_or_404(Comercio, pk=pk, estado=Comercio.Estado.APROBADA)
    valoraciones = Valoracion.objects.filter(comercio=comercio, estado=Valoracion.Estado.APROBADA)
    resumen = valoraciones.aggregate(promedio=Avg("puntaje"), total=Count("id"))
    productos = (
        comercio.productos.filter(activo=True)
        .select_related("categoria")
        .order_by("categoria__nombre", "nombre")
    )
    return render(
        request,
        "comercios/ficha.html",
        {
            "comercio": comercio,
            "productos": productos,
            "resumen": resumen,
            "comentarios": valoraciones.exclude(comentario="").select_related("cliente")[:10],
        },
    )


@rol_requerido(Usuario.Rol.ADMIN)
def solicitudes(request):
    """HU-03 (CT-12): bandeja de verificación de comercios."""
    pendientes = Comercio.objects.filter(Q(estado="pendiente") | Q(estado="observada")).select_related(
        "propietario"
    )
    resueltas = Comercio.objects.filter(estado__in=["aprobada", "rechazada"]).order_by("-verificado_en")[:20]
    return render(
        request,
        "comercios/solicitudes.html",
        {"pendientes": pendientes.order_by("creado_en"), "resueltas": resueltas},
    )


@rol_requerido(Usuario.Rol.ADMIN)
def verificar(request, pk):
    comercio = get_object_or_404(Comercio.objects.select_related("propietario"), pk=pk)
    form = VerificacionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        antes = instantanea(comercio, CAMPOS_AUDITADOS)
        accion, motivo = form.cleaned_data["accion"], form.cleaned_data["motivo"].strip()
        if accion == "aprobar" and not comercio.ubicacion:
            messages.error(request, "No se puede aprobar un comercio sin ubicación.")
            return redirect("comercios:verificar", pk=pk)
        comercio.estado = {"aprobar": "aprobada", "observar": "observada", "rechazar": "rechazada"}[accion]
        comercio.motivo, comercio.verificado_por, comercio.verificado_en = (
            motivo,
            request.user,
            timezone.now(),
        )
        comercio.save()
        auditar(
            request.user, f"verificacion_{accion}", comercio, antes, instantanea(comercio, CAMPOS_AUDITADOS)
        )
        programar_aviso(
            comercio.propietario.email,
            "verificacion",
            f"Tu ferretería {comercio.nombre} fue {comercio.get_estado_display().lower()}",
            f"Hola {comercio.propietario.nombre}:\n\nEl estado de {comercio.nombre} ahora es "
            f"«{comercio.get_estado_display()}».\n"
            + (f"Motivo: {motivo}\n" if motivo else "")
            + "\nRevisa tu panel en FerreBarrio.",
        )
        messages.success(request, f"{comercio.nombre}: {comercio.get_estado_display()}.")
        return redirect("comercios:solicitudes")
    return render(request, "comercios/verificar.html", {"comercio": comercio, "form": form})
