# CommitGuard — workshop purchasing, with proof

A purchasing assistant for independent bicycle repair workshops. Describe the supplies needed, review an exact quote, approve that commitment, then complete a PayPal-style checkout. When a capture response disappears, CommitGuard treats the outcome as **unknown**, reads the original order, and recovers the receipt without another capture POST.

**Current status: runnable local prototype with partially verified external integrations.** Three real OpenAI Responses requests passed: a valid kit proposal and an unclear brief requiring clarification. One real PayPal sandbox order completed payer approval and a verified USD 37 capture. Recovery fault tests use clearly labelled fixtures. The combined AI plus sandbox test deliberately discarded a real capture response, then recovered the verified receipt by reading the original order without another capture. This is not yet a completed competition submission.

## Run in one command

Requirements: Python 3.11+ on Linux, macOS or Windows. Tested with Python 3.12.14, including native Windows. The app has **no third-party runtime dependencies**, no build step and no account requirement in fixture mode. See the [judge runbook](docs/JUDGE-RUNBOOK.md) for reproducible evaluation.

```sh
python3 -m commitguard.server
```

Open **http://127.0.0.1:8765** in your browser. Run that command from this extracted package's root directory. The server listens only on loopback. On another port:

```sh
python3 -m commitguard.server --port 8780 --data-dir .data-demo-2
```

Do not host this development server publicly. It uses local browser sessions, not a production identity system.

## The 90-second signature demonstration

1. Keep the default brief: patches, tyre levers and gloves for 20 bike repairs, within $60.
2. Leave **Lost response after payment** selected. Build the plan: the exact fictional catalog total is **$37.00 USD**.
3. Review the three supplies and approve that exact quote. Create one checkout order.
4. Select **Simulate PayPal payer approval**, then **Capture $37.00 once**. These are separate actions.
5. The screen says **CAPTURE OUTCOME UNKNOWN**, while the separate simulated provider ledger shows one capture POST and one successful fixture capture.
6. Select **Reconcile original order**. The app reads that order, verifies items, merchant, amount, currency and completed capture, and displays a simulated receipt. The capture POST count remains **1**.
7. Download the labelled evidence JSON. Reload the page to see the same persisted state and trace.

On mobile, uncertain/pending outcomes show the exact committed USD amount and safe original-order check near the top, before the stacked brief and quote. Initial approval still requires the full quote review.

Local cancellation remains revoked across failed lookups and restarts. Captures found during preflight retain their receipt IDs; stale snapshots cannot restore payment permission.

The fixture intentionally exposes its own ledger counts for demonstration. They are simulator ground truth, not production PayPal statistics or evidence that a real payment occurred.

## Other repeatable rehearsals

Choose a scenario before building a plan. Each plan keeps its original scenario. A new choice does not rewrite an existing purchase.

| Scenario | Expected outcome |
| --- | --- |
| Normal checkout | Completed simulated capture and receipt |
| Lost response after payment | Unknown, then completed after a GET reconciliation; one capture POST |
| Timeout before capture | Unknown remains unknown, no capture occurred, retry blocked |
| Pending payment | Pending until **Settle pending fixture**, then completed |
| Authentication error | Review required; attempted POST counted, no successful fixture capture |
| Unexpected capture currency | Review required; never a verified receipt |
| Unknown order creation | Creation may have happened; no order ID available; manual investigation using saved request ID |

An unresolved create/capture, pending payment or review stops **other checkout creation in the same browser session**. You may still explore draft plans. This prevents the common “start over with a new key” mistake. Resolve the original purchase first. For a separate, intentionally stuck rehearsal, use a fresh browser profile/private window and its own `--data-dir`. This creates an independent **simulation**; it is never a way to recover or retry a real uncertain purchase.

The fixture planner is a narrow keyword interpreter, visibly labelled **not connected AI**. Use the supplied brief presets. Unclear needs, exclusions, insufficient budget/stock, and missing tube fit/quantity produce clarification questions. It does not claim general language understanding. Stock is a per-quote fixture constraint; inventory reservation, delivery, tax calculation and real fulfillment are outside scope.

## Validate the package

Core, adapter-contract and HTTP tests use only the standard library and make no external requests:

```sh
python3 scripts/run-tests.py
```

Browser QA is optional and uses locked development-only dependencies:

```sh
npm ci
CHROMIUM_PATH=/usr/bin/chromium npm run test:browser
npm audit
```

Set `CHROMIUM_PATH` to a locally installed Chromium/Chrome binary. Browser QA launches its own loopback server, fresh temporary data directory, and headless browser; it never opens the desktop. It blocks external browser requests. The cross-site return case is fulfilled from an in-browser mock page, with no external fetch. See [evidence](evidence/VERIFIED-STATUS.md) for exact results and limits.

## What the real adapters implement

- PayPal OAuth client credentials at the fixed sandbox token endpoint; Orders v2 create, read and capture; stable UUID `PayPal-Request-Id` values; `Prefer: return=representation`; PayPal-hosted payer approval; verified webhook wake-ups that only trigger an order lookup.
- A structured model proposal through the OpenAI Responses API using strict JSON Schema. The model receives the catalog as untrusted data and can return only SKU/quantity proposals, explanations and questions. It has no payment tools or network destination authority. Independent policy revalidates its output.
- Exact quote fingerprinting and approval invalidation; persisted in-flight reservations; restart recovery; duplicate/concurrent call protection; no automatic create/capture replay after an uncertain outcome.

**Adapter-contract tests are mocked transport tests, not external integration tests.** The PayPal/model contract sources and deliberate fail-closed assumptions are recorded in [technical sources](docs/TECHNICAL-SOURCES.md). Follow [live verification](docs/LIVE-VERIFICATION.md) only after credentials and access are explicitly authorized. No credentials are in this package. Environment variables are read from the server environment; `.env` files are **not automatically loaded**.

## Package contents

- `commitguard/`: deterministic policy, SQLite store, provider/model adapters, state machine and loopback HTTP server.
- `web/`: responsive accessible interface; all assets local and original, no analytics or third-party scripts.
- `tests/`: core, HTTP and mocked-contract tests, plus independent review regressions.
- `docs/`: architecture/security notes, requirements traceability, live steps, submission draft and sub-three-minute storyboard.
- `evidence/`: test reports, independent review and dependency audit.
- `BUILD-INFO.json`: build provenance and verification scope.
- `LICENSE`: MIT license.

Local state is in `.data/` by default and is excluded from release archives. Its SQLite file includes purchase briefs, browser sessions, immutable quotes, traces and the simulated provider ledger. Treat it as private local data. Data directories are pinned to their planner mode, payment mode and seller ID; use separate directories for model/sandbox testing. One server process may own a directory at a time.

## Competition readiness

Official rules checked on October 29, 2026 allow a locally runnable demo but require meaningful PayPal sandbox and AI use, an open-source public repository and a public video under three minutes. The deadline is **November 12, 2026 at 20:00 UTC** (2pm Houston; November 13 at 1am Pakistan). See the [official rules](https://paypalaihackathon.devpost.com/rules).

The fixture package alone does **not** demonstrate real PayPal or model integration. Before submission, publish the source with its license, record the real demo with honest fixture labels for failure injection, and review all eligibility requirements. No real-money payment is supported or tested.
