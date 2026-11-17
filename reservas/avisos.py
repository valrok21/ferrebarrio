import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import Aviso

log = logging.getLogger(__name__)
MAX_INTENTOS = 3
REDESPACHO_TRAS = timedelta(minutes=2)
# Un encolado aceptado que en 10 min no terminó (worker caído, reintento que no llegó a publicarse) se repite.
# Los reintentos normales de Celery (backoff 30 s, máx. 2) terminan antes.
REENCOLAR_TRAS = timedelta(minutes=10)


def correos_admin():
    from cuentas.models import Usuario

    return list(Usuario.objects.filter(rol=Usuario.Rol.ADMIN, is_active=True).values_list("email", flat=True))


def programar_aviso(destinatario, tipo, asunto, cuerpo, reserva=None):
    """Registra el aviso y lo despacha a Celery solo si la transacción que lo origina se confirma."""

    aviso = Aviso.objects.create(
        destinatario=destinatario, tipo=tipo, asunto=asunto[:200], cuerpo=cuerpo, reserva=reserva
    )
    transaction.on_commit(lambda: despachar(aviso.pk))
    log.info("Aviso %s programado: tipo=%s reserva=%s", aviso.pk, tipo, reserva and reserva.pk)
    return aviso


def despachar(aviso_id):
    """Encola el envío. Si el broker no responde, el aviso queda pendiente y lo retoma
    `redespachar_pendientes`:
    la reserva ya está confirmada y el request no debe fallar por el correo."""
    from .tasks import enviar_aviso_tarea

    try:
        enviar_aviso_tarea.delay(aviso_id)
    except Exception as e:
        log.warning(
            "Aviso %s sin despachar (broker no disponible: %s); se reintentará", aviso_id, type(e).__name__
        )
        return
    Aviso.objects.filter(pk=aviso_id).update(despachado_en=timezone.now())


def redespachar_pendientes(limite=100):
    """Pendientes de más de 2 min que nunca entraron a la cola (broker caído) o cuyo último encolado
    no terminó en 10 min (worker caído, reintento perdido). Por fecha de encolado y no por `intentos`:
    así un worker caído no acumula una copia por minuto. Una copia duplicada no reenvía: `enviar_aviso`
    bloquea la fila."""
    ahora = timezone.now()
    ids = list(
        Aviso.objects.filter(
            Q(despachado_en__isnull=True) | Q(despachado_en__lte=ahora - REENCOLAR_TRAS),
            estado=Aviso.Estado.PENDIENTE,
            intentos__lt=MAX_INTENTOS,
            creado_en__lte=ahora - REDESPACHO_TRAS,
            creado_en__gte=ahora - timedelta(days=1),
        ).values_list("pk", flat=True)[:limite]
    )
    for pk in ids:
        despachar(pk)
    if ids:
        log.warning("Re-despachados %s avisos pendientes: %s", len(ids), ids)
    return len(ids)


# Avisos sin reserva: a dónde lleva el botón del correo.
RUTA_POR_TIPO = {"catalogo_desactualizado": "catalogo:lista", "verificacion": "comercios:registrar"}


def html_aviso(aviso):
    """Versión HTML del correo: detalle de la reserva y botón de acción (el texto plano se mantiene)."""
    reserva = aviso.reserva
    if reserva:
        es_cliente = aviso.destinatario.lower() == reserva.cliente.email.lower()
        ruta, cta = (
            (reverse("reservas:detalle", args=[reserva.pk]), "Ver mi reserva")
            if es_cliente
            else (reverse("reservas:panel"), "Ir al panel")
        )
    else:
        nombre = RUTA_POR_TIPO.get(aviso.tipo)
        ruta, cta = nombre and reverse(nombre), "Abrir FerreBarrio"
    return render_to_string(
        "emails/aviso.html",
        {"aviso": aviso, "reserva": reserva, "cta_url": ruta and settings.SITIO_URL + ruta, "cta_texto": cta},
    )


def enviar_aviso(aviso_id):
    """Un intento de envío con la fila bloqueada (un despacho duplicado espera y ve el aviso ya enviado).
    Lanza la excepción para que Celery reintente; al 3.er fallo escala y no lanza.
    Entrega «al menos una vez»: si el worker muere entre el SMTP y el commit, el aviso puede repetirse."""
    fallo = escalado = None
    with transaction.atomic():
        aviso = (
            Aviso.objects.select_for_update(of=("self",))
            .select_related("reserva__cliente", "reserva__producto", "reserva__comercio")
            .get(pk=aviso_id)
        )
        if aviso.estado != Aviso.Estado.PENDIENTE:
            return aviso
        aviso.intentos += 1
        try:
            send_mail(aviso.asunto, aviso.cuerpo, None, [aviso.destinatario], html_message=html_aviso(aviso))
        except Exception as e:
            aviso.error = f"{type(e).__name__}: {e}"[:500]
            if aviso.intentos < MAX_INTENTOS:
                aviso.save(update_fields=["intentos", "error"])
                log.warning("Aviso %s intento %s fallido: %s", aviso.pk, aviso.intentos, type(e).__name__)
                fallo = e
            else:
                aviso.estado = Aviso.Estado.FALLIDO
                aviso.save(update_fields=["intentos", "error", "estado"])
                escalado = aviso
        else:
            aviso.estado, aviso.enviado_en = Aviso.Estado.ENVIADO, timezone.now()
            aviso.save(update_fields=["intentos", "estado", "enviado_en"])
            log.info("Aviso %s enviado: tipo=%s intento=%s", aviso.pk, aviso.tipo, aviso.intentos)
    if fallo:
        raise fallo
    if escalado:
        escalar(escalado)
        return escalado
    contar_cuota()
    return aviso


def escalar(aviso):
    # ponytail: el canal alternativo es un correo directo a los administradores;
    # SMS/WhatsApp si el piloto lo exige.
    log.error("Aviso %s fallido tras %s intentos: %s", aviso.pk, aviso.intentos, aviso.error)
    send_mail(
        f"[FerreBarrio] Aviso fallido: {aviso.asunto}",
        f"No se pudo avisar a {aviso.destinatario} ({aviso.tipo}) tras {aviso.intentos} intentos.\n"
        f"Error: {aviso.error}\n\nContenido:\n{aviso.cuerpo}",
        None,
        correos_admin(),
        fail_silently=True,
    )


def contar_cuota():
    """CT-18: cuenta envíos del día y alerta una sola vez al llegar al 80 % de la cuota del proveedor."""
    dia = timezone.localdate().isoformat()
    clave = f"avisos:enviados:{dia}"
    cache.add(clave, 0, timeout=2 * 86400)
    enviados = cache.incr(clave)
    if enviados >= settings.AVISOS_CUOTA_DIARIA * 0.8 and cache.add(
        f"avisos:alerta:{dia}", 1, timeout=2 * 86400
    ):
        send_mail(
            "[FerreBarrio] Cuota de correo al 80 %",
            f"Hoy se enviaron {enviados} de {settings.AVISOS_CUOTA_DIARIA} correos permitidos.",
            None,
            correos_admin(),
            fail_silently=True,
        )
    return enviados
