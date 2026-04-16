r"""Unified hierarchical scoring for verifiable-reward environments.

The scoring rule uses a ratio formula that is naturally scale-invariant:

                 /  0                                      if gate fails
    S(code)  = <   baseline / (baseline + measured)         if valid & correct
                 \  (clamped to [floor, ceiling])

Properties:
  - At measured = baseline  ->  S = 0.5  (reference-level solution)
  - As measured -> 0        ->  S -> 1.0 (perfect)
  - As measured -> inf      ->  S -> 0.0 (terrible)
  - Smooth, differentiable, no tuning parameter
  - Scale-invariant: same ratio measured/baseline gives same score
    regardless of absolute values

The module is deliberately free of any env-specific knowledge so it can be
reused for cycles, wall-clock seconds, bytes-out, cache-miss counts, or any
monotonic "lower is better" metric.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from rlvr_envs.core.models import Verdict


@dataclass(frozen=True)
class ScoringConfig:
    """Per-environment scoring parameters.

    - `baseline`: reference measurement (e.g. cycles of an unoptimized-but-
      correct implementation). Solutions matching baseline score 0.5.
    - `floor`: minimum reward for a correct-but-very-slow solution.
    - `ceiling`: maximum reward cap.
    """

    baseline: float
    floor: float = 0.0
    ceiling: float = 1.0


def speed_score(current: float, config: ScoringConfig) -> float:
    """S = baseline / (baseline + current), clamped to [floor, ceiling].

    `current` is any "lower is better" number on the same scale as `baseline`.
    """
    if not math.isfinite(current) or current < 0:
        return config.floor
    if config.baseline <= 0:
        return config.floor
    s = config.baseline / (config.baseline + current)
    return max(config.floor, min(config.ceiling, s))


def score_submission(
    verdict: Verdict,
    current: Optional[float],
    config: ScoringConfig,
) -> float:
    """Hard gate on verdict, then ratio score on the performance metric.

    Anything that didn't pass the correctness gate (compile error, incorrect
    result, timeout, memory-limit, forbidden construct) scores exactly 0.
    `INTERNAL_ERROR` also scores 0 but callers should flag these so they can be
    excluded from training batches.
    """
    if verdict != Verdict.OK:
        return 0.0
    if current is None:
        return config.floor
    return speed_score(current, config)
