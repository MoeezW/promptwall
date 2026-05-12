"""Benchmark harness for promptwall.

Run via ``python -m benchmarks.runner`` (or ``make bench``). The harness
exercises the detector pipeline directly — no proxy, no provider API
spend — and reports detection rate / FPR / latency with 95% bootstrap
confidence intervals.

Inject the system trust store at import time so urllib / requests
(used transitively by huggingface_hub / datasets) can validate certs on
machines where the bundled certifi store doesn't include the intercept.
"""

import truststore

truststore.inject_into_ssl()

RANDOM_SEED = 42
