"""In-process wrapper for running an RLVREnvironment without Docker/HTTP.

GRPO rollouts need to ingest hundreds of samples per second during training.
Going through WebSockets + Docker for each rollout is the wrong abstraction at
that scale. `LocalEnv` lets the training loop call `.reset()` / `.step(...)`
directly on a Python-native environment instance with the same surface area as
the remote `EnvClient`.

This is also what most of the unit/integration tests use: no network, no Docker,
and deterministic (given the env's seed handling).
"""

from __future__ import annotations

from typing import Any, Optional

from rlvr_envs.core.base_env import RLVREnvironment
from rlvr_envs.core.models import (
    SubmissionAction,
    SubmissionObservation,
    SubmissionState,
)


class LocalEnv:
    """Minimal sync surface over an `RLVREnvironment`."""

    def __init__(self, env: RLVREnvironment[Any]) -> None:
        self._env = env
        self._last_obs: Optional[SubmissionObservation] = None

    def reset(self, **kwargs: Any) -> SubmissionObservation:
        self._last_obs = self._env.reset(**kwargs)
        return self._last_obs

    def step(
        self,
        action: SubmissionAction,
        timeout_s: Optional[float] = None,
    ) -> SubmissionObservation:
        self._last_obs = self._env.step(action, timeout_s=timeout_s)
        return self._last_obs

    def state(self) -> SubmissionState:
        return self._env.state

    def __enter__(self) -> "LocalEnv":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None
