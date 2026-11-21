# 0006. Checkout gateway behind a port, with the check on the server

## Context

Pix (Brazil's instant payment system) copy-and-paste (ADR 0004) depends on someone looking at the
statement. The store wanted to accept card and Pix with automatic confirmation, without storing
card data and without tying the domain to one provider. The chosen gateway hosts the payment page
(checkout) and notifies by webhook, but the notice is not signed: anyone who discovers the URL
can post an arbitrary body.

## Decision

1. **`GatewayDePagamento` port** (`portas/pagamento.py`) with three operations: `criar_link`,
   `conferir` and `codigo_do_aviso`. The HTTP adapter (`gateway_checkout.py`) and the simulator
   (`gateway_simulado.py`) implement it; the domain and the routes know only the port. The HTTP
   contract is in [`docs/contracts/gateway-checkout.md`](../contracts/gateway-checkout.md).
2. **The body of the notice is never trusted.** The route `POST /gateway/checkout/aviso` uses
   only the transaction identifier from it and calls `conferir` on the gateway. What decides is
   the check's response, applied by the pure function `decidir`
   (`dominio/pagamento_online.py`): a paid amount lower than the amount charged, a charged amount
   different from the order total, a Pix with an amount different from the amount charged, a
   transaction already recorded, a payment after expiry and a payment with no stock each have
   their own result.
3. **A code on the notice URL.** Since there is no signature, each link carries `?c=` with an
   HMAC of the order id (32 characters). A wrong code is answered without consulting the gateway.
4. **Idempotency in the database.** A partial unique index on `transaction_nsu` for the results
   that take effect, `SELECT ... FOR UPDATE` on the order and a savepoint around the record
   and the effects. A repeated notice, a concurrent notice and a manual check of the same payment
   do not confirm twice.
5. **A late payment does not lose money.** Paid after expiry, the order is reactivated if stock
   remains; if not, it becomes a refund pending item (`a_estornar` or `a_decidir`) for the
   operator. The refund is done in the gateway's panel; the system only notifies and records.
6. **Fallback.** With no gateway configured, or if it fails while creating the link, the order
   is created with Pix copy-and-paste. The API key never appears in a log, an error or `repr`.
7. **Amounts in cents and tariffs in basis points** (420 = 4.20%). The summary by payment method
   shows the estimated fee with the configured à vista tariff (paid in full, not in
   installments).

## Consequences

- Switching gateway means writing another adapter and the same contract suite; the domain does
  not change.
- Each notice costs one check call. That is the price of not trusting an unsigned body.
- With no scheduler, the expired link is handled when the order or the stock is read (ADR 0005).
- The simulator (`GATEWAY=simulado`) makes it possible to run the whole flow with no account at
  any gateway.
