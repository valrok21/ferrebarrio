from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from catalogo.models import Producto
from catalogo.planilla import COLUMNAS, PlanillaInvalida, cargar, entero, plantilla


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (6990, 6990),
        (6990.0, 6990),
        ("6.990", 6990),
        ("$6.990", 6990),
        (" 12 ", 12),
        (0, 0),
        (-1, None),
        (1.5, None),
        ("abc", None),
        (True, None),
        ("", None),
    ],
)
def test_entero(valor, esperado):
    assert entero(valor) == esperado


def _xlsx(filas, cabecera=COLUMNAS):
    libro = Workbook()
    libro.active.append(cabecera)
    for fila in filas:
        libro.active.append(fila)
    salida = BytesIO()
    libro.save(salida)
    return SimpleUploadedFile("catalogo.xlsx", salida.getvalue())


def test_planilla_aplica_validas_e_informa_cada_error(crear):
    comercio = crear.comercio()
    existente = crear.producto(comercio, "Martillo carpintero", stock=1)
    usuario = comercio.propietario
    carga = cargar(
        _xlsx(
            [
                ["Tornillo coche", "Fijaciones", "caja", "$6.990", 10],  # 2 válida nueva
                [
                    "MARTILLO  carpintero",
                    "herramientas manuales",
                    "unidad",
                    5000,
                    7,
                ],  # 3 actualiza la existente
                ["Clavo", None, "unidad", 10, 1],  # 4 faltan
                ["tornillo coche", "Fijaciones", "caja", 1, 1],  # 5 repetido
                ["Pala", "Juguetería", "unidad", 1, 1],  # 6 categoría
                ["Cable", "Electricidad", "docena", 1, 1],  # 7 unidad
                ["Brocha", "Pinturas", "unidad", 1.5, 1],  # 8 precio no entero
                [None, None, None, None, None],  # fila vacía: se ignora
            ]
        ),
        comercio,
        usuario,
    )
    assert (carga.total, carga.ok) == (7, 2)
    assert [e["fila"] for e in carga.errores] == [4, 5, 6, 7, 8]
    assert "faltan categoria" in carga.errores[0]["error"]
    existente.refresh_from_db()
    assert (existente.precio_referencial, existente.stock_disponible) == (5000, 7)
    assert Producto.objects.get(comercio=comercio, nombre="Tornillo coche").precio_referencial == 6990
    comercio.refresh_from_db()
    assert comercio.catalogo_actualizado_en is not None


def test_planilla_no_cambia_la_unidad_de_un_producto_existente(crear):
    comercio = crear.comercio()
    crear.producto(comercio, "Cable", unidad="metro")
    carga = cargar(_xlsx([["Cable", "Electricidad", "rollo", 1, 1]]), comercio, comercio.propietario)
    assert carga.ok == 0 and "unidad registrada" in carga.errores[0]["error"]


def test_planilla_invalida():
    with pytest.raises(PlanillaInvalida, match="primera fila"):
        cargar(_xlsx([], cabecera=["producto", "precio"]), None, None)
    with pytest.raises(PlanillaInvalida, match=".xlsx"):
        cargar(SimpleUploadedFile("x.xlsx", b"no es un zip"), None, None)


def test_plantilla_descargable_y_valida(crear, ingresar):
    comercio = crear.comercio()
    r = ingresar(comercio.propietario).get("/panel/catalogo/plantilla.xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    carga = cargar(SimpleUploadedFile("p.xlsx", plantilla()), comercio, comercio.propietario)
    assert carga.ok == 2 and not carga.errores


def test_subir_planilla_por_la_vista(crear, ingresar):
    comercio = crear.comercio()
    r = ingresar(comercio.propietario).post(
        "/panel/catalogo/planilla/", {"archivo": _xlsx([["Clavo", "Fijaciones", "kg", 900, 3]])}
    )
    assert r.status_code == 302 and comercio.productos.filter(nombre="Clavo").exists()


def test_alta_y_baja_de_producto_propio(crear, ingresar):
    comercio = crear.comercio()
    cliente = ingresar(comercio.propietario)
    categoria = crear.producto(comercio).categoria
    r = cliente.post(
        "/panel/catalogo/nuevo/",
        {
            "nombre": "Serrucho",
            "categoria": categoria.pk,
            "unidad": "unidad",
            "precio_referencial": 8990,
            "stock_disponible": 2,
        },
    )
    assert r.status_code == 302
    serrucho = comercio.productos.get(nombre="Serrucho")
    cliente.post(f"/panel/catalogo/{serrucho.pk}/eliminar/")
    serrucho.refresh_from_db()
    assert not serrucho.activo


def test_aislamiento_un_comerciante_no_ve_ni_edita_productos_de_otro(crear, ingresar):
    ajeno = crear.producto(crear.comercio())
    otro = ingresar(crear.comercio().propietario)
    assert otro.get(f"/panel/catalogo/{ajeno.pk}/").status_code == 404
    assert otro.post(f"/panel/catalogo/{ajeno.pk}/", {"nombre": "x"}).status_code == 404
    assert otro.post(f"/panel/catalogo/{ajeno.pk}/eliminar/").status_code == 404
    assert ajeno.nombre not in otro.get("/panel/catalogo/").content.decode()
    ajeno.refresh_from_db()
    assert ajeno.activo


def test_comerciante_sin_comercio_va_a_registrar_ficha(crear, ingresar):
    r = ingresar(crear.usuario("comerciante")).get("/panel/catalogo/")
    assert r.status_code == 302 and r.url == "/panel/ficha/"
