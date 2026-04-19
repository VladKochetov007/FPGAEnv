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
# Graph algorithms (packed small graphs)
# ---------------------------------------------------------------------------


def _graph_reach_4(packed: int) -> int:
    """4-node directed reachability. adj[4*u+v]=1 iff edge u->v.
    Packing: adj[15:0], src[17:16], tgt[19:18]. Output 1 iff path src->tgt."""
    adj = packed & 0xFFFF
    src = (packed >> 16) & 0x3
    tgt = (packed >> 18) & 0x3
    visited = [False] * 4
    visited[src] = True
    stack = [src]
    while stack:
        u = stack.pop()
        for v in range(4):
            if not visited[v] and (adj >> (4 * u + v)) & 1:
                visited[v] = True
                stack.append(v)
    return 1 if visited[tgt] else 0


def _graph_reach_4_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = []
    # corners
    cases.append(0)                                              # empty graph, src=tgt=0 -> reachable
    cases.append((1 << 18) | 0)                                  # empty graph, tgt=1 -> unreachable
    cases.append(0xFFFF)                                         # complete graph, src=tgt=0 -> reachable
    cases.append(0xFFFF | (1 << 18) | (3 << 16))                 # complete, src=3->tgt=1 reachable
    cases.append(0b0010 | (1 << 16) | (0 << 18))                 # single edge 0->1, src=1->tgt=0 unreachable
    cases.append(0b0010 | (0 << 16) | (1 << 18))                 # single edge 0->1, src=0->tgt=1 reachable
    # chain 0->1->2->3
    chain = (1 << 1) | (1 << 6) | (1 << 11)                      # bits for (0,1),(1,2),(2,3)
    cases.append(chain | (0 << 16) | (3 << 18))                  # reachable via 3 hops
    cases.append(chain | (3 << 16) | (0 << 18))                  # reverse unreachable
    # self-loop only
    cases.append((1 << 0) | (0 << 16) | (0 << 18))               # src=tgt=0 trivially reachable
    for _ in range(22):
        adj = rng.randrange(0, 1 << 16)
        src = rng.randrange(0, 4)
        tgt = rng.randrange(0, 4)
        cases.append(adj | (src << 16) | (tgt << 18))
    return [(v, _graph_reach_4(v)) for v in cases]


GRAPH_REACH_4 = FPGATask(
    name="graph_reach_4",
    in_bits=20,
    out_bits=1,
    baseline_cycles=384,
    max_cycles_per_case=128,
    prompt=(
        "Directed-graph reachability on 4 nodes. `data_in[15:0]` is a 4x4\n"
        "adjacency bitmap: bit `4*u+v` is 1 iff there is a directed edge from\n"
        "u to v. `data_in[17:16] = src`, `data_in[19:18] = tgt`. Output\n"
        "`data_out[0] = 1` iff tgt is reachable from src (src is always\n"
        "reachable from itself). Fully combinational matrix-closure runs in\n"
        "one cycle: reach = I + A + A^2 + A^3 over booleans.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [19:0]      data_in,\n"
        "    output reg [0:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_graph_reach_4,
    vectors=_graph_reach_4_vectors,
)


def _edge_pairs_5() -> List[Tuple[int, int]]:
    return [(u, v) for u in range(5) for v in range(u + 1, 5)]


def _graph_triangle_5(packed: int) -> int:
    """Undirected 5-node graph, bit i of adj corresponds to _edge_pairs_5()[i].
    Returns the number of triangles (3-cliques)."""
    adj_bits = packed & 0x3FF
    pairs = _edge_pairs_5()
    e = set()
    for i, (u, v) in enumerate(pairs):
        if (adj_bits >> i) & 1:
            e.add((u, v))
    count = 0
    for u in range(5):
        for v in range(u + 1, 5):
            for w in range(v + 1, 5):
                if (u, v) in e and (v, w) in e and (u, w) in e:
                    count += 1
    return count


def _graph_triangle_5_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = [
        0,                  # no edges -> 0 triangles
        0x3FF,              # K5 complete -> 10 triangles
        0b0000000111,       # edges (0,1),(0,2),(1,2) -> 1 triangle
        0b0000001000,       # single edge (0,3) -> 0 triangles
        0b1110010000,       # 4-clique on {1,2,3,4}? -> verify via reference
    ]
    # add random graphs biased to density to cover more counts
    for _ in range(25):
        # vary density: some sparse, some dense
        p_keep = rng.choice([0.25, 0.4, 0.55, 0.7, 0.85])
        adj = 0
        for i in range(10):
            if rng.random() < p_keep:
                adj |= 1 << i
        cases.append(adj)
    return [(v, _graph_triangle_5(v)) for v in cases]


GRAPH_TRIANGLE_5 = FPGATask(
    name="graph_triangle_5",
    in_bits=10,
    out_bits=4,
    baseline_cycles=300,
    max_cycles_per_case=96,
    prompt=(
        "Undirected 5-node graph triangle count. `data_in[9:0]` encodes the\n"
        "upper-triangular adjacency in lexicographic order of pairs:\n"
        "  bit 0 = (0,1), bit 1 = (0,2), bit 2 = (0,3), bit 3 = (0,4),\n"
        "  bit 4 = (1,2), bit 5 = (1,3), bit 6 = (1,4),\n"
        "  bit 7 = (2,3), bit 8 = (2,4), bit 9 = (3,4).\n"
        "Output `data_out[3:0]` is the number of triangles (3-cliques), in\n"
        "[0, 10]. A fully-unrolled combinational AND-tree across all C(5,3)=10\n"
        "triples hits the one-cycle lower bound.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [9:0]       data_in,\n"
        "    output reg [3:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_graph_triangle_5,
    vectors=_graph_triangle_5_vectors,
)


def _edge_pairs_6() -> List[Tuple[int, int]]:
    return [(u, v) for u in range(6) for v in range(u + 1, 6)]


def _graph_bipartite_6(packed: int) -> int:
    """Undirected 6-node graph bipartite check via 2-coloring BFS.
    Bit i of adj corresponds to _edge_pairs_6()[i]. Returns 1 iff bipartite."""
    adj_bits = packed & 0x7FFF
    pairs = _edge_pairs_6()
    adj = [[False] * 6 for _ in range(6)]
    for i, (u, v) in enumerate(pairs):
        if (adj_bits >> i) & 1:
            adj[u][v] = True
            adj[v][u] = True
    color = [-1] * 6
    for start in range(6):
        if color[start] != -1:
            continue
        color[start] = 0
        queue = [start]
        while queue:
            u = queue.pop(0)
            for v in range(6):
                if adj[u][v]:
                    if color[v] == -1:
                        color[v] = 1 - color[u]
                        queue.append(v)
                    elif color[v] == color[u]:
                        return 0
    return 1


def _graph_bipartite_6_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    pairs = _edge_pairs_6()
    cases: List[int] = [0, 0x7FFF]  # empty (bipartite), K6 (not bipartite)
    # triangle on {0,1,2} -> not bipartite
    tri_bits = 0
    for i, (u, v) in enumerate(pairs):
        if (u, v) in {(0, 1), (1, 2), (0, 2)}:
            tri_bits |= 1 << i
    cases.append(tri_bits)
    # 4-cycle 0-1-2-3-0 -> bipartite
    cyc4 = 0
    for i, (u, v) in enumerate(pairs):
        if (u, v) in {(0, 1), (1, 2), (2, 3), (0, 3)}:
            cyc4 |= 1 << i
    cases.append(cyc4)
    # 5-cycle 0-1-2-3-4-0 -> odd cycle, NOT bipartite
    cyc5 = 0
    for i, (u, v) in enumerate(pairs):
        if (u, v) in {(0, 1), (1, 2), (2, 3), (3, 4), (0, 4)}:
            cyc5 |= 1 << i
    cases.append(cyc5)
    # star centered at 0: bipartite
    star = 0
    for i, (u, v) in enumerate(pairs):
        if u == 0:
            star |= 1 << i
    cases.append(star)
    for _ in range(24):
        p_keep = rng.choice([0.15, 0.25, 0.35, 0.5, 0.65])
        adj = 0
        for i in range(15):
            if rng.random() < p_keep:
                adj |= 1 << i
        cases.append(adj)
    return [(v, _graph_bipartite_6(v)) for v in cases]


GRAPH_BIPARTITE_6 = FPGATask(
    name="graph_bipartite_6",
    in_bits=15,
    out_bits=1,
    baseline_cycles=600,
    max_cycles_per_case=256,
    prompt=(
        "Undirected 6-node graph: output 1 iff the graph is bipartite (2-color\n"
        "assignable with no monochromatic edge). `data_in[14:0]` encodes the\n"
        "upper-triangular adjacency in lexicographic order of all C(6,2)=15\n"
        "pairs: bit 0 = (0,1), bit 1 = (0,2), ... bit 14 = (4,5). A graph is\n"
        "bipartite iff every connected component is 2-colorable; equivalently,\n"
        "iff it contains no odd cycle. Output `data_out[0]`.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [14:0]      data_in,\n"
        "    output reg [0:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_graph_bipartite_6,
    vectors=_graph_bipartite_6_vectors,
)


# ---------------------------------------------------------------------------
# Search / selection
# ---------------------------------------------------------------------------


def _binsearch_8x4(packed: int) -> int:
    """Search sorted array of 8 x 4-bit values for target. Return lowest index
    with value == target, or 8 if not found.
    Packing: arr[i] = packed[4*i +: 4] for i=0..7, target = packed[35:32].
    Note: vectors always supply a non-decreasing array."""
    arr = [(packed >> (4 * i)) & 0xF for i in range(8)]
    target = (packed >> 32) & 0xF
    for i in range(8):
        if arr[i] == target:
            return i
    return 8


def _pack_binsearch(arr: List[int], target: int) -> int:
    p = target & 0xF
    acc = 0
    for i, v in enumerate(arr):
        acc |= (v & 0xF) << (4 * i)
    return acc | (p << 32)


def _binsearch_8x4_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = [
        _pack_binsearch([0] * 8, 0),                 # all zeros, target 0 -> idx 0
        _pack_binsearch([0] * 8, 5),                 # all zeros, target 5 -> 8 (not found)
        _pack_binsearch([15] * 8, 15),               # all fifteens, target 15 -> idx 0
        _pack_binsearch(list(range(8)), 0),          # 0..7, target 0 -> 0
        _pack_binsearch(list(range(8)), 7),          # 0..7, target 7 -> 7
        _pack_binsearch(list(range(8)), 8),          # 0..7, target 8 -> 8 (not found, > max)
        _pack_binsearch([0, 0, 1, 1, 2, 2, 3, 3], 2),  # duplicates, target 2 -> 4 (first)
        _pack_binsearch([2, 4, 6, 8, 10, 12, 14, 15], 9),  # target between elements
    ]
    for _ in range(22):
        arr = sorted(rng.choices(range(16), k=8))
        # 60% target chosen from array (found), 40% random
        if rng.random() < 0.6:
            target = rng.choice(arr)
        else:
            target = rng.randrange(0, 16)
        cases.append(_pack_binsearch(arr, target))
    return [(v, _binsearch_8x4(v)) for v in cases]


BINSEARCH_8X4 = FPGATask(
    name="binsearch_8x4",
    in_bits=36,
    out_bits=4,
    baseline_cycles=240,
    max_cycles_per_case=64,
    prompt=(
        "Binary search. `data_in[31:0]` holds 8 non-decreasing 4-bit unsigned\n"
        "values `arr[i] = data_in[4*i +: 4]` for i=0..7. `data_in[35:32]` is\n"
        "the 4-bit target. Output `data_out[3:0]` = the lowest index i with\n"
        "`arr[i] == target`, or 8 if not present. The array is guaranteed\n"
        "sorted; exploit it. A combinational 3-level compare tree is optimal.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [35:0]      data_in,\n"
        "    output reg [3:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_binsearch_8x4,
    vectors=_binsearch_8x4_vectors,
)


def _kth_smallest_4x8(packed: int) -> int:
    """4 x uint8 values, output k-th smallest (k in [0,3])."""
    vals = [(packed >> (8 * i)) & 0xFF for i in range(4)]
    k = (packed >> 32) & 0x3
    return sorted(vals)[k]


def _pack_kth(vals: List[int], k: int) -> int:
    acc = 0
    for i, v in enumerate(vals):
        acc |= (v & 0xFF) << (8 * i)
    return acc | ((k & 0x3) << 32)


def _kth_smallest_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = [
        _pack_kth([0, 0, 0, 0], 0), _pack_kth([0, 0, 0, 0], 3),
        _pack_kth([255, 255, 255, 255], 0),
        _pack_kth([1, 2, 3, 4], 0), _pack_kth([1, 2, 3, 4], 1),
        _pack_kth([1, 2, 3, 4], 2), _pack_kth([1, 2, 3, 4], 3),
        _pack_kth([4, 3, 2, 1], 2),
        _pack_kth([7, 7, 3, 3], 1), _pack_kth([7, 7, 3, 3], 2),
    ]
    for _ in range(20):
        vals = [rng.randrange(0, 256) for _ in range(4)]
        k = rng.randrange(0, 4)
        cases.append(_pack_kth(vals, k))
    return [(v, _kth_smallest_4x8(v)) for v in cases]


KTH_SMALLEST_4X8 = FPGATask(
    name="kth_smallest_4x8",
    in_bits=34,
    out_bits=8,
    baseline_cycles=200,
    max_cycles_per_case=96,
    prompt=(
        "Select the k-th smallest (0-indexed) of 4 uint8 values.\n"
        "`data_in[7:0]=v0, [15:8]=v1, [23:16]=v2, [31:24]=v3, [33:32]=k`.\n"
        "Output `data_out[7:0]` = sorted(v0..v3)[k]. Ties resolve naturally\n"
        "(duplicates occupy adjacent rank positions). A combinational\n"
        "5-comparator sorting network + 4:1 mux on k gives 1-cycle latency.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [33:0]      data_in,\n"
        "    output reg [7:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_kth_smallest_4x8,
    vectors=_kth_smallest_vectors,
)


def _argmax_8x8(packed: int) -> int:
    """Index (0..7) of the maximum among 8 uint8 values. Lowest index wins ties."""
    vals = [(packed >> (8 * i)) & 0xFF for i in range(8)]
    best_val = -1
    best_idx = 0
    for i, v in enumerate(vals):
        if v > best_val:
            best_val = v
            best_idx = i
    return best_idx


def _argmax_8x8_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = [
        0,                                                         # all zeros -> idx 0 (tie)
        0xFFFF_FFFF_FFFF_FFFF,                                     # all max -> idx 0 (tie)
    ]
    # single max at each position
    for pos in range(8):
        cases.append((0xFF) << (8 * pos))
    # strictly increasing
    cases.append(sum((i + 1) << (8 * i) for i in range(8)))
    # strictly decreasing
    cases.append(sum((8 - i) << (8 * i) for i in range(8)))
    for _ in range(20):
        acc = 0
        for i in range(8):
            acc |= rng.randrange(0, 256) << (8 * i)
        cases.append(acc)
    return [(v, _argmax_8x8(v)) for v in cases]


ARGMAX_8X8 = FPGATask(
    name="argmax_8x8",
    in_bits=64,
    out_bits=3,
    baseline_cycles=192,
    max_cycles_per_case=64,
    prompt=(
        "Argmax over 8 uint8 values. `data_in[8*i +: 8] = v_i` for i=0..7.\n"
        "Output `data_out[2:0]` = index of the maximum value; on ties, the\n"
        "lowest index wins. A parallel max-reduction tree pairs (v0,v1),\n"
        "(v2,v3), (v4,v5), (v6,v7) in parallel, keeping track of the index\n"
        "through log2(8)=3 levels of comparators. 1-cycle combinational.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [63:0]      data_in,\n"
        "    output reg [2:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_argmax_8x8,
    vectors=_argmax_8x8_vectors,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


def _heap_check_7(packed: int) -> int:
    """Is the array a valid 7-element min-heap (complete binary tree)?
    Parent of index i is (i-1)//2. Requires a[parent] <= a[child] for all i."""
    a = [(packed >> (4 * i)) & 0xF for i in range(7)]
    for i in range(1, 7):
        p = (i - 1) // 2
        if a[p] > a[i]:
            return 0
    return 1


def _pack_heap7(a: List[int]) -> int:
    acc = 0
    for i, v in enumerate(a):
        acc |= (v & 0xF) << (4 * i)
    return acc


def _heap_check_7_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = [
        _pack_heap7([0, 0, 0, 0, 0, 0, 0]),                 # all equal -> valid heap
        _pack_heap7([0, 1, 2, 3, 4, 5, 6]),                 # increasing -> valid
        _pack_heap7([1, 2, 3, 4, 5, 6, 7]),                 # shifted increasing -> valid
        _pack_heap7([6, 5, 4, 3, 2, 1, 0]),                 # decreasing -> invalid (a[0]=6>a[1]=5)
        _pack_heap7([1, 3, 2, 5, 4, 7, 6]),                 # valid non-monotone heap
        _pack_heap7([1, 2, 3, 4, 5, 6, 0]),                 # tail violates -> invalid (a[2]=3 > a[6]=0)
        _pack_heap7([0, 1, 2, 3, 4, 5, 1]),                 # a[2]=2, a[6]=1 -> invalid
        _pack_heap7([15, 15, 15, 15, 15, 15, 15]),          # all max -> valid
    ]
    # generate random heaps: bias half toward valid (sort ascending)
    for _ in range(22):
        if rng.random() < 0.5:
            a = sorted(rng.choices(range(16), k=7))         # sorted is always a heap
        else:
            a = rng.choices(range(16), k=7)                 # random, usually invalid
        cases.append(_pack_heap7(a))
    return [(v, _heap_check_7(v)) for v in cases]


HEAP_CHECK_7 = FPGATask(
    name="heap_check_7",
    in_bits=28,
    out_bits=1,
    baseline_cycles=140,
    max_cycles_per_case=64,
    prompt=(
        "Binary min-heap property check on 7 x 4-bit unsigned values stored\n"
        "in level-order: `a[i] = data_in[4*i +: 4]` for i=0..6. The tree is\n"
        "complete (nodes 0..6). Output `data_out[0] = 1` iff a[parent(i)] <=\n"
        "a[i] for every i in 1..6, where parent(i) = (i-1) >> 1. Equivalently:\n"
        "  a[0]<=a[1], a[0]<=a[2], a[1]<=a[3], a[1]<=a[4], a[2]<=a[5], a[2]<=a[6].\n"
        "All 6 comparators run in parallel; the result is their AND.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [27:0]      data_in,\n"
        "    output reg [0:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_heap_check_7,
    vectors=_heap_check_7_vectors,
)


def _ll_traverse_4(packed: int) -> int:
    """4-node linked list: each node is (value[3:0], next[5:4]).
    Start at node 0, follow `steps` pointers. Output value at final node."""
    nodes: List[Tuple[int, int]] = []
    for i in range(4):
        word = (packed >> (6 * i)) & 0x3F
        value = word & 0xF
        nxt = (word >> 4) & 0x3
        nodes.append((value, nxt))
    steps = (packed >> 24) & 0x3
    idx = 0
    for _ in range(steps):
        idx = nodes[idx][1]
    return nodes[idx][0]


def _pack_ll(nodes: List[Tuple[int, int]], steps: int) -> int:
    acc = 0
    for i, (val, nxt) in enumerate(nodes):
        word = (val & 0xF) | ((nxt & 0x3) << 4)
        acc |= word << (6 * i)
    acc |= (steps & 0x3) << 24
    return acc


def _ll_traverse_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = [
        _pack_ll([(5, 1), (6, 2), (7, 3), (8, 0)], 0),         # steps=0 -> node 0 value = 5
        _pack_ll([(5, 1), (6, 2), (7, 3), (8, 0)], 1),         # -> 6
        _pack_ll([(5, 1), (6, 2), (7, 3), (8, 0)], 2),         # -> 7
        _pack_ll([(5, 1), (6, 2), (7, 3), (8, 0)], 3),         # -> 8
        _pack_ll([(9, 0), (0, 0), (0, 0), (0, 0)], 3),         # self-loop at 0, steps=3 -> 9
        _pack_ll([(1, 2), (0, 0), (3, 0), (0, 0)], 2),         # 0->2->3(value), steps=2 -> 3
        _pack_ll([(0xF, 3), (0, 0), (0, 0), (0xA, 3)], 2),     # 0->3->3(self), steps=2 -> 0xA
    ]
    for _ in range(23):
        nodes = [(rng.randrange(0, 16), rng.randrange(0, 4)) for _ in range(4)]
        steps = rng.randrange(0, 4)
        cases.append(_pack_ll(nodes, steps))
    return [(v, _ll_traverse_4(v)) for v in cases]


LL_TRAVERSE_4 = FPGATask(
    name="ll_traverse_4",
    in_bits=26,
    out_bits=4,
    baseline_cycles=160,
    max_cycles_per_case=64,
    prompt=(
        "Linked-list traversal over a fixed 4-node array. Each node i occupies\n"
        "`data_in[6*i +: 6]` with value = bits [3:0] and next-pointer = bits\n"
        "[5:4] (a 2-bit index into 0..3). `data_in[25:24] = steps` (0..3).\n"
        "Start at node 0 and follow the `next` pointer `steps` times; output\n"
        "`data_out[3:0]` = the value at the final node. Self-loops and cycles\n"
        "are permitted — just follow the pointer exactly `steps` times. A\n"
        "4:1 mux chain of depth `steps` is combinational; a fully unrolled\n"
        "3-level mux handles the maximum in 1 cycle.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [25:0]      data_in,\n"
        "    output reg [3:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_ll_traverse_4,
    vectors=_ll_traverse_vectors,
)


def _merge_2x4(packed: int) -> int:
    """Merge two sorted 4-arrays of 4-bit values. Output 8-array sorted."""
    a = [(packed >> (4 * i)) & 0xF for i in range(4)]
    b = [(packed >> (16 + 4 * i)) & 0xF for i in range(4)]
    i = j = 0
    out: List[int] = []
    while i < 4 and j < 4:
        if a[i] <= b[j]:
            out.append(a[i]); i += 1
        else:
            out.append(b[j]); j += 1
    out.extend(a[i:])
    out.extend(b[j:])
    return sum((out[k] & 0xF) << (4 * k) for k in range(8))


def _pack_merge(a: List[int], b: List[int]) -> int:
    acc = 0
    for i, v in enumerate(a):
        acc |= (v & 0xF) << (4 * i)
    for i, v in enumerate(b):
        acc |= (v & 0xF) << (16 + 4 * i)
    return acc


def _merge_2x4_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = [
        _pack_merge([0, 0, 0, 0], [0, 0, 0, 0]),               # all zeros
        _pack_merge([15, 15, 15, 15], [15, 15, 15, 15]),       # all fifteens
        _pack_merge([0, 1, 2, 3], [4, 5, 6, 7]),               # disjoint, A < B
        _pack_merge([4, 5, 6, 7], [0, 1, 2, 3]),               # disjoint, B < A
        _pack_merge([1, 3, 5, 7], [2, 4, 6, 8 & 0xF]),         # interleave
        _pack_merge([0, 0, 0, 0], [1, 2, 3, 4]),               # A all zero
        _pack_merge([2, 2, 2, 2], [2, 2, 2, 2]),               # all equal
    ]
    for _ in range(23):
        a = sorted(rng.choices(range(16), k=4))
        b = sorted(rng.choices(range(16), k=4))
        cases.append(_pack_merge(a, b))
    return [(v, _merge_2x4(v)) for v in cases]


MERGE_2X4 = FPGATask(
    name="merge_2x4",
    in_bits=32,
    out_bits=32,
    baseline_cycles=320,
    max_cycles_per_case=96,
    prompt=(
        "Merge two sorted 4-element arrays of 4-bit values.\n"
        "`data_in[15:0]` is array A with `A[i] = data_in[4*i +: 4]`, i=0..3,\n"
        "non-decreasing. `data_in[31:16]` is array B (same encoding).\n"
        "Output 8 sorted elements in `data_out`: `data_out[4*k +: 4]` = the\n"
        "k-th smallest (stable; A ties before B). A 4x4 bitonic merger runs\n"
        "in log2(8)=3 parallel CAS stages. Exploit sortedness — don't resort.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output reg [31:0]  data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_merge_2x4,
    vectors=_merge_2x4_vectors,
)


# ---------------------------------------------------------------------------
# Number theory
# ---------------------------------------------------------------------------


def _prime_u8(n: int) -> int:
    """1 iff n (0..255) is prime, else 0."""
    n &= 0xFF
    if n < 2:
        return 0
    if n < 4:
        return 1
    if n % 2 == 0:
        return 0
    i = 3
    while i * i <= n:
        if n % i == 0:
            return 0
        i += 2
    return 1


def _prime_u8_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    # Structurally critical: boundary primes/non-primes
    corners = [
        0, 1,                                 # not prime
        2, 3, 5, 7, 11, 13,                   # small primes
        4, 6, 8, 9, 15, 25, 27,               # composites
        127, 128,                             # boundary
        251, 253, 255,                        # top-of-range primes/composites
    ]
    cases: List[int] = list(corners)
    # include a handful of known primes for coverage
    primes_sample = [17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 97, 101, 223, 227, 229]
    rng_copy = random.Random(seed + 1_000_003)
    for p in rng_copy.sample(primes_sample, k=min(5, len(primes_sample))):
        cases.append(p)
    for _ in range(15):
        cases.append(rng.randrange(0, 256))
    return [(v, _prime_u8(v)) for v in cases]


PRIME_CHECK_U8 = FPGATask(
    name="prime_check_u8",
    in_bits=8,
    out_bits=1,
    baseline_cycles=480,
    max_cycles_per_case=256,
    prompt=(
        "Primality test for an 8-bit unsigned integer. `data_in[7:0] = n`.\n"
        "Output `data_out[0] = 1` iff n is prime, else 0. 0 and 1 are NOT\n"
        "prime. 2 IS prime. A 256-bit lookup ROM indexed by n gives a 1-cycle\n"
        "answer; serial trial-division by odd divisors up to 15 also works\n"
        "but takes more cycles.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [7:0]       data_in,\n"
        "    output reg [0:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_prime_u8,
    vectors=_prime_u8_vectors,
)


def _modexp_small(packed: int) -> int:
    """a^b mod n for a in [0,15], b in [0,15], n in [1,31]. Returns r in [0, n)."""
    a = packed & 0xF
    b = (packed >> 4) & 0xF
    n = (packed >> 8) & 0x1F
    if n == 0:
        n = 1  # vectors never pack n=0, but defensively
    return pow(a, b, n) & 0x1F


def _pack_modexp(a: int, b: int, n: int) -> int:
    return (a & 0xF) | ((b & 0xF) << 4) | ((n & 0x1F) << 8)


def _modexp_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = [
        _pack_modexp(0, 0, 7),             # 0^0 mod 7 = 1 (Python convention)
        _pack_modexp(0, 5, 7),             # 0^5 mod 7 = 0
        _pack_modexp(5, 0, 7),             # 5^0 mod 7 = 1
        _pack_modexp(1, 15, 31),           # 1^15 mod 31 = 1
        _pack_modexp(2, 10, 31),           # 2^10 mod 31 = 1024 mod 31 = 1
        _pack_modexp(3, 3, 5),             # 27 mod 5 = 2
        _pack_modexp(15, 15, 31),          # max values
        _pack_modexp(4, 6, 1),             # n=1 -> result 0
        _pack_modexp(7, 4, 13),
        _pack_modexp(2, 7, 11),            # 128 mod 11 = 7
    ]
    for _ in range(20):
        a = rng.randrange(0, 16)
        b = rng.randrange(0, 16)
        n = rng.randrange(1, 32)
        cases.append(_pack_modexp(a, b, n))
    return [(v, _modexp_small(v)) for v in cases]


MODEXP_SMALL = FPGATask(
    name="modexp_small",
    in_bits=13,
    out_bits=5,
    baseline_cycles=240,
    max_cycles_per_case=128,
    prompt=(
        "Modular exponentiation: compute a^b mod n. `data_in[3:0] = a` (0..15),\n"
        "`data_in[7:4] = b` (0..15), `data_in[12:8] = n` (1..31). Output\n"
        "`data_out[4:0]` in [0, n). Convention: 0^0 = 1 (Python `pow(0,0,n)`).\n"
        "For n=1 the result is always 0. Square-and-multiply runs in 4\n"
        "iterations; a combinational chain of 4 conditional multiplications\n"
        "achieves 1-cycle latency.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [12:0]      data_in,\n"
        "    output reg [4:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_modexp_small,
    vectors=_modexp_vectors,
)


# ---------------------------------------------------------------------------
# Sequence / string
# ---------------------------------------------------------------------------


def _seq_count_1011(packed: int) -> int:
    """Count overlapping occurrences of the 4-bit pattern 1011 in a 16-bit
    stream. Pattern value at position i is (x >> i) & 0xF == 0b1011."""
    x = packed & 0xFFFF
    count = 0
    for i in range(13):
        if ((x >> i) & 0xF) == 0b1011:
            count += 1
    return count


def _seq_count_1011_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = [
        0x0000,                 # no occurrences
        0xFFFF,                 # all ones: 4-bit window = 1111, no match
        0x000B,                 # single 1011 at LSB
        0xB000,                 # single 1011 near top
        0xBBBB,                 # 1011 1011 1011 1011: pattern every 4 bits
        0x0BBB,                 # 3 copies
        0x1011,                 # literal but MSB is 1 and window at 12 is 0001
        0x5555,                 # alternating, no 1011
    ]
    for _ in range(22):
        cases.append(rng.randrange(0, 1 << 16))
    return [(v, _seq_count_1011(v)) for v in cases]


SEQ_DETECT_1011 = FPGATask(
    name="seq_detect_1011",
    in_bits=16,
    out_bits=4,
    baseline_cycles=180,
    max_cycles_per_case=64,
    prompt=(
        "Count overlapping occurrences of the 4-bit pattern 4'b1011 in a\n"
        "16-bit input stream. At each position i in 0..12, extract the 4-bit\n"
        "window `data_in[i+3:i]` and test equality with 4'b1011. Output\n"
        "`data_out[3:0]` is the total count (0..13). All 13 comparisons\n"
        "are independent and can be evaluated in parallel; the result is the\n"
        "popcount of a 13-bit match vector.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [15:0]      data_in,\n"
        "    output reg [3:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_seq_count_1011,
    vectors=_seq_count_1011_vectors,
)


def _palindrome_8nibble(packed: int) -> int:
    """32-bit input as 8 x 4-bit symbols. 1 iff sequence is palindromic."""
    n = [(packed >> (4 * i)) & 0xF for i in range(8)]
    for i in range(4):
        if n[i] != n[7 - i]:
            return 0
    return 1


def _palindrome_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)

    def pack(sym: List[int]) -> int:
        acc = 0
        for i, v in enumerate(sym):
            acc |= (v & 0xF) << (4 * i)
        return acc

    cases: List[int] = [
        pack([0, 0, 0, 0, 0, 0, 0, 0]),                  # trivial palindrome
        pack([0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF, 0xF]),  # all-max palindrome
        pack([1, 2, 3, 4, 4, 3, 2, 1]),                  # palindrome, all distinct-ish
        pack([1, 2, 3, 4, 5, 6, 7, 8]),                  # strictly non-palindromic
        pack([1, 2, 3, 4, 4, 3, 2, 2]),                  # off-by-one non-palindrome
        pack([0xA, 0xB, 0xA, 0xB, 0xB, 0xA, 0xB, 0xA]),  # palindrome w/ duplicates
    ]
    # half biased palindromes, half random
    for _ in range(13):
        half = [rng.randrange(0, 16) for _ in range(4)]
        sym = half + half[::-1]
        cases.append(pack(sym))
    for _ in range(11):
        sym = [rng.randrange(0, 16) for _ in range(8)]
        cases.append(pack(sym))
    return [(v, _palindrome_8nibble(v)) for v in cases]


PALINDROME_8N = FPGATask(
    name="palindrome_8n",
    in_bits=32,
    out_bits=1,
    baseline_cycles=120,
    max_cycles_per_case=32,
    prompt=(
        "Palindrome check over 8 x 4-bit symbols.\n"
        "`sym[i] = data_in[4*i +: 4]` for i=0..7.\n"
        "Output `data_out[0] = 1` iff sym[i] == sym[7 - i] for all i in 0..3.\n"
        "Four independent 4-bit equality comparators are AND-reduced — fully\n"
        "combinational in one cycle.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output reg [0:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_palindrome_8nibble,
    vectors=_palindrome_vectors,
)


# ---------------------------------------------------------------------------
# Combinatorial
# ---------------------------------------------------------------------------


def _subset_sum_4x6(packed: int) -> int:
    """4 x 6-bit values, 8-bit target. Output 1 iff some subset sums to target."""
    vals = [(packed >> (6 * i)) & 0x3F for i in range(4)]
    target = (packed >> 24) & 0xFF
    for mask in range(16):
        s = 0
        for i in range(4):
            if (mask >> i) & 1:
                s += vals[i]
        if s == target:
            return 1
    return 0


def _pack_subset(vals: List[int], target: int) -> int:
    acc = 0
    for i, v in enumerate(vals):
        acc |= (v & 0x3F) << (6 * i)
    acc |= (target & 0xFF) << 24
    return acc


def _subset_sum_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)
    cases: List[int] = [
        _pack_subset([0, 0, 0, 0], 0),                    # empty subset, target 0 -> 1
        _pack_subset([1, 2, 3, 4], 0),                    # empty subset works -> 1
        _pack_subset([1, 2, 3, 4], 10),                   # all four sum to 10 -> 1
        _pack_subset([1, 2, 3, 4], 11),                   # over the max -> 0
        _pack_subset([5, 10, 15, 20], 25),                # 5+20 or 10+15 -> 1
        _pack_subset([5, 10, 15, 20], 26),                # no subset -> 0
        _pack_subset([63, 63, 63, 63], 252),              # sum of all = 252 -> 1
        _pack_subset([63, 63, 63, 63], 253),              # beyond max -> 0
        _pack_subset([1, 1, 1, 1], 2),                    # any pair -> 1
    ]
    for _ in range(21):
        vals = [rng.randrange(0, 64) for _ in range(4)]
        max_sum = sum(vals)
        # mix: half achievable targets (random subset sum), half arbitrary
        if rng.random() < 0.5:
            mask = rng.randrange(0, 16)
            target = sum(vals[i] for i in range(4) if (mask >> i) & 1)
        else:
            target = rng.randrange(0, max(1, max_sum + 5))
            target &= 0xFF
        cases.append(_pack_subset(vals, target))
    return [(v, _subset_sum_4x6(v)) for v in cases]


SUBSET_SUM_4X6 = FPGATask(
    name="subset_sum_4x6",
    in_bits=32,
    out_bits=1,
    baseline_cycles=320,
    max_cycles_per_case=128,
    prompt=(
        "Subset-sum decision. `data_in[23:0]` holds four 6-bit unsigned values\n"
        "with `v[i] = data_in[6*i +: 6]`, i=0..3. `data_in[31:24]` is an 8-bit\n"
        "target. Output `data_out[0] = 1` iff some subset S of {v0,v1,v2,v3}\n"
        "satisfies sum(S) == target. The empty set sums to 0, so target=0 is\n"
        "always satisfiable. With 2^4 = 16 subsets, a fully combinational\n"
        "16-way adder tree + OR-reduction of 16 equality comparators fits in\n"
        "one cycle.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output reg [0:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_subset_sum_4x6,
    vectors=_subset_sum_vectors,
)


def _inversion_4x4(packed: int) -> int:
    """Count inversions in 4 x 4-bit array: pairs (i,j) with i<j and a[i]>a[j]."""
    a = [(packed >> (4 * i)) & 0xF for i in range(4)]
    count = 0
    for i in range(4):
        for j in range(i + 1, 4):
            if a[i] > a[j]:
                count += 1
    return count


def _inversion_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)

    def pack(a: List[int]) -> int:
        acc = 0
        for i, v in enumerate(a):
            acc |= (v & 0xF) << (4 * i)
        return acc

    cases: List[int] = [
        pack([0, 0, 0, 0]),       # all equal -> 0 inversions
        pack([1, 2, 3, 4]),       # sorted -> 0
        pack([4, 3, 2, 1]),       # reverse -> 6 (max)
        pack([2, 1, 4, 3]),       # two adjacent swaps -> 2
        pack([1, 3, 2, 4]),       # 1 inversion
        pack([15, 0, 15, 0]),     # mixed -> 3
        pack([3, 3, 3, 3]),       # all equal -> 0
        pack([0xF, 0xF, 0, 0]),   # two groups -> 4
    ]
    for _ in range(22):
        a = [rng.randrange(0, 16) for _ in range(4)]
        cases.append(pack(a))
    return [(v, _inversion_4x4(v)) for v in cases]


INVERSION_4X4 = FPGATask(
    name="inversion_4x4",
    in_bits=16,
    out_bits=3,
    baseline_cycles=144,
    max_cycles_per_case=64,
    prompt=(
        "Count inversion pairs in a 4-element 4-bit-value array.\n"
        "`a[i] = data_in[4*i +: 4]`, i=0..3. Output `data_out[2:0]` =\n"
        "|{(i,j) : 0 <= i < j <= 3 AND a[i] > a[j]}|. Maximum is C(4,2) = 6,\n"
        "fits in 3 bits. All C(4,2)=6 comparisons are independent; the result\n"
        "is the popcount of a 6-bit compare vector — 1 cycle combinational.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [15:0]      data_in,\n"
        "    output reg [2:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_inversion_4x4,
    vectors=_inversion_vectors,
)


# ---------------------------------------------------------------------------
# Aggregate / reduction
# ---------------------------------------------------------------------------


def _histogram_4bin(packed: int) -> int:
    """8 x 4-bit values binned into 4 bins [0..3],[4..7],[8..11],[12..15].
    Output packs counts: count[b] at bits [4*b +: 4]."""
    vals = [(packed >> (4 * i)) & 0xF for i in range(8)]
    counts = [0, 0, 0, 0]
    for v in vals:
        counts[v >> 2] += 1
    return sum((counts[b] & 0xF) << (4 * b) for b in range(4))


def _histogram_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)

    def pack(vals: List[int]) -> int:
        acc = 0
        for i, v in enumerate(vals):
            acc |= (v & 0xF) << (4 * i)
        return acc

    cases: List[int] = [
        pack([0] * 8),                               # all in bin 0 -> counts 8,0,0,0
        pack([15] * 8),                              # all in bin 3 -> 0,0,0,8
        pack([0, 1, 2, 3, 4, 5, 6, 7]),              # bins 0 & 1 -> 4,4,0,0
        pack([0, 3, 4, 7, 8, 11, 12, 15]),           # 2 per bin -> 2,2,2,2
        pack([0, 4, 8, 12, 0, 4, 8, 12]),            # bin starts -> 2,2,2,2
        pack([3, 3, 3, 3, 3, 3, 3, 3]),              # all in bin 0 -> 8,0,0,0
        pack([4, 4, 4, 4, 4, 4, 4, 4]),              # all in bin 1 -> 0,8,0,0
    ]
    for _ in range(23):
        vals = [rng.randrange(0, 16) for _ in range(8)]
        cases.append(pack(vals))
    return [(v, _histogram_4bin(v)) for v in cases]


HISTOGRAM_4BIN = FPGATask(
    name="histogram_4bin",
    in_bits=32,
    out_bits=16,
    baseline_cycles=260,
    max_cycles_per_case=96,
    prompt=(
        "Histogram with 4 bins over 8 input samples. Each sample is 4-bit:\n"
        "`v[i] = data_in[4*i +: 4]`, i=0..7. Bin assignment is by the top\n"
        "two bits: `bin(v) = v >> 2`, so bin 0 = [0,3], bin 1 = [4,7],\n"
        "bin 2 = [8,11], bin 3 = [12,15]. Output `data_out[4*b +: 4]` is the\n"
        "count of samples falling in bin b (always in [0, 8]). The sum of all\n"
        "four counts is always 8 — useful as an internal sanity check.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output reg [15:0]  data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_histogram_4bin,
    vectors=_histogram_vectors,
)


def _argmax_argmin_4x8(packed: int) -> int:
    """4 uint8 values. Output {max_idx[3:2], min_idx[1:0]}. Ties: lowest index."""
    vals = [(packed >> (8 * i)) & 0xFF for i in range(4)]
    max_idx = min_idx = 0
    for i in range(1, 4):
        if vals[i] > vals[max_idx]:
            max_idx = i
        if vals[i] < vals[min_idx]:
            min_idx = i
    return ((max_idx & 0x3) << 2) | (min_idx & 0x3)


def _argmax_argmin_vectors(seed: int) -> List[Tuple[int, int]]:
    rng = random.Random(seed)

    def pack(vals: List[int]) -> int:
        acc = 0
        for i, v in enumerate(vals):
            acc |= (v & 0xFF) << (8 * i)
        return acc

    cases: List[int] = [
        pack([0, 0, 0, 0]),           # all equal -> max=0, min=0
        pack([255, 255, 255, 255]),   # all max -> 0, 0
        pack([1, 2, 3, 4]),           # sorted -> max=3, min=0
        pack([4, 3, 2, 1]),           # reverse -> max=0, min=3
        pack([100, 200, 50, 150]),    # arbitrary
        pack([0, 100, 0, 100]),       # ties -> max=1, min=0
        pack([255, 0, 255, 0]),       # extremes -> max=0, min=1
    ]
    for _ in range(23):
        vals = [rng.randrange(0, 256) for _ in range(4)]
        cases.append(pack(vals))
    return [(v, _argmax_argmin_4x8(v)) for v in cases]


ARGMAX_ARGMIN_4X8 = FPGATask(
    name="argmax_argmin_4x8",
    in_bits=32,
    out_bits=4,
    baseline_cycles=120,
    max_cycles_per_case=64,
    prompt=(
        "Joint argmax + argmin over 4 uint8 values.\n"
        "`v[i] = data_in[8*i +: 8]`, i=0..3.\n"
        "Output: `data_out[3:2] = argmax`, `data_out[1:0] = argmin`, each a\n"
        "2-bit index. On ties, the lowest index wins for BOTH. The two\n"
        "reductions share comparator logic — a good design does not duplicate\n"
        "the 4-way compare tree.\n\n"
        "module dut(\n"
        "    input              clk,\n"
        "    input              rst,\n"
        "    input              start,\n"
        "    input  [31:0]      data_in,\n"
        "    output reg [3:0]   data_out,\n"
        "    output reg         done\n"
        ");\n"
    ),
    reference_py=_argmax_argmin_4x8,
    vectors=_argmax_argmin_vectors,
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
        # Graph algorithms
        GRAPH_REACH_4, GRAPH_TRIANGLE_5, GRAPH_BIPARTITE_6,
        # Search & selection
        BINSEARCH_8X4, KTH_SMALLEST_4X8, ARGMAX_8X8,
        # Data structures
        HEAP_CHECK_7, LL_TRAVERSE_4, MERGE_2X4,
        # Number theory
        PRIME_CHECK_U8, MODEXP_SMALL,
        # Sequence / string
        SEQ_DETECT_1011, PALINDROME_8N,
        # Combinatorial
        SUBSET_SUM_4X6, INVERSION_4X4,
        # Aggregate / reduction
        HISTOGRAM_4BIN, ARGMAX_ARGMIN_4X8,
    ]
}


def get_task(name: str) -> FPGATask:
    if name not in TASK_REGISTRY:
        raise KeyError(f"unknown fpga task {name!r}; available: {sorted(TASK_REGISTRY)}")
    return TASK_REGISTRY[name]
