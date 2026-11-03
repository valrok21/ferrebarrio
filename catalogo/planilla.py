"""Carga masiva de catálogo desde .xlsx (HU-06, CT-07)."""

import re
import zipfile
from io import BytesIO

from django.db import transaction
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from cuentas.models import auditar, instantanea

from .models import CargaCatalogo, Categoria, Producto
from .texto import normalizar_texto

COLUMNAS = ["nombre", "categoria", "unidad", "precio", "stock"]
MAX_BYTES = 2 * 1024 * 1024
MAX_FILAS = 2000
MAX_DESCOMPRIMIDO = 20 * 1024 * 1024  # el .xlsx es un zip: el tope de 2 MB no acota lo que ocupa abierto
MAX_ENTERO = 100_000_000  # precio (CLP) y stock; sobre esto la columna entera de la base se desborda
CAMPOS_AUDITADOS = ["nombre", "categoria", "unidad", "precio_referencial", "stock_disponible", "activo"]


class PlanillaInvalida(Exception):
    pass


def entero(valor):
    """Entero entre 0 y MAX_ENTERO desde 6990, 6990.0, «6.990» o «$6.990»; None si no lo es."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int | float):
        numero = int(valor) if valor >= 0 and float(valor).is_integer() else None
    else:
        texto = re.sub(r"[\s$.]", "", str(valor))
        numero = int(texto) if texto.isdigit() and len(texto) < 12 else None
    return numero if numero is not None and numero <= MAX_ENTERO else None


def plantilla():
    libro = Workbook()
    hoja = libro.active
    hoja.title = "catalogo"
    hoja.append(COLUMNAS)
    hoja.append(['Tornillo coche 1/4" x 2"', "Fijaciones", "unidad", 120, 300])
    hoja.append(['Llave francesa 8"', "Herramientas manuales", "unidad", 6990, 4])
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def leer_filas(archivo):
    if archivo.size > MAX_BYTES:
        raise PlanillaInvalida("El archivo supera 2 MB.")
    try:
        # zipfile no entrega más bytes que los declarados en file_size:
        # la suma acota lo que lee openpyxl.
        with zipfile.ZipFile(archivo) as zip_:
            if sum(i.file_size for i in zip_.infolist()) > MAX_DESCOMPRIMIDO:
                raise PlanillaInvalida("La planilla es demasiado grande al abrirla.")
        archivo.seek(0)
        hoja = load_workbook(archivo, read_only=True, data_only=True).active
        filas = list(hoja.iter_rows(max_row=MAX_FILAS + 2, max_col=len(COLUMNAS), values_only=True))
    except (InvalidFileException, zipfile.BadZipFile, KeyError, ValueError, OSError) as e:
        raise PlanillaInvalida("No pudimos leer el archivo: debe ser una planilla .xlsx.") from e
    if not filas or [normalizar_texto(str(c or "")) for c in filas[0]] != COLUMNAS:
        raise PlanillaInvalida(
            "La primera fila debe ser: " + ", ".join(COLUMNAS) + ". Descarga la plantilla."
        )
    datos = [(n, f) for n, f in enumerate(filas[1:], start=2) if any(c not in (None, "") for c in f)]
    if len(datos) > MAX_FILAS:
        raise PlanillaInvalida(f"La planilla tiene más de {MAX_FILAS} filas.")
    return datos


def validar(filas, comercio):
    categorias = {normalizar_texto(c.nombre): c for c in Categoria.objects.all()}
    unidades = {normalizar_texto(v): v for v in Producto.Unidad.values}
    existentes = {p.nombre_normalizado: p for p in comercio.productos.filter(activo=True)}
    validas, errores, vistos = [], [], set()
    for n, (nombre, categoria, unidad, precio, stock) in filas:
        vacios = [
            c
            for c, v in zip(COLUMNAS, (nombre, categoria, unidad, precio, stock), strict=True)
            if v is None or str(v).strip() == ""
        ]
        clave = normalizar_texto(str(nombre or ""))[:120]
        unidad_ok = unidades.get(normalizar_texto(str(unidad or "")))
        if vacios:
            error = "faltan " + ", ".join(vacios)
        elif clave in vistos:
            error = "producto repetido en el archivo"
        elif normalizar_texto(str(categoria)) not in categorias:
            error = f"categoría «{categoria}» no existe"
        elif unidad_ok is None:
            error = f"unidad «{unidad}» no válida"
        elif entero(precio) is None or entero(stock) is None:
            error = "precio y stock deben ser enteros entre 0 y 100.000.000"
        elif clave in existentes and existentes[clave].unidad != unidad_ok:
            error = f"la unidad registrada es «{existentes[clave].unidad}»"
        else:
            error = None
            validas.append(
                {
                    "clave": clave,
                    "nombre": str(nombre).strip()[:120],
                    "categoria": categorias[normalizar_texto(str(categoria))],
                    "unidad": unidad_ok,
                    "precio": entero(precio),
                    "stock": entero(stock),
                }
            )
        vistos.add(clave)
        if error:
            errores.append({"fila": n, "error": error})
    return validas, errores


def cargar(archivo, comercio, usuario):
    filas = leer_filas(archivo)
    validas, errores = validar(filas, comercio)
    ahora = timezone.now()
    with transaction.atomic():
        bloqueados = {
            p.nombre_normalizado: p
            for p in Producto.objects.select_for_update().filter(
                comercio=comercio, activo=True, nombre_normalizado__in=[v["clave"] for v in validas]
            )
        }
        for v in validas:
            producto = bloqueados.get(v["clave"])
            antes = instantanea(producto, CAMPOS_AUDITADOS)
            producto = producto or Producto(comercio=comercio, nombre=v["nombre"], unidad=v["unidad"])
            producto.categoria, producto.precio_referencial = v["categoria"], v["precio"]
            producto.stock_disponible, producto.actualizado_en = v["stock"], ahora
            producto.save()
            auditar(usuario, "planilla_producto", producto, antes, instantanea(producto, CAMPOS_AUDITADOS))
        if validas:
            comercio.catalogo_actualizado_en = ahora
            comercio.save(update_fields=["catalogo_actualizado_en"])
        return CargaCatalogo.objects.create(
            comercio=comercio,
            usuario=usuario,
            archivo=archivo.name[:200],
            total=len(filas),
            ok=len(validas),
            errores=errores,
        )
