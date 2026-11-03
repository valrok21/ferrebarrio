from django.contrib import admin

from .models import CacheGeocodificacion, Comercio


@admin.register(Comercio)
class ComercioAdmin(admin.ModelAdmin):
    list_display = ["nombre", "rut", "comuna", "estado", "propietario"]
    list_filter = ["estado", "comuna"]
    search_fields = ["nombre", "rut"]


admin.site.register(CacheGeocodificacion)
