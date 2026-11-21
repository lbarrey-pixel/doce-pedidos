# Checkout gateway contract

What the `app/adaptadores/gateway_checkout.py` adapter expects from the gateway. The contract
tests (`backend/tests/contrato/test_gateway_checkout.py`) lock this format with `respx`; switching
provider means writing another adapter that fulfils the `GatewayDePagamento` port.

Authentication: `Authorization: Bearer <GATEWAY_API_KEY>` on every call. Timeout of 8 s.
Any failure (network, timeout, a status outside 2xx, a body that is not a JSON object) becomes
`GatewayIndisponivel`, with neither the key nor the body in the message.

## Create link: `POST {GATEWAY_API_URL}/links`

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

Response: an object with `url` (or `link`) starting with `https://`. A single item with the total
avoids a rounding difference. No personal data of the customer is sent.

- `redirect_url` comes from `CORS_ORIGENS`: it uses the request's origin if that origin is on the
  list and, otherwise, the first on the list. Without `CORS_ORIGENS`, the field is omitted.
- `webhook` comes from `API_URL_PUBLICA`: without it, the field is omitted and the link goes out
  without a notice (the customer still confirms on return and the operator through "Conferir
  pagamento" (Check payment)).

## Check payment: `POST {GATEWAY_API_URL}/payments/check`

```json
{ "order_nsu": "<id do pedido>", "transaction_nsu": "<nsu>", "slug": "<slug>" }
```

Response:

| Field | Type | Meaning |
| --- | --- | --- |
| `success` | bool | the query found the transaction |
| `paid` | bool | the transaction was paid |
| `amount` | integer, cents | amount charged by the link |
| `paid_amount` | integer, cents | amount paid (with installment interest, if any) |
| `installments` | integer | installments (minimum 1) |
| `capture_method` | text | `pix` or `credit_card` |

When `success` or `paid` is false, that is a valid response (not paid). A value that is not an
integer becomes 0 and never confirms anything.

## Notice: `POST /api/v1/gateway/checkout/aviso?c=<codigo>` (on this API)

The body from the gateway is used only to read `order_nsu`, `transaction_nsu` and
`invoice_slug`. The `c` code is `HMAC-SHA256(GATEWAY_AVISO_CODIGO, id do pedido)` truncated to
32 characters. The route also responds 200 for a repeated notice, an unconfirmed one, or one for
an order that does not exist (this last one is only recorded), so the gateway does not resend
endlessly; a body outside the format or a wrong code receives 400, without querying the gateway.

## Customer return

The customer returns to `redirect_url` with `?transaction_nsu=...&slug=...`. The store calls
`POST /api/v1/loja/pedidos/{id}/conferir` with those two values, which goes through the same
check as the notice.
