# Requirements traceability

| Requirement | Implementation / evidence | Remaining limit |
| --- | --- | --- |
| Specific audience | Bicycle workshop consumables and fixed-budget planning | Fictional catalog; no user research/impact statistics claimed |
| Genuine AI adapter | Strict Responses proposal schema; policy rejects arbitrary fields/amounts/destinations | Mocked transports/adversarial outputs tested; real key/model evaluation pending |
| Meaningful PayPal adapter | Sandbox OAuth and Orders create/approve/read/capture, UUIDs, seller binding, webhook verification | Actual provider integration pending keys and authorized buyer |
| Honest fixtures | Banner, per-purchase provenance, simulated receipts/metrics, mode/seller directory pinning | Fixture language behavior is not AI quality evidence |
| Exact approval | Full-quote hash; revision invalidates approval | Core, independent and browser tests |
| Policy boundaries | Integer cents, USD, stock/quantity/budget, item and seller verification | Static stock is per quote; no fulfillment |
| Idempotency/concurrency | Persisted reservations; duplicate returns; one capture per commitment | Unit and independent 12-thread tests; no universal exactly-once claim |
| Unknown recovery | GET-only reconcile, same-session new-checkout guard, restart recovery | Lost-response, pre-capture timeout, failed post-capture lookup and crash tests |
| Events | Verify, deduplicate, read facts, ignore stale status text | Mocked contract/fixture tests; actual HTTPS delivery pending |
| Cancellation | Local stop before capture; uncertain attempts cannot be cancelled | No provider void/refund represented |
| XSS/secrets | Text-only DOM, CSP, local credentials, sanitized errors, static route allowlist | Hostile-text browser case and HTTP exposure tests |
| Polished accessible UI | Responsive three-step workspace, keyboard focus and status regions | Chromium desktop/390px/320px and automated WCAG checks; human AT audit pending |
| Portable runnable package | No third-party runtime dependency; one-command Python start | Clean extraction, tests and start/checkout/restart verification |
| Release materials | MIT, README, architecture, storyboard and submission draft | Public repo/video/entry pending |
| Isolation | Isolated project directory; explicit public-source allowlist | Unrelated projects excluded |

Offline verification is a development milestone. Full PayPal capture and publication requirements remain open; this is not a submitted entry.

Follow-up coverage additionally verifies sticky cancellation through malformed reads, webhook/restart paths, external pending/completed fixture captures, missing legacy proof repair, changed capture IDs and stale snapshot downgrades. See `tests/review_followup.py` and the four added browser scenarios.
