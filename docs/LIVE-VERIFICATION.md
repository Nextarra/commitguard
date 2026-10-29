# Remaining authorized external verification

Three real OpenAI Responses requests passed, and a PayPal sandbox order was created. A USD 37 sandbox capture is now verified; combined model plus sandbox recovery is verified with deliberate response-loss injection. Defaults are fixture-only; no real-money mode exists.

## Needed access

Provide an existing authorized PayPal sandbox app client ID/secret, its corresponding **13-character sandbox merchant ID**, an existing sandbox buyer for payer approval, and an existing model key plus exact available structured-output model ID. Never put secrets in the repository/video/receipt. Nothing here creates them.

Use an authorized local computer and process-only credentials. Never publish owner credentials or reuse them for judge access.

## Explicit future configuration

Supply these through a secure process environment; `.env.example` is documentation and is not auto-loaded:

- `COMMITGUARD_ALLOW_NETWORK=1`
- `COMMITGUARD_PLANNER=model`, `OPENAI_API_KEY`, `OPENAI_MODEL`
- `COMMITGUARD_PAYMENTS=sandbox`, `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_MERCHANT_ID`
- `PAYPAL_WEBHOOK_ID` only for registered-app webhook testing.

Use a **separate** directory; modes/seller are pinned and cannot relabel old fixtures:

```sh
python3 -m commitguard.server --data-dir .data-authorized-sandbox
```

There is no production PayPal mode. Do not use live merchant credentials.

## Verification sequence

1. First test the structured model with payment mode still fixture and its own data directory. Record exact model ID, time and sanitized proposal/policy result. Evaluate clear/unclear requests, tube compatibility, exclusions, stock/budget limits and catalog/buyer prompt injection. Schema validity is not proof of good purchasing judgment.
2. In a separate sandbox directory, approve a quote and create an order. Verify seller ID and PayPal sandbox approval URL. Complete payer approval with an authorized sandbox buyer, then reconcile. The return query is not proof of approval/payment.
3. Capture once, then read full provider evidence: original order ID, CAPTURE intent, references, payee merchant ID, every item/quantity/unit price, USD total and completed capture. Missing evidence stops for review. Any adaptation must follow official contracts and new tests.
4. With a controlled authorized sandbox fault harness, lose the response after a capture and recover by GET. Prevent extra capture POSTs. Preserve the exact order/request IDs and verify one actual sandbox capture; disclose fault injection in the video. Never start another purchase to resolve an unknown one.
5. Test duplicate/concurrent submissions and crash/restart after capture reservation. Confirm no second capture invocation for the commitment. Repeat ownership/CSRF/forged-event checks.
6. Optional registered-app webhooks require separately authorized HTTPS forwarding to this local listener and the correct existing webhook ID. Preserve local Host routing; test actual signatures, duplicate/delayed delivery and transient lookup failure. The loopback server alone cannot receive PayPal's external HTTPS notifications; fixture events are not signature verification.
7. Re-run offline/browser tests and audit after any changes. Add actual external evidence separately from mocked/fixture results.
8. Review eligibility, ownership and rules, then separately authorize public source publication, real demo recording/video publication and registration/submission. None were performed.

| Action | Current evidence |
| --- | --- |
| OpenAI Responses | Three real gpt-5.6-terra requests passed; see evidence/lenovo-model-validation.json |
| PayPal sandbox | Real order, existing test-buyer approval and USD 37 completed capture verified |
| Webhooks | Mocked contracts only; no actual HTTPS delivery verified |
| Publication/submission | Pending; source/video must accurately disclose these limits |
