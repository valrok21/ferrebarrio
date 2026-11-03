import logging

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import Aviso

log = logging.getLogger(__name__)
MAX_INTENTOS = 3


def correos_admin():
    from cuentas.models import Usuario

    return list(Usuario.objects.filter(rol=Usuario.Rol.ADMIN, is_active=True).values_list("email", flat=True))


def programar_aviso(destinatario, tipo, asunto, cuerpo, reserva=None):
    """Registra el aviso y lo despacha a Celery solo si la transacción que lo origina se confirma."""
    from .tasks import enviar_aviso_tarea

    aviso = Aviso.objects.create(
        destinatario=destinatario, tipo=tipo, asunto=asunto[:200], cuerpo=cuerpo, reserva=reserva
    )
    transaction.on_commit(lambda: enviar_aviso_tarea.delay(aviso.pk))
    return aviso


def enviar_aviso(aviso_id):
    """Un intento de envío. Lanza la excepción para que Celery reintente; al 3.er fallo escala y no lanza."""
    aviso = Aviso.objects.get(pk=aviso_id)
    if aviso.estado != Aviso.Estado.PENDIENTE:
        return aviso
    aviso.intentos += 1
    try:
        send_mail(aviso.asunto, aviso.cuerpo, None, [aviso.destinatario])
    except Exception as e:
        aviso.error = f"{type(e).__name__}: {e}"[:500]
        if aviso.intentos < MAX_INTENTOS:
            aviso.save(update_fields=["intentos", "error"])
            raise
        aviso.estado = Aviso.Estado.FALLIDO
        aviso.save(update_fields=["intentos", "error", "estado"])
        escalar(aviso)
        return aviso
    aviso.estado, aviso.enviado_en = Aviso.Estado.ENVIADO, timezone.now()
    aviso.save(update_fields=["intentos", "estado", "enviado_en"])
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
