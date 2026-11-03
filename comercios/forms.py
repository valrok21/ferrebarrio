from django import forms
from django.core.exceptions import ValidationError

from .geo import dentro_de_chile
from .models import Comercio
from .rut import normalizar_rut


class ComercioForm(forms.ModelForm):
    lat = forms.FloatField(required=False, widget=forms.HiddenInput)
    lon = forms.FloatField(required=False, widget=forms.HiddenInput)
    marcador_movido = forms.BooleanField(required=False, widget=forms.HiddenInput)
    acepto_terminos = forms.BooleanField(
        label="Declaro que los datos son verídicos y acepto los términos de uso"
    )

    class Meta:
        model = Comercio
        fields = ["nombre", "rut", "direccion", "comuna", "telefono", "horario"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.ubicacion:
            self.initial.update(lat=self.instance.ubicacion.y, lon=self.instance.ubicacion.x)
        if self.instance.pk:
            self.fields["acepto_terminos"].required = False
            self.fields["acepto_terminos"].widget = forms.HiddenInput()

    def clean_rut(self):
        rut = normalizar_rut(self.cleaned_data["rut"])
        if Comercio.objects.filter(rut=rut).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ese RUT ya está registrado.")
        return rut

    def clean(self):
        datos = super().clean()
        if datos.get("marcador_movido"):
            lat, lon = datos.get("lat"), datos.get("lon")
            if lat is None or lon is None or not dentro_de_chile(lat, lon):
                raise ValidationError("La ubicación marcada debe estar dentro de Chile.")
        return datos


class FichaAprobadaForm(forms.ModelForm):
    class Meta:
        model = Comercio
        fields = ["horario", "telefono"]


class VerificacionForm(forms.Form):
    accion = forms.ChoiceField(
        choices=[("aprobar", "Aprobar"), ("observar", "Observar"), ("rechazar", "Rechazar")]
    )
    motivo = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), max_length=1000)

    def clean(self):
        datos = super().clean()
        if datos.get("accion") in ("observar", "rechazar") and not datos.get("motivo", "").strip():
            self.add_error("motivo", "Indica el motivo para que el comerciante pueda corregir.")
        return datos
