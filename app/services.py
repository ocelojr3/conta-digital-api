"""Regras de negócio da conta digital, separadas das rotas HTTP."""
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Cliente, Conta, Transacao


class ErroNegocio(Exception):
    def __init__(self, status: int, mensagem: str):
        self.status = status
        self.mensagem = mensagem


def abrir_conta(session: Session, nome: str, cpf: str) -> Conta:
    if session.scalar(select(Cliente).where(Cliente.cpf == cpf)):
        raise ErroNegocio(409, "Já existe conta para este CPF")
    cliente = Cliente(nome=nome, cpf=cpf)
    conta = Conta(cliente=cliente)
    session.add_all([cliente, conta])
    session.commit()
    return conta


def buscar_conta(session: Session, conta_id: int, travar: bool = False) -> Conta:
    consulta = select(Conta).where(Conta.id == conta_id)
    if travar:
        # No PostgreSQL trava a linha até o fim da transação: dois Pix
        # simultâneos da mesma conta não conseguem gastar o mesmo saldo.
        # populate_existing relê o saldo do banco em vez de usar a cópia em memória.
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    conta = session.scalar(consulta)
    if conta is None:
        raise ErroNegocio(404, "Conta não encontrada")
    return conta


def cadastrar_chave_pix(session: Session, conta_id: int, chave: str) -> Conta:
    conta = buscar_conta(session, conta_id)
    if session.scalar(select(Conta).where(Conta.chave_pix == chave)):
        raise ErroNegocio(409, "Chave Pix já cadastrada")
    conta.chave_pix = chave
    session.commit()
    return conta


def depositar(session: Session, conta_id: int, valor: int) -> Transacao:
    conta = buscar_conta(session, conta_id, travar=True)
    conta.saldo_centavos += valor
    transacao = Transacao(tipo="deposito", conta_destino_id=conta.id, valor_centavos=valor)
    session.add(transacao)
    session.commit()
    return transacao


def fazer_pix(
    session: Session, conta_origem_id: int, chave_destino: str, valor: int, chave_idempotencia: str
) -> tuple[Transacao, bool]:
    """Faz o Pix. Devolve (transação, criada_agora)."""
    repetida = session.scalar(
        select(Transacao).where(Transacao.chave_idempotencia == chave_idempotencia)
    )
    if repetida:
        if repetida.conta_origem_id != conta_origem_id or repetida.valor_centavos != valor:
            raise ErroNegocio(409, "Chave de idempotência já usada em outro Pix")
        return repetida, False

    destino = session.scalar(select(Conta).where(Conta.chave_pix == chave_destino))
    if destino is None:
        raise ErroNegocio(404, "Chave Pix de destino não encontrada")
    if destino.id == conta_origem_id:
        raise ErroNegocio(422, "Não é possível fazer Pix para a própria conta")

    # Trava sempre na mesma ordem (menor id primeiro) para evitar deadlock.
    for conta_id in sorted((conta_origem_id, destino.id)):
        buscar_conta(session, conta_id, travar=True)
    origem = session.get(Conta, conta_origem_id)
    destino = session.get(Conta, destino.id)

    if origem.saldo_centavos < valor:
        session.rollback()
        raise ErroNegocio(422, "Saldo insuficiente")

    origem.saldo_centavos -= valor
    destino.saldo_centavos += valor
    transacao = Transacao(
        tipo="pix",
        conta_origem_id=origem.id,
        conta_destino_id=destino.id,
        valor_centavos=valor,
        chave_idempotencia=chave_idempotencia,
    )
    session.add(transacao)
    try:
        session.commit()
    except IntegrityError:
        # Outra requisição com a mesma chave terminou primeiro.
        session.rollback()
        raise ErroNegocio(409, "Pix já processado com esta chave de idempotência")
    return transacao, True


def extrato(session: Session, conta_id: int) -> list[Transacao]:
    buscar_conta(session, conta_id)
    consulta = (
        select(Transacao)
        .where(or_(Transacao.conta_origem_id == conta_id, Transacao.conta_destino_id == conta_id))
        .order_by(Transacao.id.desc())
    )
    return list(session.scalars(consulta))
