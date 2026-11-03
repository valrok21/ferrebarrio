from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import connection
from django.http import HttpResponse
from django.shortcuts import redirect, render

from .forms import EliminarCuentaForm, IngresoForm, MiCuentaForm, RegistroForm
from .models import Usuario
from .permisos import rol_requerido
from .servicios import eliminar_cuenta


class IngresarView(LoginView):
    template_name = "cuentas/ingresar.html"
    authentication_form = IngresoForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return destino_por_rol(self.request.user)


def destino_por_rol(usuario):
    if usuario.es_comerciante:
        return "/panel/"
    if usuario.es_admin:
        return "/administracion/"
    return "/"


def registro(request):
    if request.user.is_authenticated:
        return redirect("busqueda:inicio")
    form = RegistroForm(request.POST or None, initial={"rol": request.GET.get("rol", Usuario.Rol.CLIENTE)})
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Cuenta creada.")
        return redirect("comercios:registrar" if usuario.es_comerciante else "busqueda:inicio")
    return render(request, "cuentas/registro.html", {"form": form})


@login_required
def mi_cuenta(request):
    form = MiCuentaForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Datos actualizados.")
        return redirect("cuentas:mi_cuenta")
    return render(request, "cuentas/mi_cuenta.html", {"form": form})


@rol_requerido(Usuario.Rol.CLIENTE)
def eliminar(request):
    form = EliminarCuentaForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        eliminar_cuenta(request.user)
        logout(request)
        messages.success(request, "Tu cuenta fue eliminada y tus datos personales anonimizados.")
        return redirect("busqueda:inicio")
    return render(request, "cuentas/eliminar.html", {"form": form})


def salud(request):
    try:
        connection.ensure_connection()
    except Exception:
        return HttpResponse("sin base de datos", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")
