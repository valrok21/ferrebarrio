"""Datos de demostración (idempotente): python manage.py poblar_demo."""

import random
from datetime import timedelta

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from busqueda.models import Busqueda
from catalogo.models import Categoria, Producto
from comercios.models import Comercio
from comercios.rut import digito_verificador
from cuentas.models import Usuario
from reservas import servicios
from reservas.models import Reserva
from valoraciones.models import Valoracion

CLAVE = "FerreDemo2026"
DOMINIO = "demo.ferrebarrio.cl"

COMERCIOS = [
    # (correo, propietario, nombre, rut, dirección, comuna, lat, lon, estado)
    (
        "sanpablo",
        "Jorge Muñoz",
        "Ferretería San Pablo",
        76123456,
        "Av. Los Leones 1234",
        "Providencia",
        -33.4290,
        -70.6040,
        "aprobada",
    ),
    (
        "eltornillo",
        "Marta Díaz",
        "Ferretería El Tornillo",
        76234567,
        "Av. Providencia 1650",
        "Providencia",
        -33.4360,
        -70.6140,
        "aprobada",
    ),
    (
        "donluis",
        "Luis Soto",
        "Ferretería Don Luis",
        76345678,
        "Av. Irarrázaval 3200",
        "Ñuñoa",
        -33.4450,
        -70.5960,
        "aprobada",
    ),
    (
        "losaromos",
        "Ana Pérez",
        "Ferretería Los Aromos",
        76456789,
        "Av. Grecia 2100",
        "Ñuñoa",
        -33.4600,
        -70.6010,
        "pendiente",
    ),
]

PRODUCTOS = [
    ('Tornillo coche 1/4" x 2"', "Fijaciones", "unidad", 120),
    ('Golilla plana 1/4"', "Fijaciones", "unidad", 30),
    ("Tarugo plástico 8 mm", "Fijaciones", "bolsa", 1490),
    ('Clavo corriente 2"', "Fijaciones", "kg", 2290),
    ('Llave francesa 8"', "Herramientas manuales", "unidad", 6990),
    ("Martillo carpintero 16 oz", "Herramientas manuales", "unidad", 8490),
    ("Destornillador cruz PH2", "Herramientas manuales", "unidad", 2490),
    ("Huincha de medir 5 m", "Herramientas manuales", "unidad", 3990),
    ("Taladro percutor 650 W", "Herramientas eléctricas", "unidad", 39990),
    ("Broca concreto 8 mm", "Herramientas eléctricas", "unidad", 1990),
    ('Teflón 1/2"', "Gasfitería", "rollo", 590),
    ('Llave de paso 1/2"', "Gasfitería", "unidad", 5490),
    ("Cable eléctrico 1,5 mm", "Electricidad", "metro", 450),
    ("Ampolleta LED 9 W", "Electricidad", "unidad", 1290),
    ("Látex blanco interior", "Pinturas", "galon", 12990),
    ("Silicona transparente", "Adhesivos y sellantes", "unidad", 3490),
]

TERMINOS = [
    "tornillo coche",
    "llave francesa",
    "taladro",
    "teflon",
    "silicona",
    "brocha",
    "lija al agua",
    "codo pvc",
    "tornillo coche",
    "llave francesa",
    "candado",
    "ampolleta led",
]


class Command(BaseCommand):
    help = "Carga usuarios, ferreterías, catálogo, búsquedas y reservas de demostración (no duplica)."

    def handle(self, *args, **opciones):
        if Usuario.objects.filter(email=f"admin@{DOMINIO}").exists():
            self.stdout.write("Los datos de demostración ya están cargados.")
            return
        with transaction.atomic():
            self.poblar()
        self.stdout.write(self.style.SUCCESS(f"Datos de demostración cargados. Contraseña de todos: {CLAVE}"))

    def poblar(self):
        ahora = timezone.now()
        admin = Usuario.objects.create_superuser(
            f"admin@{DOMINIO}",
            CLAVE,
            nombre="Administración FerreBarrio",
            telefono="+56 2 2345 6789",
            acepto_privacidad_en=ahora,
        )
        categorias = {c.nombre: c for c in Categoria.objects.all()}
        comercios = []
        for i, (correo, persona, nombre, rut, direccion, comuna, lat, lon, estado) in enumerate(COMERCIOS):
            propietario = Usuario.objects.create_user(
                f"{correo}@{DOMINIO}",
                CLAVE,
                nombre=persona,
                telefono=f"+56 9 8{i}12 345{i}",
                rol=Usuario.Rol.COMERCIANTE,
                acepto_privacidad_en=ahora,
            )
            aprobada = estado == Comercio.Estado.APROBADA
            comercio = Comercio.objects.create(
                propietario=propietario,
                rut=f"{rut}-{digito_verificador(rut)}",
                nombre=nombre,
                direccion=direccion,
                comuna=comuna,
                ubicacion=Point(lon, lat, srid=4326),
                origen_ubicacion=Comercio.Origen.GEOCODIFICADA,
                horario="Lun a Vie 9:00–19:00, Sáb 9:00–14:00",
                telefono=f"+56 2 2{i}34 567{i}",
                estado=estado,
                verificado_por=admin if aprobada else None,
                verificado_en=ahora if aprobada else None,
                catalogo_actualizado_en=ahora if aprobada else None,
                acepto_terminos_en=ahora,
            )
            comercios.append(comercio)
            azar = random.Random(i)  # nosec B311 (datos de demo)
            for j, (producto, categoria, unidad, precio) in enumerate(PRODUCTOS):
                # Cada 5.º producto sin stock y cada 4.º sin actualizar hace 4 días (se ve «POR CONFIRMAR»).
                Producto.objects.create(
                    comercio=comercio,
                    categoria=categorias[categoria],
                    nombre=producto,
                    unidad=unidad,
                    precio_referencial=round(precio * azar.uniform(0.9, 1.15) / 10) * 10,
                    stock_disponible=0 if j % 5 == 4 else azar.randint(2, 60),
                    actualizado_en=ahora - timedelta(days=4) if j % 4 == 3 else ahora,
                )
        # La llave francesa de San Pablo queda con 1 unidad: sirve para mostrar la última unidad disputada.
        Producto.objects.filter(comercio=comercios[0], nombre__startswith="Llave francesa").update(
            stock_disponible=1
        )

        camila = Usuario.objects.create_user(
            f"camila@{DOMINIO}",
            CLAVE,
            nombre="Camila Rojas",
            telefono="+56 9 7123 4567",
            acepto_privacidad_en=ahora,
        )
        pedro = Usuario.objects.create_user(
            f"pedro@{DOMINIO}",
            CLAVE,
            nombre="Pedro M.",
            telefono="+56 9 6234 5678",
            acepto_privacidad_en=ahora,
        )
        self.reservas(comercios[:3], camila, pedro)
        self.busquedas(comercios[0], categorias, ahora)

    def reservas(self, comercios, camila, pedro):
        def producto(comercio, inicio):
            return comercio.productos.filter(nombre__startswith=inicio).get()

        san_pablo, tornillo, don_luis = comercios
        dueno = {c.pk: c.propietario for c in comercios}
        # Pedro: una retirada valorada, una anulada, una expirada y una pendiente.
        r = servicios.crear_reserva(pedro, producto(san_pablo, "Tornillo coche").pk, 2)
        servicios.atender_reserva(r.pk, dueno[san_pablo.pk])
        servicios.confirmar_retiro(r.pk, dueno[san_pablo.pk])
        Valoracion.objects.create(
            reserva=r, comercio=san_pablo, cliente=pedro, puntaje=5, estado=Valoracion.Estado.APROBADA
        )
        r = servicios.crear_reserva(pedro, producto(tornillo, "Martillo").pk, 1)
        servicios.anular_reserva(r.pk, pedro, por_cliente=True)
        r = servicios.crear_reserva(pedro, producto(don_luis, "Huincha").pk, 2)
        Reserva.objects.filter(pk=r.pk).update(vence_en=timezone.now() - timedelta(minutes=1))
        servicios.expirar_vencidas()
        servicios.crear_reserva(pedro, producto(san_pablo, "Silicona").pk, 2)
        # Camila: una retirada con comentario por moderar, una pendiente y una lista para retiro.
        r = servicios.crear_reserva(camila, producto(tornillo, "Golilla").pk, 2)
        servicios.confirmar_retiro(r.pk, dueno[tornillo.pk])
        Valoracion.objects.create(
            reserva=r,
            comercio=tornillo,
            cliente=camila,
            puntaje=4,
            comentario="Me tenían todo apartado, muy rápido.",
        )
        servicios.crear_reserva(camila, producto(san_pablo, "Teflón").pk, 2)
        r = servicios.crear_reserva(camila, producto(san_pablo, "Ampolleta").pk, 2)
        servicios.atender_reserva(r.pk, dueno[san_pablo.pk])

    def busquedas(self, comercio, categorias, ahora):
        azar = random.Random(42)  # nosec B311 (datos de demo)
        for k in range(60):
            termino = TERMINOS[k % len(TERMINOS)]
            n = Producto.objects.filter(
                nombre_normalizado__contains=termino.split()[0],
                activo=True,
                comercio__estado=Comercio.Estado.APROBADA,
            ).count()
            b = Busqueda.objects.create(
                termino=termino,
                ubicacion_aprox=Point(
                    round(comercio.ubicacion.x + azar.uniform(-0.01, 0.01), 3),
                    round(comercio.ubicacion.y + azar.uniform(-0.01, 0.01), 3),
                    srid=4326,
                ),
                comuna=comercio.comuna,
                radio_km=2,
                n_resultados=n,
                n_con_stock=n and azar.randint(0, n),
            )
            Busqueda.objects.filter(pk=b.pk).update(
                fecha=ahora - timedelta(days=azar.randint(0, 29), hours=azar.randint(0, 23))
            )
