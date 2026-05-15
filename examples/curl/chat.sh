#!/usr/bin/env bash
# Benign chat completion. Allowed by the default policy; forwarded to OpenAI.
set -euo pipefail

curl -sS http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "user", "content": "What is the capital of Canada?"}
    ]
  }' | jq .
