"""Abstract OpenEnv environment base for all RLVR tasks in this suite.

Every concrete env only has to implement `_reset_task` (pick a task, return the
prompt the LLM should see) and `_grade` (score one submission). Everything else
— uuid/episode accounting, state mirroring, default verdict handling, prompt
echoing, done-flag logic — lives here. This keeps task code tight and
pattern-uniform, which matters when the training harness runs dozens of envs
side-by-side.

We deliberately treat each episode as a single grading step (reset -> step ->
done). Multi-turn tool-use is a separate base class that would sit alongside
this one; not building that now because GRPO group rollouts are single-shot.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, Optional, TypeVar
from uuid import uuid4

from openenv.core.env_server import Environment

from rlvr_envs.core.models import (
    SubmissionAction,
    SubmissionObservation,
    SubmissionState,
    Verdict,
)

TaskT = TypeVar("TaskT")


@dataclass
class GradingResult:
    """What `_grade` returns. `score` already accounts for the hard gate: if
    verdict != OK, score must be 0. We re-check in the base class to keep that
    invariant uniform across envs."""

    verdict: Verdict
    score: float
    raw_metric: Optional[float] = None
    baseline_metric: Optional[float] = None
    stdout: str = ""
    stderr: str = ""
    details: Optional[dict] = None


class RLVREnvironment(
    Environment[SubmissionAction, SubmissionObservation, SubmissionState],
    Generic[TaskT],
):
    """Base for envs that grade a single free-form submission per episode."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self) -> None:
        super().__init__()
        self._state = SubmissionState(episode_id=str(uuid4()), step_count=0)
        self._current_task: Optional[TaskT] = None
        self._current_prompt: str = ""

    @property
    def state(self) -> SubmissionState:
        return self._state

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SubmissionObservation:
        self._state = SubmissionState(
            episode_id=episode_id or str(uuid4()),
            step_count=0,
            task_id=task_id,
        )
        task, prompt = self._reset_task(seed=seed, task_id=task_id, **kwargs)
        self._current_task = task
        self._current_prompt = prompt
        return SubmissionObservation(
            verdict=Verdict.OK,
            score=0.0,
            prompt=prompt,
            done=False,
            reward=0.0,
            metadata={"episode_id": self._state.episode_id},
        )

    def step(
        self,
        action: SubmissionAction,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> SubmissionObservation:
        if self._current_task is None:
            raise RuntimeError("step() called before reset(); no active task")

        self._state.step_count += 1

        graded = self._grade(action, self._current_task, timeout_s=timeout_s)
        # Enforce the hard-gate invariant in one place: if the env miscalculated
        # and a non-OK verdict sneaked through with score > 0, zero it.
        score = graded.score if graded.verdict == Verdict.OK else 0.0
        score = max(0.0, min(1.0, score))

        self._state.last_verdict = graded.verdict
        self._state.last_score = score

        return SubmissionObservation(
            verdict=graded.verdict,
            score=score,
            raw_metric=graded.raw_metric,
            baseline_metric=graded.baseline_metric,
            prompt=self._current_prompt,
            stdout=graded.stdout,
            stderr=graded.stderr,
            details=graded.details or {},
            done=True,  # single-step episode: one grading per reset
            reward=score,
            metadata={"episode_id": self._state.episode_id},
        )

    @abstractmethod
    def _reset_task(
        self, *, seed: Optional[int], task_id: Optional[str], **kwargs: Any
    ) -> tuple[TaskT, str]:
        """Return `(task_spec, human_readable_prompt)` for the new episode."""

    @abstractmethod
    def _grade(
        self,
        action: SubmissionAction,
        task: TaskT,
        *,
        timeout_s: Optional[float] = None,
    ) -> GradingResult:
        """Score the submission. Must uphold: verdict != OK ⇒ score == 0."""
