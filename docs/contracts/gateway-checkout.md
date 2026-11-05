# Contrato do gateway de checkout

O que o adaptador `app/adaptadores/gateway_checkout.py` espera do gateway. Os testes de contrato
(`backend/tests/contrato/test_gateway_checkout.py`) fixam este formato com `respx`; trocar de
fornecedor é escrever outro adaptador que cumpra a porta `GatewayDePagamento`.

Autenticação: `Authorization: Bearer <GATEWAY_API_KEY>` em toda chamada. Tempo limite de 8 s.
Qualquer falha (rede, tempo, status fora de 2xx, corpo que não é JSON objeto) vira
`GatewayIndisponivel`, sem a chave nem o corpo na mensagem.

## Criar link: `POST {GATEWAY_API_URL}/links`

```json
{
  "order_nsu": "<id do pedido>",
  "items": [{ "quantity": 1, "price": 5380, "description": "Pedido nº 42 · Doce Ateliê" }],
  "redirect_url": "https://doceatelie.example/pedido/<id>",
  "webhook": {
    "url": "https://api.doceatelie.example/api/v1/gateway/checkout/aviso?c=<codigo>",
    "events": ["paid", "canceled", "refunded"]
  },
  "options": {
    "single_payment": true,
    "valid_until": "2026-11-02T18:30:00-03:00",
    "payment_methods_enabled": ["credit_card", "pix"],
    "assured_installments": 0
  }
}
```

Resposta: objeto com `url` (ou `link`) começando em `https://`. Um item só com o total evita
diferença de arredondamento. Nenhum dado pessoal do cliente é enviado.

- `redirect_url` vem de `CORS_ORIGENS`: usa a origem da requisição se ela estiver na lista e,
  senão, a primeira da lista. Sem `CORS_ORIGENS`, o campo é omitido.
- `webhook` vem de `API_URL_PUBLICA`: sem ela, o campo é omitido e o link sai sem aviso (o
  cliente ainda confirma pela volta e o operador por "Conferir pagamento").

## Conferir pagamento: `POST {GATEWAY_API_URL}/payments/check`

```json
{ "order_nsu": "<id do pedido>", "transaction_nsu": "<nsu>", "slug": "<slug>" }
```

Resposta:

| Campo | Tipo | Significado |
| --- | --- | --- |
| `success` | bool | a consulta achou a transação |
| `paid` | bool | a transação foi paga |
| `amount` | inteiro, centavos | valor cobrado pelo link |
| `paid_amount` | inteiro, centavos | valor pago (com juros do parcelamento, se houver) |
| `installments` | inteiro | parcelas (mínimo 1) |
| `capture_method` | texto | `pix` ou `credit_card` |

`success` ou `paid` falsos são resposta válida (não pago). Valor que não seja inteiro vira 0 e
nunca confirma nada.

## Aviso: `POST /api/v1/gateway/checkout/aviso?c=<codigo>` (nesta API)

Corpo do gateway, usado só para ler `order_nsu`, `transaction_nsu` e `invoice_slug`. O código `c` é
`HMAC-SHA256(GATEWAY_AVISO_CODIGO, id do pedido)` cortado em 32 caracteres. Responde 200 também
para aviso repetido, não confirmado ou de pedido que não existe (este só fica registrado), para o
gateway não reenviar sem fim; corpo fora do formato ou código errado recebem 400, sem consultar o
gateway.

## Volta do cliente

O cliente volta para `redirect_url` com `?transaction_nsu=...&slug=...`. A loja chama
`POST /api/v1/loja/pedidos/{id}/conferir` com esses dois valores, que passa pela mesma
conferência do aviso.
