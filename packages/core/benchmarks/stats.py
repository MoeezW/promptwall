"""Bootstrap confidence intervals over benchmark metrics.

Percentile bootstrap with a fixed seed (42). 10 000 resamples is the
default; that's the round number the build plan calls for and the
standard recommendation when the CI itself isn't the bottleneck.
"""

from collections.abc import Sequence

import numpy as np

from benchmarks import RANDOM_SEED

_DEFAULT_RESAMPLES = 10_000
_DEFAULT_CI = 0.95


def bootstrap_ci(
    values: Sequence[float],
    *,
    n_resamples: int = _DEFAULT_RESAMPLES,
    ci: float = _DEFAULT_CI,
    seed: int = RANDOM_SEED,
) -> tuple[float, float, float]:
    """Return ``(point_estimate, lower, upper)`` for the mean of ``values``.

    Uses the percentile method on ``n_resamples`` bootstrap resamples drawn
    with replacement. ``seed`` controls the RNG so runs are reproducible.
    """
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return 0.0, 0.0, 0.0
    point = float(arr.mean())
    rng = np.random.default_rng(seed)
    resamples = rng.choice(arr, size=(n_resamples, arr.size), replace=True)
    means = resamples.mean(axis=1)
    alpha = (1.0 - ci) / 2.0
    lower = float(np.quantile(means, alpha))
    upper = float(np.quantile(means, 1.0 - alpha))
    return point, lower, upper


def percentile(values: Sequence[float], q: float) -> float:
    """Return the ``q``-th percentile (0..1) of ``values`` (0 if empty)."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return 0.0
    return float(np.quantile(arr, q))
