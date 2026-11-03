from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Replace

from .forms import DOMINIO_ANONIMO
from .models import Usuario, auditar


def eliminar_cuenta(usuario):
    """Ley 21.719: anula las reservas activas (libera stock) y anonimiza los datos personales."""
    from reservas.models import Aviso, Reserva
    from reservas.servicios import anular_reserva

    with transaction.atomic():
        for reserva in Reserva.objects.filter(cliente=usuario, estado__in=Reserva.ACTIVAS):
            anular_reserva(reserva.pk, usuario, por_cliente=True)
        usuario = Usuario.objects.select_for_update().get(pk=usuario.pk)
        anonimo = f"eliminado-{usuario.pk}@{DOMINIO_ANONIMO}"
        # Los avisos dirigidos al titular se borran; en los demás (los del comerciante sobre sus reservas,
        # incluido el de anulación recién creado) se reemplazan su nombre y su correo.
        Aviso.objects.filter(destinatario=usuario.email).delete()
        # El correo es único y se reemplaza en todos (p. ej. escalamientos);
        # el nombre no lo es: solo en los avisos de sus reservas.
        for filtro, texto, reemplazo in [
            (Q(reserva__cliente=usuario) | Q(cuerpo__contains=usuario.email), usuario.email, anonimo),
            (Q(reserva__cliente=usuario), usuario.nombre, "Usuario eliminado"),
        ]:
            Aviso.objects.filter(filtro).update(
                cuerpo=Replace("cuerpo", Value(texto), Value(reemplazo)),
                asunto=Replace("asunto", Value(texto), Value(reemplazo)),
            )
        usuario.email = anonimo
        usuario.nombre = "Usuario eliminado"
        usuario.telefono = ""
        usuario.is_active = False
        usuario.set_unusable_password()
        usuario.save()
        auditar(None, "eliminar_cuenta", usuario)
    return usuario
