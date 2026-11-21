# 0003. Stock as a movement ledger

## Context

Stock has to match the physical count, and every difference needs an explanation: production, a
sale, a loss, a sweet set aside for an order. A balance that can be edited directly hides that
history.

## Decision

No balance is changed by hand. Every effect is an immutable **movement** (type, quantity, origin
state and destination state, author, reason, time) and the balance of each variant is the sum of
the movements. For fast reads, the balance is materialised in the `saldo` table, updated in the
same transaction as the movement, with the row locked by `SELECT ... FOR UPDATE`;
`conferir_saldos` recalculates from the sum of the ledger and must return an empty list.

The states are `pronta`, `separada`, `congelada`, `descongelando` and `reserva`, and each variant
has a control type (`congelavel`, `reserva`, `simples`) that defines which states and which
movements make sense. Validation lives in the domain (`dominio/estoque.py`); the database
reinforces it with `CHECK (... >= 0)` and with permissions: the API role only inserts and reads
in `movimento`.

## Consequences

- A correction is always an adjustment movement with a reason, never an edit.
- Two orders competing for the last unit are settled by the row lock: one sets it aside, the
  other gets an out-of-stock result (there is a concurrency test with threads).
- The materialised balance is a redundancy to watch; that is why the check exists.
