from django.contrib.gis.db import models


class Busqueda(models.Model):
    """HU-20, CT-14: registro anónimo de cada búsqueda (ubicación redondeada a ~100 m)."""

    termino = models.CharField(max_length=60, db_index=True)
    categoria = models.ForeignKey("catalogo.Categoria", null=True, blank=True, on_delete=models.SET_NULL)
    ubicacion_aprox = models.PointField(geography=True, srid=4326)
    comuna = models.CharField(max_length=60, blank=True)
    radio_km = models.PositiveSmallIntegerField()
    n_resultados = models.PositiveSmallIntegerField()
    n_con_stock = models.PositiveSmallIntegerField()
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-fecha"]
