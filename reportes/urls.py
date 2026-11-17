from django.urls import path

from . import datos, views

app_name = "reportes"
urlpatterns = [
    path("panel/reportes/", views.comerciante, name="comerciante"),
    path("administracion/", views.admin, name="admin"),
    path("administracion/datos/", datos.indice, name="datos"),
    path("administracion/datos/usuarios/<int:pk>/activo/", datos.usuario_activo, name="datos_usuario_activo"),
    path("administracion/datos/categorias/nueva/", datos.categoria, name="datos_categoria_nueva"),
    path("administracion/datos/categorias/<int:pk>/", datos.categoria, name="datos_categoria"),
    path("administracion/datos/<slug:tabla>/", datos.tabla, name="datos_tabla"),
]
