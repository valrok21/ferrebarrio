"""Reglas de reserva (M4). Todo cambio de stock pasa por aquí, con la fila bloqueada (CT-04, CT-05)."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone

from catalogo.models import Producto
from comercios.models import Comercio
from cuentas.models import Usuario, auditar, instantanea

from .avisos import programar_aviso
from .models import Reserva

CAMPOS = ["estado", "cantidad", "atendida_en", "cerrada_en"]


class ReservaError(Exception):
    pass


def nuevo_codigo():
    # ponytail: 900 000 códigos y verificación previa; el índice único cubre la carrera improbable.
    while True:
        codigo = f"FB-{secrets.randbelow(900_000) + 100_000}"
        if not Reserva.objects.filter(codigo=codigo).exists():
            return codigo


def _url(ruta):
    return settings.SITIO_URL + ruta


def crear_reserva(cliente, producto_pk, cantidad):
    if not cliente.es_cliente:
        raise ReservaError("Solo los clientes pueden reservar.")
    if not cliente.telefono:
        raise ReservaError("Agrega un teléfono en «Mi cuenta» para que el comercio pueda contactarte.")
    if not 1 <= cantidad <= settings.RESERVA_MAX_CANTIDAD:
        raise ReservaError(f"La cantidad debe estar entre 1 y {settings.RESERVA_MAX_CANTIDAD}.")
    with transaction.atomic():
        # Bloquear al usuario serializa sus reservas simultáneas:
        # el límite de activas no se puede saltar (CT-05).
        Usuario.objects.select_for_update().get(pk=cliente.pk)
        if (
            Reserva.objects.filter(cliente=cliente, estado__in=Reserva.ACTIVAS).count()
            >= settings.RESERVA_MAX_ACTIVAS
        ):
            raise ReservaError(
                f"Ya tienes {settings.RESERVA_MAX_ACTIVAS} reservas activas. Retira o anula una antes."
            )
        producto = get_object_or_404(
            Producto.objects.select_for_update(of=("self",)).select_related("comercio__propietario"),
            pk=producto_pk,
            activo=True,
            comercio__estado=Comercio.Estado.APROBADA,
        )
        if producto.stock_disponible < cantidad:
            raise ReservaError("Ya no quedan unidades suficientes de este producto.")
        producto.stock_disponible -= cantidad
        producto.stock_reservado += cantidad
        producto.save(update_fields=["stock_disponible", "stock_reservado"])
        ahora = timezone.now()
        reserva = Reserva.objects.create(
            codigo=nuevo_codigo(),
            producto=producto,
            comercio=producto.comercio,
            cliente=cliente,
            cantidad=cantidad,
            precio_unitario=producto.precio_referencial,
            creada_en=ahora,
            vence_en=ahora + timedelta(hours=settings.RESERVA_VIGENCIA_HORAS),
        )
        auditar(cliente, "crear_reserva", reserva, None, instantanea(reserva, CAMPOS))
        comercio = producto.comercio
        programar_aviso(
            comercio.propietario.email,
            "reserva_nueva",
            f"Nueva reserva {reserva.codigo}",
            f"{cliente.nombre} reservó {cantidad} × {producto.nombre}.\nAtiéndela en {_url('/panel/')}",
            reserva,
        )
        programar_aviso(
            cliente.email,
            "reserva_creada",
            f"Tu reserva {reserva.codigo} en {comercio.nombre}",
            f"Reservaste {cantidad} × {producto.nombre} en {comercio.nombre} ({comercio.direccion}).\n"
            f"Vence el {timezone.localtime(reserva.vence_en):%d/%m a las %H:%M}. "
            "La reserva no es una compra: pagas al retirar.",
            reserva,
        )
    return reserva


def _transicionar(reserva_pk, filtro, desde, hacia, usuario, accion):
    """Cambia de estado con la reserva y el producto bloqueados (orden reserva → producto).

    El filtro lleva siempre el dueño (cliente o propietario del comercio): una reserva ajena da 404 (CT-15).
    """
    with transaction.atomic():
        reserva = get_object_or_404(Reserva.objects.select_for_update(), pk=reserva_pk, **filtro)
        if reserva.estado not in desde:
            raise ReservaError(f"La reserva {reserva.codigo} está {reserva.get_estado_display().lower()}.")
        antes = instantanea(reserva, CAMPOS)
        ahora = timezone.now()
        if hacia != Reserva.Estado.ATENDIDA:
            producto = Producto.objects.select_for_update().get(pk=reserva.producto_id)
            producto.stock_reservado -= reserva.cantidad
            if hacia in (Reserva.Estado.ANULADA, Reserva.Estado.EXPIRADA):
                producto.stock_disponible += reserva.cantidad
            producto.save(update_fields=["stock_disponible", "stock_reservado"])
            reserva.cerrada_en = ahora
        else:
            reserva.atendida_en = ahora
        reserva.estado = hacia
        reserva.save()
        auditar(usuario, accion, reserva, antes, instantanea(reserva, CAMPOS))
        return reserva


def atender_reserva(reserva_pk, usuario):
    """El comercio deja el producto apartado: pendiente → lista para retiro."""
    reserva = _transicionar(
        reserva_pk,
        {"comercio__propietario": usuario},
        [Reserva.Estado.PENDIENTE],
        Reserva.Estado.ATENDIDA,
        usuario,
        "atender_reserva",
    )
    programar_aviso(
        reserva.cliente.email,
        "reserva_atendida",
        f"Tu reserva {reserva.codigo} está lista",
        f"{reserva.comercio.nombre} ya apartó tu pedido. Retíralo antes de las "
        f"{timezone.localtime(reserva.vence_en):%H:%M} con el código {reserva.codigo}.",
        reserva,
    )
    return reserva


def confirmar_retiro(reserva_pk, usuario):
    """El cliente retiró: el stock reservado sale definitivamente del local."""
    return _transicionar(
        reserva_pk,
        {"comercio__propietario": usuario},
        Reserva.ACTIVAS,
        Reserva.Estado.RETIRADA,
        usuario,
        "confirmar_retiro",
    )


def anular_reserva(reserva_pk, usuario, por_cliente=True):
    """HU-14 (cliente) o anulación del comercio: las unidades vuelven a estar disponibles."""
    filtro = {"cliente": usuario} if por_cliente else {"comercio__propietario": usuario}
    reserva = _transicionar(
        reserva_pk,
        filtro,
        Reserva.ACTIVAS,
        Reserva.Estado.ANULADA,
        usuario,
        "anular_reserva_cliente" if por_cliente else "anular_reserva_comercio",
    )
    if por_cliente:
        destino, texto = reserva.comercio.propietario.email, f"{reserva.cliente.nombre} anuló la reserva."
    else:
        destino, texto = (
            reserva.cliente.email,
            f"{reserva.comercio.nombre} anuló tu reserva. Llama al local si tienes dudas.",
        )
    programar_aviso(destino, "reserva_anulada", f"Reserva {reserva.codigo} anulada", texto, reserva)
    return reserva


def expirar_vencidas():
    """CT-10, HU-13: las reservas activas vencidas (también las atendidas) devuelven su stock."""
    expiradas = 0
    for pk in Reserva.objects.filter(estado__in=Reserva.ACTIVAS, vence_en__lte=timezone.now()).values_list(
        "pk", flat=True
    ):
        try:
            reserva = _transicionar(
                pk,
                {"vence_en__lte": timezone.now()},
                Reserva.ACTIVAS,
                Reserva.Estado.EXPIRADA,
                None,
                "expirar_reserva",
            )
        except ReservaError:  # alguien la cerró entre la consulta y el bloqueo
            continue
        expiradas += 1
        programar_aviso(
            reserva.cliente.email,
            "reserva_expirada",
            f"Tu reserva {reserva.codigo} venció",
            f"La reserva de {reserva.producto.nombre} en {reserva.comercio.nombre} venció sin retiro.",
            reserva,
        )
    return expiradas


def avisar_sin_atencion():
    """CT-16: si el comercio no atiende en 30 min, se avisa al cliente con el teléfono del local."""
    limite = timezone.now() - timedelta(minutes=settings.RESERVA_AVISO_SIN_ATENCION_MIN)
    avisadas = 0
    for reserva in Reserva.objects.filter(
        estado=Reserva.Estado.PENDIENTE, creada_en__lte=limite, cliente_avisado_sin_atencion=False
    ).select_related("comercio", "cliente"):
        if Reserva.objects.filter(pk=reserva.pk, cliente_avisado_sin_atencion=False).update(
            cliente_avisado_sin_atencion=True
        ):
            avisadas += 1
            programar_aviso(
                reserva.cliente.email,
                "reserva_sin_atencion",
                f"{reserva.codigo}: el local aún no responde",
                f"{reserva.comercio.nombre} todavía no atiende tu reserva. Puedes llamar al "
                f"{reserva.comercio.telefono}. Tu reserva sigue vigente.",
                reserva,
            )
    return avisadas


def diferencias_stock():
    """CT-11: productos cuyo stock reservado no cuadra con la suma de sus reservas activas."""
    return list(
        Producto.objects.annotate(
            en_reservas=Coalesce(Sum("reservas__cantidad", filter=Q(reservas__estado__in=Reserva.ACTIVAS)), 0)
        )
        .exclude(stock_reservado=F("en_reservas"))
        .select_related("comercio")
    )
