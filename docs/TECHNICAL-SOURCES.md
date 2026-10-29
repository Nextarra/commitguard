# Current official technical sources

Checked October 29, 2026 before implementation, using public official documentation. No authenticated provider execution occurred. These establish intended contracts; mocked tests do not establish provider acceptance.

| Source | Implementation decision |
| --- | --- |
| [Orders v2](https://developer.paypal.com/api/orders/v2) and [current schema](https://developer.paypal.com/api/orders/v2/schema.json) | Create/read/capture paths, CAPTURE intent, purchase-unit references/payee/items and capture evidence |
| [Create order](https://developer.paypal.com/api/orders/v2/orders-create) | One purchase unit, experience context, payer approval link, item breakdown and seller binding |
| [Capture order](https://developer.paypal.com/api/orders/v2/orders-capture) | Payer approval, empty capture body, request ID and representation preference; full GET to verify original quote |
| [Read order](https://developer.paypal.com/api/orders/v2/orders-get) | Original order ID reconciliation; no invented lookup by request ID |
| [OAuth](https://developer.paypal.com/api/rest/authentication/) | Server Basic client-credentials exchange at sandbox token endpoint |
| [Idempotency](https://developer.paypal.com/api/rest/reference/idempotency/) | Separate stable UUIDs; concurrent same-ID requests/retention are not assumed unlimited |
| [Webhooks](https://developer.paypal.com/api/rest/webhooks/rest/) and [signature verification](https://developer.paypal.com/api/webhooks/v1/verify-webhook-signature-post) | Verify before event use; order GET drives state; duplicate-safe wake-ups |
| [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) | Responses `text.format` strict JSON Schema; completed output-text parsing; refusal/incomplete handling and independent validation |
| [Hackathon rules](https://paypalaihackathon.devpost.com/rules) and [overview](https://paypalaihackathon.devpost.com/) | Genuine PayPal and AI, runnable demo, open-source public repository and video under three minutes |

The current order schema supports original item details, merchant ID and references, but fields are not mandatory in every response. We fail closed if the configured sandbox does not return required evidence. Investigate missing fields and adapt against verified documentation rather than inferring a match. Actual contract compatibility remains pending.

The operator must choose an account-available model supporting strict structured outputs; no model name is guessed or hardcoded. The adapter uses standard-library HTTPS directly, without an AI SDK dependency.

Our authenticated fixture-event API is separate from PayPal's own webhook simulator. We do not claim mock PayPal events can be verified by postback; registered-app signature verification is a distinct pending external test.
