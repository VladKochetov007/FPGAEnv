"""OpenEnv HTTP/WebSocket client for the FPGA environment."""

from __future__ import annotations

from typing import Any, Dict

from openenv.core.env_client import EnvClient, StepResult

from rlvr_envs.core.models import SubmissionState
from rlvr_envs.envs.fpga.models import FPGAAction, FPGAObservation


class FPGAEnvClient(EnvClient[FPGAAction, FPGAObservation, SubmissionState]):
    def _step_payload(self, action: FPGAAction) -> Dict[str, Any]:
        return action.model_dump()

    def _parse_result(self, payload: Dict[str, Any]) -> StepResult[FPGAObservation]:
        obs_data = payload.get("observation", payload)
        obs = FPGAObservation(**obs_data)
        return StepResult(
            observation=obs,
            reward=payload.get("reward", obs.reward),
            done=payload.get("done", obs.done),
        )

    def _parse_state(self, payload: Dict[str, Any]) -> SubmissionState:
        return SubmissionState(**payload)
