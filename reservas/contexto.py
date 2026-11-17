from .models import Reserva


def pendientes(request):
    """Contador de reservas nuevas en la navbar del comerciante (una consulta por página, solo ese rol)."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated and user.es_comerciante):
        return {}
    return {
        "reservas_pendientes": Reserva.objects.filter(
            comercio__propietario=user, estado=Reserva.Estado.PENDIENTE
        ).count()
    }
