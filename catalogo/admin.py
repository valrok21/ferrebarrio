from django.contrib import admin

from .models import CargaCatalogo, Categoria, Producto

admin.site.register(Categoria)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = [
        "nombre",
        "comercio",
        "categoria",
        "precio_referencial",
        "stock_disponible",
        "stock_reservado",
        "actualizado_en",
        "activo",
    ]
    list_filter = ["activo", "categoria", "comercio"]
    search_fields = ["nombre"]
    readonly_fields = ["stock_reservado"]


@admin.register(CargaCatalogo)
class CargaCatalogoAdmin(admin.ModelAdmin):
    list_display = ["comercio", "archivo", "total", "ok", "fecha"]
