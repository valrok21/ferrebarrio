"""Importación de catálogo desde .csv y carga en bloque (FERREBARRIO-20261116, puntos 3 y 6)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalogo.models import Producto
from catalogo.planilla import MAX_FILAS, PlanillaInvalida, cargar
from cuentas.models import RegistroAuditoria

pytestmark = pytest.mark.django_db


def _csv(texto, codificacion="utf-8", nombre="catalogo.csv"):
    return SimpleUploadedFile(nombre, texto.encode(codificacion))


@pytest.mark.parametrize(
    "texto, codificacion",
    [
        ("nombre,categoria,unidad,precio,stock\nTaladro,Herramientas eléctricas,unidad,$39.990,3\n", "utf-8"),
        ("﻿nombre;categoria;unidad;precio;stock\nTaladro;Herramientas eléctricas;unidad;39990;3\n", "utf-8"),
        (
            "Nombre;Categoría;Unidad;Precio;Stock\r\nTaladro;Herramientas eléctricas;unidad;39.990;3\r\n",
            "latin-1",
        ),
    ],
    ids=["coma-utf8", "punto-y-coma-bom", "excel-latin1"],
)
def test_csv_en_formatos_comunes(crear, texto, codificacion):
    comercio = crear.comercio()
    carga = cargar(_csv(texto, codificacion), comercio, comercio.propietario)
    assert (carga.total, carga.ok, carga.errores) == (1, 1, [])
    producto = Producto.objects.get(comercio=comercio, nombre="Taladro")
    assert (producto.precio_referencial, producto.stock_disponible, producto.categoria.nombre) == (
        39990,
        3,
        "Herramientas eléctricas",
    )


def test_csv_informa_errores_por_fila_y_acepta_columnas_de_mas(crear):
    comercio = crear.comercio()
    texto = (
        "nombre,categoria,unidad,precio,stock\n"
        "Pala,Jardín,unidad,8990,4,columna extra\n"  # 2 válida
        "Rastrillo,Jardín\n"  # 3 faltan unidad, precio, stock
        ",,,,\n"  # vacía: se ignora
        "Pala,Jardín,unidad,1,1\n"  # 5 repetida
        "Cemento,Construcción,unidad,-5,2\n"  # 6 precio negativo
    )
    carga = cargar(_csv(texto), comercio, comercio.propietario)
    assert (carga.total, carga.ok) == (4, 1)
    assert [(e["fila"], e["error"]) for e in carga.errores] == [
        (3, "faltan unidad, precio, stock"),
        (5, "producto repetido en el archivo"),
        (6, "precio y stock deben ser enteros entre 0 y 100.000.000"),
    ]


@pytest.mark.parametrize(
    "contenido",
    [b"producto;precio\nx;1\n", b"PK\x03\x04\x00\x00binario", b""],
    ids=["cabecera", "binario", "vacio"],
)
def test_csv_invalido(contenido):
    with pytest.raises(PlanillaInvalida):
        cargar(SimpleUploadedFile("x.csv", contenido), None, None)


def test_csv_con_demasiadas_filas():
    texto = "nombre,categoria,unidad,precio,stock\n" + "".join(
        f"P{i},Fijaciones,unidad,1,1\n" for i in range(MAX_FILAS + 1)
    )
    with pytest.raises(PlanillaInvalida, match="más de"):
        cargar(_csv(texto), None, None)


def test_carga_en_bloque_con_consultas_constantes_y_auditoria(crear):
    comercio = crear.comercio()
    existente = crear.producto(comercio, "Martillo carpintero", stock=1)
    filas = "".join(f"Tornillo {i},Fijaciones,caja,{100 + i},{i}\n" for i in range(300))
    texto = (
        "nombre,categoria,unidad,precio,stock\nmartillo CARPINTERO,Herramientas manuales,unidad,5000,7\n"
        + filas
    )
    with CaptureQueriesContext(connection) as consultas:
        carga = cargar(_csv(texto), comercio, comercio.propietario)
    assert carga.ok == 301 and len(consultas) < 30
    existente.refresh_from_db()
    assert (existente.precio_referencial, existente.stock_disponible) == (5000, 7)
    nuevo = Producto.objects.get(comercio=comercio, nombre="Tornillo 7")
    assert nuevo.nombre_normalizado == "tornillo 7" and nuevo.precio_referencial == 107
    auditoria = RegistroAuditoria.objects.filter(accion="planilla_producto")
    assert auditoria.count() == 301
    registro = auditoria.get(entidad_id=str(existente.pk))
    assert registro.antes["stock_disponible"] == 1 and registro.despues["stock_disponible"] == 7
    assert auditoria.get(entidad_id=str(nuevo.pk)).antes is None


def test_subir_csv_por_la_vista_muestra_la_tabla_de_errores(crear, ingresar):
    comercio = crear.comercio()
    cliente = ingresar(comercio.propietario)
    texto = "nombre,categoria,unidad,precio,stock\nClavo,Fijaciones,kg,900,3\nPala,Juguetería,unidad,1,1\n"
    respuesta = cliente.post("/panel/catalogo/planilla/", {"archivo": _csv(texto)}, follow=True)
    assert Producto.objects.filter(comercio=comercio, nombre="Clavo").exists()
    html = respuesta.content.decode()
    assert "Filas con error (1)" in html and "categoría «Juguetería» no existe" in html
