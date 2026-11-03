from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "cuentas"
urlpatterns = [
    path("cuentas/ingresar/", views.IngresarView.as_view(), name="ingresar"),
    path("cuentas/salir/", LogoutView.as_view(), name="salir"),
    path("cuentas/registro/", views.registro, name="registro"),
    path("cuentas/mi-cuenta/", views.mi_cuenta, name="mi_cuenta"),
    path("cuentas/eliminar/", views.eliminar, name="eliminar"),
    path("privacidad/", TemplateView.as_view(template_name="cuentas/privacidad.html"), name="privacidad"),
    path("terminos/", TemplateView.as_view(template_name="cuentas/terminos.html"), name="terminos"),
    path("salud/", views.salud, name="salud"),
]
