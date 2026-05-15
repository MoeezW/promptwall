# ADR 0004 — ONNX Runtime, not PyTorch, for inference

**Status:** Accepted
**Date:** 2026-04-30

## Context

The ML prompt-injection detector uses `protectai/deberta-v3-base-prompt-injection-v2`. The obvious way to run it is the HuggingFace `transformers` pipeline backed by `torch`. The container math, though, is brutal:

- `torch` (CPU build): ~750 MB on disk including bundled BLAS / cuDNN stubs.
- `transformers`: ~80 MB.
- Tokenizer + model weights for DeBERTa-v3-base: ~700 MB FP32.

A naïve image hits 2–3 GB. The mission is to ship a runtime container under 1 GB so the deploy story is "pull and run" instead of "wait three minutes for the registry."

The torch payload buys us things we don't use in this codebase: autograd, optimizer kernels, distributed training primitives, the CUDA driver shim. Pure CPU inference on a transformer this size can be served from a much smaller stack.

## Decision

The ML detector is exported once to ONNX via `optimum-cli export onnx` and served at runtime by ONNX Runtime (CPU EP). The model is downloaded from HuggingFace and exported on first construction; subsequent loads reuse the HuggingFace cache.

The runtime container's `pip uninstall torch` step removes torch after `optimum`'s install resolves it as a transitive dep — we need `optimum` at build time to perform the export but not at inference time once the ONNX file exists.

Inference is synchronous (ONNX Runtime's Python API doesn't expose an async path). It runs under `asyncio.to_thread(...)` so the request loop isn't blocked.

## Consequences

**Good:**

- Runtime image lands at ~900 MB instead of 2.5–3 GB, well inside our <1 GB ambition (see Dockerfile).
- Measured p99 on FP32 is ~18 ms for a 256-token prompt on a 4-core CPU — under our 25 ms budget. We don't need INT8 quantization for v0.1; that's an optional optimization we can do later if the budget tightens.
- The Pre-load + warmup pattern (5 dummy prompts at lifespan startup) means the first real request doesn't pay the cold-cache hit.

**Tradeoffs:**

- Synchronous inference under `to_thread` consumes a default-pool thread for the duration of the call. At very high concurrency this becomes a bottleneck; if we hit it we'd raise `anyio.to_thread.current_default_thread_limiter().total_tokens`. Currently fine.
- Re-exporting the model is a one-time ~50 s cold cost per host. The export script (`scripts/export_model.py`) is committed; in containerized deploys you'd pre-bake the ONNX file into a model-prep image to skip this entirely.
- We carry `optimum` and `transformers` in the build environment for the export step, which is heavier than carrying *only* ONNX Runtime. Acceptable; alternative is shipping the .onnx file in-repo, which we explicitly don't want (binary asset in git).

## Rejected alternatives

- **Keep torch at runtime.** Image grows to 2.5+ GB; we lose the "small container" claim and the deploy story degrades.
- **Re-export to INT8 quantization at build time.** Would shave another ~70% off model weights. Worth doing if p99 budget tightens; not worth the export-pipeline complexity at v0.1 when we have headroom.
- **Distilled smaller injection classifier.** Smaller, but published checkpoints don't beat DeBERTa-v3 on the public corpora we benchmark against, and "we ship the actually-best open detector" is more credible than "we ship a smaller one to save 100 MB."
- **Run inference in a separate container/service.** Cleaner separation but doubles the deploy surface for what is currently a single-binary product.
