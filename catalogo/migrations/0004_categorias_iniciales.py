from django.db import migrations

CATEGORIAS = [
    "Adhesivos y sellantes", "Construcción", "Electricidad", "Fijaciones", "Gasfitería",
    "Herramientas eléctricas", "Herramientas manuales", "Jardín", "Pinturas", "Seguridad",
]


def crear(apps, schema_editor):
    Categoria = apps.get_model("catalogo", "Categoria")
    for nombre in CATEGORIAS:
        Categoria.objects.get_or_create(nombre=nombre)


class Migration(migrations.Migration):
    """HU-18: categorías compartidas por defecto."""

    dependencies = [("catalogo", "0003_initial")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]
