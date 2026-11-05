# doce-pedidos

Aplicação de pedidos, estoque e cobrança para uma confeitaria artesanal ("Doce Ateliê", nome
fictício). O cliente monta o pedido pelo celular, vê a taxa de entrega calculada pela distância de
rua e paga com cartão ou Pix numa página de checkout (ou com Pix copia e cola); quem opera a loja
acompanha o pedido até a entrega, resolve pagamentos pendentes e controla o estoque num painel.

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
  mascarado), pagamento por link (cartão em até 12x e Pix) ou Pix copia e cola com QR,
  acompanhamento do pedido e botão de WhatsApp da loja.
- **Painel (com login):** pedidos novos em destaque, confirmação do Pix manual só com o valor
  exato, conferência do pagamento no gateway, pagamentos a conferir e estornos pendentes, venda
  lançada no painel com link para mandar por WhatsApp, resumos por forma de pagamento com taxa
  estimada, tarifas configuráveis, mudança de estado (preparo, saída com entregador, entregue, cancelado com devolução), produção
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

## Pagamento online

O link de pagamento é criado por um gateway de checkout atrás de uma porta (ADR 0006). O servidor
nunca confia no corpo do aviso: confere o pagamento no gateway antes de efetivar. Sem gateway, ou
se ele falhar, o pedido cai no Pix copia e cola.

| Variável (backend) | Para quê |
| --- | --- |
| `GATEWAY_API_URL`, `GATEWAY_API_KEY` | Ligam o gateway real (contrato em `docs/contracts/gateway-checkout.md`) |
| `GATEWAY_AVISO_CODIGO` | Segredo do código `?c=` da URL do aviso (`POST /gateway/checkout/aviso`). Obrigatório com o gateway real e diferente da chave da API: sem ele a API não sobe |
| `API_URL_PUBLICA` | URL pública da API; sem ela o link sai sem webhook |
| `GATEWAY=simulado` | Simulador local, sem conta em gateway nenhum. A API se recusa a subir com ele quando `SUPABASE_URL` está definido (sinal de ambiente real) |

Com `GATEWAY=simulado` (já ligado no `docker compose`) o checkout do cliente leva à página
`/simulador/<pedido>` do frontend, que "paga" no cartão ou no Pix e volta para o pedido; a rota
`/gateway/simulado/pagar` só existe nesse modo e nunca em ambiente real. O access log do uvicorn
não registra o `?c=` do aviso. As tarifas (cartão 4,20%, Pix 0%) ficam em
"Configuração" no painel.

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
| `backend/app/portas/` | Contratos (`Protocol`) de roteador, Pix e gateway de pagamento |
| `backend/app/adaptadores/` | Pix manual, gateway de checkout e simulado, roteador Google e falso, repositórios SQL |
| `backend/app/api/` | Rotas da loja e do painel, autenticação, formato de erro |
| `backend/migrations/` | Alembic aplicando SQL puro de `migrations/sql/` |
| `backend/dados/cardapio.csv` | Cardápio fictício carregado pelo seed |
| `backend/scripts/` | Seed, senha do papel da API, token de desenvolvimento |
| `frontend/src/loja/` | App do cliente: cardápio, checkout, pagamento |
| `frontend/src/painel/` | Painel: pedidos, vendas, produção, estoque, resumos, configuração, acesso |
| `frontend/src/comum/` | API, dinheiro, rotas, atualização do PWA |
| `docs/adr/` | Decisões de arquitetura |
| `docs/contracts/` | Contrato do gateway de checkout |

## Decisões

1. [Site instalável (PWA)](docs/adr/0001-site-instalavel.md)
2. [Domínio puro e portas](docs/adr/0002-dominio-isolado-e-portas.md)
3. [Estoque como livro de movimentos](docs/adr/0003-estoque-como-livro-de-movimentos.md)
4. [Pix copia e cola local](docs/adr/0004-pix-copia-e-cola-local.md)
5. [Reserva e expiração sem agendador](docs/adr/0005-reserva-e-expiracao-sem-agendador.md)
6. [Gateway de checkout atrás de uma porta](docs/adr/0006-gateway-de-checkout-atras-de-porta.md)
7. [Confirmação manual só com o valor exato](docs/adr/0007-confirmacao-manual-sem-diferenca.md)

Dinheiro é sempre inteiro em centavos, no banco, na API e na tela.

## Limitações conhecidas

- O Pix copia e cola continua manual: o operador confere o extrato e confirma no painel.
- Estorno de pagamento online é feito no painel do gateway; o sistema só avisa e registra.
- Fora desta versão: emissão fiscal, canais de venda além do app e do balcão, aviso sonoro de
  pedido novo e histórico de alterações da configuração.
- Configuração da loja só para as tarifas; o restante fica na tabela `configuracao_loja` e o
  cardápio entra por CSV.
- A marca e os ícones do PWA são provisórios (`frontend/scripts/gerar-icones.py`).

## English

**doce-pedidos** is an ordering, stock and Pix-payment app for a small artisan bakery ("Doce
Ateliê", a fictional name). Customers build an order on their phone, see a delivery fee computed
from street distance and pay by card or Pix on a hosted checkout page (or with a Pix
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
