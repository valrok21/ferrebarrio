from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Búsqueda de la sección «Datos» sin distinguir tildes: «Ferreteria» encuentra «Ferretería»."""

    dependencies = [("catalogo", "0006_nombres_admin")]
    operations = [UnaccentExtension()]
