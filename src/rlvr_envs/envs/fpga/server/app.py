"""FastAPI app entrypoint for the FPGA environment.

Run locally with:

    .venv/bin/uvicorn rlvr_envs.envs.fpga.server.app:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import os

from openenv.core import create_app

from rlvr_envs.envs.fpga.environment import FPGAEnvironment
from rlvr_envs.envs.fpga.models import FPGAAction, FPGAObservation


env = FPGAEnvironment(
    default_task=os.environ.get("FPGA_DEFAULT_TASK", "popcount32"),
)

app = create_app(env, action_cls=FPGAAction, observation_cls=FPGAObservation)
