from celery import shared_task

from . import servicios
from .avisos import correos_admin, enviar_aviso, programar_aviso


@shared_task(autoretry_for=(Exception,), max_retries=2, retry_backoff=30)
def enviar_aviso_tarea(aviso_id):
    enviar_aviso(aviso_id)


@shared_task
def expirar_reservas():
    return servicios.expirar_vencidas()


@shared_task
def avisar_sin_atencion():
    return servicios.avisar_sin_atencion()


@shared_task
def conciliar_stock():
    """CT-11: diaria. Avisa a los administradores si el stock reservado no cuadra con las reservas activas."""
    diferencias = servicios.diferencias_stock()
    if diferencias:
        detalle = "\n".join(
            f"- {p.comercio} / {p.nombre}: reservado {p.stock_reservado}, en reservas {p.en_reservas}"
            for p in diferencias
        )
        for correo in correos_admin():
            programar_aviso(
                correo, "conciliacion", f"Conciliación: {len(diferencias)} diferencias de stock", detalle
            )
    return len(diferencias)
