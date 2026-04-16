"""RLVR/GRPO environment suite for LLM training, built on Meta OpenEnv.

Library-first: each environment lives under `rlvr_envs.envs.<name>` and can be
used in three ways:

    * In-process via `.local.LocalEnv(...)` - fastest for GRPO rollouts and tests.
    * HTTP/WebSocket via `client.Client(base_url=...)` - standard OpenEnv.
    * Docker / UV via OpenEnv's provider system.

Every env returns a reward in [0, 1] using the hierarchical-gate scoring from
`rlvr_envs.core.scoring`: compile/verify failures score 0; valid submissions are
scored by a sigmoid over (T_baseline - T_current). Units (cycles, elapsed
seconds, instructions retired) are per-environment.
"""

from rlvr_envs.core.models import (
    SubmissionAction,
    SubmissionObservation,
    SubmissionState,
    Verdict,
)
from rlvr_envs.core.scoring import ScoringConfig, score_submission, sigmoid_speed_score

__all__ = [
    "SubmissionAction",
    "SubmissionObservation",
    "SubmissionState",
    "Verdict",
    "ScoringConfig",
    "score_submission",
    "sigmoid_speed_score",
]
