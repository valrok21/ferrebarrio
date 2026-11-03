from django.urls import path

from . import views

app_name = "reservas"
urlpatterns = [
    path("reservar/<int:producto_pk>/", views.nueva, name="nueva"),
    path("mis-reservas/", views.mis_reservas, name="mis_reservas"),
    path("mis-reservas/<int:pk>/", views.detalle, name="detalle"),
    path("mis-reservas/<int:pk>/anular/", views.anular, name="anular"),
    path("panel/", views.panel, name="panel"),
    path("panel/reservas/<int:pk>/<slug:accion>/", views.accion_comercio, name="accion"),
]
