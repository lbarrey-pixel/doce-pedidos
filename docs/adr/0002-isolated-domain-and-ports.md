# 0002. Pure domain in Python, integrations behind ports

## Context

The rules that cost the most to get wrong are money, stock, the delivery fee and hours. They
cannot depend on FastAPI, the database or external services, or else every test becomes a slow,
fragile integration test.

## Decision

The rules live in `backend/app/dominio/`, importing no framework, database or network, and are
tested through the public interface. Everything that talks to the outside world comes in through
a port (`typing.Protocol` in `app/portas/`) and has one or more adapters in `app/adaptadores/`:

| Port | Adapters |
| --- | --- |
| `Roteador` (CEP [Brazilian postal code], coordinates, street distance) | `roteador_google` (BrasilAPI + Google Maps), `roteador_fake` |
| `ProvedorDePagamento` | `pix_manual` |

The API receives the adapters in `criar_app(...)`; the tests inject the fakes. Persistence uses
SQLAlchemy Core with explicit SQL (`repositorio_sql`, `repositorio_pedidos`), always receiving the
connection from the caller, so that a compound operation fits in a single transaction.

## Consequences

- Domain tests run in milliseconds, without Postgres.
- Replacing the map or payment provider means writing a new adapter.
- A little more ceremony: each integration needs a Protocol, a real adapter and a fake.
