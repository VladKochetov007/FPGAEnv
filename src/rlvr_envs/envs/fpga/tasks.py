"""Catalogue of FPGA tasks spanning arithmetic, crypto, checksums, network
framing, matrix math, and geometry. Every task uses the same DUT signature so
the C++ harness is one file and the reward signal is uniform (cycles from
`start` to `done`).

    module dut(
        input              clk,
        input              rst,        // synchronous, active-high
        input              start,      // pulse high for one cycle
        input  [IW-1:0]    data_in,    // packed task-specific payload
        output [OW-1:0]    data_out,   // packed task-specific result
        output             done        // high when data_out is stable
    );

Tasks that logically take two or more operands pack them into `data_in` with
the MSB-operand-first convention documented in the prompt. Results follow the
same convention. Keeping every task inside the single-word interface lets the
training harness pool arbitrary tasks without touching the harness generator.
"""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

from rlvr_envs.envs.fpga.models import FPGATask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask(bits: int) -> int:
    return (1 << bits) - 1


# ---------------------------------------------------------------------------
# Bit manipulation
# ---------------------------------------------------------------------------


def _popcount(x: int) -> int:
    return bin(x & 0xFFFF_FFFF).count("1")


def _popcount32_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    corners = [0, 0xFFFFFFFF, 0x55555555, 0xAAAAAAAA, 1, 1 << 31]
    rand = [rng.randrange(0, 1 << 32) for _ in range(26)]
    return [(v, _popcount(v)) for v in corners + rand]


POPCOUNT32 = FPGATask(
    name="popcount32",
    in_bits=32,
    out_bits=6,
    baseline_cycles=1056,
    max_cycles_per_case=128,
    prompt=(
        "Implement Verilog module `dut` with the interface below.\n"
        "`data_in` is 32 bits, `data_out` is 6 bits and must equal the number\n"
        "of 1-bits in `data_in`. Assert `done` as soon as `data_out` is valid.\n"
        "Reset is synchronous, active-high. Fewer cycles between `start` and\n"
        "`done` score higher.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output reg [5:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_popcount,
    vectors=_popcount32_vectors,
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
    baseline_cycles=510,
    max_cycles_per_case=64,
    prompt=(
        "Implement `dut` returning the bit-reversal of the 16-bit `data_in`.\n"
        "One-cycle combinational implementations score best.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [15:0]      data_in,\n"
        "    output reg [15:0]  data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_bitrev16,
    vectors=_bitrev16_vectors,
)


# ---------------------------------------------------------------------------
# Arithmetic / math pipelines
# ---------------------------------------------------------------------------


def _gcd(a: int) -> int:
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
    baseline_cycles=500,
    max_cycles_per_case=4096,
    prompt=(
        "Implement `dut` computing gcd(x, y) for 16-bit unsigneds packed as\n"
        "`data_in = {x[15:0], y[15:0]}`. Output `data_out[15:0]` = gcd(x, y).\n"
        "Inputs are never both zero. Faster implementations score higher.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output reg [15:0]  data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_gcd,
    vectors=_gcd_vectors,
)


def _mul8(a: int) -> int:
    x = (a >> 8) & 0xFF
    y = a & 0xFF
    return (x * y) & 0xFFFF


def _mul8_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases = [0, 0xFFFF, 0x0001, 0xFF00, 0x00FF, 0x0101, 0xFFFE, 0xAAAA]
    for _ in range(24):
        cases.append(rng.randrange(0, 1 << 16))
    return [(v, _mul8(v)) for v in cases]


MUL8 = FPGATask(
    name="mul8",
    in_bits=16,
    out_bits=16,
    baseline_cycles=288,
    max_cycles_per_case=64,
    prompt=(
        "Implement `dut` computing the 16-bit product of two 8-bit unsigned\n"
        "operands packed as `data_in = {a[7:0], b[7:0]}`. Output `data_out` is\n"
        "the 16-bit product. Any implementation (combinational, shift-add,\n"
        "Booth, table-based) is allowed — cycle count determines the score.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [15:0]      data_in,\n"
        "    output reg [15:0]  data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_mul8,
    vectors=_mul8_vectors,
)


def _div16(a: int) -> int:
    x = (a >> 16) & 0xFFFF
    y = a & 0xFFFF
    q = (x // y) & 0xFFFF
    r = (x % y) & 0xFFFF
    return ((q & 0xFFFF) << 16) | (r & 0xFFFF)


def _div16_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases = [
        (100 << 16) | 7,
        (0xFFFF << 16) | 1,
        (1 << 16) | 1,
        (1000 << 16) | 999,
        (0xABCD << 16) | 0x1234,
    ]
    for _ in range(20):
        x = rng.randrange(0, 1 << 16)
        y = rng.randrange(1, 1 << 16)
        cases.append((x << 16) | y)
    return [(v, _div16(v)) for v in cases]


DIV16 = FPGATask(
    name="div16",
    in_bits=32,
    out_bits=32,
    baseline_cycles=450,
    max_cycles_per_case=128,
    prompt=(
        "Implement `dut` computing unsigned 16-bit division with remainder.\n"
        "`data_in = {x[15:0], y[15:0]}` with y != 0. Output\n"
        "`data_out = {quotient[15:0], remainder[15:0]}`. Fewer cycles score\n"
        "higher — consider non-restoring or SRT division for speed.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output reg [31:0]  data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_div16,
    vectors=_div16_vectors,
)


def _isqrt32(x: int) -> int:
    x &= 0xFFFFFFFF
    if x < 2:
        return x
    lo, hi = 0, 1 << 16
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if mid * mid <= x:
            lo = mid
        else:
            hi = mid - 1
    return lo & 0xFFFF


def _isqrt32_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases = [0, 1, 4, 100, 10000, 65535, 0xFFFFFFFF, 1 << 31]
    for _ in range(24):
        cases.append(rng.randrange(0, 1 << 32))
    return [(v, _isqrt32(v)) for v in cases]


ISQRT32 = FPGATask(
    name="isqrt32",
    in_bits=32,
    out_bits=16,
    baseline_cycles=576,
    max_cycles_per_case=128,
    prompt=(
        "Implement `dut` computing the integer square root of a 32-bit\n"
        "unsigned, i.e. the largest y with y*y <= data_in. `data_out[15:0]` is\n"
        "the result. Classical non-restoring digit-by-digit isqrt is fine; a\n"
        "log-depth combinational tree is better.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output reg [15:0]  data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_isqrt32,
    vectors=_isqrt32_vectors,
)


# ---------------------------------------------------------------------------
# Crypto / checksum / network framing
# ---------------------------------------------------------------------------


def _crc8_maxim(data: int, width: int = 16, init: int = 0x00, poly: int = 0x8C) -> int:
    """CRC-8/MAXIM variant: reflected, poly 0x31 -> 0x8C when reflected. Stream
    the `width`-bit input LSB-first so submissions can build it as a shift
    register with an XOR gate."""
    crc = init & 0xFF
    for i in range(width):
        bit = (data >> i) & 1
        mix = (crc ^ bit) & 1
        crc >>= 1
        if mix:
            crc ^= poly
    return crc & 0xFF


def _crc8_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases = [0, 0xFFFF, 0x1234, 0xABCD, 0x0001, 0x8000]
    for _ in range(24):
        cases.append(rng.randrange(0, 1 << 16))
    return [(v, _crc8_maxim(v)) for v in cases]


CRC8 = FPGATask(
    name="crc8",
    in_bits=16,
    out_bits=8,
    baseline_cycles=540,
    max_cycles_per_case=96,
    prompt=(
        "Implement CRC-8/MAXIM over a 16-bit payload (reflected, polynomial\n"
        "0x31 reflected to 0x8C, initial value 0x00, no final XOR). Bits are\n"
        "processed LSB-first. Output `data_out[7:0]` is the final CRC.\n"
        "Example: data_in=0x0000 -> CRC=0x00.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [15:0]      data_in,\n"
        "    output reg [7:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_crc8_maxim,
    vectors=_crc8_vectors,
)


def _xor_cipher16(data: int, key: int = 0xA55A) -> int:
    """Fixed-key XOR block 'cipher'. Tests that the DUT wires the key
    correctly and preserves the round-trip E(E(x)) == x property if the
    submission is pure XOR. The scorer only checks E(x), so you could also
    implement a more structured round function — as long as it matches the
    reference on every test vector."""
    return (data ^ key) & 0xFFFF


def _xor_cipher16_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases = [0, 0xFFFF, 0xA55A, 0x0001, 0x1234, 0xDEAD, 0xBEEF]
    for _ in range(24):
        cases.append(rng.randrange(0, 1 << 16))
    return [(v, _xor_cipher16(v)) for v in cases]


XOR_CIPHER16 = FPGATask(
    name="xor_cipher16",
    in_bits=16,
    out_bits=16,
    baseline_cycles=31,
    max_cycles_per_case=32,
    prompt=(
        "Implement `dut` as a one-round XOR 'block cipher' using the fixed\n"
        "16-bit key 0xA55A: `data_out = data_in ^ 16'hA55A`. Pure\n"
        "combinational impls win this one. The test harness also feeds the\n"
        "output back as input to validate the involution property.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [15:0]      data_in,\n"
        "    output reg [15:0]  data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_xor_cipher16,
    vectors=_xor_cipher16_vectors,
)


def _parity32_adler(a: int) -> int:
    """Tiny Adler-like rolling checksum over 4 bytes of a 32-bit word.
    Output is {a[7:0], b[7:0]} with MOD_ADLER = 251 (small so it fits in 8b).
    Purpose: exercise a streaming accumulate-and-reduce pipeline."""
    MOD = 251
    s1 = 1
    s2 = 0
    for i in range(4):
        byte = (a >> (8 * i)) & 0xFF
        s1 = (s1 + byte) % MOD
        s2 = (s2 + s1) % MOD
    return ((s2 & 0xFF) << 8) | (s1 & 0xFF)


def _parity32_adler_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases = [0, 0xFFFFFFFF, 0x12345678, 0xDEADBEEF, 0x01010101]
    for _ in range(24):
        cases.append(rng.randrange(0, 1 << 32))
    return [(v, _parity32_adler(v)) for v in cases]


ADLER32 = FPGATask(
    name="adler32",
    in_bits=32,
    out_bits=16,
    baseline_cycles=174,
    max_cycles_per_case=96,
    prompt=(
        "Implement a 4-byte Adler-lite rolling checksum. Stream bytes from\n"
        "LSB to MSB of `data_in`. With MOD = 251, s1 = 1, s2 = 0 at start:\n"
        "    for each byte b: s1 = (s1 + b) mod 251; s2 = (s2 + s1) mod 251;\n"
        "Output `data_out = {s2[7:0], s1[7:0]}`. Fewer cycles score higher.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output reg [15:0]  data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_parity32_adler,
    vectors=_parity32_adler_vectors,
)


# ---------------------------------------------------------------------------
# Matrix math / geometry
# ---------------------------------------------------------------------------


def _matvec_2x2_int4(packed: int) -> int:
    """Compute r = M @ v where M is 2x2 and v is 2x1, all int4 signed.

    Packing (MSB-first):
        data_in[23:20] = M[0,0], data_in[19:16] = M[0,1],
        data_in[15:12] = M[1,0], data_in[11:8]  = M[1,1],
        data_in[7:4]   = v[0],   data_in[3:0]   = v[1].
    Output:
        data_out[15:8] = r[0] (int8, two's complement),
        data_out[7:0]  = r[1] (int8, two's complement).
    """
    def _s4(x: int) -> int:
        x &= 0xF
        return x - 16 if x >= 8 else x

    def _s8(x: int) -> int:
        return x & 0xFF

    m00 = _s4(packed >> 20); m01 = _s4(packed >> 16)
    m10 = _s4(packed >> 12); m11 = _s4(packed >> 8)
    v0 = _s4(packed >> 4);  v1 = _s4(packed)
    r0 = m00 * v0 + m01 * v1
    r1 = m10 * v0 + m11 * v1
    return (_s8(r0) << 8) | _s8(r1)


def _matvec_2x2_int4_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = []
    for _ in range(28):
        cases.append(rng.randrange(0, 1 << 24))
    return [(v, _matvec_2x2_int4(v)) for v in cases]


MATVEC_2X2_INT4 = FPGATask(
    name="matvec_2x2_int4",
    in_bits=24,
    out_bits=16,
    baseline_cycles=168,
    max_cycles_per_case=64,
    prompt=(
        "Implement a 2x2 signed int4 matrix times a 2x1 signed int4 vector.\n"
        "Packing (MSB-first, int4 two's complement): `data_in[23:20]=M00,\n"
        "data_in[19:16]=M01, data_in[15:12]=M10, data_in[11:8]=M11,\n"
        "data_in[7:4]=v0, data_in[3:0]=v1`. Output `data_out[15:8]=r0,\n"
        "data_out[7:0]=r1`, both two's complement int8. A fully-parallel 4-MAC\n"
        "combinational design hits the one-cycle lower bound.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [23:0]      data_in,\n"
        "    output reg [15:0]  data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_matvec_2x2_int4,
    vectors=_matvec_2x2_int4_vectors,
)


# Fixed-point ray vs sphere (2D, Q4.4 signed). Packing:
#    data_in[23:16] = ox (int8, Q4.4)
#    data_in[15:8]  = oy
#    data_in[7:4]   = dx (int4, Q2.2; non-zero)
#    data_in[3:0]   = dy
# Sphere is fixed at origin, radius 2 (Q4.4 = 32).
# Output:
#    data_out[0] = hit (1 iff ray hits sphere in forward direction)


def _ray_hit(packed: int) -> int:
    ox = ((packed >> 16) & 0xFF)
    oy = ((packed >> 8) & 0xFF)
    dx = (packed >> 4) & 0xF
    dy = packed & 0xF
    # Sign-extend Q4.4 8-bit origin and Q2.2 4-bit direction.
    ox_s = ox - 256 if ox >= 128 else ox
    oy_s = oy - 256 if oy >= 128 else oy
    dx_s = dx - 16 if dx >= 8 else dx
    dy_s = dy - 16 if dy >= 8 else dy
    R = 32  # radius in Q4.4, so r^2 in Q8.8 = 1024
    # t = -(O . D) / (D . D). Hit iff dd > 0, discriminant >= 0, and t > 0.
    dd = dx_s * dx_s + dy_s * dy_s
    if dd == 0:
        return 0
    od = ox_s * dx_s + oy_s * dy_s
    oo = ox_s * ox_s + oy_s * oy_s
    disc = od * od - dd * (oo - R * R)
    if disc < 0:
        return 0
    # t > 0 iff -od > 0 iff od < 0.
    return int(od < 0)


def _ray_hit_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = []
    for _ in range(32):
        cases.append(rng.randrange(0, 1 << 24))
    return [(v, _ray_hit(v)) for v in cases]


RAY_HIT_2D = FPGATask(
    name="ray_hit_2d",
    in_bits=24,
    out_bits=1,
    baseline_cycles=192,
    max_cycles_per_case=96,
    prompt=(
        "Decide whether a 2D ray from origin O = (ox, oy) in direction\n"
        "D = (dx, dy) intersects the circle centred at (0,0) with radius 2 in\n"
        "the forward direction. Fixed-point format: ox/oy are 8-bit Q4.4\n"
        "two's complement; dx/dy are 4-bit Q2.2 two's complement. Packing:\n"
        "`{ox[7:0], oy[7:0], dx[3:0], dy[3:0]}`. Output `data_out[0]` = 1 iff\n"
        "a forward hit exists (discriminant >= 0 AND t = -(O.D)/(D.D) > 0).\n"
        "A degenerate zero-direction ray never hits.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [23:0]      data_in,\n"
        "    output reg [0:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_ray_hit,
    vectors=_ray_hit_vectors,
)


# ---------------------------------------------------------------------------
# Arbitration / load balancing
# ---------------------------------------------------------------------------


def _round_robin_grant(packed: int) -> int:
    """Round-robin arbiter grant: given `req[7:0]` and previous `last[2:0]`,
    output the index of the lowest-set request strictly greater than `last`,
    wrapping modulo 8. Returns 8 if no request. Packing:
        data_in[10:8] = last, data_in[7:0] = req
        data_out[3:0] = grant index (0..7) or 8 (no grant)."""
    last = (packed >> 8) & 0x7
    req = packed & 0xFF
    if req == 0:
        return 8
    for k in range(1, 9):
        idx = (last + k) % 8
        if (req >> idx) & 1:
            return idx
    return 8  # unreachable


def _round_robin_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases = [0, 0xFF, 0x01, 0x80, (3 << 8) | 0x0F, (7 << 8) | 0xFF]
    for _ in range(26):
        cases.append(rng.randrange(0, 1 << 11))
    return [(v, _round_robin_grant(v)) for v in cases]


ARBITER_RR = FPGATask(
    name="arbiter_rr",
    in_bits=11,
    out_bits=4,
    baseline_cycles=105,
    max_cycles_per_case=32,
    prompt=(
        "Implement a round-robin arbiter (load balancer) over 8 requesters.\n"
        "Inputs: `req[7:0] = data_in[7:0]`, previous grant `last[2:0] =\n"
        "data_in[10:8]`. Output `data_out[3:0]`: the index (0..7) of the\n"
        "lowest-set request strictly after `last`, wrapping; 8 iff no request.\n"
        "One-cycle combinational implementations win.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [10:0]      data_in,\n"
        "    output reg [3:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_round_robin_grant,
    vectors=_round_robin_vectors,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


TASK_REGISTRY: Dict[str, FPGATask] = {
    t.name: t
    for t in [
        POPCOUNT32, BITREV16,
        GCD16, MUL8, DIV16, ISQRT32,
        CRC8, XOR_CIPHER16, ADLER32,
        MATVEC_2X2_INT4, RAY_HIT_2D,
        ARBITER_RR,
    ]
}


def get_task(name: str) -> FPGATask:
    if name not in TASK_REGISTRY:
        raise KeyError(f"unknown fpga task {name!r}; available: {sorted(TASK_REGISTRY)}")
    return TASK_REGISTRY[name]
