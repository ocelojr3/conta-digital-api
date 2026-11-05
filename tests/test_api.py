"""Testes da API. Cada teste roda num banco SQLite novo e vazio."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_session
from app.main import app
from app.schemas import cpf_valido

CPF_ANA = "529.982.247-25"
CPF_BRUNO = "111.444.777-35"


@pytest.fixture()
def cliente(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/teste.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def sessao_de_teste():
        s = Sessao()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = sessao_de_teste
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def abrir(c, nome, cpf, chave=None, deposito=0):
    conta = c.post("/contas", json={"nome": nome, "cpf": cpf}).json()
    if chave:
        c.put(f"/contas/{conta['conta_id']}/chave-pix", json={"chave": chave})
    if deposito:
        c.post(f"/contas/{conta['conta_id']}/depositos", json={"valor_centavos": deposito})
    return conta["conta_id"]


def pix(c, origem, chave, valor, idem="pix-0001-abc"):
    return c.post(
        "/pix",
        json={"conta_origem_id": origem, "chave_destino": chave, "valor_centavos": valor},
        headers={"Idempotency-Key": idem},
    )


def saldo(c, conta_id):
    return c.get(f"/contas/{conta_id}").json()["saldo_centavos"]


def test_cpf_valido_e_invalido():
    assert cpf_valido("52998224725")
    assert not cpf_valido("52998224724")
    assert not cpf_valido("11111111111")


def test_abre_conta_e_mascara_cpf(cliente):
    r = cliente.post("/contas", json={"nome": "Ana Souza", "cpf": CPF_ANA})
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["cpf"] == "***.982.247-**"
    assert corpo["saldo_centavos"] == 0
    assert corpo["agencia"] == "0001"


def test_recusa_cpf_invalido_e_duplicado(cliente):
    assert cliente.post("/contas", json={"nome": "Ana", "cpf": "123.456.789-00"}).status_code == 422
    cliente.post("/contas", json={"nome": "Ana Souza", "cpf": CPF_ANA})
    r = cliente.post("/contas", json={"nome": "Ana Souza", "cpf": CPF_ANA})
    assert r.status_code == 409


def test_deposito_soma_no_saldo(cliente):
    conta = abrir(cliente, "Ana Souza", CPF_ANA, deposito=10_000)
    assert saldo(cliente, conta) == 10_000


def test_deposito_negativo_recusado(cliente):
    conta = abrir(cliente, "Ana Souza", CPF_ANA)
    r = cliente.post(f"/contas/{conta}/depositos", json={"valor_centavos": -500})
    assert r.status_code == 422


def test_pix_move_dinheiro(cliente):
    ana = abrir(cliente, "Ana Souza", CPF_ANA, deposito=10_000)
    bruno = abrir(cliente, "Bruno Lima", CPF_BRUNO, chave="bruno@email.com")
    r = pix(cliente, ana, "bruno@email.com", 2_550)
    assert r.status_code == 201
    assert saldo(cliente, ana) == 7_450
    assert saldo(cliente, bruno) == 2_550


def test_pix_sem_saldo_nao_mexe_em_nada(cliente):
    ana = abrir(cliente, "Ana Souza", CPF_ANA, deposito=1_000)
    bruno = abrir(cliente, "Bruno Lima", CPF_BRUNO, chave="bruno@email.com")
    r = pix(cliente, ana, "bruno@email.com", 5_000)
    assert r.status_code == 422
    assert saldo(cliente, ana) == 1_000
    assert saldo(cliente, bruno) == 0


def test_pix_repetido_nao_cobra_duas_vezes(cliente):
    ana = abrir(cliente, "Ana Souza", CPF_ANA, deposito=10_000)
    abrir(cliente, "Bruno Lima", CPF_BRUNO, chave="bruno@email.com")
    primeira = pix(cliente, ana, "bruno@email.com", 3_000, idem="mesma-chave-123")
    segunda = pix(cliente, ana, "bruno@email.com", 3_000, idem="mesma-chave-123")
    assert primeira.status_code == 201
    assert segunda.status_code == 200
    assert primeira.json()["id"] == segunda.json()["id"]
    assert saldo(cliente, ana) == 7_000


def test_chave_de_idempotencia_reusada_com_outro_valor(cliente):
    ana = abrir(cliente, "Ana Souza", CPF_ANA, deposito=10_000)
    abrir(cliente, "Bruno Lima", CPF_BRUNO, chave="bruno@email.com")
    pix(cliente, ana, "bruno@email.com", 3_000, idem="mesma-chave-123")
    r = pix(cliente, ana, "bruno@email.com", 9_000, idem="mesma-chave-123")
    assert r.status_code == 409
    assert saldo(cliente, ana) == 7_000


def test_pix_para_si_mesmo_e_chave_inexistente(cliente):
    ana = abrir(cliente, "Ana Souza", CPF_ANA, chave="ana@email.com", deposito=10_000)
    assert pix(cliente, ana, "ana@email.com", 100).status_code == 422
    assert pix(cliente, ana, "ninguem@email.com", 100, idem="outra-chave-1").status_code == 404


def test_chave_pix_duplicada(cliente):
    abrir(cliente, "Ana Souza", CPF_ANA, chave="mesma@email.com")
    bruno = abrir(cliente, "Bruno Lima", CPF_BRUNO)
    r = cliente.put(f"/contas/{bruno}/chave-pix", json={"chave": "mesma@email.com"})
    assert r.status_code == 409


def test_extrato_mostra_mais_recente_primeiro(cliente):
    ana = abrir(cliente, "Ana Souza", CPF_ANA, deposito=10_000)
    abrir(cliente, "Bruno Lima", CPF_BRUNO, chave="bruno@email.com")
    pix(cliente, ana, "bruno@email.com", 1_000)
    itens = cliente.get(f"/contas/{ana}/extrato").json()
    assert [i["tipo"] for i in itens] == ["pix", "deposito"]


def test_conta_inexistente(cliente):
    assert cliente.get("/contas/999").status_code == 404
