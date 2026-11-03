from django.conf import settings
from django.db import models
from django.db.models import Q


class Valoracion(models.Model):
    """HU-21..23: una por reserva retirada del propio cliente (CT-06)."""

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "En moderación"
        APROBADA = "aprobada", "Publicada"
        RECHAZADA = "rechazada", "Rechazada"

    reserva = models.OneToOneField("reservas.Reserva", on_delete=models.CASCADE, related_name="valoracion")
    comercio = models.ForeignKey("comercios.Comercio", on_delete=models.CASCADE, related_name="valoraciones")
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="valoraciones"
    )
    puntaje = models.PositiveSmallIntegerField()
    comentario = models.TextField(max_length=500, blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    moderada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-creada_en"]
        verbose_name_plural = "valoraciones"
        constraints = [
            models.CheckConstraint(condition=Q(puntaje__gte=1, puntaje__lte=5), name="puntaje_1_a_5")
        ]

    def __str__(self):
        return f"★{self.puntaje} {self.comercio}"
