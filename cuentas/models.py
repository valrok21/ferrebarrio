from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.gis.geos import GEOSGeometry
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import RegexValidator
from django.db import models
from django.forms.models import model_to_dict

validar_telefono = RegexValidator(
    r"^\+?[0-9 ]{8,15}$", "Ingresa un teléfono válido, por ejemplo +56 9 1234 5678."
)


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        extra.setdefault("rol", Usuario.Rol.CLIENTE)
        usuario = self.model(email=self.normalize_email(email).lower(), **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, rol=Usuario.Rol.ADMIN)
        return self.create_user(email, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    class Rol(models.TextChoices):
        CLIENTE = "cliente", "Cliente"
        COMERCIANTE = "comerciante", "Comerciante"
        ADMIN = "admin", "Administrador"

    email = models.EmailField("correo", unique=True)
    nombre = models.CharField(max_length=120)
    telefono = models.CharField("teléfono", max_length=20, validators=[validar_telefono])
    rol = models.CharField(max_length=12, choices=Rol.choices, default=Rol.CLIENTE)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    acepto_privacidad_en = models.DateTimeField(null=True, blank=True)

    objects = UsuarioManager()
    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["nombre", "telefono"]

    def __str__(self):
        return f"{self.nombre} <{self.email}>"

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    @property
    def es_cliente(self):
        return self.rol == self.Rol.CLIENTE

    @property
    def es_comerciante(self):
        return self.rol == self.Rol.COMERCIANTE

    @property
    def es_admin(self):
        return self.rol == self.Rol.ADMIN


class EncoderAuditoria(DjangoJSONEncoder):
    def default(self, o):
        if isinstance(o, GEOSGeometry):
            return o.wkt
        if isinstance(o, models.Model):
            return o.pk
        return super().default(o)


class RegistroAuditoria(models.Model):
    """Bitácora de escrituras sensibles (CT-15): catálogo, stock, reservas y verificación."""

    usuario = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL)
    accion = models.CharField(max_length=40)
    entidad = models.CharField(max_length=40)
    entidad_id = models.CharField(max_length=40)
    antes = models.JSONField(null=True, blank=True, encoder=EncoderAuditoria)
    despues = models.JSONField(null=True, blank=True, encoder=EncoderAuditoria)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "registro de auditoría"
        verbose_name_plural = "bitácora de auditoría"

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} {self.accion} {self.entidad}#{self.entidad_id}"


def instantanea(obj, campos=None):
    return model_to_dict(obj, fields=campos) if obj is not None else None


def auditar(usuario, accion, obj, antes=None, despues=None):
    return RegistroAuditoria.objects.create(
        usuario=usuario if getattr(usuario, "pk", None) else None,
        accion=accion,
        entidad=obj._meta.model_name,
        entidad_id=str(obj.pk),
        antes=antes,
        despues=despues,
    )
