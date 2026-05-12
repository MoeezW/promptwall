"""Policy expression evaluator and decision engine.

Evaluates each rule's ``if`` expression against the namespace of detector
results in policy order — first matching rule wins. The expression
language is intentionally tiny (and / or / not, comparisons, attribute
access, parentheses) and runs via :mod:`simpleeval`, which sandboxes
attribute access and never reaches ``eval()``.

Degraded semantics: if a rule references a detector that is missing or
degraded, the rule fires the policy's ``degraded_action`` (default
``block``). This is the safe-by-default failure mode the build plan
calls for.
"""

import re
from dataclasses import dataclass

import structlog
from simpleeval import EvalWithCompoundTypes, InvalidExpression, NameNotDefined

from promptwall.config import Action, Policy
from promptwall.detectors.base import DetectorResult

log = structlog.get_logger()

_DETECTOR_REF = re.compile(r"\b([a-z_][a-z_0-9]*)\.\w+")


@dataclass(frozen=True)
class Decision:
    """The outcome of evaluating a policy."""

    action: Action
    reason: str | None = None
    matched_rule_index: int | None = None
    degraded_detectors: tuple[str, ...] = ()


def referenced_detectors(condition: str) -> set[str]:
    """Return the set of detector names referenced as ``name.field`` in ``condition``."""
    return set(_DETECTOR_REF.findall(condition))


def evaluate(policy: Policy, results: list[DetectorResult]) -> Decision:
    """Walk rules top-to-bottom; return the first match (or ``default_action``)."""
    by_name = {r.detector: r for r in results}

    for index, rule in enumerate(policy.rules):
        refs = referenced_detectors(rule.condition)
        degraded = tuple(
            sorted(name for name in refs if name not in by_name or by_name[name].degraded)
        )
        if degraded:
            return Decision(
                action=policy.degraded_action,
                reason=f"degraded detector(s): {', '.join(degraded)}",
                matched_rule_index=index,
                degraded_detectors=degraded,
            )

        try:
            evaluator = EvalWithCompoundTypes(names=dict(by_name))
            matched = bool(evaluator.eval(rule.condition))
        except (NameNotDefined, InvalidExpression):
            return Decision(
                action=policy.degraded_action,
                reason=f"invalid expression in rule {index}",
                matched_rule_index=index,
            )
        except Exception as exc:
            # Boundary: a buggy expression must not break the request path.
            # The runner has the equivalent catch at its safety boundary;
            # this is the policy lane's version.
            log.exception(
                "policy.eval.crash",
                rule_index=index,
                condition=rule.condition,
                error_type=type(exc).__name__,
            )
            return Decision(
                action=policy.degraded_action,
                reason=f"evaluator error in rule {index}",
                matched_rule_index=index,
            )

        if matched:
            return Decision(
                action=rule.action,
                reason=rule.reason,
                matched_rule_index=index,
            )

    return Decision(action=policy.default_action)
