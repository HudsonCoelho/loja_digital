"""Utilidades: dinheiro, códigos (SKU / EAN-13), CPF, datas."""
import re
import unicodedata
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


class ErroNegocio(Exception):
    """Erro de regra de negócio, devolvido ao frontend como JSON."""

    def __init__(self, mensagem: str, status: int = 400, **extra):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
        self.extra = extra


# ---------------- Dinheiro ----------------
def money(valor) -> Decimal:
    """Converte para Decimal com 2 casas (arredondamento comercial)."""
    if valor is None or valor == "":
        return Decimal("0.00")
    try:
        if isinstance(valor, float):
            valor = repr(valor)
        return Decimal(str(valor).replace(",", ".")).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ErroNegocio(f"Valor monetário inválido: {valor}")


def to_float(valor) -> float:
    if isinstance(valor, Decimal):
        return float(valor.quantize(CENT, rounding=ROUND_HALF_UP))
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)
    return float(money(valor))


def parse_int(valor, campo: str, minimo: int | None = None) -> int:
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ErroNegocio(f"{campo}: número inteiro inválido")
    if minimo is not None and n < minimo:
        raise ErroNegocio(f"{campo}: deve ser no mínimo {minimo}")
    return n


# ---------------- Texto ----------------
def sem_acentos(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", txt or "") if unicodedata.category(c) != "Mn")


def limpar(txt, max_len: int = 200) -> str:
    return re.sub(r"\s+", " ", str(txt or "")).strip()[:max_len]


def _sigla(txt: str, n: int = 3) -> str:
    base = re.sub(r"[^A-Z0-9]", "", sem_acentos(txt).upper())
    return (base[:n] or "X").ljust(n, "X")


def gerar_sku(produto_id: int, categoria: str, cor: str, tamanho: str) -> str:
    tam = re.sub(r"[^A-Z0-9]", "", sem_acentos(tamanho).upper()) or "U"
    return f"{_sigla(categoria)}-{produto_id:05d}-{_sigla(cor)}-{tam}"


# ---------------- EAN-13 ----------------
def ean13_digito(doze: str) -> str:
    soma = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(doze))
    return str((10 - soma % 10) % 10)


def ean13_valido(codigo: str) -> bool:
    return bool(re.fullmatch(r"\d{13}", codigo or "")) and ean13_digito(codigo[:12]) == codigo[12]


def gerar_ean13_interno(variacao_id: int) -> str:
    """Prefixo 2 = faixa reservada para uso interno da loja (GS1)."""
    doze = "2" + str(variacao_id).zfill(11)
    return doze + ean13_digito(doze)


def validar_codigo_barras(codigo: str) -> str:
    codigo = re.sub(r"\s", "", codigo or "")
    if not codigo:
        return ""
    if not re.fullmatch(r"[0-9A-Za-z\-]{4,32}", codigo):
        raise ErroNegocio(f"Código de barras inválido: {codigo}")
    if len(codigo) == 13 and codigo.isdigit() and not ean13_valido(codigo):
        raise ErroNegocio(f"EAN-13 com dígito verificador inválido: {codigo}")
    return codigo


# ---------------- CPF ----------------
def cpf_valido(cpf: str) -> bool:
    d = re.sub(r"\D", "", cpf or "")
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        dig = (soma * 10 % 11) % 10
        if dig != int(d[n]):
            return False
    return True


# ---------------- Datas ----------------
def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
