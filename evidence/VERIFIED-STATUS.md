# Verification scope — October 29, 2026

- 126 private Python tests passed; the public package excludes the private harness test (125 public tests), including cross-process locks, payment invariants, concurrent/restart-persistent model limits and two local servers sharing a browser cookie jar.
- Real OpenAI gpt-5.6-terra Responses: valid USD 37 kit proposal and clarification without a purchase. Payments in these two tests were fixtures.
- Real PayPal sandbox: original order, existing Personal sandbox buyer approval, one capture reservation, completed USD 37 sandbox capture. Planner in this test was a fixture. No real money.
- Browser fault injection: HTTP reply lost after completed fixture capture; both response and fallback read lost; restart and read recovered the original receipt, without another capture.
- Historical reviewed source passed 24 local browser scenarios and automated accessibility checks. That complete browser suite has not been rerun on the latest Windows/session changes.

Combined real model plus sandbox recovery passed: a real capture response was deliberately discarded, then an original-order GET recovered the receipt with one capture reservation. Three model attempts total, conservatively reserving $0.30 of the approved $1 allowance. Actual billing is not measured.

Remaining: final browser review, public video and submission. No actual webhook delivery has been verified. This file does not assert full accessibility conformance or production readiness.
