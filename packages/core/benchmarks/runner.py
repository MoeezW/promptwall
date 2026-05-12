"""Benchmark orchestrator.

Builds the detector pipeline, runs it across each dataset, computes
detection rate / false-positive rate / latency percentiles with 95%
bootstrap confidence intervals, and writes the result table to
``benchmarks/results.md``.

The harness skips the proxy entirely — detectors are called directly so
no provider API spend is incurred and CI runs are reproducible.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from benchmarks import RANDOM_SEED
from benchmarks.datasets import (
    BenchmarkExample,
    load_hackaprompt,
    load_jailbreakbench,
    load_openassistant_benign,
)
from benchmarks.stats import bootstrap_ci, percentile
from promptwall.config import Action, Policy, Rule
from promptwall.detectors.base import Detector, ScanContext
from promptwall.detectors.injection_regex import InjectionRegexDetector
from promptwall.detectors.pii import PIIDetector
from promptwall.detectors.runner import run_detectors
from promptwall.detectors.secrets import SecretsDetector
from promptwall.policy import evaluate

logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("datasets").setLevel(logging.ERROR)


@dataclass
class _Row:
    label: int
    dataset: str
    scores: dict[str, float]
    matched: dict[str, bool]
    degraded: dict[str, bool]
    latencies: dict[str, float]
    policy_blocked: bool


_BENCH_PII_TIMEOUT_MS = 500  # higher than default; bench avoids degraded fallbacks
_BENCH_SECRETS_TIMEOUT_MS = 500


def _build_detectors(*, with_ml: bool) -> list[Detector]:
    detectors: list[Detector] = [
        InjectionRegexDetector(),
        SecretsDetector(timeout_ms=_BENCH_SECRETS_TIMEOUT_MS),
        PIIDetector(timeout_ms=_BENCH_PII_TIMEOUT_MS),
    ]
    if with_ml:
        from promptwall.detectors.injection_ml import InjectionMLDetector

        detectors.append(InjectionMLDetector(timeout_ms=200))
    return detectors


def _bench_policy(*, with_ml: bool) -> Policy:
    """Build a maximalist bench policy: any strong detector hit blocks; PII redacts."""
    rules: list[Rule] = []
    if with_ml:
        rules.append(
            Rule(condition="injection_ml.score >= 0.5", action=Action.BLOCK, reason="ml"),
        )
    rules.extend(
        [
            Rule(condition="injection_regex.score >= 0.5", action=Action.BLOCK, reason="regex"),
            Rule(condition="secrets.matched", action=Action.BLOCK, reason="secret"),
            Rule(condition="pii.matched", action=Action.REDACT, reason="pii"),
        ],
    )
    return Policy(rules=rules, default_action=Action.ALLOW, degraded_action=Action.BLOCK)


async def _scan_examples(
    examples: Sequence[BenchmarkExample],
    detectors: Sequence[Detector],
    policy: Policy,
) -> list[_Row]:
    rows: list[_Row] = []
    detector_names = [d.name for d in detectors]
    for index, example in enumerate(examples, start=1):
        ctx = ScanContext(request_id=f"bench-{index}", direction="input")
        results = await run_detectors(detectors, example.text, ctx)
        by_name = {r.detector: r for r in results}
        decision = evaluate(policy, list(results))
        rows.append(
            _Row(
                label=example.label,
                dataset=example.dataset,
                scores={name: by_name[name].score for name in detector_names},
                matched={name: by_name[name].matched for name in detector_names},
                degraded={name: by_name[name].degraded for name in detector_names},
                latencies={name: by_name[name].latency_ms for name in detector_names},
                policy_blocked=decision.action == Action.BLOCK,
            ),
        )
        if index % 25 == 0:
            print(f"  scanned {index}/{len(examples)}", flush=True)
    return rows


def _detection_rate(rows: list[_Row], detector: str) -> tuple[float, float, float]:
    positives = [float(r.matched[detector]) for r in rows if r.label == 1]
    return bootstrap_ci(positives)


def _false_positive_rate(rows: list[_Row], detector: str) -> tuple[float, float, float]:
    negatives = [float(r.matched[detector]) for r in rows if r.label == 0]
    return bootstrap_ci(negatives)


def _policy_detection_rate(rows: list[_Row]) -> tuple[float, float, float]:
    return bootstrap_ci([float(r.policy_blocked) for r in rows if r.label == 1])


def _policy_fpr(rows: list[_Row]) -> tuple[float, float, float]:
    return bootstrap_ci([float(r.policy_blocked) for r in rows if r.label == 0])


def _latency_p50(rows: list[_Row], detector: str) -> float:
    return percentile([r.latencies[detector] for r in rows], 0.50)


def _latency_p99(rows: list[_Row], detector: str) -> float:
    return percentile([r.latencies[detector] for r in rows], 0.99)


def _format_ci(triple: tuple[float, float, float]) -> str:
    point, lower, upper = triple
    return f"{point:.3f} [{lower:.3f}, {upper:.3f}]"


def _format_ms(value: float) -> str:
    return f"{value:.1f}ms"


def _render_detection_table(
    rows: list[_Row],
    detector_names: list[str],
    *,
    dataset: str,
    n: int,
) -> str:
    lines = [
        f"## {dataset} (n={n}, seed={RANDOM_SEED})",
        "",
        "| Detector | Detection rate | 95% CI | p50 latency | p99 latency |",
        "|---|---|---|---|---|",
    ]
    for name in detector_names:
        rate = _detection_rate(rows, name)
        lines.append(
            f"| {name} | {rate[0]:.3f} | [{rate[1]:.3f}, {rate[2]:.3f}] |"
            f" {_format_ms(_latency_p50(rows, name))} |"
            f" {_format_ms(_latency_p99(rows, name))} |"
        )
    p = _policy_detection_rate(rows)
    lines.append(
        f"| **policy (combined)** | **{p[0]:.3f}** | **[{p[1]:.3f}, {p[2]:.3f}]** | — | — |",
    )
    return "\n".join(lines)


def _render_fpr_table(
    rows: list[_Row],
    detector_names: list[str],
    *,
    n: int,
    dataset_label: str = "benign",
) -> str:
    lines = [
        f"## False-positive rate on benign — `{dataset_label}` (n={n}, seed={RANDOM_SEED})",
        "",
        "| Detector | FPR | 95% CI |",
        "|---|---|---|",
    ]
    for name in detector_names:
        fpr = _false_positive_rate(rows, name)
        lines.append(f"| {name} | {fpr[0]:.3f} | [{fpr[1]:.3f}, {fpr[2]:.3f}] |")
    policy = _policy_fpr(rows)
    lines.append(
        f"| **policy (combined)** | **{policy[0]:.3f}** | **[{policy[1]:.3f}, {policy[2]:.3f}]** |",
    )
    return "\n".join(lines)


def _dataset_label(rows: list[_Row], fallback: str) -> str:
    if rows:
        return rows[0].dataset
    return fallback


def _render_results(
    timestamp: datetime,
    hackaprompt_rows: list[_Row],
    jbb_rows: list[_Row],
    benign_rows: list[_Row],
    detector_names: list[str],
) -> str:
    pi_label = _dataset_label(hackaprompt_rows, "prompt_injections")
    benign_label = _dataset_label(benign_rows, "benign")
    header = (
        f"# Benchmark results\n\n"
        f"_Generated {timestamp.isoformat(timespec='seconds')}; seed={RANDOM_SEED}; "
        f"bootstrap CIs use 10 000 percentile resamples._\n"
        f"\nNumbers are reproduced by ``make bench``. Dataset sources are"
        f" shown in each section's title so the corpus is auditable.\n"
        f"\n- **Prompt-injection corpus** — chained Hub sources in"
        f" `benchmarks.datasets._INJECTION_HUB_SOURCES`; the first source with"
        f" positive examples wins. Falls back to an embedded list when offline."
        f" HackAPrompt is gated on the Hub, so we don't use it.\n"
        f"- **JailbreakBench harmful behaviors** — harmful-content goals."
        f" These are direct harmful-content asks, not injection patterns;"
        f" an injection detector legitimately scores near 0% on them."
        f" Reported for completeness.\n"
        f"- **Benign baseline** — `OpenAssistant/oasst1` first-turn English"
        f" prompts, or an embedded benign list when offline.\n"
    )
    pieces = [header]
    if hackaprompt_rows:
        pieces.append(
            _render_detection_table(
                hackaprompt_rows,
                detector_names,
                dataset=f"Prompt-injection corpus — `{pi_label}`",
                n=len(hackaprompt_rows),
            ),
        )
    if jbb_rows:
        pieces.append(
            _render_detection_table(
                jbb_rows,
                detector_names,
                dataset="JailbreakBench harmful behaviors",
                n=len(jbb_rows),
            ),
        )
    if benign_rows:
        pieces.append(
            _render_fpr_table(
                benign_rows,
                detector_names,
                n=len(benign_rows),
                dataset_label=benign_label,
            ),
        )
    return "\n\n".join(pieces) + "\n"


async def run(
    *,
    n: int = 1000,
    with_ml: bool = False,
    output: Path | None = None,
) -> Path:
    """Execute the benchmark and write results to ``output`` (default: results.md)."""
    output = output or Path(__file__).parent / "results.md"
    timestamp = datetime.now(tz=UTC)
    print(f"== promptwall bench (n={n}, with_ml={with_ml}) ==", flush=True)

    print("loading datasets...", flush=True)
    hp = load_hackaprompt(n=n)
    jbb = load_jailbreakbench(n=min(n, 200))
    benign = load_openassistant_benign(n=n)
    print(
        f"  prompt_injection={len(hp)} jailbreakbench={len(jbb)} benign={len(benign)}",
        flush=True,
    )

    print("building detector pipeline...", flush=True)
    detectors = _build_detectors(with_ml=with_ml)
    policy = _bench_policy(with_ml=with_ml)
    names = [d.name for d in detectors]

    start = time.perf_counter()
    print("scanning prompt-injection corpus...", flush=True)
    hp_rows = await _scan_examples(hp, detectors, policy)
    print("scanning JailbreakBench...", flush=True)
    jbb_rows = await _scan_examples(jbb, detectors, policy)
    print("scanning OpenAssistant benign...", flush=True)
    benign_rows = await _scan_examples(benign, detectors, policy)
    elapsed = time.perf_counter() - start
    total = len(hp_rows) + len(jbb_rows) + len(benign_rows)
    print(f"  scanned {total} prompts in {elapsed:.1f}s", flush=True)

    body = _render_results(
        timestamp=timestamp,
        hackaprompt_rows=hp_rows,
        jbb_rows=jbb_rows,
        benign_rows=benign_rows,
        detector_names=names,
    )
    output.write_text(body, encoding="utf-8")
    print(f"wrote {output}", flush=True)
    return output


def main() -> None:
    """Console entrypoint — see ``promptwall.cli`` for the public CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="Run the promptwall benchmark harness")
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--with-ml", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    asyncio.run(run(n=args.n, with_ml=args.with_ml, output=args.output))


if __name__ == "__main__":
    main()
