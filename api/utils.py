import hashlib
import re


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def formatar_placa(placa: str) -> str:
    if not placa:
        return ""
    placa_limpa = re.sub(r"[^A-Z0-9]", "", placa.upper())
    if len(placa_limpa) == 7 and placa_limpa[4].isdigit():
        return f"{placa_limpa[:3]}-{placa_limpa[3:]}"
    return placa_limpa


def formatar_telefone(numero: str) -> str:
    if not numero:
        return ""
    numeros = re.sub(r"\D", "", numero)
    if len(numeros) == 11:
        return f"({numeros[:2]}){numeros[2:7]}-{numeros[7:]}"
    if len(numeros) == 10:
        return f"({numeros[:2]}){numeros[2:6]}-{numeros[6:]}"
    return numero
