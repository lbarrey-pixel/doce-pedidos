# doce-pedidos

Ordering, stock and billing application for an artisan confectionery ("Doce Ateliê", a fictional
name). The customer builds the order on their phone, sees the delivery fee calculated from street
distance and pays by card or Pix (Brazil's instant payment system) on a checkout page (or with a
Pix copy-and-paste code); whoever operates the store follows the order through to delivery,
resolves pending payments and controls stock in a panel.

> Portfolio version. This is a portfolio sample of a system running in production for a client;
> brand and data here are fictional, and the full production code is private by contract.

## Why it exists

A small confectionery sold through messages and kept stock from memory. The problems were
concrete: selling what had already run out, losing track of who had paid and who had not,
calculating the delivery fee by eye, and not knowing what to produce for the next day's
pre-orders. The project solves this with a few well-tested rules: stock as a movement ledger, a
reservation per order with expiry, a fee by distance band, and Pix for the exact amount.

## What it does

- **Store (no account):** menu by category, ready now or pre-order, delivery or pickup,
  scheduling a time, a delivery quote by CEP (Brazilian postal code), recognition of someone who
  has ordered before (masked address), payment by link (card in up to 12 installments and Pix)
  or Pix copy-and-paste with a QR code, order tracking and the store's WhatsApp button.
- **Panel (with login):** new orders highlighted, manual Pix confirmation only for the exact
  amount, a payment check on the gateway, payments to check and pending refunds, a sale entered
  in the panel with a link to send by WhatsApp, summaries by payment method with an estimated
  fee, configurable tariffs, state changes (preparation, out with a courier, delivered, cancelled
  with a return), the day's production and an alert for tomorrow's pre-orders, stock by variant
  with entries (production, loss, adjustment, freeze, thaw, transfer).

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy Core (`text()`), Alembic, psycopg 3, httpx, PyJWT |
| Database | PostgreSQL 16, schema `doce`, roles `doce_api` (fine-grained permissions) and `doce_backup` (read-only) |
| Frontend | React 18, Vite, strict TypeScript, PWA (`vite-plugin-pwa`) |
| Tests | pytest (domain, contract with `respx`, integration with real Postgres), Vitest + Testing Library |
| CI | GitHub Actions: ruff, pytest with Postgres, tsc, eslint, prettier, vitest, build |

## How to run

With Docker (Postgres + API, already with migrations and demo data):

```bash
docker compose up --build            # API em http://localhost:8000
docker compose exec api python -m scripts.token_dev   # imprime um JWT de desenvolvimento

cd frontend
npm ci
echo "VITE_DEV_TOKEN=<cole o token aqui>" > .env.local
npm run dev                          # loja em http://localhost:5173, painel em /painel
```

The store works without a token. The panel uses the token in place of login (**panel without
Supabase**); in production, authentication is Supabase Auth: set `SUPABASE_URL` on the backend
and `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` on the frontend. The local map uses a
fake router (`ROTEADOR=fake`: the CEP `12345-678` is 5 km away); without that it uses BrasilAPI
and Google Maps (`GOOGLE_MAPS_API_KEY`). Details are in `backend/.env.example` and
`frontend/.env.example`.

Without Docker, with any Postgres 16:

```bash
cd backend
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # ajuste as URLs do banco
export $(grep -v '^#' .env | xargs)
alembic upgrade head && python -m scripts.preparar_banco && python -m scripts.seed
uvicorn app.main:app_de_producao --factory --reload
```

## Online payment

The payment link is created by a checkout gateway behind a port (ADR 0006). The server never
trusts the body of the notice: it checks the payment with the gateway before applying it. Without
a gateway, or if it fails, the order falls back to Pix copy-and-paste.

| Variable (backend) | Purpose |
| --- | --- |
| `GATEWAY_API_URL`, `GATEWAY_API_KEY` | Turn on the real gateway (contract in `docs/contracts/gateway-checkout.md`) |
| `GATEWAY_AVISO_CODIGO` | Secret for the `?c=` code on the notice URL (`POST /gateway/checkout/aviso`). Required with the real gateway and different from the API key: without it the API does not start |
| `API_URL_PUBLICA` | Public URL of the API; without it the link goes out without a webhook |
| `GATEWAY=simulado` | Local simulator, with no account at any gateway. The API refuses to start with it when `SUPABASE_URL` is set (a sign of a real environment) |

With `GATEWAY=simulado` (already on in `docker compose`) the customer's checkout goes to the
frontend page `/simulador/<pedido>`, which "pays" by card or by Pix and returns to the order; the
route `/gateway/simulado/pagar` exists only in this mode and never in a real environment. The
uvicorn access log does not record the notice's `?c=`. The tariffs (card 4.20%, Pix 0%) are under
"Configuração" (Settings) in the panel.

## Tests

```bash
cd backend
pytest                                # integração é pulada sem TEST_ADMIN_DATABASE_URL
TEST_ADMIN_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres pytest
ruff check . && ruff format --check .

cd ../frontend
npx tsc --noEmit && npx eslint . && npx prettier --check . && npx vitest run && npx vite build
```

The integration tests create a new database, run `alembic upgrade head` as the schema owner and
exercise the API connected as `doce_api`, the same role as in production.

## Structure

| Path | What it contains |
| --- | --- |
| `backend/app/dominio/` | Pure rules: money, stock, order, delivery, hours, Pix, customer, catalogue, pre-order |
| `backend/app/portas/` | Contracts (`Protocol`) for the router, Pix and the payment gateway |
| `backend/app/adaptadores/` | Manual Pix, the checkout gateway and the simulator, the Google router and the fake one, SQL repositories |
| `backend/app/api/` | Store and panel routes, authentication, error format |
| `backend/migrations/` | Alembic applying plain SQL from `migrations/sql/` |
| `backend/dados/cardapio.csv` | Fictional menu loaded by the seed |
| `backend/scripts/` | Seed, API-role password, development token |
| `frontend/src/loja/` | Customer app: menu, checkout, payment |
| `frontend/src/painel/` | Panel: orders, sales, production, stock, summaries, configuration, access |
| `frontend/src/comum/` | API, money, routes, PWA update |
| `docs/adr/` | Architecture decisions |
| `docs/contracts/` | Checkout gateway contract |

## Decisions

1. [Installable site (PWA)](docs/adr/0001-installable-site.md)
2. [Pure domain and ports](docs/adr/0002-isolated-domain-and-ports.md)
3. [Stock as a movement ledger](docs/adr/0003-stock-as-a-movement-ledger.md)
4. [Local Pix copy-and-paste](docs/adr/0004-local-pix-copy-and-paste.md)
5. [Reservation and expiry without a scheduler](docs/adr/0005-reservation-and-expiry-without-a-scheduler.md)
6. [Checkout gateway behind a port](docs/adr/0006-checkout-gateway-behind-a-port.md)
7. [Manual confirmation only with the exact amount](docs/adr/0007-manual-confirmation-without-a-difference.md)

Money is always an integer in cents, in the database, in the API and on screen.

## Known limitations

- Pix copy-and-paste stays manual: the operator checks the statement and confirms in the panel.
- A refund of an online payment is done in the gateway's panel; the system only notifies and
  records.
- Outside this version: tax-document issuance, sales channels beyond the app and the counter, a
  sound alert for a new order, and a history of configuration changes.
- Store configuration covers only the tariffs; the rest stays in the `configuracao_loja` table
  and the menu comes in by CSV.
- The brand and the PWA icons are provisional (`frontend/scripts/gerar-icones.py`).

## English

**doce-pedidos** is an ordering, stock and Pix-payment app for a small artisan confectionery
("Doce Ateliê", a fictional name). Customers build an order on their phone, see a delivery fee
computed from street distance and pay by card or Pix on a hosted checkout page (or with a Pix
copy-and-paste code); staff follow the order to delivery, resolve pending payments and manage
stock in a back-office panel.

> Portfolio version. The system runs in production for a client; brand and data are fictional
> here, and the production code is private by contract.

- **Stack:** Python 3.12 / FastAPI / SQLAlchemy Core / Alembic / psycopg 3 on PostgreSQL 16;
  React 18 + Vite + strict TypeScript as an installable PWA; pytest (domain, contract, real
  Postgres integration), Vitest + Testing Library; GitHub Actions CI.
- **Design:** pure domain layer (money in integer cents, stock, order, delivery fee, opening
  hours, Pix BR Code) behind `Protocol` ports; stock as an immutable movement ledger with a
  materialised balance locked per row; reservations that expire lazily on read (no scheduler);
  fine-grained database grants (`doce_api` can only insert/read the ledger).
- **Online payment:** a checkout gateway behind a `GatewayDePagamento` port (HTTP adapter plus a
  local simulator, `GATEWAY=simulado`). The webhook is unsigned, so each link carries an HMAC
  code and the server never trusts the body: it always re-checks the payment with the gateway
  (pure `decidir` function, unique-NSU index and row lock for idempotency). Late payments,
  wrong amounts and out-of-stock payments become pending items for the operator; refunds are
  done in the gateway's own dashboard. Falls back to manual Pix when the gateway is absent or
  down. Left out of this version: tax documents, extra sales channels, new-order sound and
  config history.
- **Run:** `docker compose up --build`, then `docker compose exec api python -m scripts.token_dev`,
  put the token in `frontend/.env.local` as `VITE_DEV_TOKEN`, and `npm ci && npm run dev` in
  `frontend/`. Production auth is Supabase Auth; locally a plain HS256 `JWT_SECRET` works.
- **Test:** `pytest` in `backend/` (integration tests need `TEST_ADMIN_DATABASE_URL`) and
  `npx vitest run` in `frontend/`.
- **Not included:** tax documents, iFood/WhatsApp/Instagram sales channels, a new-order sound,
  a configuration change history and a catalogue admin; the menu is loaded from
  `backend/dados/cardapio.csv`.
