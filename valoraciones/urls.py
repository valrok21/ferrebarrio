from django.urls import path

from . import views

app_name = "valoraciones"
urlpatterns = [
    path("mis-reservas/<int:reserva_pk>/valorar/", views.valorar, name="valorar"),
    path("administracion/valoraciones/", views.moderar, name="moderar"),
    path("administracion/valoraciones/<int:pk>/", views.resolver, name="resolver"),
]
