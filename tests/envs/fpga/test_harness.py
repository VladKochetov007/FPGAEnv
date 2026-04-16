from __future__ import annotations

import pytest

from rlvr_envs.envs.fpga.harness import render_harness
from rlvr_envs.envs.fpga.models import FPGATask
from rlvr_envs.envs.fpga.tasks import TASK_REGISTRY, get_task


def _make_task(name="test_task", in_bits=32, out_bits=16):
    return FPGATask(
        name=name,
        in_bits=in_bits,
        out_bits=out_bits,
        baseline_cycles=100,
        max_cycles_per_case=64,
        prompt="test",
        reference_py=lambda x: x & 0xFFFF,
        vectors=lambda seed: [(i, i & 0xFFFF) for i in range(10)],
    )


class TestRenderHarness:
    def test_produces_nonempty_files(self):
        task = _make_task()
        vectors = task.vectors(0)
        h = render_harness(task, vectors)
        assert len(h.tb_cpp) > 0
        assert len(h.vectors_h) > 0

    def test_vectors_h_contains_correct_count(self):
        task = _make_task()
        vectors = task.vectors(0)
        h = render_harness(task, vectors)
        assert f"N_CASES = {len(vectors)}" in h.vectors_h

    def test_vectors_h_contains_all_test_cases(self):
        task = _make_task()
        vectors = task.vectors(0)
        h = render_harness(task, vectors)
        for inp, exp in vectors:
            assert f"0x{inp:016x}ULL" in h.vectors_h
            assert f"0x{exp:016x}ULL" in h.vectors_h

    def test_vectors_h_has_correct_bit_widths(self):
        task = _make_task(in_bits=24, out_bits=8)
        h = render_harness(task, [(0, 0)])
        assert "IN_BITS = 24" in h.vectors_h
        assert "OUT_BITS = 8" in h.vectors_h

    def test_sim_main_includes_vectors_h(self):
        task = _make_task()
        h = render_harness(task, [(0, 0)])
        assert '#include "vectors.h"' in h.tb_cpp

    def test_sim_main_includes_vdut(self):
        task = _make_task()
        h = render_harness(task, [(0, 0)])
        assert '#include "Vdut.h"' in h.tb_cpp

    def test_sim_main_prints_ok_on_success(self):
        task = _make_task()
        h = render_harness(task, [(0, 0)])
        assert 'printf("OK\\n")' in h.tb_cpp

    def test_sim_main_prints_incorrect_on_mismatch(self):
        task = _make_task()
        h = render_harness(task, [(0, 0)])
        assert "INCORRECT" in h.tb_cpp

    def test_sim_main_prints_timeout(self):
        task = _make_task()
        h = render_harness(task, [(0, 0)])
        assert "TIMEOUT" in h.tb_cpp


class TestTaskWidthVariants:
    def test_1bit_output_ray_hit(self):
        task = get_task("ray_hit_2d")
        assert task.out_bits == 1
        vectors = task.vectors(42)
        h = render_harness(task, vectors)
        assert "OUT_BITS = 1" in h.vectors_h
        assert "uint32_t" in h.tb_cpp

    def test_32bit_output_div16(self):
        task = get_task("div16")
        assert task.out_bits == 32
        vectors = task.vectors(42)
        h = render_harness(task, vectors)
        assert "OUT_BITS = 32" in h.vectors_h

    def test_6bit_output_popcount(self):
        task = get_task("popcount32")
        assert task.out_bits == 6
        vectors = task.vectors(42)
        h = render_harness(task, vectors)
        assert "OUT_BITS = 6" in h.vectors_h

    def test_24bit_input_matvec(self):
        task = get_task("matvec_2x2_int4")
        assert task.in_bits == 24
        vectors = task.vectors(42)
        h = render_harness(task, vectors)
        assert "IN_BITS = 24" in h.vectors_h


class TestRealTaskHarness:
    @pytest.mark.parametrize("task_name", list(TASK_REGISTRY.keys()))
    def test_every_task_renders_valid_harness(self, task_name):
        task = get_task(task_name)
        vectors = task.vectors(0)
        h = render_harness(task, vectors)
        assert f"N_CASES = {len(vectors)}" in h.vectors_h
        assert f"IN_BITS = {task.in_bits}" in h.vectors_h
        assert f"OUT_BITS = {task.out_bits}" in h.vectors_h
        assert f"MAX_CYCLES_PER_CASE = {task.max_cycles_per_case}" in h.vectors_h
        assert "Vdut" in h.tb_cpp
