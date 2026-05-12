from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from promptwall.config import Action, Policy, Rule, load_policy
from promptwall.detectors.base import DetectorResult
from promptwall.policy import Decision, evaluate, referenced_detectors


def _result(name: str, *, score: float = 0.0, matched: bool = False, degraded: bool = False):
    return DetectorResult(
        detector=name,
        score=score,
        matched=matched,
        latency_ms=1.0,
        degraded=degraded,
    )


def _policy(
    *rules: Rule,
    default: Action = Action.ALLOW,
    degraded: Action = Action.BLOCK,
) -> Policy:
    return Policy(rules=list(rules), default_action=default, degraded_action=degraded)


# --- referenced_detectors -------------------------------------------------


def test_referenced_detectors_extracts_names():
    refs = referenced_detectors("pii.matched or injection_ml.score > 0.8")
    assert refs == {"pii", "injection_ml"}


def test_referenced_detectors_empty_for_literal():
    assert referenced_detectors("true") == set()


# --- evaluate happy path --------------------------------------------------


def test_returns_default_action_when_no_rules_match():
    policy = _policy(Rule(condition="pii.matched", action=Action.BLOCK))
    decision = evaluate(policy, [_result("pii", matched=False)])
    assert decision.action == Action.ALLOW
    assert decision.matched_rule_index is None


def test_first_matching_rule_wins():
    policy = _policy(
        Rule(condition="pii.matched", action=Action.REDACT),
        Rule(condition="pii.matched", action=Action.BLOCK),
    )
    decision = evaluate(policy, [_result("pii", matched=True)])
    assert decision.action == Action.REDACT
    assert decision.matched_rule_index == 0


def test_comparison_rules_evaluate_correctly():
    policy = _policy(Rule(condition="injection_regex.score >= 0.9", action=Action.BLOCK))
    above = evaluate(policy, [_result("injection_regex", score=0.95)])
    below = evaluate(policy, [_result("injection_regex", score=0.85)])
    assert above.action == Action.BLOCK
    assert below.action == Action.ALLOW


def test_boolean_or_combines_rules():
    policy = _policy(
        Rule(
            condition="pii.matched or injection_regex.score > 0.8",
            action=Action.BLOCK,
            reason="combined",
        ),
    )
    pii_only = evaluate(
        policy,
        [_result("pii", matched=True), _result("injection_regex", score=0.0)],
    )
    inj_only = evaluate(
        policy,
        [_result("pii", matched=False), _result("injection_regex", score=0.9)],
    )
    assert pii_only.action == Action.BLOCK
    assert inj_only.action == Action.BLOCK


# --- degraded fallback ----------------------------------------------------


def test_missing_detector_triggers_degraded_action():
    policy = _policy(Rule(condition="absent.matched", action=Action.BLOCK))
    decision = evaluate(policy, [_result("pii", matched=True)])
    assert decision.action == Action.BLOCK  # degraded
    assert "absent" in decision.degraded_detectors


def test_degraded_detector_triggers_degraded_action():
    policy = _policy(Rule(condition="pii.matched", action=Action.REDACT))
    decision = evaluate(
        policy,
        [_result("pii", matched=False, degraded=True)],
        # pii is the only referenced; it's degraded → policy.degraded_action = block
    )
    assert decision.action == Action.BLOCK
    assert decision.degraded_detectors == ("pii",)


def test_invalid_expression_falls_back_to_degraded():
    policy = _policy(Rule(condition="this is not valid python!!!", action=Action.ALLOW))
    decision = evaluate(policy, [])
    assert decision.action == Action.BLOCK
    assert decision.reason is not None


# --- YAML loading ---------------------------------------------------------


def test_load_default_policy():
    src = Path(__file__).parent.parent.parent.parent / "policies" / "default.yaml"
    policy = load_policy(src)
    assert policy.version == 1
    assert any(r.action == Action.REDACT for r in policy.rules)
    assert policy.default_action == Action.ALLOW
    assert policy.degraded_action == Action.BLOCK


def test_load_policy_validates_action_enum(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 1\nrules:\n  - if: 'pii.matched'\n    action: nonsense\n",
    )
    with pytest.raises(Exception):  # noqa: B017,PT011 -- pydantic ValidationError
        load_policy(bad)


# --- property test --------------------------------------------------------


_CONDITIONS = st.sampled_from(
    [
        "true",
        "false",
        "pii.matched",
        "pii.matched and injection_regex.matched",
        "pii.matched or injection_regex.matched",
        "not pii.matched",
        "pii.score >= 0.5",
        "injection_regex.score > 0.9",
        "injection_regex.score >= injection_ml.score",
        "(pii.matched or secrets.matched) and not injection_regex.degraded",
        "unknown.field > 0",  # always degraded
        "weird syntax !!!",  # always invalid
        "1 / 0",  # eval error
        "pii.matched == True",
    ]
)
_ACTIONS = st.sampled_from(list(Action))


@st.composite
def _random_rule(draw: st.DrawFn) -> Rule:
    return Rule(condition=draw(_CONDITIONS), action=draw(_ACTIONS))


@st.composite
def _random_result(draw: st.DrawFn) -> DetectorResult:
    name = draw(st.sampled_from(["pii", "injection_regex", "injection_ml", "secrets"]))
    return _result(
        name,
        score=draw(st.floats(min_value=0.0, max_value=1.0)),
        matched=draw(st.booleans()),
        degraded=draw(st.booleans()),
    )


@given(
    rules=st.lists(_random_rule(), min_size=0, max_size=4),
    results=st.lists(_random_result(), min_size=0, max_size=4),
)
@hyp_settings(max_examples=200, deadline=None)
def test_evaluator_never_crashes(rules: list[Rule], results: list[DetectorResult]):
    policy = Policy(rules=rules)
    decision = evaluate(policy, results)
    assert isinstance(decision, Decision)
    assert decision.action in {Action.ALLOW, Action.REDACT, Action.BLOCK}
