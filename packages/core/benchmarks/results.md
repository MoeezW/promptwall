# Benchmark results

_Generated 2026-05-12T06:50:09+00:00; seed=42; bootstrap CIs use 10 000 percentile resamples._

Numbers are reproduced by ``make bench``. Corpora:

- **Prompt-injection corpus** — `deepset/prompt-injections` from the Hub (used as a public stand-in for HackAPrompt levels 1-3, which is a gated dataset); falls back to a small embedded list if the Hub is unreachable.
- **JailbreakBench harmful behaviors** — harmful-content goals fetched from the JBB artifacts repo (or the embedded fallback). These are direct harmful-content asks, not injection patterns; an injection detector legitimately scores near 0% on them. Listed here for completeness and because the build plan calls for it.
- **Benign baseline** — `OpenAssistant/oasst1` first-turn English prompter messages (streamed), or an embedded benign list if offline.


## Prompt-injection corpus (n=203, seed=42)

| Detector | Detection rate | 95% CI | p50 latency | p99 latency |
|---|---|---|---|---|
| injection_regex | 0.084 | [0.049, 0.123] | 0.1ms | 0.7ms |
| secrets | 0.000 | [0.000, 0.000] | 6.5ms | 27.3ms |
| pii | 0.000 | [0.000, 0.000] | 16.6ms | 143.2ms |
| injection_ml | 0.419 | [0.350, 0.488] | 25.6ms | 113.3ms |
| **policy (combined)** | **0.458** | **[0.389, 0.527]** | — | — |

## JailbreakBench harmful behaviors (n=20, seed=42)

| Detector | Detection rate | 95% CI | p50 latency | p99 latency |
|---|---|---|---|---|
| injection_regex | 0.000 | [0.000, 0.000] | 0.0ms | 0.1ms |
| secrets | 0.000 | [0.000, 0.000] | 5.6ms | 7.5ms |
| pii | 0.000 | [0.000, 0.000] | 11.5ms | 13.1ms |
| injection_ml | 0.000 | [0.000, 0.000] | 19.8ms | 22.4ms |
| **policy (combined)** | **0.000** | **[0.000, 0.000]** | — | — |

## False-positive rate on OpenAssistant benign (n=500, seed=42)

| Detector | FPR | 95% CI |
|---|---|---|
| injection_regex | 0.002 | [0.000, 0.006] |
| secrets | 0.000 | [0.000, 0.000] |
| pii | 0.002 | [0.000, 0.006] |
| injection_ml | 0.006 | [0.000, 0.014] |
| **policy (combined)** | **0.012** | **[0.004, 0.022]** |
