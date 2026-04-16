"""Generates the C++ Verilator harness and test-vector header for a task.

The harness instantiates `Vdut`, applies every (input, expected) pair, and
prints a machine-parseable summary that the scorer reads back:

    CASE <idx> <cycles> <result_hex>   // per case
    TOTAL_CYCLES <n>
    INCORRECT <idx>                     // on first miscompare
    TIMEOUT <idx>                       // if done never asserts
    OK                                   // only if every case passed

Everything runs in obj_dir under a per-episode temp root, so concurrent episodes
do not step on each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from rlvr_envs.envs.fpga.models import FPGATask


@dataclass(frozen=True)
class HarnessFiles:
    tb_cpp: str
    vectors_h: str


def render_harness(task: FPGATask, vectors: List[Tuple[int, int]]) -> HarnessFiles:
    """Return the source of `sim_main.cpp` and `vectors.h` for this task."""
    vectors_h = _render_vectors_header(task, vectors)
    tb = _render_sim_main(task)
    return HarnessFiles(tb_cpp=tb, vectors_h=vectors_h)


def _render_vectors_header(task: FPGATask, vectors: List[Tuple[int, int]]) -> str:
    # Use hex literals so 64-bit inputs survive C++ integer promotion.
    lines = [
        "// Auto-generated; do not edit.",
        "#pragma once",
        "#include <cstdint>",
        "#include <cstddef>",
        "",
        f"static constexpr size_t N_CASES = {len(vectors)};",
        f"static constexpr unsigned IN_BITS = {task.in_bits};",
        f"static constexpr unsigned OUT_BITS = {task.out_bits};",
        f"static constexpr unsigned MAX_CYCLES_PER_CASE = {task.max_cycles_per_case};",
        "",
        "struct TestCase { uint64_t input_word; uint64_t expected; };",
        "",
        "static const TestCase TEST_CASES[N_CASES] = {",
    ]
    for inp, exp in vectors:
        lines.append(f"    {{ 0x{inp:016x}ULL, 0x{exp:016x}ULL }},")
    lines.append("};")
    return "\n".join(lines) + "\n"


def _render_sim_main(task: FPGATask) -> str:
    # Pick a wide-enough C type for data_in / data_out. Verilator maps <=32b to
    # uint32_t, 33..64 to uint64_t, and >64 to VlWide; we stay <=64 for now.
    if task.in_bits <= 32:
        in_type, in_mask = "uint32_t", (1 << task.in_bits) - 1
    else:
        in_type, in_mask = "uint64_t", (1 << task.in_bits) - 1
    if task.out_bits <= 32:
        out_type = "uint32_t"
    else:
        out_type = "uint64_t"
    out_mask = (1 << task.out_bits) - 1

    return f"""// Auto-generated Verilator testbench for task {task.name!r}.
#include <cstdio>
#include <cstdint>
#include "Vdut.h"
#include "verilated.h"
#include "vectors.h"

static inline void tick(Vdut* top) {{
    top->clk = 0; top->eval();
    top->clk = 1; top->eval();
}}

int main(int argc, char** argv) {{
    VerilatedContext ctx;
    ctx.commandArgs(argc, argv);
    Vdut top(&ctx);

    // Synchronous reset for 3 cycles.
    top.clk = 0; top.rst = 1; top.start = 0; top.data_in = 0;
    top.eval();
    for (int i = 0; i < 3; ++i) tick(&top);
    top.rst = 0;
    tick(&top);

    uint64_t total_cycles = 0;

    for (size_t c = 0; c < N_CASES; ++c) {{
        // Pulse `start` for one cycle with the input latched, then read
        // `done` BEFORE the next tick so 1-cycle combinational-ish DUTs (which
        // drive `done` from a register clocked by the start pulse itself) are
        // not missed.
        top.data_in = ({in_type})(TEST_CASES[c].input_word & 0x{in_mask:x}ULL);
        top.start   = 1;
        tick(&top);
        top.start   = 0;

        uint32_t cycles = 1;
        bool finished = top.done;
        while (!finished && cycles < MAX_CYCLES_PER_CASE) {{
            tick(&top);
            ++cycles;
            finished = top.done;
        }}

        if (!finished) {{
            printf("TIMEOUT %zu\\n", c);
            printf("TOTAL_CYCLES %llu\\n", (unsigned long long)total_cycles);
            return 1;
        }}

        {out_type} got = ({out_type})(top.data_out) & ({out_type})0x{out_mask:x}ULL;
        {out_type} want = ({out_type})(TEST_CASES[c].expected & 0x{out_mask:x}ULL);

        printf("CASE %zu %u 0x%llx\\n",
               c, cycles, (unsigned long long)got);

        if (got != want) {{
            printf("INCORRECT %zu want=0x%llx got=0x%llx\\n",
                   c, (unsigned long long)want, (unsigned long long)got);
            printf("TOTAL_CYCLES %llu\\n", (unsigned long long)total_cycles);
            return 2;
        }}

        total_cycles += cycles;

        // Drain one cycle so `done` has time to drop before next start.
        tick(&top);
    }}

    printf("TOTAL_CYCLES %llu\\n", (unsigned long long)total_cycles);
    printf("OK\\n");
    return 0;
}}
"""
