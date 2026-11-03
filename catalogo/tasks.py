from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from comercios.models import Comercio
from reservas.avisos import programar_aviso


@shared_task
def avisar_catalogo_desactualizado():
    """CT-08: aviso diario al comerciante con productos sin actualizar hace más de 72 h."""
    limite = timezone.now() - timedelta(hours=settings.STOCK_DESACTUALIZADO_HORAS)
    comercios = (
        Comercio.objects.filter(estado=Comercio.Estado.APROBADA)
        .annotate(
            viejos=Count("productos", filter=Q(productos__activo=True, productos__actualizado_en__lt=limite))
        )
        .filter(viejos__gt=0)
        .select_related("propietario")
    )
    for c in comercios:
        programar_aviso(
            c.propietario.email,
            "catalogo_desactualizado",
            f"{c.viejos} productos de {c.nombre} por confirmar",
            f"Hola {c.propietario.nombre}:\n\n{c.viejos} productos llevan más de "
            f"{settings.STOCK_DESACTUALIZADO_HORAS} h sin actualizar y se muestran como «POR CONFIRMAR».\n"
            f"Actualízalos en {settings.SITIO_URL}/panel/catalogo/",
        )
    return len(comercios)
