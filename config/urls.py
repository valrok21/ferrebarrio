from django.urls import include, path

urlpatterns = [
    path("", include("cuentas.urls")),
    path("", include("comercios.urls")),
    path("", include("catalogo.urls")),
    path("", include("busqueda.urls")),
    path("", include("reservas.urls")),
    path("", include("valoraciones.urls")),
    path("", include("reportes.urls")),
]
