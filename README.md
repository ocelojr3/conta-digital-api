# Conta Digital API

API simples de uma conta digital: abrir conta, depositar, cadastrar chave Pix, fazer Pix e ver o extrato.

Fiz este projeto para estudar como um banco protege o saldo do cliente. O foco não é ter muitas telas. O foco é o dinheiro nunca sumir, nunca duplicar e nunca ficar negativo.

## O problema

Um Pix parece simples: tira de uma conta e põe na outra. Na prática aparecem quatro riscos:

1. **Pix em dobro.** A internet do cliente cai, o app tenta de novo e o dinheiro sai duas vezes.
2. **Dois Pix ao mesmo tempo.** Duas transferências usam o mesmo saldo e a conta fica negativa.
3. **Erro de centavo.** Número com vírgula no computador arredonda errado (0,1 + 0,2 vira 0,30000000000000004).
4. **Dado pessoal exposto.** A API devolve o CPF completo para quem não deveria ver.

## Como resolvi cada um

| Risco | Solução | Onde está |
|---|---|---|
| Pix em dobro | Cada Pix leva uma **chave de idempotência** (cabeçalho `Idempotency-Key`). Se a mesma chave chegar de novo, a API devolve o Pix que já foi feito, sem cobrar outra vez. | `app/services.py`, `fazer_pix` |
| Dois Pix ao mesmo tempo | As duas contas são **travadas no banco** (`SELECT ... FOR UPDATE`) durante a transferência, sempre na mesma ordem para não haver travamento mútuo. O banco também tem uma regra que proíbe saldo negativo. | `app/services.py`, `app/models.py` |
| Erro de centavo | Todo valor é guardado em **centavos, como número inteiro**. R$ 25,50 vira `2550`. | `app/models.py` |
| Dado exposto | O CPF é validado pelos dígitos verificadores e **sempre sai mascarado** (`***.982.247-**`), seguindo a LGPD. | `app/schemas.py` |

## Tecnologias

- **Python 3.11** e **FastAPI** para a API
- **PostgreSQL** como banco (SQLite para rodar e testar sem instalar nada)
- **SQLAlchemy 2** para conversar com o banco
- **Pytest** com 13 testes automatizados
- **Docker** e **Docker Compose** para subir tudo com um comando

## Como rodar

Com Docker (sobe a API e o PostgreSQL juntos):

```bash
docker compose up --build
```

Sem Docker:

```bash
python -m venv .venv
.venv\Scripts\activate        # no Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Depois abra http://localhost:8000/docs. O FastAPI gera uma página onde dá para testar cada rota pelo navegador.

## Rotas

| Método | Rota | O que faz |
|---|---|---|
| POST | `/contas` | Abre conta com nome e CPF |
| GET | `/contas/{id}` | Mostra titular, CPF mascarado e saldo |
| PUT | `/contas/{id}/chave-pix` | Cadastra a chave Pix da conta |
| POST | `/contas/{id}/depositos` | Deposita um valor em centavos |
| POST | `/pix` | Faz um Pix (exige o cabeçalho `Idempotency-Key`) |
| GET | `/contas/{id}/extrato` | Lista as transações, da mais recente para a mais antiga |

Exemplo de Pix:

```bash
curl -X POST http://localhost:8000/pix \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: pix-2026-11-05-0001" \
  -d '{"conta_origem_id": 1, "chave_destino": "bruno@email.com", "valor_centavos": 2550}'
```

## Testes

```bash
pytest -q
```

Os testes cobrem: CPF válido e inválido, conta duplicada, depósito, Pix com e sem saldo, Pix repetido com a mesma chave, chave reaproveitada com outro valor, Pix para a própria conta, chave Pix duplicada, extrato e conta inexistente.

## Próximos passos

- Publicar na nuvem com pipeline automático de testes e deploy (CI/CD)
- Autenticação, para cada cliente só ver a própria conta
- Teste de carga com vários Pix simultâneos no PostgreSQL
