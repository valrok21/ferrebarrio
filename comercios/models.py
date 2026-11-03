from django.conf import settings
from django.contrib.gis.db import models

from cuentas.models import validar_telefono

COMUNAS = {
    # ponytail: centroides aproximados de las comunas del piloto; agregar filas al ampliar la cobertura.
    "Providencia": (-33.4314, -70.6093),
    "Ñuñoa": (-33.4543, -70.6036),
    "Santiago": (-33.4489, -70.6693),
    "Las Condes": (-33.4130, -70.5830),
    "La Reina": (-33.4500, -70.5420),
    "Macul": (-33.4870, -70.5990),
    "San Miguel": (-33.4970, -70.6510),
    "Recoleta": (-33.4060, -70.6400),
}


class Comercio(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de verificación"
        OBSERVADA = "observada", "Observada"
        APROBADA = "aprobada", "Aprobada"
        RECHAZADA = "rechazada", "Rechazada"

    class Origen(models.TextChoices):
        GEOCODIFICADA = "geocodificada", "Geocodificada"
        MANUAL = "manual", "Marcada en el mapa"

    propietario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comercio"
    )
    rut = models.CharField("RUT", max_length=12, unique=True)
    nombre = models.CharField(max_length=120)
    direccion = models.CharField("dirección", max_length=200)
    comuna = models.CharField(max_length=60, choices=[(c, c) for c in COMUNAS])
    ubicacion = models.PointField(geography=True, srid=4326, null=True, blank=True)
    origen_ubicacion = models.CharField(max_length=15, choices=Origen.choices, blank=True)
    horario = models.CharField(max_length=200, help_text="Ej.: Lun a Vie 9:00–19:00, Sáb 9:00–14:00")
    telefono = models.CharField("teléfono", max_length=20, validators=[validar_telefono])
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    motivo = models.TextField(blank=True)
    verificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    verificado_en = models.DateTimeField(null=True, blank=True)
    catalogo_actualizado_en = models.DateTimeField(null=True, blank=True)
    acepto_terminos_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

    @property
    def editable_completo(self):
        return self.estado in (self.Estado.PENDIENTE, self.Estado.OBSERVADA)


class CacheGeocodificacion(models.Model):
    """CT-17: cada dirección se consulta a Nominatim una sola vez."""

    direccion = models.CharField(max_length=300, unique=True)
    lat = models.FloatField()
    lon = models.FloatField()
    fecha = models.DateTimeField(auto_now_add=True)
