# Judge runbook — pre-submission draft

Verified: offline fixture recovery, three real gpt-5.6-terra Responses requests, and real PayPal sandbox order creation. A USD 37 sandbox capture is also verified. Combined real model plus sandbox recovery passed with a deliberately discarded capture response and original-order GET. Final submission remains pending.

## Local fixture rehearsal (no account, payment or API cost)

1. Install an existing supported Python 3.11+ runtime, extract this repository and open a terminal in its root. No Python packages are required.
2. Run `python -m commitguard.server` (or `python3` on systems using that name).
3. Open http://127.0.0.1:8765. Check that the banner says fixture rehearsal.
4. Keep the default 20-repair brief, $60 budget and lost-response scenario. Build the plan; inspect the exact $37 quote; approve it.
5. Create one order, simulate payer approval, then capture once. The provider fixture records success while the response is lost. Observe unknown status, one capture POST and one fixture capture.
6. Stop and restart the server using the same data directory. Reload the same browser session. Unknown status must persist. Reconcile the original order; verify the labelled simulated receipt and unchanged capture counts.
7. Export the evidence JSON. It labels the planner and payment mode; do not treat it as a real PayPal receipt.

For a separate intentionally unresolved scenario, use independent fixture data and browser context. Never reset state to recover an actual uncertain purchase.

## Review checkpoints

- Adjusting the quote removes approval.
- Payer approval is distinct from quote approval.
- Capture uncertainty prevents blind retries and same-session replacement checkout.
- Pending is not completed; mismatched evidence requires review.
- If the local connection is lost, payment controls disappear until saved state is read again. Refresh is a GET, not a capture replay.
- Inspect `tests`, `docs/ARCHITECTURE-SECURITY.md`, and the original versus Lenovo-specific evidence files. Run `python scripts/run-tests.py` for offline validation.

## External evaluation — pending verification

Use the evaluator's own authorized PayPal sandbox app/buyer and model access; never publish reusable owner credentials. The environment-variable names and fixed sandbox scope are documented in `.env.example` and `docs/LIVE-VERIFICATION.md`. Environment files are not automatically loaded. Set OPENAI_MODEL=gpt-5.6-terra for the tested model. The app caps real model attempts at ten with a persistent .data-model-budget/allowance.sqlite3 ledger, 16000 request bytes, 2048 output tokens, standard service tier, no tools or retries. Failed attempts count. Preserve this ledger across restarts and source moves; do not reset it to extend an approved allowance. Verify your own billing/credits before enabling network calls; the app cannot choose the provider's credit source.

The final public README must state the tested model, exact supported setup, time/cost limits, and how judges obtain permitted access. The current loopback server is not a public hosted service. Hosting, payment refunds, fulfillment, tax computation and production identity are out of scope.

## Video shot discipline

Use the 160-second storyboard. Show a real verified model proposal and real PayPal sandbox checkout only after those tests pass; label fixture fault injection clearly. Capture the recovery evidence and explain its bounded guarantee. Keep browser account details, credential pages and private files out of footage. Do not upload the private visual-review archive as the demo.
