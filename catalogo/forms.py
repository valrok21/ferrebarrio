from django import forms

from .models import Producto


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["nombre", "categoria", "unidad", "precio_referencial", "stock_disponible"]
        help_texts = {
            "stock_disponible": "Unidades que se pueden reservar ahora (sin contar las ya reservadas)."
        }

    def clean_stock_disponible(self):
        stock = self.cleaned_data["stock_disponible"]
        if stock < 0:
            raise forms.ValidationError("El stock no puede ser negativo.")
        return stock

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        repetido = Producto.objects.filter(
            comercio=self.instance.comercio, activo=True, nombre_normalizado=Producto.clave(nombre)
        ).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Ya tienes un producto con ese nombre.")
        return nombre


class PlanillaForm(forms.Form):
    archivo = forms.FileField(
        label="Planilla .xlsx o .csv", widget=forms.ClearableFileInput(attrs={"accept": ".xlsx,.csv"})
    )
