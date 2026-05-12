"""Policy YAML schema and loader.

Operators define one YAML file per environment (default / strict / bank).
The schema is Pydantic-validated so a malformed policy fails at startup
rather than at the first request.
"""

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Action(StrEnum):
    """The three terminal actions a rule can fire."""

    ALLOW = "allow"
    REDACT = "redact"
    BLOCK = "block"


class DetectorConfig(BaseModel):
    """Per-detector knobs that the operator can override from YAML."""

    enabled: bool = True
    timeout_ms: int = 100


class Rule(BaseModel):
    """One conditional row in the policy. First match wins."""

    model_config = ConfigDict(populate_by_name=True)

    condition: str = Field(alias="if")
    action: Action
    reason: str | None = None
    apply_to: list[str] = Field(default_factory=list)


class Policy(BaseModel):
    """A complete policy document loaded from YAML."""

    version: int = 1
    detectors: dict[str, DetectorConfig] = Field(default_factory=dict)
    rules: list[Rule] = Field(default_factory=list)
    default_action: Action = Action.ALLOW
    degraded_action: Action = Action.BLOCK


def load_policy(path: Path) -> Policy:
    """Read a YAML policy from disk and validate it."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Policy.model_validate(data)
