from __future__ import annotations

import math

import pytest

from rlvr_envs.core.scoring import ScoringConfig, score_submission, sigmoid_speed_score
from rlvr_envs.core.models import Verdict


class TestSigmoidSpeedScore:
    def test_at_baseline_returns_half(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        assert sigmoid_speed_score(100.0, cfg) == pytest.approx(0.5)

    def test_much_faster_approaches_one(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        assert sigmoid_speed_score(0.0, cfg) > 0.99

    def test_much_slower_approaches_zero(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        assert sigmoid_speed_score(1000.0, cfg) < 0.01

    def test_floor_enforced(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0, floor=0.1)
        score = sigmoid_speed_score(10_000.0, cfg)
        assert score >= 0.1

    def test_ceiling_enforced(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0, ceiling=0.8)
        score = sigmoid_speed_score(0.0, cfg)
        assert score <= 0.8

    def test_floor_and_ceiling_together(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0, floor=0.2, ceiling=0.7)
        assert sigmoid_speed_score(10_000.0, cfg) == pytest.approx(0.2)
        assert sigmoid_speed_score(0.0, cfg) == pytest.approx(0.7)

    def test_negative_input_returns_floor(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0, floor=0.05)
        assert sigmoid_speed_score(-1.0, cfg) == 0.05

    def test_nan_input_returns_floor(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0, floor=0.0)
        assert sigmoid_speed_score(float("nan"), cfg) == 0.0

    def test_inf_input_returns_floor(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0, floor=0.0)
        assert sigmoid_speed_score(float("inf"), cfg) == 0.0

    def test_negative_inf_returns_floor(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0, floor=0.0)
        assert sigmoid_speed_score(float("-inf"), cfg) == 0.0

    def test_k_zero_always_half(self):
        cfg = ScoringConfig(baseline=100.0, k=0.0)
        assert sigmoid_speed_score(0.0, cfg) == pytest.approx(0.5)
        assert sigmoid_speed_score(100.0, cfg) == pytest.approx(0.5)
        assert sigmoid_speed_score(999.0, cfg) == pytest.approx(0.5)

    def test_large_k_acts_like_step_function(self):
        cfg = ScoringConfig(baseline=100.0, k=100.0)
        assert sigmoid_speed_score(99.0, cfg) > 0.99
        assert sigmoid_speed_score(101.0, cfg) < 0.01

    def test_monotonically_decreasing_with_current(self):
        cfg = ScoringConfig(baseline=100.0, k=0.1)
        scores = [sigmoid_speed_score(float(c), cfg) for c in range(0, 200, 10)]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]

    def test_zero_current_high_score(self):
        cfg = ScoringConfig(baseline=1000.0, k=0.01)
        assert sigmoid_speed_score(0.0, cfg) > 0.5


class TestScoreSubmission:
    def test_ok_verdict_scores_sigmoid(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        assert score_submission(Verdict.OK, 100.0, cfg) == pytest.approx(0.5)

    def test_compile_error_scores_zero(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        assert score_submission(Verdict.COMPILE_ERROR, 50.0, cfg) == 0.0

    def test_incorrect_scores_zero(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        assert score_submission(Verdict.INCORRECT, 10.0, cfg) == 0.0

    def test_timeout_scores_zero(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        assert score_submission(Verdict.TIMEOUT, 10.0, cfg) == 0.0

    def test_memory_limit_scores_zero(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        assert score_submission(Verdict.MEMORY_LIMIT, 10.0, cfg) == 0.0

    def test_forbidden_scores_zero(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        assert score_submission(Verdict.FORBIDDEN, 10.0, cfg) == 0.0

    def test_internal_error_scores_zero(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        assert score_submission(Verdict.INTERNAL_ERROR, 10.0, cfg) == 0.0

    def test_ok_with_none_metric_returns_floor(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0, floor=0.05)
        assert score_submission(Verdict.OK, None, cfg) == 0.05

    def test_ok_with_none_metric_default_floor(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        assert score_submission(Verdict.OK, None, cfg) == 0.0

    def test_all_non_ok_verdicts_score_zero(self):
        cfg = ScoringConfig(baseline=100.0, k=1.0)
        for v in Verdict:
            if v == Verdict.OK:
                continue
            assert score_submission(v, 1.0, cfg) == 0.0
