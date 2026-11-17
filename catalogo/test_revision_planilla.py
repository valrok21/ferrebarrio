"""Hallazgos de la revisión de la planilla (FERREBARRIO-20261116): enteros raros y clave única."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalogo.models import Producto
from catalogo.planilla import cargar, entero

pytestmark = pytest.mark.django_db


def _csv(*filas):
    texto = "nombre,categoria,unidad,precio,stock\n" + "".join(f"{f}\n" for f in filas)
    return SimpleUploadedFile("catalogo.csv", texto.encode())


@pytest.mark.parametrize("valor", ["²", "1²", "١٢", "12345678901234"])
def test_entero_rechaza_digitos_no_ascii_y_largos(valor):
    assert entero(valor) is None


@pytest.mark.parametrize("valor, esperado", [("6.990", 6990), ("$39.990", 39990), ("0", 0), (" 7 ", 7)])
def test_entero_sigue_aceptando_formatos_validos(valor, esperado):
    assert entero(valor) == esperado


def test_superindice_en_csv_es_error_de_fila_no_500(crear):
    comercio = crear.comercio()
    carga = cargar(_csv("Taladro,Herramientas eléctricas,unidad,²,3"), comercio, comercio.propietario)
    assert (carga.total, carga.ok) == (1, 0) and "enteros" in carga.errores[0]["error"]


def test_nombre_largo_con_espacios_dobles_no_duplica_al_editar_y_recargar(crear):
    comercio = crear.comercio()
    nombre = "Tornillo  " + "x" * 115  # 125 caracteres: el recorte cae después del espacio doble
    cargar(_csv(f"{nombre},Fijaciones,unidad,100,1"), comercio, comercio.propietario)
    producto = Producto.objects.get(comercio=comercio)
    clave = producto.nombre_normalizado
    producto.save()  # edición del comerciante: save() recalcula la clave
    assert producto.nombre_normalizado == clave
    carga = cargar(_csv(f"{nombre},Fijaciones,unidad,200,5"), comercio, comercio.propietario)
    assert carga.ok == 1 and Producto.objects.filter(comercio=comercio).count() == 1
    assert Producto.objects.get(comercio=comercio).precio_referencial == 200
