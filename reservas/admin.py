from django.contrib import admin

from .models import Aviso, Reserva


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = [
        "codigo",
        "comercio",
        "producto",
        "cliente",
        "cantidad",
        "estado",
        "creada_en",
        "vence_en",
    ]
    list_filter = ["estado", "comercio"]
    search_fields = ["codigo"]

    def has_change_permission(self, request, obj=None):
        return False  # las transiciones pasan por los servicios, que mueven el stock


@admin.register(Aviso)
class AvisoAdmin(admin.ModelAdmin):
    list_display = ["tipo", "destinatario", "estado", "intentos", "creado_en"]
    list_filter = ["estado", "tipo"]
