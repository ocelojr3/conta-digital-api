"""Formato dos dados que entram e saem da API, com validação."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def cpf_valido(cpf: str) -> bool:
    """Confere os dois dígitos verificadores do CPF."""
    if len(cpf) != 11 or not cpf.isdigit() or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def mascarar_cpf(cpf: str) -> str:
    """LGPD: a API nunca devolve o CPF completo."""
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**"


class ClienteNovo(BaseModel):
    nome: str = Field(min_length=3, max_length=120)
    cpf: str

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, valor: str) -> str:
        so_digitos = "".join(c for c in valor if c.isdigit())
        if not cpf_valido(so_digitos):
            raise ValueError("CPF inválido")
        return so_digitos


class ContaSaida(BaseModel):
    conta_id: int
    agencia: str
    titular: str
    cpf: str
    saldo_centavos: int
    chave_pix: str | None


class ChavePixNova(BaseModel):
    chave: str = Field(min_length=3, max_length=77)


class Deposito(BaseModel):
    valor_centavos: int = Field(gt=0, le=100_000_000)


class PixNovo(BaseModel):
    conta_origem_id: int
    chave_destino: str
    valor_centavos: int = Field(gt=0, le=100_000_000)


class TransacaoSaida(BaseModel):
    id: int
    tipo: str
    conta_origem_id: int | None
    conta_destino_id: int
    valor_centavos: int
    criado_em: datetime
