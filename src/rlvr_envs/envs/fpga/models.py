"""Typed contracts for the FPGA environment.

We extend the shared submission models rather than redefining them so that
mixed-env training loops can treat every RLVR env uniformly. The FPGA env only
adds a `FPGATask` dataclass describing the chosen task (ports, test vectors,
baseline cycle count) — that's not sent over the wire, it's internal bookkeeping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple

from rlvr_envs.core.models import (
    SubmissionAction as FPGAAction,
    SubmissionObservation as FPGAObservation,
    SubmissionState as FPGAState,
)


TestVectorFn = Callable[[int], List[Tuple[int, int]]]
"""seed -> list of (input_word, expected_output_word) test cases."""


@dataclass(frozen=True)
class FPGATask:
    """Describes a single HDL task.

    * `name`                  — stable task id (used in prompts and registry).
    * `in_bits` / `out_bits`  — widths of `data_in` and `data_out`.
    * `baseline_cycles`       — cycle count of a reference naive implementation
                                across the default vector set; sigmoid center.
    * `max_cycles_per_case`   — timeout enforced by the testbench per vector.
    * `prompt`                — human-readable spec shown to the LLM.
    * `reference_py`          — Python oracle to derive expected outputs (also
                                used by the mock scorer in tests).
    * `vectors`               — test-vector generator keyed by seed.
    """

    name: str
    in_bits: int
    out_bits: int
    baseline_cycles: int
    max_cycles_per_case: int
    prompt: str
    reference_py: Callable[[int], int]
    vectors: TestVectorFn


__all__ = ["FPGAAction", "FPGAObservation", "FPGAState", "FPGATask", "TestVectorFn"]
