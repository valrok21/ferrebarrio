from django.urls import path

from . import views

app_name = "comercios"
urlpatterns = [
    path("panel/ficha/", views.registrar, name="registrar"),
    path("comercios/<int:pk>/", views.ficha, name="ficha"),
    path("administracion/comercios/", views.solicitudes, name="solicitudes"),
    path("administracion/comercios/<int:pk>/", views.verificar, name="verificar"),
]
