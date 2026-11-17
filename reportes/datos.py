"""Sección «Datos» del panel del administrador: tablas de la plataforma con búsqueda, filtro y paginación.

Reemplaza al admin de Django. Reservas, avisos y valoraciones son de solo lectura: crearlas o cambiarlas pasa
por los servicios, que mueven el stock y envían los correos. Las únicas escrituras son activar o desactivar
usuarios y crear o renombrar categorías, y todas quedan en la bitácora de auditoría.
"""

from datetime import datetime

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogo.models import CargaCatalogo, Categoria, Producto
from catalogo.texto import normalizar_texto
from comercios.models import Comercio
from cuentas.models import RegistroAuditoria, Usuario, auditar, instantanea
from cuentas.permisos import rol_requerido
from reservas.models import Aviso, Reserva
from valoraciones.models import Valoracion

POR_PAGINA = 50
SI_NO = [("1", "Sí"), ("0", "No")]

# Una entrada por tabla: título, queryset (con select_related para no hacer una consulta por fila), columnas
# (encabezado, atributo; «a.b» recorre relaciones), campos de búsqueda y un filtro opcional (campo, opciones).
# El nombre del campo filtrado y los de búsqueda salen de aquí, nunca de la URL.
TABLAS = {
    "usuarios": {
        "titulo": "Usuarios",
        "qs": lambda: Usuario.objects.order_by("email"),
        "columnas": [
            ("Correo", "email"),
            ("Nombre", "nombre"),
            ("Rol", "get_rol_display"),
            ("Activo", "is_active"),
            ("Registro", "fecha_registro"),
        ],
        "buscar": ["email", "nombre"],
        "filtro": ("rol", Usuario.Rol.choices),
    },
    "comercios": {
        "titulo": "Comercios",
        "qs": lambda: Comercio.objects.select_related("propietario").order_by("nombre"),
        "columnas": [
            ("Nombre", "nombre"),
            ("RUT", "rut"),
            ("Comuna", "comuna"),
            ("Estado", "get_estado_display"),
            ("Propietario", "propietario.email"),
        ],
        "buscar": ["nombre", "rut"],
        "filtro": ("estado", Comercio.Estado.choices),
    },
    "productos": {
        "titulo": "Productos",
        "qs": lambda: Producto.objects.select_related("comercio", "categoria").order_by("nombre", "pk"),
        "columnas": [
            ("Nombre", "nombre"),
            ("Comercio", "comercio.nombre"),
            ("Categoría", "categoria.nombre"),
            ("Precio", "precio_referencial"),
            ("Disponible", "stock_disponible"),
            ("Reservado", "stock_reservado"),
            ("Actualizado", "actualizado_en"),
            ("Activo", "activo"),
        ],
        "buscar": ["nombre", "comercio__nombre"],
        "filtro": ("activo", SI_NO),
    },
    "categorias": {
        "titulo": "Categorías",
        "qs": lambda: Categoria.objects.order_by("nombre"),
        "columnas": [("Nombre", "nombre")],
        "buscar": ["nombre"],
    },
    "reservas": {
        "titulo": "Reservas",
        "qs": lambda: Reserva.objects.select_related("comercio", "producto", "cliente").order_by(
            "-creada_en"
        ),
        "columnas": [
            ("Código", "codigo"),
            ("Comercio", "comercio.nombre"),
            ("Producto", "producto.nombre"),
            ("Cliente", "cliente.email"),
            ("Cantidad", "cantidad"),
            ("Estado", "get_estado_display"),
            ("Creada", "creada_en"),
            ("Vence", "vence_en"),
        ],
        "buscar": ["codigo"],
        "filtro": ("estado", Reserva.Estado.choices),
    },
    "avisos": {
        "titulo": "Avisos por correo",
        "qs": lambda: Aviso.objects.order_by("-creado_en"),
        "columnas": [
            ("Asunto", "asunto"),
            ("Destinatario", "destinatario"),
            ("Tipo", "tipo"),
            ("Estado", "get_estado_display"),
            ("Intentos", "intentos"),
            ("Creado", "creado_en"),
            ("Enviado", "enviado_en"),
        ],
        "buscar": ["destinatario", "asunto"],
        "filtro": ("estado", Aviso.Estado.choices),
    },
    "cargas": {
        "titulo": "Cargas de planilla",
        "qs": lambda: CargaCatalogo.objects.select_related("comercio").order_by("-fecha"),
        "columnas": [
            ("Comercio", "comercio.nombre"),
            ("Archivo", "archivo"),
            ("Filas", "total"),
            ("Correctas", "ok"),
            ("Fecha", "fecha"),
        ],
        "buscar": ["comercio__nombre", "archivo"],
    },
    "auditoria": {
        "titulo": "Bitácora de auditoría",
        "qs": lambda: RegistroAuditoria.objects.select_related("usuario").order_by("-fecha"),
        "columnas": [
            ("Fecha", "fecha"),
            ("Usuario", "usuario.email"),
            ("Acción", "accion"),
            ("Entidad", "entidad"),
            ("Id", "entidad_id"),
        ],
        "buscar": ["accion", "entidad", "entidad_id"],
    },
    "valoraciones": {
        "titulo": "Valoraciones",
        "qs": lambda: Valoracion.objects.select_related("comercio").order_by("-creada_en"),
        "columnas": [
            ("Comercio", "comercio.nombre"),
            ("Puntaje", "puntaje"),
            ("Estado", "get_estado_display"),
            ("Creada", "creada_en"),
        ],
        "buscar": ["comercio__nombre"],
        "filtro": ("estado", Valoracion.Estado.choices),
    },
}


def _valor(obj, atributo):
    """Lee «a.b.c» sobre el objeto; llama los métodos (get_*_display) y traduce booleanos, fechas y vacíos."""
    for parte in atributo.split("."):
        obj = getattr(obj, parte, None)
        if obj is None:
            return "—"
    if callable(obj):
        obj = obj()
    if isinstance(obj, bool):
        return "Sí" if obj else "No"
    if isinstance(obj, datetime):
        return f"{timezone.localtime(obj):%d/%m/%Y %H:%M}"
    return obj


@rol_requerido(Usuario.Rol.ADMIN)
def indice(request):
    tablas = [(clave, conf["titulo"]) for clave, conf in TABLAS.items()]
    return render(request, "reportes/datos.html", {"tablas": tablas})


@rol_requerido(Usuario.Rol.ADMIN)
def tabla(request, tabla):
    conf = TABLAS.get(tabla)
    if conf is None:
        raise Http404
    qs = conf["qs"]()
    q = request.GET.get("q", "").strip()
    if q:
        condicion = Q()
        for campo in conf["buscar"]:
            condicion |= Q(**{f"{campo}__icontains": q})
        qs = qs.filter(condicion)
    filtro, valor = conf.get("filtro"), None
    if filtro:
        campo, opciones = filtro
        valor = request.GET.get(campo)
        if valor in dict(opciones):  # un valor ajeno a las opciones se ignora
            qs = qs.filter(**{campo: valor})
        else:
            valor = None
    pagina = Paginator(qs, POR_PAGINA).get_page(request.GET.get("pagina"))
    return render(
        request,
        "reportes/datos_tabla.html",
        {
            "tabla": tabla,
            "titulo": conf["titulo"],
            "encabezados": [titulo for titulo, _ in conf["columnas"]],
            "filas": [(obj, [_valor(obj, a) for _, a in conf["columnas"]]) for obj in pagina],
            "pagina": pagina,
            "q": q,
            "filtro_campo": filtro[0] if filtro else None,
            "filtro_opciones": filtro[1] if filtro else [],
            "filtro_valor": valor,
        },
    )


@require_POST
@rol_requerido(Usuario.Rol.ADMIN)
def usuario_activo(request, pk):
    """Activa o desactiva una cuenta. Recibe el valor final, no alterna: un reintento no deshace el cambio."""
    valor = request.POST.get("activo")
    if valor not in ("0", "1"):
        return HttpResponseBadRequest("activo debe ser 0 o 1")
    activo = valor == "1"
    with transaction.atomic():  # el cambio y su registro en la bitácora, juntos o ninguno
        # Bloquea a los admins activos: si dos se desactivan entre sí a la vez, el segundo ve al actor ya
        # inactivo y se rechaza, así la plataforma nunca queda sin admins activos.
        activos = set(
            Usuario.objects.select_for_update()
            .filter(rol=Usuario.Rol.ADMIN, is_active=True)
            .values_list("pk", flat=True)
        )
        if request.user.pk not in activos:
            raise PermissionDenied
        usuario = get_object_or_404(Usuario.objects.select_for_update(), pk=pk)
        if usuario.pk == request.user.pk and not activo:
            messages.error(request, "No puedes desactivar tu propia cuenta.")
        elif usuario.is_active != activo:
            usuario.is_active = activo
            usuario.save(update_fields=["is_active"])
            accion = "activar_usuario" if activo else "desactivar_usuario"
            auditar(request.user, accion, usuario, {"is_active": not activo}, {"is_active": activo})
            messages.success(request, f"{usuario.email}: cuenta {'activada' if activo else 'desactivada'}.")
    return redirect("reportes:datos_tabla", tabla="usuarios")


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre"]

    def clean_nombre(self):
        # La planilla asocia la categoría por nombre normalizado: «Jardinería» y «jardineria» chocarían.
        nombre = self.cleaned_data["nombre"]
        clave = normalizar_texto(nombre)
        otras = Categoria.objects.exclude(pk=self.instance.pk).values_list("nombre", flat=True)
        if any(normalizar_texto(otra) == clave for otra in otras):
            raise forms.ValidationError("Ya existe una categoría con ese nombre.")
        return nombre


@rol_requerido(Usuario.Rol.ADMIN)
def categoria(request, pk=None):
    """Crea (sin pk) o renombra una categoría. Borrar no se ofrece: los productos la protegen."""
    instancia = get_object_or_404(Categoria, pk=pk) if pk else None
    antes = instantanea(instancia, ["nombre"])
    form = CategoriaForm(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            guardada = form.save()
            accion = "renombrar_categoria" if instancia else "crear_categoria"
            auditar(request.user, accion, guardada, antes, instantanea(guardada, ["nombre"]))
        messages.success(request, f"Categoría «{guardada.nombre}» guardada.")
        return redirect("reportes:datos_tabla", tabla="categorias")
    titulo = f"Renombrar «{instancia.nombre}»" if instancia else "Nueva categoría"
    return render(
        request, "reportes/datos_categoria.html", {"form": form, "titulo": titulo, "boton": "Guardar"}
    )
