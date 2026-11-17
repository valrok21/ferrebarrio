"""La búsqueda por fragmento de nombre puede usar el índice trigram (FERREBARRIO-20261116, punto 6)."""

import pytest
from django.db import connection

from catalogo.models import Producto

pytestmark = pytest.mark.django_db


def test_busqueda_por_fragmento_usa_indice_trigram(crear):
    crear.producto(crear.comercio(), "Taladro percutor")
    consulta = Producto.objects.filter(nombre_normalizado__contains="ladro")
    with connection.cursor() as cursor:
        cursor.execute(
            "SET LOCAL enable_seqscan = off"
        )  # tabla chica: sin esto el planificador prefiere recorrerla
        plan = consulta.explain()
    assert "producto_nombre_trgm" in plan
    assert list(consulta.values_list("nombre", flat=True)) == ["Taladro percutor"]
