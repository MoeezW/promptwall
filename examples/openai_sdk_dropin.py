"""Three-line integration with the OpenAI Python SDK.

Point the OpenAI client at the promptwall proxy by overriding ``base_url``.
Everything else is unchanged — the proxy speaks the OpenAI chat-completions
shape and forwards to the real provider after running detectors and the
policy.

Run:

    OPENAI_API_KEY=sk-... uv run python examples/openai_sdk_dropin.py

(or any other way you usually set the env var; the SDK reads it itself.)
"""

from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1")  # ← only change

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "user", "content": "Summarize the OWASP LLM Top 10 in three bullets."},
    ],
)

print(response.choices[0].message.content)
