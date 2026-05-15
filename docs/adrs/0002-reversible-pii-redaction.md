# ADR 0002 — Reversible PII redaction with HMAC-keyed tokens

**Status:** Accepted
**Date:** 2026-04-27

## Context

A proxy that scans user prompts for PII has three options: do nothing (the obvious safety hole), block on detection (kills the completion-quality story), or redact. Naive redaction — replacing detected entities with `[REDACTED]` or asterisks — destroys both context and grammar:

> "Please send the invoice to **[REDACTED]** and confirm receipt at **[REDACTED]**."

The model loses the structural cue that the two slots are different *types* of contact (email vs. phone), and any downstream string template that expects the original values back is broken.

We also need the operator to be able to *audit* what was redacted, which means the redaction has to be reversible by the proxy itself (and only by the proxy) — never by the upstream provider.

## Decision

Each PII span is replaced with a deterministic token of the form:

```
<PII:{TYPE}_{HMAC8}>
```

where:

- `{TYPE}` is the Presidio entity label (`EMAIL_ADDRESS`, `CA_SIN`, `CREDIT_CARD`, ...). The model sees a typed slot.
- `{HMAC8}` is the first 8 hex characters of `HMAC-SHA256(salt, original)`, where `salt` is a cryptographically random 32 bytes generated per request.

The token → original mapping is held in memory for the duration of the request and discarded once the response is hydrated. The per-request salt ensures the same email in two different requests gets different tokens — no cross-request linkability.

Hydration on the response side walks the `<PII:..._XXXX>` pattern and substitutes back **only when the HMAC matches a token in the per-request mapping.** Tokens whose HMAC is unknown — i.e., look-alike strings the model may have hallucinated — are left alone.

## Consequences

**Good:**

- The model sees `<PII:EMAIL_a1b2c3d4>`, which is a clean structural slot rather than a string of asterisks.
- The HMAC keeps tokens stable within a single request (so the same email mentioned twice gets the same token) but unguessable from outside.
- The mapping never leaves the proxy. A compromised upstream provider learns nothing it didn't already see in the prompt.
- The round-trip property `hydrate(redact(text)) == text` is verifiable with hypothesis, and it is (see `tests/property/test_redaction.py`).

**Tradeoffs:**

- In-memory mapping means a crash mid-request loses the ability to hydrate that response. The crashed response would not be returned anyway, so this is fine for v0.1. Encrypted-at-rest mapping persistence for audit playback is on the roadmap.
- Tokens are 18–25 chars long. A prompt that's tightly packed against the model's context window may notice this overhead; in practice the savings of typed slots over verbose `[REDACTED_EMAIL_ADDRESS]` style placeholders compensate.

## Rejected alternatives

- **Deterministic global tokens.** A static lookup of `email → <EMAIL_1>`. Simple, but the same address gets the same token across users and requests, leaking linkability.
- **Full encryption (Fernet-style).** Replace the email with `gAAAAAB...`. The token is opaque to the model — it can't reason about it as an email-shaped value. Completion quality drops measurably on tasks like "format this as a contact card."
- **Format-preserving encryption.** Replaces the email with another valid-looking email. Cute, but a hallucinated reply that pattern-matches the format would be hydrated back to a real address it didn't actually receive — a correctness hazard worse than the problem it solves.
- **Drop redaction entirely; block on PII.** Off the table. The mission is to scan *without* breaking benign traffic.
