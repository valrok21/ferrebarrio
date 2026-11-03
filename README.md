# FerreBarrio

Plataforma web para encontrar productos en las ferreterías de barrio cercanas, ver si tienen stock y reservarlos para retirarlos en el local. No incluye pagos ni despacho.

- **Vecinos (clientes):** buscan por cercanía, ven resultados en lista y mapa, reservan y valoran el local después del retiro.
- **Comerciantes:** registran su ferretería, mantienen el catálogo (uno a uno o por planilla Excel) y atienden las reservas.
- **Administrador:** verifica los comercios nuevos, modera las valoraciones y sigue los indicadores del piloto.

Proyecto de título — Ingeniería en Computación, Universidad Andrés Bello.

**Stack:** Python 3.12 · Django 5.2 · PostgreSQL 16 + PostGIS 3.4 · Celery + Redis 7 · Bootstrap 5.3 · Leaflet + OpenStreetMap · Nominatim (geocodificación) · correo SMTP (Mailpit en local) · Docker Compose · pytest, ruff, bandit, pip-audit.

---

## Contenido

1. [Inicio rápido](#inicio-rápido)
2. [Direcciones](#direcciones)
3. [Usuarios de demo](#usuarios-de-demo)
4. [Recorrido de demostración](#recorrido-de-demostración)
5. [Reglas de negocio](#reglas-de-negocio)
6. [Servicios y tareas programadas](#servicios-y-tareas-programadas)
7. [Carga de catálogo por planilla](#carga-de-catálogo-por-planilla)
8. [Comandos útiles](#comandos-útiles)
9. [Pruebas y calidad](#pruebas-y-calidad)
10. [Estructura del proyecto](#estructura-del-proyecto)
11. [Variables de entorno](#variables-de-entorno)
12. [Problemas frecuentes](#problemas-frecuentes)

---

## Inicio rápido

**Requisitos:** Docker con Compose v2 (Docker Desktop en macOS o Windows). No hace falta instalar Python ni PostgreSQL.

```sh
git clone https://github.com/valrok21/ferrebarrio.git
cd ferrebarrio
docker compose up --build
```

La primera vez tarda unos minutos (descarga imágenes e instala dependencias). Cuando en el registro aparezca `Starting development server at http://0.0.0.0:8000/`, abre **http://127.0.0.1:8000**.

Al arrancar, el servicio `web` aplica las migraciones y carga los datos de demo con `poblar_demo`. Es idempotente: si los datos ya están, no duplica nada.

Para dejarlo corriendo en segundo plano y detenerlo:

```sh
docker compose up --build -d   # levantar en segundo plano
docker compose ps              # ver el estado de los servicios
docker compose down            # detener (conserva la base)
docker compose down -v         # detener y borrar la base (empezar de cero)
```

### Si los puertos 8000 o 8025 están ocupados

Crea un archivo `.env` junto a `docker-compose.yml` (está en `.gitignore`):

```sh
WEB_PORT=8010
MAILPIT_PORT=8035
```

y vuelve a correr `docker compose up -d`. Las direcciones pasan a ser `http://127.0.0.1:8010` y `http://127.0.0.1:8035`.

---

## Direcciones

Con los puertos por defecto:

| Qué | Dirección |
|---|---|
| Aplicación | http://127.0.0.1:8000 |
| Correos enviados (Mailpit) | http://127.0.0.1:8025 |
| Panel del comerciante | http://127.0.0.1:8000/panel/ |
| Administración (verificación, moderación, indicadores) | http://127.0.0.1:8000/administracion/ |
| Admin técnico de Django | http://127.0.0.1:8000/django-admin/ |
| Chequeo de salud | http://127.0.0.1:8000/salud/ |

Usa **`127.0.0.1` y no `localhost`**: el navegador comparte las cookies de `localhost` entre todos los puertos, y otra aplicación local puede pisar la sesión (síntoma: ingresas y la página vuelve a pedir el ingreso).

Los puertos solo se publican en `127.0.0.1`: la demo no queda visible para otros equipos de la red. Ningún correo sale a internet: todos quedan en Mailpit.

---

## Usuarios de demo

Contraseña de todos: **`FerreDemo2026`** (solo existe en el entorno local).

| Rol | Correo | Para qué sirve |
|---|---|---|
| Administrador | `admin@demo.ferrebarrio.cl` | Verificar comercios, moderar valoraciones, ver indicadores. También entra al admin técnico. |
| Comerciante | `sanpablo@demo.ferrebarrio.cl` | Ferretería San Pablo (Av. Los Leones 1234, Providencia), aprobada. |
| Comerciante | `eltornillo@demo.ferrebarrio.cl` | Ferretería El Tornillo, aprobada. |
| Comerciante | `donluis@demo.ferrebarrio.cl` | Ferretería Don Luis, aprobada. |
| Comerciante | `losaromos@demo.ferrebarrio.cl` | Solicitud pendiente de verificación. |
| Cliente | `camila@demo.ferrebarrio.cl` | Camila Rojas. |
| Cliente | `pedro@demo.ferrebarrio.cl` | Pedro M. |

Cada local aprobado trae unos 15 productos. Algunos están sin stock y otros con stock desactualizado (más de 72 horas sin revisar), para ver las marcas correspondientes. También hay búsquedas, reservas en todos los estados y una valoración, para que los reportes muestren datos desde el primer momento.

---

## Recorrido de demostración

Para ver los correos de cada paso, deja Mailpit abierto en otra pestaña.

1. **Buscar (sin ingresar).** En el inicio, busca «tornillo», elige la comuna Providencia y un radio de 2 km. Los resultados salen ordenados por distancia, en lista y en el mapa, con marca de stock y de frescura.
2. **Reservar.** Ingresa como Camila y reserva 2 unidades de un producto. Recibes un código `FB-xxxxxx`, y llegan dos correos: el del cliente y el del comercio. La reserva queda en «Mis reservas».
3. **Atender.** Sal e ingresa como San Pablo. En **Panel**, marca la reserva como *Atendida* y luego como *Entregada*. Al reservar, las unidades pasan de disponibles a reservadas; al entregar, salen del stock.
4. **Valorar.** Vuelve como Camila y valora la reserva retirada. Si escribes un comentario, queda pendiente de moderación.
5. **Mantener el catálogo.** Como San Pablo, en **Panel → Catálogo**, edita un producto o descarga la plantilla `.xlsx`, modifícala y súbela (ver [Carga por planilla](#carga-de-catálogo-por-planilla)).
6. **Ver reportes.** Como San Pablo, en `/panel/reportes/`, revisa los términos más buscados cerca del local (HU-24), la demanda no cubierta (HU-25) y las reservas por estado (HU-26).
7. **Administrar.** Ingresa como administrador y abre `/administracion/`. Ahí están los indicadores, la solicitud pendiente de Los Aromos (aprobar, observar o rechazar con motivo) y la moderación de valoraciones.
8. **Registrar una ferretería nueva (opcional).** Regístrate con un correo nuevo eligiendo «Registrar mi ferretería» y completa la ficha. La dirección se geocodifica con Nominatim; si falla o no hay internet, arrastra el marcador en el mapa. La ficha queda pendiente hasta que el administrador la verifique.

---

## Reglas de negocio

Están en `config/settings.py` (sección «Reglas de negocio»):

| Regla | Valor |
|---|---|
| Vigencia de una reserva sin retirar | 4 horas; después expira sola y el stock vuelve a estar disponible |
| Reservas activas por cliente | 3 como máximo |
| Reservas creadas por cliente en 24 horas | 10 como máximo |
| Unidades por reserva | entre 1 y 20 |
| Aviso al comercio por reserva sin atender | a los 30 minutos |
| Stock «desactualizado» | sin revisar hace más de 72 horas |
| Radio de búsqueda | 1 a 3 km |
| Búsquedas por minuto | 30 por sesión y 120 por IP |
| Bloqueo de ingreso | 15 minutos tras 5 fallos con el mismo correo desde la misma IP (también en el admin técnico) |
| Cuota diaria de correos | 300, con alerta a los administradores al llegar al 80 % (`AVISOS_CUOTA_DIARIA`) |

Si dos clientes se disputan la última unidad, solo uno la obtiene: el stock se descuenta con la fila del producto bloqueada.

Un cliente puede eliminar su cuenta desde «Mi cuenta» (Ley 21.719). Al hacerlo se anulan sus reservas activas, se libera el stock y se anonimizan sus datos.

---

## Servicios y tareas programadas

| Servicio | Qué hace |
|---|---|
| `db` | PostgreSQL 16 con PostGIS (consultas por distancia). Datos en el volumen `pgdata`. |
| `redis` | Caché en la base 1 (límites de búsqueda e ingreso) y cola de Celery en la base 0. |
| `mailpit` | Servidor SMTP de prueba con bandeja web. |
| `web` | Django (`runserver`, recarga sola al editar el código: el repo está montado en `/app`). |
| `worker` | Celery: envía los avisos por correo con reintentos. Si un aviso falla del todo, avisa a los administradores. |
| `beat` | Celery beat: ejecuta las tareas programadas. |

Tareas programadas (`CELERY_BEAT_SCHEDULE`):

| Tarea | Cuándo |
|---|---|
| Expirar reservas vencidas y liberar su stock | cada minuto |
| Avisar al comercio de reservas sin atender | cada minuto |
| Conciliación: detectar diferencias entre el stock reservado y las reservas activas, y avisar a los administradores | todos los días a las 03:00 |
| Avisar a los comercios con catálogo desactualizado | todos los días a las 09:00 |

Para ver qué está haciendo cada uno:

```sh
docker compose logs -f worker beat
```

---

## Carga de catálogo por planilla

En **Panel → Catálogo** se descarga la plantilla (`/panel/catalogo/plantilla.xlsx`). La primera fila debe ser exactamente:

| nombre | categoria | unidad | precio | stock |
|---|---|---|---|---|
| Tornillo coche 1/4" x 2" | Fijaciones | unidad | 120 | 300 |

- **categoria:** Adhesivos y sellantes, Construcción, Electricidad, Fijaciones, Gasfitería, Herramientas eléctricas, Herramientas manuales, Jardín, Pinturas o Seguridad. No distingue mayúsculas ni tildes.
- **unidad:** unidad, caja, bolsa, kg, metro, litro, galón, par o rollo.
- **precio y stock:** enteros entre 0 y 100.000.000. Se aceptan formatos como `6990`, `6.990` o `$6.990`.
- **Límites:** archivo `.xlsx` de hasta 2 MB (20 MB descomprimido) y 2.000 filas.

Si el nombre coincide con un producto que ya existe (sin importar mayúsculas ni tildes), se actualizan su categoría, su precio y su stock (la unidad debe ser la misma); si no, se crea un producto nuevo. Las filas válidas se aplican y las demás se informan con su número de fila y el motivo.

---

## Comandos útiles

Todos se corren desde la carpeta del repo, con los servicios levantados.

```sh
docker compose logs -f web                              # registro de la aplicación
docker compose exec web python manage.py shell          # consola de Django
docker compose exec web python manage.py migrate        # aplicar migraciones
docker compose exec web python manage.py makemigrations # crear migraciones tras cambiar modelos
docker compose exec web python manage.py poblar_demo    # recargar datos de demo (no duplica)
docker compose exec web python manage.py createsuperuser
docker compose exec db psql -U ferrebarrio              # consola de PostgreSQL
```

Para volver a la demo desde cero (borra la base):

```sh
docker compose down -v && docker compose up --build -d
```

`poblar_demo` solo corre con `DJANGO_DEBUG=1`: crea un administrador con la contraseña pública de esta guía y nunca debe ejecutarse en otro entorno.

---

## Pruebas y calidad

Las pruebas corren contra PostGIS y Redis reales, dentro de Docker:

```sh
docker compose run --rm web pytest -q
```

La suite exige al menos 70 % de cobertura (hoy está sobre 90 %). Cubre, entre otras cosas, la disputa por la última unidad, el límite de reservas, la expiración, el aislamiento entre comercios y entre clientes, y la carga por planilla.

Las mismas revisiones que corre el CI (`.github/workflows/ci.yml`, en cada push a `main`):

```sh
docker compose run --rm web sh -c "\
  ruff check . && ruff format --check . && \
  bandit -q -r . -x ./.venv,./conftest.py,'*/tests.py','./test_*.py' && \
  pip-audit -r requirements.txt && \
  python manage.py makemigrations --check --dry-run && \
  pytest -q"
```

Para formatear el código antes de un commit: `docker compose run --rm web ruff format .`

---

## Estructura del proyecto

| Carpeta | Módulo | Qué contiene |
|---|---|---|
| `config/` | — | Ajustes, URLs raíz, Celery. |
| `cuentas/` | M7 | Usuario por correo y rol (cliente, comerciante, administrador), registro, ingreso con bloqueo, «Mi cuenta», eliminación de cuenta, auditoría, privacidad y términos, `poblar_demo`. |
| `comercios/` | M1 | Ficha del comercio, validación de RUT, geocodificación, verificación por el administrador y ficha pública (HU-17). |
| `catalogo/` | M2 | Productos, stock, frescura del catálogo y carga por planilla (HU-06). |
| `busqueda/` | M3 | Búsqueda por cercanía con PostGIS, mapa Leaflet y registro de búsquedas para los reportes. |
| `reservas/` | M4 | Reservas, estados, límites, expiración, conciliación y avisos por correo. Toda la lógica de stock está en `reservas/servicios.py`. |
| `valoraciones/` | M5 | Valoración después del retiro y moderación (HU-21 a HU-23). |
| `reportes/` | M6 | Reportes del comerciante (HU-24 a HU-26) e indicadores del administrador. |
| `templates/` | — | Plantillas HTML (Bootstrap 5), una carpeta por módulo. |

Los tests están en `tests.py` dentro de cada módulo y en `test_revision_seguridad.py`. Los datos de prueba compartidos están en `conftest.py`.

---

## Variables de entorno

`docker-compose.yml` ya trae valores para el entorno local; no hace falta configurar nada. Para otro entorno:

| Variable | Uso | Valor local |
|---|---|---|
| `DJANGO_SECRET_KEY` | Clave de Django (**obligatoria**) | valor de desarrollo |
| `DJANGO_DEBUG` | `1` activa el modo desarrollo | `1` |
| `DJANGO_ALLOWED_HOSTS` | Dominios aceptados, separados por coma | `localhost,127.0.0.1,web` |
| `DJANGO_HTTPS` | `1` activa cookies seguras, HSTS y redirección a HTTPS | sin definir |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Base de datos | `db`, `5432`, `ferrebarrio` ×3 |
| `REDIS_URL` | Caché y cola de Celery | `redis://redis:6379` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | SMTP (Brevo u otro) | Mailpit, `1025` |
| `DEFAULT_FROM_EMAIL` | Remitente de los avisos | `FerreBarrio <no-responder@ferrebarrio.cl>` |
| `AVISOS_CUOTA_DIARIA` | Cuota diaria del proveedor de correo | `300` |
| `SITIO_URL` | URL base de los enlaces en los correos | `http://127.0.0.1:<WEB_PORT>` |
| `NOMINATIM_URL` | Servicio de geocodificación; vacío lo desactiva | servidor público de OpenStreetMap |
| `NOMINATIM_USER_AGENT` | Identificación ante Nominatim | `FerreBarrio/1.0 (…)` |
| `CELERY_EAGER` | `1` ejecuta las tareas sin worker | sin definir |
| `WEB_PORT`, `MAILPIT_PORT` | Puertos publicados (en `.env`) | `8000`, `8025` |

Las credenciales de `docker-compose.yml` son solo para desarrollo local. El entorno local no incluye lo que necesitaría un despliegue real: servidor de aplicación en lugar de `runserver`, proxy HTTPS, archivos estáticos servidos aparte y secretos fuera del repo.

---

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| Ingreso y vuelve a pedirme el ingreso | Estás en `localhost`: usa `http://127.0.0.1:<puerto>`. |
| `port is already allocated` al levantar | Otro programa usa el puerto: define `WEB_PORT`/`MAILPIT_PORT` en `.env`. |
| `web` se reinicia o no conecta a la base en el primer arranque | PostGIS se inicializa una vez antes de quedar listo: `web` espera su chequeo de salud. Si se cortó a la mitad, `docker compose down -v` y vuelve a levantar. |
| El mapa sale gris, sin calles | Las teselas de OpenStreetMap necesitan internet. La búsqueda funciona igual. |
| Al registrar un comercio no encuentra la dirección | Nominatim no respondió (o no hay internet): arrastra el marcador al lugar correcto. |
| No llegan los correos | Revisa Mailpit y `docker compose logs worker`: el envío lo hace el worker, no `web`. |
| «Demasiados intentos fallidos» | Bloqueo de 15 minutos tras 5 fallos. Para liberarlo ya, vacía la caché: `docker compose exec redis redis-cli -n 1 FLUSHDB`. |
| La reserva desapareció de «activas» | Pasaron 4 horas sin retiro y expiró. Así está diseñado. |
| En Mac con chip Apple la base arranca lenta | La imagen `postgis/postgis` es x86 y corre emulada. Funciona; solo es más lenta la primera vez. |
