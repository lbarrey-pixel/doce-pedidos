# 0004. Locally generated Pix "copy and paste", confirmed by the operator

## Context

The customer pays by Pix (Brazil's instant payment system) and, for now, the store does not want
to hire a payment provider or pay a fee per transaction.

## Decision

The backend builds the static Pix BR Code (`dominio/pix.py`), the copy-and-paste payload, with
the store's key, the exact amount of the order and a `txid` derived from the order number,
following the Central Bank of Brazil manual (TLV fields and CRC-16/CCITT-FALSE over the payload
ending in `6304`; the tests check the manual's examples). The customer copies the code or reads
the QR code and pays; whoever operates the store confirms receipt in the panel, entering the
amount that came in. An amount different from the one charged is refused (ADR 0007).

The generator sits behind the `ProvedorDePagamento` port (ADR 0002), with the `pix_manual`
adapter.

## Consequences

- Zero cost and no new integration account.
- No automatic confirmation: it depends on someone looking at the statement. Online payment with
  automatic confirmation came later, as another port (ADR 0006), without changing the domain.
- With no Pix key registered in the store configuration, the order is not created (503) and the
  stock set-aside is undone in the same transaction.
