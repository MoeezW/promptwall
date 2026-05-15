#!/usr/bin/env bash
# Prompt with a credit card. Presidio's PII detector fires, the policy's
# `redact` rule replaces the number with an HMAC-keyed token before
# forwarding. The response is hydrated on the way back so the caller sees
# the original number, but the upstream provider only ever saw the token.
set -euo pipefail

curl -sS http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "user", "content": "Format this for our records: customer paid with card 4111-1111-1111-1111 on 2026-05-13."}
    ]
  }' | jq .
