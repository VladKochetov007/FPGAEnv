from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import pytest

from rlvr_envs.envs.fpga.harness import render_harness, write_vectors_bin
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
    def test_produces_nonempty_cpp(self):
        task = _make_task()
        h = render_harness(task)
        assert len(h.tb_cpp) > 0

    def test_sim_main_includes_vdut(self):
        task = _make_task()
        h = render_harness(task)
        assert '#include "Vdut.h"' in h.tb_cpp

    def test_sim_main_prints_ok_on_success(self):
        task = _make_task()
        h = render_harness(task)
        assert 'printf("@@H@@OK\\n")' in h.tb_cpp

    def test_sim_main_prints_incorrect_on_mismatch(self):
        task = _make_task()
        h = render_harness(task)
        assert "@@H@@INCORRECT" in h.tb_cpp

    def test_sim_main_prints_timeout(self):
        task = _make_task()
        h = render_harness(task)
        assert "@@H@@TIMEOUT" in h.tb_cpp

    def test_sim_main_reads_vectors_at_runtime(self):
        task = _make_task()
        h = render_harness(task)
        assert "fopen" in h.tb_cpp
        assert "argv[1]" in h.tb_cpp

    def test_sim_main_does_not_embed_vectors(self):
        task = _make_task()
        h = render_harness(task)
        assert "TEST_CASES" not in h.tb_cpp
        assert "0x0000000000000000ULL" not in h.tb_cpp

    def test_task_name_in_comment(self):
        task = _make_task(name="my_task")
        h = render_harness(task)
        assert "my_task" in h.tb_cpp

    def test_resets_between_cases(self):
        """Anti-reward-hack: each case must start from rst, breaking any
        hidden FSM state a submission might carry across cases."""
        task = _make_task()
        h = render_harness(task)
        loop_idx = h.tb_cpp.find("for (size_t c = 0; c < n_cases;")
        assert loop_idx != -1, "per-case loop missing"
        assert "top.rst = 1;" in h.tb_cpp[loop_idx:], \
            "rst not asserted inside per-case loop"


class TestWriteVectorsBin:
    def test_roundtrip_header(self):
        task = _make_task(in_bits=24, out_bits=8)
        vectors = [(0xABCDEF, 0x12), (0x000001, 0xFF)]
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            path = Path(f.name)
        write_vectors_bin(task, vectors, path)

        data = path.read_bytes()
        n, ib, ob, mc = struct.unpack_from("<4I", data, 0)
        assert n == 2
        assert ib == 24
        assert ob == 8
        assert mc == task.max_cycles_per_case

    def test_roundtrip_cases(self):
        task = _make_task()
        vectors = [(0xDEADBEEF, 0x1234), (0x00000001, 0x0001)]
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            path = Path(f.name)
        write_vectors_bin(task, vectors, path)

        data = path.read_bytes()
        offset = 4 * 4  # skip header
        for inp, exp in vectors:
            a, b = struct.unpack_from("<QQ", data, offset)
            assert a == inp
            assert b == exp
            offset += 16

    def test_file_size(self):
        task = _make_task()
        vectors = [(i, i) for i in range(32)]
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            path = Path(f.name)
        write_vectors_bin(task, vectors, path)
        # 4 uint32s header + 32 * (uint64 + uint64)
        assert path.stat().st_size == 4 * 4 + 32 * 16

    def test_large_64bit_values(self):
        task = FPGATask(
            name="t", in_bits=64, out_bits=64, baseline_cycles=10,
            max_cycles_per_case=32, prompt="",
            reference_py=lambda x: x, vectors=lambda s: [],
        )
        vectors = [(0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF)]
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            path = Path(f.name)
        write_vectors_bin(task, vectors, path)
        data = path.read_bytes()
        a, b = struct.unpack_from("<QQ", data, 16)
        assert a == 0xFFFFFFFFFFFFFFFF
        assert b == 0xFFFFFFFFFFFFFFFF


class TestTaskWidthVariants:
    def test_1bit_output_ray_hit(self):
        task = get_task("ray_hit_2d")
        h = render_harness(task)
        assert "uint32_t" in h.tb_cpp

    def test_32bit_output_div16(self):
        task = get_task("div16")
        h = render_harness(task)
        assert h.tb_cpp  # just renders without error

    def test_6bit_output_popcount(self):
        task = get_task("popcount32")
        h = render_harness(task)
        assert "0x3fULL" in h.tb_cpp  # mask for 6 bits

    def test_24bit_input_matvec(self):
        task = get_task("matvec_2x2_int4")
        h = render_harness(task)
        assert "0xffffffULL" in h.tb_cpp  # mask for 24 bits


class TestRealTaskHarness:
    @pytest.mark.parametrize("task_name", list(TASK_REGISTRY.keys()))
    def test_every_task_renders_valid_harness(self, task_name):
        task = get_task(task_name)
        h = render_harness(task)
        assert "Vdut" in h.tb_cpp
        assert "fopen" in h.tb_cpp
        assert "TOTAL_CYCLES" in h.tb_cpp

    @pytest.mark.parametrize("task_name", list(TASK_REGISTRY.keys()))
    def test_every_task_vectors_bin_roundtrip(self, task_name):
        task = get_task(task_name)
        vectors = task.vectors(0)
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            path = Path(f.name)
        write_vectors_bin(task, vectors, path)
        data = path.read_bytes()
        n, ib, ob, mc = struct.unpack_from("<4I", data, 0)
        assert n == len(vectors)
        assert ib == task.in_bits
        assert ob == task.out_bits
        assert mc == task.max_cycles_per_case
