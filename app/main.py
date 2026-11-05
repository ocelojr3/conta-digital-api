"""Rotas HTTP da API de conta digital."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from . import services
from .db import Base, engine, get_session
from .models import Conta, Transacao
from .schemas import (
    ChavePixNova,
    ClienteNovo,
    ContaSaida,
    Deposito,
    PixNovo,
    TransacaoSaida,
    mascarar_cpf,
)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="Conta Digital API",
    description="Abertura de conta, depósito, Pix com idempotência e extrato.",
    version="1.0.0",
    lifespan=ciclo_de_vida,
)


@app.exception_handler(services.ErroNegocio)
async def tratar_erro_negocio(request: Request, erro: services.ErroNegocio):
    return JSONResponse(status_code=erro.status, content={"erro": erro.mensagem})


def conta_para_saida(conta: Conta) -> ContaSaida:
    return ContaSaida(
        conta_id=conta.id,
        agencia=conta.agencia,
        titular=conta.cliente.nome,
        cpf=mascarar_cpf(conta.cliente.cpf),
        saldo_centavos=conta.saldo_centavos,
        chave_pix=conta.chave_pix,
    )


def transacao_para_saida(t: Transacao) -> TransacaoSaida:
    return TransacaoSaida.model_validate(t, from_attributes=True)


@app.get("/saude")
def saude():
    return {"status": "ok"}


@app.post("/contas", status_code=201, response_model=ContaSaida)
def abrir_conta(dados: ClienteNovo, session: Session = Depends(get_session)):
    return conta_para_saida(services.abrir_conta(session, dados.nome, dados.cpf))


@app.get("/contas/{conta_id}", response_model=ContaSaida)
def ver_conta(conta_id: int, session: Session = Depends(get_session)):
    return conta_para_saida(services.buscar_conta(session, conta_id))


@app.put("/contas/{conta_id}/chave-pix", response_model=ContaSaida)
def cadastrar_chave(conta_id: int, dados: ChavePixNova, session: Session = Depends(get_session)):
    return conta_para_saida(services.cadastrar_chave_pix(session, conta_id, dados.chave))


@app.post("/contas/{conta_id}/depositos", status_code=201, response_model=TransacaoSaida)
def depositar(conta_id: int, dados: Deposito, session: Session = Depends(get_session)):
    return transacao_para_saida(services.depositar(session, conta_id, dados.valor_centavos))


@app.post("/pix", status_code=201, response_model=TransacaoSaida)
def fazer_pix(
    dados: PixNovo,
    response: Response,
    idempotency_key: str = Header(min_length=8, max_length=64),
    session: Session = Depends(get_session),
):
    transacao, criada = services.fazer_pix(
        session, dados.conta_origem_id, dados.chave_destino, dados.valor_centavos, idempotency_key
    )
    if not criada:
        response.status_code = 200  # repetição: devolve o mesmo Pix, sem cobrar de novo
    return transacao_para_saida(transacao)


@app.get("/contas/{conta_id}/extrato", response_model=list[TransacaoSaida])
def ver_extrato(conta_id: int, session: Session = Depends(get_session)):
    return [transacao_para_saida(t) for t in services.extrato(session, conta_id)]
