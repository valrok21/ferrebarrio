from django.urls import path

from . import views

app_name = "catalogo"
urlpatterns = [
    path("panel/catalogo/", views.lista, name="lista"),
    path("panel/catalogo/nuevo/", views.editar, name="nuevo"),
    path("panel/catalogo/<int:pk>/", views.editar, name="editar"),
    path("panel/catalogo/<int:pk>/eliminar/", views.eliminar, name="eliminar"),
    path("panel/catalogo/planilla/", views.subir_planilla, name="planilla"),
    path("panel/catalogo/plantilla.xlsx", views.descargar_plantilla, name="plantilla"),
]
