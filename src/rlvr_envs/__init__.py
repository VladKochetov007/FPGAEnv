"""RLVR/GRPO environment suite for LLM training on FPGA/HDL design tasks.

Library-first: tasks live under `rlvr_envs.envs.fpga` and can be used in three
ways:

    * In-process via `LocalEnv(env)` - fastest for GRPO rollouts and tests.
    * HTTP/WebSocket via `FPGAEnvClient(base_url=...)` - standard OpenEnv.
    * Docker / UV via OpenEnv's provider system.

Every task returns a reward in [0, 1] using hierarchical-gate scoring: compile
and correctness failures score 0; valid submissions are scored by a ratio
formula S = baseline / (baseline + measured).
"""

from rlvr_envs.core.models import (
    SubmissionAction,
    SubmissionObservation,
    SubmissionState,
    Verdict,
)
from rlvr_envs.core.scoring import ScoringConfig, score_submission, speed_score

__all__ = [
    "SubmissionAction",
    "SubmissionObservation",
    "SubmissionState",
    "Verdict",
    "ScoringConfig",
    "score_submission",
    "speed_score",
]
