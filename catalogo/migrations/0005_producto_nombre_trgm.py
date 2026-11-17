from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Rendimiento de la búsqueda: índice trigram para `nombre_normalizado LIKE '%token%'`."""

    dependencies = [("catalogo", "0004_categorias_iniciales")]
    operations = [
        TrigramExtension(),
        migrations.AddIndex(
            model_name="producto",
            index=GinIndex(fields=["nombre_normalizado"], name="producto_nombre_trgm", opclasses=["gin_trgm_ops"]),
        ),
    ]
