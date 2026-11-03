from django import forms
from django.conf import settings
from django.core.validators import RegexValidator

from catalogo.models import Categoria
from comercios.geo import dentro_de_chile
from comercios.models import COMUNAS


class BusquedaForm(forms.Form):
    """CT-01: término acotado; CT-03: radio máximo 3 km; ubicación del navegador o comuna."""

    q = forms.CharField(
        label="¿Qué necesitas?",
        min_length=2,
        max_length=60,
        validators=[
            RegexValidator(
                r"^[\w\s\"'.,/#°º+\-]+$", "Usa solo letras, números y los signos \" ' . , / # ° + -"
            )
        ],
    )
    categoria = forms.ModelChoiceField(
        Categoria.objects.all(), required=False, empty_label="Todas las categorías"
    )
    comuna = forms.ChoiceField(choices=[("", "Elige tu comuna")] + [(c, c) for c in COMUNAS], required=False)
    radio = forms.TypedChoiceField(
        choices=[(k, f"{k} km") for k in range(1, settings.BUSQUEDA_RADIO_MAX_KM + 1)], coerce=int, initial=2
    )
    lat = forms.FloatField(required=False, widget=forms.HiddenInput)
    lon = forms.FloatField(required=False, widget=forms.HiddenInput)

    def clean(self):
        datos = super().clean()
        lat, lon = datos.get("lat"), datos.get("lon")
        if lat is not None and lon is not None and dentro_de_chile(lat, lon):
            datos["punto"] = (lat, lon)
        elif datos.get("comuna"):
            datos["punto"] = COMUNAS[datos["comuna"]]
        else:
            raise forms.ValidationError("Permite tu ubicación o elige una comuna.")
        return datos
