# doce-pedidos

Aplicação de pedidos, estoque e cobrança por Pix para uma confeitaria artesanal ("Doce Ateliê",
nome fictício). O cliente monta o pedido pelo celular, vê a taxa de entrega calculada pela
distância de rua e paga com Pix copia e cola; quem opera a loja confirma o pagamento, acompanha o
pedido até a entrega e controla o estoque num painel.

> Versão de portfólio. O sistema roda em produção para um cliente; aqui marca e dados são
> fictícios, e o código em produção é privado por contrato.

## Por que existe

Uma confeitaria pequena vendia por mensagem e controlava estoque de cabeça. Os problemas eram
concretos: vender o que já tinha acabado, perder o fio de quem pagou e quem não pagou, calcular
taxa de entrega no olho e não saber o que produzir para as encomendas do dia seguinte. O projeto
resolve isso com poucas regras bem testadas: estoque como livro de movimentos, reserva por pedido
com expiração, taxa por faixa de distância e Pix com valor exato.

## O que faz

- **Loja (sem conta):** cardápio por categoria, pronta entrega ou encomenda, entrega ou retirada,
  agendamento de horário, cotação de entrega por CEP, reconhecimento de quem já pediu (endereço
  mascarado), Pix copia e cola com QR, acompanhamento do pedido e botão de WhatsApp da loja.
- **Painel (com login):** pedidos novos em destaque, confirmação do Pix com conferência de valor,
  mudança de estado (preparo, saída com entregador, entregue, cancelado com devolução), produção
  do dia e alerta de encomendas de amanhã, estoque por variante com lançamentos (produção, perda,
  ajuste, congelar, descongelar, transferir).

## Stack

| Camada | Tecnologia |
| --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy Core (`text()`), Alembic, psycopg 3, httpx, PyJWT |
| Banco | PostgreSQL 16, schema `doce`, papéis `doce_api` (permissões finas) e `doce_backup` (só leitura) |
| Frontend | React 18, Vite, TypeScript estrito, PWA (`vite-plugin-pwa`) |
| Testes | pytest (domínio, contrato com `respx`, integração com Postgres real), Vitest + Testing Library |
| CI | GitHub Actions: ruff, pytest com Postgres, tsc, eslint, prettier, vitest, build |

## Como rodar

Com Docker (Postgres + API, já com migrations e dados de demonstração):

```bash
docker compose up --build            # API em http://localhost:8000
docker compose exec api python -m scripts.token_dev   # imprime um JWT de desenvolvimento

cd frontend
npm ci
echo "VITE_DEV_TOKEN=<cole o token aqui>" > .env.local
npm run dev                          # loja em http://localhost:5173, painel em /painel
```

A loja funciona sem token. O painel usa o token no lugar do login (**painel sem Supabase**);
em produção a autenticação é o Supabase Auth: defina `SUPABASE_URL` no backend e
`VITE_SUPABASE_URL` e `VITE_SUPABASE_PUBLISHABLE_KEY` no frontend. O mapa local usa um
roteador falso (`ROTEADOR=fake`: o CEP `12345-678` fica a 5 km); sem isso usa BrasilAPI e Google
Maps (`GOOGLE_MAPS_API_KEY`). Detalhes em `backend/.env.example` e `frontend/.env.example`.

Sem Docker, com um Postgres 16 qualquer:

```bash
cd backend
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # ajuste as URLs do banco
export $(grep -v '^#' .env | xargs)
alembic upgrade head && python -m scripts.preparar_banco && python -m scripts.seed
uvicorn app.main:app_de_producao --factory --reload
```

## Testes

```bash
cd backend
pytest                                # integração é pulada sem TEST_ADMIN_DATABASE_URL
TEST_ADMIN_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres pytest
ruff check . && ruff format --check .

cd ../frontend
npx tsc --noEmit && npx eslint . && npx prettier --check . && npx vitest run && npx vite build
```

Os testes de integração criam um banco novo, rodam `alembic upgrade head` como dono do schema e
exercitam a API conectada como `doce_api`, o mesmo papel de produção.

## Estrutura

| Caminho | O que tem |
| --- | --- |
| `backend/app/dominio/` | Regras puras: dinheiro, estoque, pedido, entrega, horário, Pix, cliente, catálogo, encomenda |
| `backend/app/portas/` | Contratos (`Protocol`) de roteador e pagamento |
| `backend/app/adaptadores/` | Pix manual, roteador Google e falso, repositórios SQL |
| `backend/app/api/` | Rotas da loja e do painel, autenticação, formato de erro |
| `backend/migrations/` | Alembic aplicando SQL puro de `migrations/sql/` |
| `backend/dados/cardapio.csv` | Cardápio fictício carregado pelo seed |
| `backend/scripts/` | Seed, senha do papel da API, token de desenvolvimento |
| `frontend/src/loja/` | App do cliente: cardápio, checkout, pagamento |
| `frontend/src/painel/` | Painel: pedidos, produção, estoque, acesso |
| `frontend/src/comum/` | API, dinheiro, rotas, atualização do PWA |
| `docs/adr/` | Decisões de arquitetura |

## Decisões

1. [Site instalável (PWA)](docs/adr/0001-site-instalavel.md)
2. [Domínio puro e portas](docs/adr/0002-dominio-isolado-e-portas.md)
3. [Estoque como livro de movimentos](docs/adr/0003-estoque-como-livro-de-movimentos.md)
4. [Pix copia e cola local](docs/adr/0004-pix-copia-e-cola-local.md)
5. [Reserva e expiração sem agendador](docs/adr/0005-reserva-e-expiracao-sem-agendador.md)

Dinheiro é sempre inteiro em centavos, no banco, na API e na tela.

## Limitações conhecidas

- Sem confirmação automática de Pix: o operador confere o extrato e confirma no painel.
- Sem tela de configuração da loja nem de catálogo nesta versão: a configuração fica na tabela
  `configuracao_loja` e o cardápio entra por CSV.
- A marca e os ícones do PWA são provisórios (`frontend/scripts/gerar-icones.py`).

## English

**doce-pedidos** is an ordering, stock and Pix-payment app for a small artisan bakery ("Doce
Ateliê", a fictional name). Customers build an order on their phone, see a delivery fee computed
from street distance and pay with a Pix copy-and-paste code; staff confirm the payment, follow
the order to delivery and manage stock in a back-office panel.

> Portfolio version. The system runs in production for a client; brand and data are fictional
> here, and the production code is private by contract.

- **Stack:** Python 3.12 / FastAPI / SQLAlchemy Core / Alembic / psycopg 3 on PostgreSQL 16;
  React 18 + Vite + strict TypeScript as an installable PWA; pytest (domain, contract, real
  Postgres integration), Vitest + Testing Library; GitHub Actions CI.
- **Design:** pure domain layer (money in integer cents, stock, order, delivery fee, opening
  hours, Pix BR Code) behind `Protocol` ports; stock as an immutable movement ledger with a
  materialised balance locked per row; reservations that expire lazily on read (no scheduler);
  fine-grained database grants (`doce_api` can only insert/read the ledger).
- **Run:** `docker compose up --build`, then `docker compose exec api python -m scripts.token_dev`,
  put the token in `frontend/.env.local` as `VITE_DEV_TOKEN`, and `npm ci && npm run dev` in
  `frontend/`. Production auth is Supabase Auth; locally a plain HS256 `JWT_SECRET` works.
- **Test:** `pytest` in `backend/` (integration tests need `TEST_ADMIN_DATABASE_URL`) and
  `npx vitest run` in `frontend/`.
- **Not included:** payment-provider webhooks, a store-configuration screen and a catalogue
  admin; the menu is loaded from `backend/dados/cardapio.csv`.
