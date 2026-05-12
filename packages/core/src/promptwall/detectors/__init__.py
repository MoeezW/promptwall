"""Detector framework — the abstraction the rest of the project hangs from.

Concrete detectors live in their own modules (:mod:`injection_regex`,
:mod:`secrets`, :mod:`pii`, etc.) and aren't imported here — the heavy ones
(Presidio, ONNX) shouldn't pay their construction cost just because a
caller wanted the Protocol.
"""

from promptwall.detectors.base import Detector, DetectorResult, ScanContext, Span
from promptwall.detectors.circuit import BreakerState, CircuitBreaker
from promptwall.detectors.runner import run_detectors

__all__ = (
    "BreakerState",
    "CircuitBreaker",
    "Detector",
    "DetectorResult",
    "ScanContext",
    "Span",
    "run_detectors",
)
