"""La interfaz usa Tailwind compilado y versionado (static/css/app.css), sin Bootstrap ni CDN de CSS.

La demo debe verse sin internet: si alguna plantilla vuelve a cargar Bootstrap o el script "play" de
Tailwind, o usa una clase que no está en app.css (falta recompilar), estos tests lo detectan.
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

RAIZ = Path(__file__).resolve().parent
PLANTILLAS = RAIZ / "templates"
APP_CSS = RAIZ / "static" / "css" / "app.css"

# Clases de Bootstrap que no deben quedar (misma expresión que el grep de revisión del encargo).
CLASES_BOOTSTRAP = re.compile(
    r'class="[^"]*\b(btn|card|row|col-|container|alert|navbar|form-control|d-flex|mb-[0-9]|text-muted|table)\b'
)


def _plantillas():
    """Plantillas HTML salvo correos (estilos en línea)."""
    excluidas = {"emails"}
    return [p for p in PLANTILLAS.rglob("*.html") if not excluidas & set(p.relative_to(PLANTILLAS).parts)]


@pytest.mark.django_db
@pytest.mark.parametrize("url", ["/", reverse("cuentas:ingresar")])
def test_paginas_cargan_tailwind_compilado_y_no_bootstrap(client, url):
    r = client.get(url)
    html = r.content.decode()
    assert r.status_code == 200
    assert "/static/css/app.css" in html
    assert "bootstrap" not in html.lower()


def test_app_css_compilado_contiene_utilidades_de_las_plantillas():
    css = APP_CSS.read_text(encoding="utf-8")
    assert css.strip(), "static/css/app.css está vacío: recompila Tailwind (ver README)"
    # Color de marca (el mismo del correo HTML) y la utilidad que lo usa en las plantillas.
    assert "#c2410c" in css.lower()
    assert ".border-marca" in css


def _selector(clase):
    """Escapa una clase como la escribe Tailwind en el CSS (p. ej. md:p-6 -> md\\:p-6)."""
    return "".join(c if c.isalnum() or c in "-_" else "\\" + c for c in clase)


def test_app_css_esta_al_dia_con_las_clases_de_las_plantillas():
    """Toda clase usada en una plantilla tiene regla en app.css: si falla, falta recompilar."""
    css = APP_CSS.read_text(encoding="utf-8")
    faltantes = set()
    for p in _plantillas():
        for valor in re.findall(r'class="([^"]*)"', p.read_text(encoding="utf-8")):
            # Las partes armadas con etiquetas de plantilla no son clases literales: se omiten.
            valor = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", "§", valor)
            for clase in valor.split():
                regla = r"\." + re.escape(_selector(clase)) + r"(?![\w-])"
                if "§" not in clase and not re.search(regla, css):
                    faltantes.add(f"{p.relative_to(PLANTILLAS)}: {clase}")
    assert not faltantes, sorted(faltantes)


def test_ninguna_plantilla_usa_bootstrap_ni_cdn_de_tailwind():
    plantillas = _plantillas()
    assert plantillas, "no se encontraron plantillas"
    for p in plantillas:
        texto = p.read_text(encoding="utf-8")
        nombre = p.relative_to(PLANTILLAS)
        assert "bootstrap" not in texto.lower(), nombre
        assert "cdn.tailwindcss.com" not in texto and "@tailwindcss/browser" not in texto, nombre
        assert not CLASES_BOOTSTRAP.search(texto), f"{nombre}: {CLASES_BOOTSTRAP.search(texto).group(0)}"
