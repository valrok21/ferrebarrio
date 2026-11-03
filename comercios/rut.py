import re

from django.core.exceptions import ValidationError


def digito_verificador(cuerpo: int) -> str:
    suma, factor = 0, 2
    for d in reversed(str(cuerpo)):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return {11: "0", 10: "K"}.get(resto, str(resto))


def normalizar_rut(valor: str) -> str:
    """Devuelve el RUT como «12345678-5» o lanza ValidationError si el dígito verificador no cuadra."""
    limpio = re.sub(r"[^0-9kK]", "", valor or "").upper()
    if len(limpio) < 2 or not limpio[:-1].isdigit():
        raise ValidationError("RUT con formato inválido.")
    cuerpo, dv = int(limpio[:-1]), limpio[-1]
    if not 1_000_000 <= cuerpo <= 99_999_999 or digito_verificador(cuerpo) != dv:
        raise ValidationError("RUT inválido: el dígito verificador no corresponde.")
    return f"{cuerpo}-{dv}"
