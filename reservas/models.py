from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Reserva(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ATENDIDA = "atendida", "Lista para retiro"
        RETIRADA = "retirada", "Retirada"
        ANULADA = "anulada", "Anulada"
        EXPIRADA = "expirada", "Expirada"

    ACTIVAS = ("pendiente", "atendida")

    codigo = models.CharField(max_length=9, unique=True)
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, related_name="reservas")
    comercio = models.ForeignKey("comercios.Comercio", on_delete=models.PROTECT, related_name="reservas")
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reservas")
    cantidad = models.PositiveSmallIntegerField()
    precio_unitario = models.PositiveIntegerField()
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    creada_en = models.DateTimeField(default=timezone.now, db_index=True)
    vence_en = models.DateTimeField(db_index=True)
    atendida_en = models.DateTimeField(null=True, blank=True)
    cerrada_en = models.DateTimeField(null=True, blank=True)
    cliente_avisado_sin_atencion = models.BooleanField(default=False)

    class Meta:
        ordering = ["-creada_en"]
        constraints = [
            models.CheckConstraint(
                condition=Q(cantidad__gte=1, cantidad__lte=20), name="reserva_cantidad_1_a_20"
            ),
        ]

    def __str__(self):
        return self.codigo

    @property
    def total(self):
        return self.cantidad * self.precio_unitario

    @property
    def activa(self):
        return self.estado in self.ACTIVAS


class Aviso(models.Model):
    """Correo transaccional con reintentos y trazabilidad (CT-09, CT-18)."""

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADO = "enviado", "Enviado"
        FALLIDO = "fallido", "Fallido"

    reserva = models.ForeignKey(
        Reserva, null=True, blank=True, on_delete=models.SET_NULL, related_name="avisos"
    )
    destinatario = models.EmailField()
    tipo = models.CharField(max_length=40)
    asunto = models.CharField(max_length=200)
    cuerpo = models.TextField()
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    intentos = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    enviado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.tipo} → {self.destinatario} ({self.estado})"
