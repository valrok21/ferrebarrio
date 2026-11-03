from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import RegistroAuditoria, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    ordering = ["email"]
    list_display = ["email", "nombre", "rol", "is_active", "fecha_registro"]
    list_filter = ["rol", "is_active"]
    search_fields = ["email", "nombre"]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Datos", {"fields": ["nombre", "telefono", "rol", "acepto_privacidad_en"]}),
        ("Permisos", {"fields": ["is_active", "is_staff", "is_superuser"]}),
    ]
    add_fieldsets = [(None, {"fields": ["email", "nombre", "telefono", "rol", "password1", "password2"]})]
    readonly_fields = ["acepto_privacidad_en"]


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ["fecha", "usuario", "accion", "entidad", "entidad_id"]
    list_filter = ["accion", "entidad"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
