# Benchmark results

_Generated 2026-05-12T07:09:54+00:00; seed=42; bootstrap CIs use 10 000 percentile resamples._

Numbers are reproduced by ``make bench``. Dataset sources are shown in each section's title so the corpus is auditable.

- **Prompt-injection corpus** — chained Hub sources in `benchmarks.datasets._INJECTION_HUB_SOURCES`; the first source with positive examples wins. Falls back to an embedded list when offline. HackAPrompt is gated on the Hub, so we don't use it.
- **JailbreakBench harmful behaviors** — harmful-content goals. These are direct harmful-content asks, not injection patterns; an injection detector legitimately scores near 0% on them. Reported for completeness.
- **Benign baseline** — `OpenAssistant/oasst1` first-turn English prompts, or an embedded benign list when offline.


## Prompt-injection corpus — `Lakera/gandalf_ignore_instructions` (n=500, seed=42)

| Detector | Detection rate | 95% CI | p50 latency | p99 latency |
|---|---|---|---|---|
| injection_regex | 0.216 | [0.180, 0.252] | 0.1ms | 0.2ms |
| secrets | 0.000 | [0.000, 0.000] | 5.7ms | 9.4ms |
| pii | 0.000 | [0.000, 0.000] | 11.6ms | 27.5ms |
| injection_ml | 1.000 | [1.000, 1.000] | 20.2ms | 32.8ms |
| **policy (combined)** | **1.000** | **[1.000, 1.000]** | — | — |

## JailbreakBench harmful behaviors (n=20, seed=42)

| Detector | Detection rate | 95% CI | p50 latency | p99 latency |
|---|---|---|---|---|
| injection_regex | 0.000 | [0.000, 0.000] | 0.0ms | 0.1ms |
| secrets | 0.000 | [0.000, 0.000] | 5.5ms | 7.4ms |
| pii | 0.000 | [0.000, 0.000] | 11.3ms | 12.9ms |
| injection_ml | 0.000 | [0.000, 0.000] | 20.6ms | 22.5ms |
| **policy (combined)** | **0.000** | **[0.000, 0.000]** | — | — |

## False-positive rate on benign — `openassistant` (n=500, seed=42)

| Detector | FPR | 95% CI |
|---|---|---|
| injection_regex | 0.002 | [0.000, 0.006] |
| secrets | 0.000 | [0.000, 0.000] |
| pii | 0.002 | [0.000, 0.006] |
| injection_ml | 0.006 | [0.000, 0.014] |
| **policy (combined)** | **0.010** | **[0.002, 0.020]** |
