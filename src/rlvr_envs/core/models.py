"""Shared Pydantic contract for every RLVR environment in this suite.

Every environment in the suite accepts a single free-form source submission and
returns a structured grading result. Environments add their own task-description
payload via `reset(...)` and may extend these models with extra fields, but
every environment preserves the invariants:

    * `SubmissionAction.source` is the model's complete code/answer.
    * `SubmissionObservation.reward` is in [0, 1].
    * `SubmissionObservation.verdict` explains why the score is what it is.

Keeping this narrow on purpose: GRPO rollouts are cheaper when every env has the
same action shape, and a uniform observation schema lets training loops batch
environments without case analysis.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from openenv.core.env_server import Action, Observation, State
from pydantic import Field


class Verdict(str, Enum):
    """Hierarchical verdict; only `OK` is scored on the sigmoid axis.

    Anything coarser than OK forces reward = 0 (hard gate), which matches the
    "compile-fail / wrong answer -> 0" convention the rest of the scoring stack
    assumes.
    """

    OK = "ok"
    COMPILE_ERROR = "compile_error"
    INCORRECT = "incorrect"
    TIMEOUT = "timeout"
    MEMORY_LIMIT = "memory_limit"
    FORBIDDEN = "forbidden"          # tripped a reward-hack guard
    INTERNAL_ERROR = "internal_error"  # env itself failed; do NOT train on this


class SubmissionAction(Action):
    """LLM-submitted source code plus an optional language hint."""

    source: str = Field(..., description="Full source code / answer submitted by the model")
    language: Optional[str] = Field(
        default=None,
        description="Language hint ('python', 'verilog', ...); envs may override or ignore",
    )
    extras: Dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form action metadata (e.g., chosen algorithm variant)",
    )


class SubmissionObservation(Observation):
    """Unified grading result.

    `reward` is the final scalar in [0, 1] (already gated). `raw_metric` is the
    pre-sigmoid performance number (cycles, seconds, bytes, ...) so downstream
    analyses can re-score with a different sigmoid without re-running the env.
    """

    verdict: Verdict = Field(default=Verdict.INTERNAL_ERROR)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_metric: Optional[float] = Field(
        default=None,
        description="Pre-sigmoid performance measurement, units defined per env",
    )
    baseline_metric: Optional[float] = Field(default=None)
    prompt: Optional[str] = Field(default=None, description="Task prompt (echoed for logging)")
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    details: Dict[str, Any] = Field(default_factory=dict)


class SubmissionState(State):
    """Minimal persistent state: episode id, step count, last grading."""

    task_id: Optional[str] = Field(default=None)
    last_verdict: Optional[Verdict] = Field(default=None)
    last_score: float = Field(default=0.0)
