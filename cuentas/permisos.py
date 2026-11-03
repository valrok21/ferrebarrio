from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def rol_requerido(*roles):
    """Exige sesión iniciada y uno de los roles indicados; si no, 403."""

    def decorador(vista):
        @wraps(vista)
        @login_required
        def envuelta(request, *args, **kwargs):
            if request.user.rol not in roles:
                raise PermissionDenied
            return vista(request, *args, **kwargs)

        return envuelta

    return decorador


def comerciante_con_comercio(vista):
    """Rol comerciante y comercio ya registrado; deja el comercio en request.comercio (aislamiento CT-15)."""
    from django.contrib import messages
    from django.shortcuts import redirect

    from comercios.models import Comercio

    @wraps(vista)
    @rol_requerido("comerciante")
    def envuelta(request, *args, **kwargs):
        request.comercio = Comercio.objects.filter(propietario=request.user).first()
        if request.comercio is None:
            messages.info(request, "Primero registra los datos de tu ferretería.")
            return redirect("comercios:registrar")
        return vista(request, *args, **kwargs)

    return envuelta
