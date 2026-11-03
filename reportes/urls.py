from django.urls import path

from . import views

app_name = "reportes"
urlpatterns = [
    path("panel/reportes/", views.comerciante, name="comerciante"),
    path("administracion/", views.admin, name="admin"),
]
