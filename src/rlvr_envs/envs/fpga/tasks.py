"""Catalogue of FPGA tasks with their reference implementations.

Every task exposes the same module signature so the C++ harness is one file:

    module dut(
        input              clk,
        input              rst,        // synchronous, active-high
        input              start,      // pulse high for 1 cycle to latch data_in
        input  [IW-1:0]    data_in,
        output [OW-1:0]    data_out,
        output             done        // high when data_out is stable
    );

The LLM must produce the body of `dut`. Cycles are counted from the cycle
`start` is asserted until `done` goes high. Fewer cycles -> higher reward.
"""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

from rlvr_envs.envs.fpga.models import FPGATask


def _popcount(x: int) -> int:
    return bin(x & 0xFFFF_FFFF).count("1")


def _popcount32_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    # Deterministic mix: corner cases first, then random.
    corners = [0, 0xFFFFFFFF, 0x55555555, 0xAAAAAAAA, 1, 1 << 31]
    rand = [rng.randrange(0, 1 << 32) for _ in range(26)]
    return [(v, _popcount(v)) for v in corners + rand]


POPCOUNT32 = FPGATask(
    name="popcount32",
    in_bits=32,
    out_bits=6,
    baseline_cycles=32 * 32,  # naive one-bit-per-cycle shifter: 32 cycles per case
    max_cycles_per_case=128,
    prompt=(
        "Implement Verilog module `dut` with the interface below.\n"
        "`data_in` is 32 bits, `data_out` is 6 bits and must equal the number of\n"
        "bits set to 1 in `data_in`. Assert `done` as soon as `data_out` is\n"
        "valid and hold it until the next `start` pulse. Reset is synchronous,\n"
        "active-high. Fewer cycles between `start` and `done` score higher.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output [5:0]       data_out,\n"
        "    output             done\n"
        ");\n"
    ),
    reference_py=_popcount,
    vectors=_popcount32_vectors,
)


def _gcd(a: int) -> int:
    # Packed encoding: hi 16 bits = x, lo 16 bits = y.
    x = (a >> 16) & 0xFFFF
    y = a & 0xFFFF
    while y:
        x, y = y, x % y
    return x & 0xFFFF


def _gcd_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases = [
        ((12 << 16) | 18),
        ((1 << 16) | 1),
        ((1000 << 16) | 7),
        ((0xFFFF << 16) | 1),
    ]
    for _ in range(20):
        x = rng.randrange(1, 1 << 16)
        y = rng.randrange(1, 1 << 16)
        cases.append((x << 16) | y)
    return [(v, _gcd(v)) for v in cases]


GCD16 = FPGATask(
    name="gcd16",
    in_bits=32,
    out_bits=16,
    baseline_cycles=16 * 80,  # Euclid's iterative division worst case ~80 cycles
    max_cycles_per_case=4096,
    prompt=(
        "Implement `dut` computing gcd(x, y) for 16-bit unsigneds packed as\n"
        "`data_in = {x[15:0], y[15:0]}`. Output `data_out[15:0]` = gcd(x, y).\n"
        "Assert `done` when valid. Faster implementations score higher.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output [15:0]      data_out,\n"
        "    output             done\n"
        ");\n"
    ),
    reference_py=_gcd,
    vectors=_gcd_vectors,
)


def _bitrev16(x: int) -> int:
    x &= 0xFFFF
    out = 0
    for _ in range(16):
        out = (out << 1) | (x & 1)
        x >>= 1
    return out


def _bitrev16_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    corners = [0, 0xFFFF, 0xAAAA, 0x5555, 0x1, 0x8000]
    rand = [rng.randrange(0, 1 << 16) for _ in range(24)]
    return [(v, _bitrev16(v)) for v in corners + rand]


BITREV16 = FPGATask(
    name="bitrev16",
    in_bits=16,
    out_bits=16,
    baseline_cycles=16 * 16,
    max_cycles_per_case=64,
    prompt=(
        "Implement `dut` computing the bit reversal of a 16-bit word. One cycle\n"
        "combinational implementations score best.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [15:0]      data_in,\n"
        "    output [15:0]      data_out,\n"
        "    output             done\n"
        ");\n"
    ),
    reference_py=_bitrev16,
    vectors=_bitrev16_vectors,
)


TASK_REGISTRY: Dict[str, FPGATask] = {
    POPCOUNT32.name: POPCOUNT32,
    GCD16.name: GCD16,
    BITREV16.name: BITREV16,
}


def get_task(name: str) -> FPGATask:
    if name not in TASK_REGISTRY:
        raise KeyError(f"unknown fpga task {name!r}; available: {sorted(TASK_REGISTRY)}")
    return TASK_REGISTRY[name]
