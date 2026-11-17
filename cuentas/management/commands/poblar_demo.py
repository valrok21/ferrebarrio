"""Datos de demostración (idempotente): python manage.py poblar_demo."""

import math
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from busqueda.models import Busqueda
from catalogo.models import Categoria, Producto
from comercios.models import COMUNAS, Comercio
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

# Catálogo amplio: los nombres no empiezan como los productos que usa `reservas()` («Tornillo coche»,
# «Martillo», «Huincha», «Silicona», «Golilla», «Teflón», «Ampolleta», «Llave francesa»), porque allí
# se buscan con `nombre__startswith(...).get()` y un segundo producto parecido rompería esa búsqueda.
EXTRAS = [
    ('Tornillo drywall 6 x 1 1/4"', "Fijaciones", "caja", 3990),
    ('Tornillo madera 8 x 2"', "Fijaciones", "unidad", 40),
    ('Perno hexagonal 3/8" x 2"', "Fijaciones", "unidad", 220),
    ('Tuerca hexagonal 3/8"', "Fijaciones", "unidad", 60),
    ('Clavo terminación 1 1/2"', "Fijaciones", "kg", 2590),
    ("Remache pop 4 mm", "Fijaciones", "caja", 3490),
    ('Abrazadera metálica 1/2"', "Fijaciones", "unidad", 390),
    ('Alicate universal 8"', "Herramientas manuales", "unidad", 5990),
    ('Serrucho carpintero 20"', "Herramientas manuales", "unidad", 9990),
    ("Nivel de burbuja 60 cm", "Herramientas manuales", "unidad", 7490),
    ("Juego de llaves Allen 9 piezas", "Herramientas manuales", "unidad", 4990),
    ("Cuchillo cartonero 18 mm", "Herramientas manuales", "unidad", 1490),
    ('Llave Stillson 14"', "Herramientas manuales", "unidad", 14990),
    ("Combo 4 lb", "Herramientas manuales", "unidad", 12990),
    ('Esmeril angular 4 1/2" 850 W', "Herramientas eléctricas", "unidad", 34990),
    ("Atornillador inalámbrico 12 V", "Herramientas eléctricas", "unidad", 49990),
    ('Disco de corte metal 4 1/2"', "Herramientas eléctricas", "unidad", 990),
    ("Sierra caladora 500 W", "Herramientas eléctricas", "unidad", 29990),
    ("Broca madera 10 mm", "Herramientas eléctricas", "unidad", 1590),
    ("Lijadora orbital 200 W", "Herramientas eléctricas", "unidad", 32990),
    ("Codo PVC 110 mm", "Gasfitería", "unidad", 1290),
    ("Tubo PVC 110 mm x 3 m", "Gasfitería", "unidad", 8990),
    ("Flexible de agua 40 cm", "Gasfitería", "unidad", 2490),
    ("Sifón plástico lavaplatos", "Gasfitería", "unidad", 3490),
    ("Grifería monomando lavaplatos", "Gasfitería", "unidad", 24990),
    ("Adhesivo PVC 240 cc", "Gasfitería", "unidad", 3990),
    ("Tee PVC 40 mm", "Gasfitería", "unidad", 790),
    ("Interruptor simple 10 A", "Electricidad", "unidad", 1990),
    ("Enchufe doble 10 A", "Electricidad", "unidad", 2490),
    ("Cinta aisladora 20 m", "Electricidad", "rollo", 990),
    ("Extensión eléctrica 10 m", "Electricidad", "unidad", 6990),
    ("Foco LED exterior 20 W", "Electricidad", "unidad", 8990),
    ("Interruptor automático 16 A", "Electricidad", "unidad", 5990),
    ("Canaleta 20 x 10 mm", "Electricidad", "metro", 790),
    ("Zapatilla 6 enchufes", "Electricidad", "unidad", 7990),
    ("Esmalte sintético negro", "Pinturas", "galon", 15990),
    ("Látex blanco exterior", "Pinturas", "galon", 14990),
    ('Brocha 2"', "Pinturas", "unidad", 1990),
    ("Rodillo antigota 23 cm", "Pinturas", "unidad", 3990),
    ("Diluyente sintético", "Pinturas", "litro", 2990),
    ("Lija al agua N° 220", "Pinturas", "unidad", 490),
    ("Barniz marino", "Pinturas", "galon", 12990),
    ("Cinta de enmascarar 24 mm", "Pinturas", "rollo", 1490),
    ("Adhesivo de montaje 300 ml", "Adhesivos y sellantes", "unidad", 4490),
    ("Adhesivo de contacto", "Adhesivos y sellantes", "litro", 6990),
    ("Sellante acrílico blanco", "Adhesivos y sellantes", "unidad", 2990),
    ("Espuma de poliuretano 500 ml", "Adhesivos y sellantes", "unidad", 5990),
    ("Cola fría", "Adhesivos y sellantes", "kg", 3490),
    ("Cemento 25 kg", "Construcción", "bolsa", 5990),
    ("Yeso 5 kg", "Construcción", "bolsa", 2490),
    ("Plancha volcanita 10 mm", "Construcción", "unidad", 7990),
    ("Montante metalcon 60 mm x 3 m", "Construcción", "unidad", 3290),
    ("Fierro estriado 8 mm x 6 m", "Construcción", "unidad", 3990),
    ("Manguera de jardín 15 m", "Jardín", "unidad", 9990),
    ("Pala punta huevo", "Jardín", "unidad", 11990),
    ("Tijera de podar", "Jardín", "unidad", 7990),
    ("Tierra de hoja 50 L", "Jardín", "bolsa", 3990),
    ("Malla raschel 80 %", "Jardín", "metro", 1490),
    ("Candado bronce 40 mm", "Seguridad", "unidad", 5990),
    ("Guantes de cabritilla", "Seguridad", "par", 2990),
    ("Lentes de seguridad", "Seguridad", "unidad", 1990),
    ("Casco de seguridad", "Seguridad", "unidad", 4990),
    ("Protector auditivo tipo fono", "Seguridad", "unidad", 6990),
]
CATALOGO = PRODUCTOS + EXTRAS

# Ferreterías ficticias para llegar a 5 aprobadas por comuna (contando las de COMERCIOS).
# Las direcciones usan calles que existen en cada comuna; la ubicación es aproximada (cerca del
# centroide de la comuna, no geocodificada), por eso se marca como «Marcada en el mapa».
FERRETERIAS = {
    "Providencia": [
        ("Ferretería El Roble", "Av. Manuel Montt 1420"),
        ("Ferretería Ricardo Lyon", "Av. Ricardo Lyon 1340"),
        ("Ferretería y Pinturas Pocuro", "Av. Pocuro 2150"),
    ],
    "Ñuñoa": [
        ("Ferretería Plaza Ñuñoa", "Jorge Washington 98"),
        ("Ferretería Los Jardines", "Av. José Pedro Alessandri 1250"),
        ("Ferretería Villaseca", "Av. Pedro de Valdivia 3410"),
        ("Ferretería Simón Bolívar", "Av. Simón Bolívar 3450"),
    ],
    "Santiago": [
        ("Ferretería San Diego", "San Diego 1150"),
        ("Ferretería Avenida Matta", "Av. Matta 820"),
        ("Ferretería Barrio Brasil", "Av. Brasil 340"),
        ("Ferretería Diez de Julio", "Av. Diez de Julio 1050"),
        ("Comercial Ferretera Santa Rosa", "Av. Santa Rosa 980"),
    ],
    "Las Condes": [
        ("Ferretería Apoquindo", "Av. Apoquindo 4900"),
        ("Ferretería Manquehue", "Av. Manquehue Sur 330"),
        ("Ferretería Cristóbal Colón", "Av. Cristóbal Colón 4500"),
        ("Ferretería Martín de Zamora", "Av. Martín de Zamora 4800"),
        ("Ferretería Tomás Moro", "Av. Tomás Moro 1250"),
    ],
    "La Reina": [
        ("Ferretería Larraín", "Av. Larraín 6520"),
        ("Ferretería Príncipe de Gales", "Av. Príncipe de Gales 6850"),
        ("Ferretería Echeñique", "Av. Echeñique 6150"),
        ("Ferretería Carlos Ossandón", "Av. Carlos Ossandón 1150"),
        ("Ferretería La Reina Alta", "Av. Francisco Bilbao 7380"),
    ],
    "Macul": [
        ("Ferretería Macul", "Av. Macul 3450"),
        ("Ferretería Quilín", "Av. Quilín 3200"),
        ("Ferretería Escuela Agrícola", "Av. Escuela Agrícola 1650"),
        ("Ferretería Los Plátanos", "Av. José Pedro Alessandri 2800"),
        ("Ferretería Departamental", "Av. Departamental 4050"),
    ],
    "San Miguel": [
        ("Ferretería Gran Avenida", "Gran Avenida José Miguel Carrera 4850"),
        ("Ferretería El Llano", "Av. El Llano Subercaseaux 3600"),
        ("Ferretería Salesianos", "Av. Salesianos 1150"),
        ("Ferretería San Miguel Centro", "Av. Departamental 1250"),
        ("Ferretería Lo Ovalle", "Av. Lo Ovalle 920"),
    ],
    "Recoleta": [
        ("Ferretería Recoleta", "Av. Recoleta 1450"),
        ("Ferretería Avenida Perú", "Av. Perú 1100"),
        ("Ferretería Einstein", "Av. Einstein 750"),
        ("Ferretería Bellavista", "Purísima 250"),
        ("Ferretería Patronato", "Av. Santos Dumont 650"),
    ],
}
NOMBRES = (
    "Rodrigo Carolina Héctor Valentina Patricio Francisca Mauricio Daniela Cristián Paula "
    "Sergio Javiera Gonzalo Lorena Felipe Macarena Andrés Soledad Ignacio"
).split()
APELLIDOS = (
    "Fuentes Contreras Sepúlveda Morales Araya Espinoza Valenzuela Castillo Tapia Reyes "
    "Gutiérrez Vergara Riquelme Navarro Salinas Cáceres Orellana Bravo Figueroa Pizarro "
    "Carrasco Vidal Henríquez"
).split()
HORARIOS = [
    "Lun a Vie 9:00–19:00, Sáb 9:00–14:00",
    "Lun a Vie 8:30–18:30, Sáb 9:00–13:30",
    "Lun a Sáb 9:00–20:00",
    "Lun a Vie 9:00–18:00, Sáb y Dom 10:00–14:00",
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


def _cerca_del_centro(comuna, azar):
    """Punto a 0,2–1,3 km del centroide de la comuna (1° de latitud ≈ 111,32 km)."""
    lat, lon = COMUNAS[comuna]
    km, angulo = azar.uniform(0.2, 1.3), azar.uniform(0, 2 * math.pi)
    dlat = km * math.cos(angulo) / 111.32
    dlon = km * math.sin(angulo) / (111.32 * math.cos(math.radians(lat)))
    return Point(round(lon + dlon, 5), round(lat + dlat, 5), srid=4326)


def _producto(comercio, fila, categorias, azar, ahora):
    """Producto con precio y stock variados según `azar`; calcula lo que haría Producto.save()."""
    nombre, categoria, unidad, precio = fila
    sorteo = azar.random()
    # ~12 % sin stock y ~15 % con 1–3 unidades: se ven las marcas SIN STOCK y de stock bajo.
    stock = 0 if sorteo < 0.12 else azar.randint(1, 3) if sorteo < 0.27 else azar.randint(4, 80)
    return Producto(
        comercio=comercio,
        categoria=categorias[categoria],
        nombre=nombre,
        nombre_normalizado=Producto.clave(nombre),
        unidad=unidad,
        precio_referencial=round(precio * azar.uniform(0.85, 1.2) / 10) * 10,
        stock_disponible=stock,
        # ~10 % sin actualizar hace 4 días: se ve «POR CONFIRMAR».
        actualizado_en=ahora - timedelta(days=4) if azar.random() < 0.1 else ahora,
    )


class Command(BaseCommand):
    help = "Carga usuarios, ferreterías, catálogo, búsquedas y reservas de demostración (no duplica)."

    def handle(self, *args, **opciones):
        if not settings.DEBUG:
            # Crea un superusuario con la contraseña pública del README: nunca fuera del entorno local.
            raise CommandError("poblar_demo solo corre con DJANGO_DEBUG=1.")
        with transaction.atomic():
            base = not Usuario.objects.filter(email=f"admin@{DOMINIO}").exists()
            if base:
                self.poblar()
            # Corre siempre: completa también una base cargada con una versión anterior del comando.
            nuevas = self.ampliar()
        if not base and not nuevas:
            self.stdout.write("Los datos de demostración ya están cargados.")
            return
        self.stdout.write(self.style.SUCCESS(f"Datos de demostración cargados. Contraseña de todos: {CLAVE}"))

    def ampliar(self):
        """Crea las ferreterías de FERRETERIAS que falten, con catálogo; devuelve cuántas creó.

        Usa bulk_create (corre en cada arranque del contenedor), así que replica a mano lo que
        haría save(): `nombre_normalizado` del producto. Comercio y Usuario no calculan nada en
        save() que falte aquí (Usuario solo pasa el correo a minúsculas, y ya va en minúsculas).
        """
        fichas = [
            (f"{slugify(nombre)}@{DOMINIO}", nombre, direccion, comuna)
            for comuna, lista in FERRETERIAS.items()
            for nombre, direccion in lista
        ]
        existentes = set(
            Usuario.objects.filter(email__in=[f[0] for f in fichas]).values_list("email", flat=True)
        )
        # El índice i se fija sobre la lista completa: RUT y teléfonos no cambian entre ejecuciones.
        faltan = [(i, *f) for i, f in enumerate(fichas) if f[0] not in existentes]
        if not faltan:
            return 0
        ahora = timezone.now()
        admin = Usuario.objects.get(email=f"admin@{DOMINIO}")
        categorias = {c.nombre: c for c in Categoria.objects.all()}
        # Un solo hash para todos (la clave es pública y de demo): hashear 37 veces tarda segundos.
        clave = make_password(CLAVE)
        propietarios = Usuario.objects.bulk_create(
            Usuario(
                email=correo,
                password=clave,
                nombre=f"{NOMBRES[i % len(NOMBRES)]} {APELLIDOS[i % len(APELLIDOS)]}",
                telefono=f"+56 9 {6100 + i} {2000 + 53 * i}",
                rol=Usuario.Rol.COMERCIANTE,
                acepto_privacidad_en=ahora,
            )
            for i, correo, *_ in faltan
        )
        comercios = Comercio.objects.bulk_create(
            Comercio(
                propietario=propietario,
                rut=f"{77_200_000 + 7_919 * i}-{digito_verificador(77_200_000 + 7_919 * i)}",
                nombre=nombre,
                direccion=direccion,
                comuna=comuna,
                ubicacion=_cerca_del_centro(comuna, random.Random(correo)),  # nosec B311 (demo)
                origen_ubicacion=Comercio.Origen.MANUAL,
                horario=HORARIOS[i % len(HORARIOS)],
                telefono=f"+56 2 2{500 + i} {1000 + 37 * i}",
                estado=Comercio.Estado.APROBADA,
                verificado_por=admin,
                verificado_en=ahora,
                catalogo_actualizado_en=ahora,
                acepto_terminos_en=ahora,
            )
            for propietario, (i, correo, nombre, direccion, comuna) in zip(propietarios, faltan, strict=True)
        )
        productos = []
        for comercio, ficha in zip(comercios, faltan, strict=True):
            azar = random.Random(f"catalogo-{ficha[1]}")  # nosec B311 (demo): reproducible por comercio
            elegidos = azar.sample(CATALOGO, azar.randint(25, 50))
            productos += [_producto(comercio, fila, categorias, azar, ahora) for fila in elegidos]
        # Los comercios de COMERCIOS (16 productos) suman productos de EXTRAS que aún no tengan.
        originales = Comercio.objects.filter(propietario__email__in=[f"{c[0]}@{DOMINIO}" for c in COMERCIOS])
        tienen = set(
            Producto.objects.filter(comercio__in=originales, activo=True).values_list(
                "comercio_id", "nombre_normalizado"
            )
        )
        for comercio in originales:
            azar = random.Random(f"extras-{comercio.rut}")  # nosec B311 (demo)
            productos += [
                _producto(comercio, fila, categorias, azar, ahora)
                for fila in azar.sample(EXTRAS, 14)
                if (comercio.pk, Producto.clave(fila[0])) not in tienen
            ]
        Producto.objects.bulk_create(productos)
        return len(comercios)

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
