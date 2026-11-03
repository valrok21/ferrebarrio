from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.utils import timezone

from .models import Usuario

MAX_FALLOS = 5
VENTANA_BLOQUEO = 15 * 60
DOMINIO_ANONIMO = "ferrebarrio.invalid"  # lo usa eliminar_cuenta; nadie puede registrarlo


def _claves_bloqueo(email, ip):
    # ponytail: sin contador solo por IP; detrás de un proxy todos comparten REMOTE_ADDR y bloquearía
    # el ingreso de todo el sitio. Contra el rociado de contraseñas: límite o captcha en el proxy.
    return [(f"login-fallos:{(email or '').strip().lower()}:{ip}", MAX_FALLOS)]


class IngresoForm(AuthenticationForm):
    """Login por correo con bloqueo de 15 minutos tras 5 fallos por correo + IP."""

    username = forms.EmailField(label="Correo", widget=forms.EmailInput(attrs={"autofocus": True}))
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Correo o contraseña incorrectos.",
        "bloqueado": "Demasiados intentos fallidos. Espera 15 minutos e inténtalo de nuevo.",
    }

    def clean(self):
        # ponytail: REMOTE_ADDR y no X-Forwarded-For, que lo controla el cliente; detrás de un proxy hay que
        # confiar solo en la cabecera que fije ese proxy.
        ip = self.request.META.get("REMOTE_ADDR", "") if self.request else ""
        claves = _claves_bloqueo(self.data.get("username"), ip)
        if any((cache.get(clave) or 0) >= tope for clave, tope in claves):
            raise forms.ValidationError(self.error_messages["bloqueado"], code="bloqueado")
        try:
            datos = super().clean()
        except forms.ValidationError:
            for clave, _ in claves:
                cache.add(clave, 0, VENTANA_BLOQUEO)
                cache.incr(clave)
            raise
        cache.delete(claves[0][0])
        return datos


class IngresoAdminForm(IngresoForm, AdminAuthenticationForm):
    """El mismo bloqueo para /django-admin/login/; AdminAuthenticationForm exige is_staff."""


class RegistroForm(forms.ModelForm):
    rol = forms.ChoiceField(
        label="Quiero",
        choices=[
            (Usuario.Rol.CLIENTE, "Buscar y reservar productos"),
            (Usuario.Rol.COMERCIANTE, "Registrar mi ferretería"),
        ],
        widget=forms.RadioSelect,
    )
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="Repite la contraseña", widget=forms.PasswordInput, strip=False)
    acepto_privacidad = forms.BooleanField(label="Acepto la política de privacidad y los términos de uso")

    class Meta:
        model = Usuario
        fields = ["nombre", "email", "telefono", "rol"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if email.endswith("@" + DOMINIO_ANONIMO):
            raise forms.ValidationError("Ese correo no es válido.")
        if Usuario.objects.filter(email=email).exists():
            raise forms.ValidationError("Ya existe una cuenta con ese correo.")
        return email

    def clean(self):
        datos = super().clean()
        p1, p2 = datos.get("password1"), datos.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        elif p1:
            usuario = Usuario(email=datos.get("email", ""), nombre=datos.get("nombre", ""))
            try:
                password_validation.validate_password(p1, usuario)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data["password1"])
        usuario.acepto_privacidad_en = timezone.now()
        if commit:
            usuario.save()
        return usuario


class MiCuentaForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ["nombre", "telefono"]


class EliminarCuentaForm(forms.Form):
    password = forms.CharField(label="Confirma con tu contraseña", widget=forms.PasswordInput)

    def __init__(self, usuario, *args, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean_password(self):
        if not self.usuario.check_password(self.cleaned_data["password"]):
            raise forms.ValidationError("Contraseña incorrecta.")
        return self.cleaned_data["password"]
