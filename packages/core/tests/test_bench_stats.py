import sys
from pathlib import Path

# Make the top-level benchmarks/ package importable when pytest CWD is packages/core.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks.stats import bootstrap_ci, percentile


def test_bootstrap_ci_point_estimate_equals_mean():
    values = [0.0, 1.0, 0.0, 1.0, 0.5]
    point, _lower, _upper = bootstrap_ci(values, n_resamples=100)
    assert point == sum(values) / len(values)


def test_bootstrap_ci_brackets_point_estimate():
    values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    point, lower, upper = bootstrap_ci(values, n_resamples=2000)
    assert lower <= point <= upper


def test_bootstrap_ci_empty_input_is_zero():
    point, lower, upper = bootstrap_ci([])
    assert (point, lower, upper) == (0.0, 0.0, 0.0)


def test_bootstrap_ci_seed_is_deterministic():
    values = [0.0, 1.0] * 30
    a = bootstrap_ci(values, n_resamples=500, seed=42)
    b = bootstrap_ci(values, n_resamples=500, seed=42)
    assert a == b


def test_percentile_basic():
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == 3.0


def test_percentile_empty():
    assert percentile([], 0.99) == 0.0
