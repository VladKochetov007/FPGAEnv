"""Generates the C++ Verilator harness for a task.

The harness instantiates `Vdut`, loads test vectors from a binary file at
runtime (passed as argv[1]), and prints a machine-parseable summary:

    CASE <idx> <cycles> <result_hex>   // per case
    TOTAL_CYCLES <n>
    INCORRECT <idx>                     // on first miscompare
    TIMEOUT <idx>                       // if done never asserts
    OK                                   // only if every case passed

Vectors are a separate binary blob written per-seed:
    [uint32_t n_cases, in_bits, out_bits, max_cycles_per_case]
    [uint64_t input, uint64_t expected] * n_cases

Decoupling vectors from the compiled binary means a single build can be
re-tested against N different seed sets without recompiling.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from rlvr_envs.envs.fpga.models import FPGATask


@dataclass(frozen=True)
class HarnessFiles:
    tb_cpp: str


def render_harness(task: FPGATask) -> HarnessFiles:
    """Return sim_main.cpp for this task. Vectors are loaded at runtime."""
    return HarnessFiles(tb_cpp=_render_sim_main(task))


def write_vectors_bin(task: FPGATask, vectors: List[Tuple[int, int]], path: Path) -> None:
    """Serialize test vectors to a binary file consumed by the harness."""
    with open(path, "wb") as f:
        f.write(struct.pack("<4I", len(vectors), task.in_bits, task.out_bits, task.max_cycles_per_case))
        for inp, exp in vectors:
            f.write(struct.pack("<QQ", inp & ((1 << 64) - 1), exp & ((1 << 64) - 1)))


def _render_sim_main(task: FPGATask) -> str:
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
// Vectors loaded at runtime from argv[1] (binary format: see harness.py).
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include "Vdut.h"
#include "verilated.h"

struct TestCase {{ uint64_t input_word; uint64_t expected; }};

static inline void tick(Vdut* top) {{
    top->clk = 0; top->eval();
    top->clk = 1; top->eval();
}}

int main(int argc, char** argv) {{
    if (argc < 2) {{
        fprintf(stderr, "usage: Vdut <vectors.bin>\\n");
        return 1;
    }}

    FILE* vf = fopen(argv[1], "rb");
    if (!vf) {{ perror("open vectors"); return 1; }}

    uint32_t hdr[4];
    if (fread(hdr, sizeof(uint32_t), 4, vf) != 4) {{
        fprintf(stderr, "bad vectors header\\n"); return 1;
    }}
    size_t   n_cases           = hdr[0];
    unsigned max_cycles_per_case = hdr[3];

    TestCase* cases = (TestCase*)malloc(n_cases * sizeof(TestCase));
    if (fread(cases, sizeof(TestCase), n_cases, vf) != n_cases) {{
        fprintf(stderr, "short vectors body\\n"); return 1;
    }}
    fclose(vf);

    VerilatedContext ctx;
    ctx.commandArgs(argc, argv);
    Vdut top(&ctx);

    // Initial bring-up.
    top.clk = 0; top.rst = 1; top.start = 0; top.data_in = 0;
    top.eval();

    uint64_t total_cycles = 0;

    for (size_t c = 0; c < n_cases; ++c) {{
        // Reset between cases: a submission that accumulates hidden FSM state
        // across cases (online memorisation / sequence-prediction attack) loses
        // that state every case. Synchronous, active-high rst for 3 ticks.
        top.rst = 1; top.start = 0; top.data_in = 0;
        for (int i = 0; i < 3; ++i) tick(&top);
        top.rst = 0;
        tick(&top);

        top.data_in = ({in_type})(cases[c].input_word & 0x{in_mask:x}ULL);
        top.start   = 1;
        tick(&top);
        top.start   = 0;

        uint32_t cycles = 1;
        bool finished = top.done;
        while (!finished && cycles < max_cycles_per_case) {{
            tick(&top);
            ++cycles;
            finished = top.done;
        }}

        if (!finished) {{
            printf("TIMEOUT %zu\\n", c);
            printf("TOTAL_CYCLES %llu\\n", (unsigned long long)total_cycles);
            free(cases);
            return 1;
        }}

        {out_type} got  = ({out_type})(top.data_out) & ({out_type})0x{out_mask:x}ULL;
        {out_type} want = ({out_type})(cases[c].expected & 0x{out_mask:x}ULL);

        printf("CASE %zu %u 0x%llx\\n", c, cycles, (unsigned long long)got);

        if (got != want) {{
            printf("INCORRECT %zu want=0x%llx got=0x%llx\\n",
                   c, (unsigned long long)want, (unsigned long long)got);
            printf("TOTAL_CYCLES %llu\\n", (unsigned long long)total_cycles);
            free(cases);
            return 2;
        }}

        total_cycles += cycles;
        tick(&top);  // drain: let done drop before next start
    }}

    printf("TOTAL_CYCLES %llu\\n", (unsigned long long)total_cycles);
    printf("OK\\n");
    free(cases);
    return 0;
}}
"""
