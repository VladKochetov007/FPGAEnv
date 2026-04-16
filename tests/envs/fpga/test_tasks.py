from __future__ import annotations

import pytest

from rlvr_envs.envs.fpga.tasks import TASK_REGISTRY, get_task

EXPECTED_TASKS = [
    "popcount32", "bitrev16", "gcd16", "mul8", "div16", "isqrt32",
    "crc8", "xor_cipher16", "adler32", "matvec_2x2_int4", "ray_hit_2d",
    "arbiter_rr",
]


class TestTaskRegistryCoverage:
    def test_all_12_tasks_present(self):
        assert len(TASK_REGISTRY) == 12

    @pytest.mark.parametrize("name", EXPECTED_TASKS)
    def test_task_in_registry(self, name):
        assert name in TASK_REGISTRY

    def test_get_task_unknown_raises(self):
        with pytest.raises(KeyError, match="unknown fpga task"):
            get_task("nonexistent_task")


class TestReferenceConsistency:
    @pytest.mark.parametrize("name", EXPECTED_TASKS)
    def test_reference_py_matches_vectors(self, name):
        task = get_task(name)
        vectors = task.vectors(42)
        for inp, expected in vectors:
            assert task.reference_py(inp) == expected, (
                f"task={name} input=0x{inp:x} expected=0x{expected:x} "
                f"got=0x{task.reference_py(inp):x}"
            )


class TestVectorDeterminism:
    @pytest.mark.parametrize("name", EXPECTED_TASKS)
    def test_same_seed_same_vectors(self, name):
        task = get_task(name)
        v1 = task.vectors(123)
        v2 = task.vectors(123)
        assert v1 == v2

    @pytest.mark.parametrize("name", EXPECTED_TASKS)
    def test_different_seeds_different_vectors(self, name):
        task = get_task(name)
        v1 = task.vectors(0)
        v2 = task.vectors(999)
        assert v1 != v2


class TestTaskProperties:
    @pytest.mark.parametrize("name", EXPECTED_TASKS)
    def test_positive_bit_widths(self, name):
        task = get_task(name)
        assert task.in_bits > 0
        assert task.out_bits > 0

    @pytest.mark.parametrize("name", EXPECTED_TASKS)
    def test_positive_baseline_cycles(self, name):
        task = get_task(name)
        assert task.baseline_cycles > 0

    @pytest.mark.parametrize("name", EXPECTED_TASKS)
    def test_nonempty_prompt(self, name):
        task = get_task(name)
        assert len(task.prompt) > 0
        assert "module dut" in task.prompt

    @pytest.mark.parametrize("name", EXPECTED_TASKS)
    def test_vectors_nonempty(self, name):
        task = get_task(name)
        vectors = task.vectors(0)
        assert len(vectors) > 0

    @pytest.mark.parametrize("name", EXPECTED_TASKS)
    def test_outputs_fit_in_declared_width(self, name):
        task = get_task(name)
        mask = (1 << task.out_bits) - 1
        for _, expected in task.vectors(42):
            assert expected == (expected & mask), (
                f"task={name} output 0x{expected:x} exceeds {task.out_bits} bits"
            )

    @pytest.mark.parametrize("name", EXPECTED_TASKS)
    def test_inputs_fit_in_declared_width(self, name):
        task = get_task(name)
        mask = (1 << task.in_bits) - 1
        for inp, _ in task.vectors(42):
            assert inp == (inp & mask), (
                f"task={name} input 0x{inp:x} exceeds {task.in_bits} bits"
            )
