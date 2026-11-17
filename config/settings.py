import os
from pathlib import Path

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
SITIO_URL = os.environ.get("SITIO_URL", "http://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.gis",
    "django.contrib.postgres",
    "cuentas",
    "comercios",
    "catalogo",
    "busqueda",
    "reservas",
    "valoraciones",
    "reportes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "reservas.contexto.pendientes",
            ]
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "NAME": os.environ.get("POSTGRES_DB", "ferrebarrio"),
        "USER": os.environ.get("POSTGRES_USER", "ferrebarrio"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        # Reusa conexiones entre requests y descarta las rotas (BD reiniciada) antes de usarlas.
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": f"{REDIS_URL}/1"}}

AUTH_USER_MODEL = "cuentas.Usuario"
LOGIN_URL = "cuentas:ingresar"
LOGIN_REDIRECT_URL = "busqueda:inicio"
LOGOUT_REDIRECT_URL = "busqueda:inicio"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]  # static/css/app.css: Tailwind compilado (ver README)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cookies y cabeceras: endurecidas siempre; las que exigen HTTPS se activan con DJANGO_HTTPS=1.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 8
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
# OSM exige Referer en sus teselas; hacia otros dominios solo viaja el origen, nunca la ruta ni la búsqueda.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
if os.environ.get("DJANGO_HTTPS") == "1":
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Correo: Mailpit en local, Brevo (SMTP) en producción, ambos por variables de entorno.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "1025"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS") == "1"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "FerreBarrio <no-responder@ferrebarrio.cl>")
AVISOS_CUOTA_DIARIA = int(os.environ.get("AVISOS_CUOTA_DIARIA", "300"))

# Geocodificación (CT-13, CT-17). Vacío desactiva la consulta externa.
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
NOMINATIM_USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "FerreBarrio/1.0 (proyecto de titulo UNAB)")

# Reglas de negocio
RESERVA_VIGENCIA_HORAS = 4
RESERVA_MAX_ACTIVAS = 3
RESERVA_MAX_POR_DIA = 10  # creadas en 24 h: corta el ciclo reservar → anular que gasta la cuota de correos
RESERVA_MAX_CANTIDAD = 20
RESERVA_AVISO_SIN_ATENCION_MIN = 30
STOCK_DESACTUALIZADO_HORAS = 72
BUSQUEDA_RADIO_MAX_KM = 3
BUSQUEDA_POR_MINUTO = 30

CELERY_BROKER_URL = f"{REDIS_URL}/0"
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_EAGER") == "1"
CELERY_TIMEZONE = TIME_ZONE
# Resiliencia: la tarea se confirma al terminar (si el worker muere, Redis la reentrega) y cada worker toma
# una a la vez. Publicar con el broker caído falla rápido: el aviso queda pendiente y beat lo re-despacha.
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_PUBLISH_RETRY_POLICY = {"max_retries": 1, "interval_start": 0, "interval_step": 0.5}
CELERY_BROKER_TRANSPORT_OPTIONS = {"socket_connect_timeout": 2, "socket_timeout": 5}
CELERY_BEAT_SCHEDULE = {
    "redespachar-avisos": {"task": "reservas.tasks.redespachar_avisos", "schedule": 60},
    "expirar-reservas": {"task": "reservas.tasks.expirar_reservas", "schedule": 60},
    "avisar-sin-atencion": {"task": "reservas.tasks.avisar_sin_atencion", "schedule": 60},
    "conciliar-stock": {"task": "reservas.tasks.conciliar_stock", "schedule": crontab(hour=3, minute=0)},
    "catalogo-desactualizado": {
        "task": "catalogo.tasks.avisar_catalogo_desactualizado",
        "schedule": crontab(hour=9, minute=0),
    },
}

# Logs con hora, nivel y módulo. Solo identificadores (pk, código de reserva, tipo): nunca correo, teléfono ni
# nombre de personas (Ley 21.719).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"fb": {"format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "fb"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
