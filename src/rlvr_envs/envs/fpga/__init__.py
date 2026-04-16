"""FPGA / HDL environment: the LLM submits a Verilog module implementing a
fixed interface; the environment lints, simulates, verifies, and scores by
cycle count vs. a task-specific baseline."""

from rlvr_envs.envs.fpga.models import FPGAAction, FPGAObservation, FPGAState, FPGATask
from rlvr_envs.envs.fpga.environment import FPGAEnvironment
from rlvr_envs.envs.fpga.tasks import TASK_REGISTRY, get_task

__all__ = [
    "FPGAEnvironment",
    "FPGAAction",
    "FPGAObservation",
    "FPGAState",
    "FPGATask",
    "TASK_REGISTRY",
    "get_task",
]
