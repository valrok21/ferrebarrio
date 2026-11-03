# FerreBarrio

Plataforma web para buscar productos en ferreterías de barrio cercanas, ver si hay stock y reservarlos para retiro en el local. Proyecto de título.

Stack: Python 3.12, Django 5.2, PostgreSQL 16 + PostGIS, Celery + Redis 7, Bootstrap 5.3 y Leaflet por CDN, correo SMTP (Mailpit en local).

## Levantar en local

Requiere Docker con Compose.

```sh
docker compose up --build
```

El servicio `web` aplica las migraciones y carga los datos de demo (`poblar_demo`, se puede correr varias veces sin duplicar nada).

| Qué | Dirección |
|---|---|
| Aplicación | http://localhost:8000 |
| Correos enviados (Mailpit) | http://localhost:8025 |
| Administración de Django | http://localhost:8000/django-admin/ |

Si esos puertos están ocupados, crea un `.env` junto a `docker-compose.yml`:

```sh
WEB_PORT=8010
MAILPIT_PORT=8035
```

Si en el navegador el ingreso no se mantiene, usa `http://127.0.0.1:<puerto>`: las cookies de `localhost` se comparten entre puertos y otra aplicación local puede pisar la sesión.

Servicios: `db` (PostGIS), `redis`, `mailpit`, `web`, `worker` (envía los avisos por correo) y `beat` (cada minuto expira reservas vencidas y avisa reservas sin atender; a las 03:00 concilia el stock).

## Usuarios de demo

Contraseña de todos: `FerreDemo2026`.

| Rol | Correo |
|---|---|
| Administrador | `admin@demo.ferrebarrio.cl` |
| Comerciante (Ferretería San Pablo, Providencia) | `sanpablo@demo.ferrebarrio.cl` |
| Comerciante (Ferretería El Tornillo) | `eltornillo@demo.ferrebarrio.cl` |
| Comerciante (Ferretería Don Luis) | `donluis@demo.ferrebarrio.cl` |
| Comerciante con solicitud pendiente | `losaromos@demo.ferrebarrio.cl` |
| Cliente | `camila@demo.ferrebarrio.cl` |
| Cliente | `pedro@demo.ferrebarrio.cl` |

## Recorrido sugerido

1. En el inicio, busca «tornillo» con la comuna Providencia y radio 2 km: resultados por distancia, en lista y mapa.
2. Ingresa como Camila y reserva 2 unidades. Llega el correo en Mailpit.
3. Ingresa como San Pablo, en «Panel» marca la reserva como atendida y luego entregada.
4. De vuelta como Camila, valora la reserva retirada.
5. Como administrador, revisa `/administracion/`: indicadores y solicitudes de comercios.

## Reportes (HU-24 a HU-26)

En `/panel/reportes/`, cada comerciante ve lo buscado en 3 km de su local durante los últimos 30 días:

- **Más buscados** (HU-24): los términos más frecuentes en su zona.
- **Demanda no cubierta** (HU-25): búsquedas que no encontraron stock en la zona.
- **Reservas** (HU-26): reservas por estado, tasa de retiro y productos en quiebre (stock 0).

En `/administracion/`, el administrador ve los indicadores de los objetivos: comercios aprobados con catálogo (OE1), porcentaje de búsquedas con resultados (OE2), reservas y tasa de retiro (OE3), diferencias de stock detectadas por la conciliación y avisos que no se pudieron enviar.

## Pruebas

```sh
docker compose run --rm web pytest -q
```

Exige cobertura de al menos 70 %. El CI (`.github/workflows/ci.yml`) además corre `ruff`, `bandit` y `pip-audit`.
