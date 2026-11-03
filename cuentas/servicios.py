from django.db import transaction

from .models import Usuario, auditar


def eliminar_cuenta(usuario):
    """Ley 21.719: anula las reservas activas (libera stock) y anonimiza los datos personales."""
    from reservas.models import Reserva
    from reservas.servicios import anular_reserva

    with transaction.atomic():
        for reserva in Reserva.objects.filter(cliente=usuario, estado__in=Reserva.ACTIVAS):
            anular_reserva(reserva.pk, usuario, por_cliente=True)
        usuario = Usuario.objects.select_for_update().get(pk=usuario.pk)
        usuario.email = f"eliminado-{usuario.pk}@ferrebarrio.invalid"
        usuario.nombre = "Usuario eliminado"
        usuario.telefono = ""
        usuario.is_active = False
        usuario.set_unusable_password()
        usuario.save()
        auditar(None, "eliminar_cuenta", usuario)
    return usuario
