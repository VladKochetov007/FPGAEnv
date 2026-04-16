r"""Unified hierarchical scoring for verifiable-reward environments.

The scoring rule is the one discussed in task.md:

                 /  0                                           if gate fails
    S(code)  = <   sigmoid( k * (T_baseline - T_current) )      if valid & correct
                 \  (clamped to [0, 1])

We keep a tiny data class (`ScoringConfig`) per-environment so baselines and the
sigmoid steepness can be tuned without editing library code. The module is
deliberately free of any env-specific knowledge so it can be reused for cycles,
wall-clock seconds, bytes-out, cache-miss counts, or any monotonic "lower is
better" metric.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from rlvr_envs.core.models import Verdict


@dataclass(frozen=True)
class ScoringConfig:
    """Per-environment scoring parameters.

    `baseline` is the reference measurement (e.g. cycles an unoptimized-but-
    correct reference implementation takes). `k` controls how sharp the reward
    cliff around the baseline is: too high and GRPO sees a step function; too
    low and a 10x speedup barely moves the reward.

    `floor` lets a submission earn a tiny-but-nonzero reward even if it fails
    just the perf bar (correct + compiled) — useful early in training so GRPO
    doesn't collapse when every rollout in the group happens to be slower than
    the baseline.
    """

    baseline: float
    k: float = 1.0
    floor: float = 0.0
    ceiling: float = 1.0


def sigmoid_speed_score(current: float, config: ScoringConfig) -> float:
    """S = sigmoid(k * (baseline - current)), clamped to [floor, ceiling].

    `current` is any "lower is better" number on the same scale as `baseline`.
    """
    if not math.isfinite(current) or current < 0:
        return config.floor
    x = config.k * (config.baseline - current)
    # Numerically stable sigmoid: avoid overflow for very negative x.
    if x >= 0:
        s = 1.0 / (1.0 + math.exp(-x))
    else:
        ex = math.exp(x)
        s = ex / (1.0 + ex)
    return max(config.floor, min(config.ceiling, s))


def score_submission(
    verdict: Verdict,
    current: Optional[float],
    config: ScoringConfig,
) -> float:
    """Hard gate on verdict, then sigmoid on the performance metric.

    Anything that didn't pass the correctness gate (compile error, incorrect
    result, timeout, memory-limit, forbidden construct) scores exactly 0.
    `INTERNAL_ERROR` also scores 0 but callers should flag these so they can be
    excluded from training batches — a crash in the env itself is not a signal
    about the model.
    """
    if verdict != Verdict.OK:
        return 0.0
    if current is None:
        return config.floor
    return sigmoid_speed_score(current, config)
