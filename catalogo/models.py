from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .texto import normalizar_texto


class Categoria(models.Model):
    """HU-18: categorías compartidas por todos los comercios (se administran en el Django admin)."""

    nombre = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "categorías"

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    class Unidad(models.TextChoices):
        UNIDAD = "unidad", "unidad"
        CAJA = "caja", "caja"
        BOLSA = "bolsa", "bolsa"
        KILO = "kg", "kg"
        METRO = "metro", "metro"
        LITRO = "litro", "litro"
        GALON = "galon", "galón"
        PAR = "par", "par"
        ROLLO = "rollo", "rollo"

    comercio = models.ForeignKey("comercios.Comercio", on_delete=models.CASCADE, related_name="productos")
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="productos")
    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, editable=False, db_index=True)
    unidad = models.CharField(max_length=10, choices=Unidad.choices, default=Unidad.UNIDAD)
    precio_referencial = models.PositiveIntegerField("precio referencial (CLP)")
    stock_disponible = models.IntegerField("stock disponible", default=0)
    stock_reservado = models.IntegerField(default=0, editable=False)
    # Solo cambia cuando el comerciante edita o carga planilla: mide la frescura del stock (CT-02).
    actualizado_en = models.DateTimeField(default=timezone.now)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["comercio", "nombre_normalizado"],
                condition=Q(activo=True),
                name="producto_unico_por_comercio",
            ),
            models.CheckConstraint(condition=Q(stock_disponible__gte=0), name="stock_disponible_no_negativo"),
            models.CheckConstraint(condition=Q(stock_reservado__gte=0), name="stock_reservado_no_negativo"),
        ]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        # NFKD puede alargar el texto («㎏» → «kg»): se recorta igual que la clave de la planilla.
        self.nombre_normalizado = normalizar_texto(self.nombre)[:120]
        if "update_fields" in kwargs and kwargs["update_fields"] is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "nombre_normalizado"}
        super().save(*args, **kwargs)

    @property
    def desactualizado(self):
        return timezone.now() - self.actualizado_en > timedelta(hours=settings.STOCK_DESACTUALIZADO_HORAS)

    @property
    def marca(self):
        """(clave, texto) de la marca de stock: POR CONFIRMAR manda sobre el número (CT-02, HU-09)."""
        if self.desactualizado:
            return "confirmar", "POR CONFIRMAR"
        if self.stock_disponible > 0:
            return "stock", f"STOCK {self.stock_disponible}"
        return "sin", "SIN STOCK"


class CargaCatalogo(models.Model):
    """HU-06 (CT-07): resultado de cada carga de planilla."""

    comercio = models.ForeignKey("comercios.Comercio", on_delete=models.CASCADE, related_name="cargas")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    archivo = models.CharField(max_length=200)
    total = models.PositiveIntegerField(default=0)
    ok = models.PositiveIntegerField(default=0)
    errores = models.JSONField(default=list)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    @property
    def resumen(self):
        texto = f"{self.total} filas, {self.ok} ok, {len(self.errores)} con error"
        if self.errores:
            texto += " (" + "; ".join(f"fila {e['fila']}: {e['error']}" for e in self.errores[:5])
            texto += "…)" if len(self.errores) > 5 else ")"
        return texto
