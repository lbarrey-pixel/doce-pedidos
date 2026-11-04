# 0002. Domínio em Python puro, integrações atrás de portas

## Contexto

As regras que mais custam errar são dinheiro, estoque, taxa de entrega e horário. Elas não podem
depender de FastAPI, do banco nem de serviços externos, senão cada teste vira um teste de
integração lento e frágil.

## Decisão

As regras ficam em `backend/app/dominio/`, sem importar framework, banco ou rede, e são testadas
pela interface pública. Tudo que fala com o mundo de fora entra por uma porta (`typing.Protocol`
em `app/portas/`) e tem um ou mais adaptadores em `app/adaptadores/`:

| Porta | Adaptadores |
| --- | --- |
| `Roteador` (CEP, coordenadas, distância de rua) | `roteador_google` (BrasilAPI + Google Maps), `roteador_fake` |
| `ProvedorDePagamento` | `pix_manual` |

A API recebe os adaptadores em `criar_app(...)`; os testes injetam os falsos. A persistência usa
SQLAlchemy Core com SQL explícito (`repositorio_sql`, `repositorio_pedidos`), sempre recebendo a
conexão de quem chama, de modo que uma operação composta cabe em uma única transação.

## Consequências

- Testes de domínio rodam em milissegundos, sem Postgres.
- Trocar o provedor de mapa ou de pagamento é escrever um adaptador novo.
- Um pouco mais de cerimônia: cada integração precisa de Protocol, adaptador real e falso.
