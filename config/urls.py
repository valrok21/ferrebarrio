from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "FerreBarrio — administración técnica"

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("", include("cuentas.urls")),
    path("", include("comercios.urls")),
    path("", include("catalogo.urls")),
    path("", include("busqueda.urls")),
    path("", include("reservas.urls")),
    path("", include("valoraciones.urls")),
    path("", include("reportes.urls")),
]
