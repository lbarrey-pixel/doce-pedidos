# 0007. Manual confirmation only with the exact amount

## Context

ADR 0004 allowed confirming a manual Pix (Brazil's instant payment system) with a different
amount, accepting the difference explicitly. With online payment, the rule for the money became
stricter: what comes in has to equal what was charged, or it becomes a pending item for the
operator to resolve outside the flow.

## Decision

- Manual confirmation accepts only the exact amount of the order. A different amount is refused
  (409 `valor_divergente`) and does not change the order; the operator checks the statement and
  arranges the refund or the charge for the rest.
- An order that has a payment link is not confirmed by hand (409 `pagamento_pelo_gateway`): the
  operator uses "Conferir pagamento" (Check payment), which queries the gateway.
- The parameter for accepting a difference left the API and the screen.

## Consequences

- The total charged, the total paid and the summary by payment method never diverge silently.
- A Pix paid short or over needs a deliberate action by the operator, not a click.
