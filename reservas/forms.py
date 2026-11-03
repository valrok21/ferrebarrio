from django import forms
from django.conf import settings


class ReservaForm(forms.Form):
    cantidad = forms.IntegerField(min_value=1, max_value=settings.RESERVA_MAX_CANTIDAD, initial=1)
