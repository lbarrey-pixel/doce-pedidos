# 0005. Stock reservation and expiry calculated on read, without a scheduler

## Context

When the customer places the order, the units stay reserved until the Pix (Brazil's instant
payment system) is confirmed. If the customer gives up, the reservation has to return to stock.
The same goes for thawing, which finishes on its own after a time limit. The chosen hosting
sleeps when idle and does not guarantee cron.

## Decision

An order awaiting payment stores `expira_em`. Every route that reads or writes stock or orders
calls `liberar_expirados` first: expired orders become cancelled and the units set aside return
to pronta entrega (ready to sell now), in movements recorded in the same transaction. Thawing follows
the same idea: `atualizar_descongelamentos` records the endings that have expired when stock
is read. Both operations are idempotent and use `FOR UPDATE SKIP LOCKED` when there is
concurrency.

If the money comes in after the deadline, the operator can still confirm the payment: if a unit
is available, it is set aside again; if not, the API responds 409 with the instruction to offer
an Encomenda (pre-order for a future date) or to return the Pix.

## Consequences

- No background process to maintain, monitor or pay for.
- The "real" state only appears when someone looks: a report that reads straight from the
  database needs to apply the same expiry rule.
- The first request after an idle period pays the cost of releasing what has expired.
