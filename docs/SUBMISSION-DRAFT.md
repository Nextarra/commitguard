# CommitGuard

**Tagline:** An agent proposes. A person commits. Evidence closes the loop.

## The problem

Independent bicycle repair workshops make small, repeated supply purchases while handling repairs. An assistant can help turn a busy owner's request into a kit, but an uncertain checkout response creates a dangerous temptation: start over. The previous purchase may already have succeeded.

## The experience

CommitGuard builds an exact, reviewable kit from a bounded supplier catalog and budget. The buyer approves a fingerprint of the complete quote. PayPal payer approval is a separate step. Before capture, the server checks the seller, intent, item details, amount and currency against that immutable commitment.

If the response disappears, the app says **unknown**, preserves its request IDs, and blocks another capture or new same-session checkout. Recovery reads the original order and verifies a matching completed capture. A pending capture remains pending; a mismatch requires review. The trace and approval survive a server restart.

## Why AI and PayPal both matter

The structured AI adapter interprets a workshop brief, explains quantity assumptions and asks questions about unclear fit, stock or budget. It cannot set arbitrary prices, invoke payment tools or choose merchant endpoints. Deterministic policy owns payment boundaries. PayPal Orders provides order creation, payer approval, capture and the provider evidence required for recovery. Verified webhook notifications prompt a fresh order lookup rather than acting as payment authority themselves.

## What is implemented and tested now

A runnable Python/local-browser prototype, fictional catalog, deterministic labelled rehearsal planner, sandbox-only PayPal adapter, structured-model adapter, persisted state machine, fault replays and independent regression coverage. Desktop/mobile browser tests include the lost-response flow, hostile text rendering and accessibility checks.

**Important submission disclosure:** Three real structured-model requests succeeded and a real PayPal sandbox order was created. A USD 37 sandbox capture is verified; the combined flow recovered a deliberately discarded real sandbox capture response by original-order GET. Recovery fault evidence is simulated; adapter contract tests use mocked transport. Do not submit this draft unchanged as a completed integration.

## What makes it different

The demonstration focuses on a specific failure in agentic commerce: losing the outcome after a payment request. Exact-quote approval, durable uncertainty and evidence-based recovery form one coherent purchasing workflow for a bounded audience. The app prioritizes recoverable decisions over autonomous payment authority.

## Current limits and next work

USD and one fictional workshop supplier, per-quote fixture stock, no tax/fulfillment/refunds/real money, local browser sessions rather than production identities. No universal exactly-once claim. Next: authorized model and sandbox evidence, real workshop feedback, externally verified demo footage and separately authorized public source/video publication.

## Submission fields to fill after authorization

- Public repository URL: pending; MIT source included in package.
- Public YouTube demo under three minutes: pending; storyboard included.
- Exact model and external test evidence: pending credentials.
- PayPal sandbox app/buyer test instructions for judges: pending authorized access.
- Entrant/team identity, eligibility, registration and submission: pending user review and authorization.
