"""Tabelas do banco.

Dinheiro é guardado em centavos (inteiro). Número decimal com vírgula
flutuante gera erro de arredondamento, o que não pode acontecer com saldo.
"""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    cpf: Mapped[str] = mapped_column(String(11), unique=True, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    conta: Mapped["Conta"] = relationship(back_populates="cliente", uselist=False)


class Conta(Base):
    __tablename__ = "contas"
    __table_args__ = (CheckConstraint("saldo_centavos >= 0", name="saldo_nao_negativo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), unique=True)
    agencia: Mapped[str] = mapped_column(String(4), default="0001")
    saldo_centavos: Mapped[int] = mapped_column(Integer, default=0)
    chave_pix: Mapped[str | None] = mapped_column(String(77), unique=True, index=True, nullable=True)

    cliente: Mapped[Cliente] = relationship(back_populates="conta")


class Transacao(Base):
    __tablename__ = "transacoes"
    __table_args__ = (CheckConstraint("valor_centavos > 0", name="valor_positivo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))  # deposito | pix
    conta_origem_id: Mapped[int | None] = mapped_column(ForeignKey("contas.id"), nullable=True)
    conta_destino_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))
    valor_centavos: Mapped[int] = mapped_column(Integer)
    # Chave enviada pelo app do cliente. Se a mesma requisição chegar duas
    # vezes (rede instável, clique duplo), o Pix não é feito em dobro.
    chave_idempotencia: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
