from django.contrib import admin

from .models import Valoracion


@admin.register(Valoracion)
class ValoracionAdmin(admin.ModelAdmin):
    list_display = ["comercio", "puntaje", "estado", "creada_en"]
    list_filter = ["estado"]
