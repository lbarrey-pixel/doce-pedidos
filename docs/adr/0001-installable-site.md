# 0001. Installable site (PWA) instead of an app in the app stores

## Context

The store needs a screen for the customer to order and a panel for whoever operates it. The
audience uses a phone almost exclusively, and the team is too small to maintain two native applications,
developer accounts and the app stores' review cycle.

## Decision

A single responsive site in React + Vite, installable as a PWA (`vite-plugin-pwa`). The service
worker stores the application and the icons; calls to the API never go into the cache, so that
price and stock always come from the server. The store is public and has no account. The panel
loads on demand (`lazy`), so the customer downloads neither the operator's code nor the Supabase
Auth client.

## Consequences

- One codebase for customer and operator, immediate publishing, no store fee.
- No presence in the app stores, and limited notification on iPhone. The order notice goes out
  by WhatsApp message, which does not depend on push.
- A new version going live reloads the app on its own, except in the middle of the cart, a
  payment or a password change (`comum/atualizacao.ts`).
