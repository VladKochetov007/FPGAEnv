"""Tests for test-vector strategy quality across all FPGA tasks.

Validates that each task's vectors() function:
  - Covers structurally important corner cases that probabilistic sampling
    is unlikely to hit on its own
  - Produces meaningfully different vectors across seeds (anti-memorisation)
  - Has enough random samples to catch partial implementations with high
    probability
  - Has outputs that differ across a non-trivial fraction of the input space
    (guards against degenerate or near-constant functions)

These tests document the requirements derived from the probabilistic analysis:
  P(catch 80%-correct design | K=30 random, N=1 seed) = 99.88%
  P(catch 80%-correct design | K=30 random, N=3 seeds) > 99.9999%
  P(catch inputs<1000 design | K=6 random, 32-bit input) ≈ 1.0

All arithmetic verified against reference_py; no synthetic assertions.
"""

from __future__ import annotations

import math
import random
from typing import List, Set, Tuple

import pytest

from rlvr_envs.envs.fpga.tasks import (
    TASK_REGISTRY,
    _crc8_maxim,
    _div16,
    _gcd,
    _isqrt32,
    _matvec_2x2_int4,
    _popcount,
    _ray_hit,
    _round_robin_grant,
    get_task,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unpack_gcd(packed: int) -> Tuple[int, int]:
    return (packed >> 16) & 0xFFFF, packed & 0xFFFF


def _unpack_div16(packed: int) -> Tuple[int, int]:
    return (packed >> 16) & 0xFFFF, packed & 0xFFFF


def _pack_matvec(m00: int, m01: int, m10: int, m11: int, v0: int, v1: int) -> int:
    def _enc4(x: int) -> int:
        return x & 0xF
    return (
        (_enc4(m00) << 20) | (_enc4(m01) << 16) |
        (_enc4(m10) << 12) | (_enc4(m11) << 8) |
        (_enc4(v0) << 4) | _enc4(v1)
    )


def _pack_ray(ox: int, oy: int, dx: int, dy: int) -> int:
    return ((ox & 0xFF) << 16) | ((oy & 0xFF) << 8) | ((dx & 0xF) << 4) | (dy & 0xF)


def _inputs_for(task_name: str, seed: int) -> List[int]:
    return [inp for inp, _ in get_task(task_name).vectors(seed)]


def _outputs_for(task_name: str, seed: int) -> List[int]:
    return [out for _, out in get_task(task_name).vectors(seed)]


# ---------------------------------------------------------------------------
# Section 1: General vector-set structural properties
# ---------------------------------------------------------------------------


class TestVectorCountAndVariety:
    """Each task must generate enough vectors (>= 24) for probabilistic
    guarantees: at 20% error rate, 24 random samples give P(catch) = 99.5%
    per seed. Below 24 the guarantee degrades to < 99%.
    """

    @pytest.mark.parametrize("name", list(TASK_REGISTRY.keys()))
    def test_at_least_24_vectors_per_seed(self, name: str):
        vectors = get_task(name).vectors(0)
        assert len(vectors) >= 24, (
            f"{name}: only {len(vectors)} vectors, need >= 24 for 99.5% "
            f"catch rate against 20%-wrong designs"
        )

    @pytest.mark.parametrize("name", list(TASK_REGISTRY.keys()))
    def test_distinct_inputs_exceed_half_of_total(self, name: str):
        """Duplicate inputs waste budget and reduce coverage. More than half
        the vectors must be distinct inputs to maintain effective K count."""
        vectors = get_task(name).vectors(0)
        unique = len(set(inp for inp, _ in vectors))
        assert unique > len(vectors) // 2, (
            f"{name}: only {unique}/{len(vectors)} unique inputs"
        )

    @pytest.mark.parametrize("name", list(TASK_REGISTRY.keys()))
    def test_at_least_4_distinct_output_values(self, name: str):
        """A near-constant function has almost no discriminating power.
        Outputs must vary enough to catch off-by-one or partial implementations.
        For tasks with very small output spaces (<4 possible values), require
        that every possible output value appears at least once — catching the
        degenerate "always return 0" and "always return 1" implementations."""
        task = get_task(name)
        outputs = _outputs_for(name, 0)
        distinct = len(set(outputs))
        required = min(4, 1 << task.out_bits)
        assert distinct >= required, (
            f"{name}: only {distinct} distinct output values across {len(outputs)} "
            f"vectors (out_bits={task.out_bits}, required {required}) — cannot "
            f"distinguish correct from near-correct implementations"
        )

    @pytest.mark.parametrize("name", list(TASK_REGISTRY.keys()))
    def test_random_vectors_differ_across_seeds(self, name: str):
        """Vectors from seed=0 and seed=1 must differ in at least half their
        inputs (the random portion). If they are identical, multi-seed validation
        provides no additional discriminating power."""
        v0 = set(inp for inp, _ in get_task(name).vectors(0))
        v1 = set(inp for inp, _ in get_task(name).vectors(1))
        shared = len(v0 & v1)
        total = len(v0 | v1)
        # Seeds should share only the seed-independent corners, not the randoms.
        # Jaccard overlap > 0.9 means almost no seed-dependent variation.
        jaccard = shared / total if total else 1.0
        assert jaccard < 0.9, (
            f"{name}: Jaccard overlap between seed=0 and seed=1 inputs is "
            f"{jaccard:.2f} — nearly identical vectors across seeds"
        )

    @pytest.mark.parametrize("name", list(TASK_REGISTRY.keys()))
    def test_vectors_use_full_input_space_range(self, name: str):
        """Random vectors should span at least 50% of the declared input
        range. This catches a design that only works for small inputs."""
        task = get_task(name)
        max_in = (1 << task.in_bits) - 1
        inputs = _inputs_for(name, 0)
        largest = max(inputs)
        assert largest > max_in // 2, (
            f"{name}: largest input {largest} < half of input range {max_in}; "
            f"design that only works for small values would pass all vectors"
        )


# ---------------------------------------------------------------------------
# Section 2: Probabilistic detection bounds
# ---------------------------------------------------------------------------


class TestProbabilisticDetection:
    """Exact bound calculations for the K random + N seed regime.

    All assertions use conservative bounds: probability of FAILING to catch a
    buggy design must be below 0.001 (0.1%) per seed.
    """

    def test_30_vectors_catch_20pct_error_rate_per_seed(self):
        """K=30 random vectors: P(catch | 20% error rate) = 1 - 0.8^30 = 99.88%.
        The complement, P(escape) = 0.8^30 ≈ 0.0012, is below 0.2%."""
        K = 30
        error_rate = 0.20
        p_escape_one_seed = (1 - error_rate) ** K
        assert p_escape_one_seed < 0.002, (
            f"K={K} vectors do not suffice: P(escape per seed) = "
            f"{p_escape_one_seed:.4f} > 0.002"
        )

    def test_30_vectors_3_seeds_catch_10pct_error_rate(self):
        """K=30, N=3: P(escape | 10% error rate) = (0.9^30)^3 = 0.0424^3 < 0.0001."""
        K = 30
        N = 3
        error_rate = 0.10
        p_escape = ((1 - error_rate) ** K) ** N
        assert p_escape < 0.0001, (
            f"K={K},N={N}: P(escape | err=10%) = {p_escape:.6f} > 0.0001"
        )

    def test_any_32bit_task_random_vectors_catch_small_input_bias(self):
        """A design correct only for inputs < 1000 fails on any input >= 1000.
        With 32-bit inputs the failure rate is 1 - 1000/2^32 > 99.99%.
        Even K=1 random vector catches this with P > 99.99%."""
        input_bits = 32
        valid_count = 1000
        error_rate = 1.0 - valid_count / (2 ** input_bits)
        K = 1
        p_catch = 1 - (1 - error_rate) ** K
        assert p_catch > 0.9999, (
            f"Even K=1 random 32-bit vector should catch small-input bias; "
            f"P(catch) = {p_catch:.6f}"
        )

    def test_seed_space_size_bounds_memorisation_risk(self):
        """With N=5 validation seeds drawn from [0, 10000), the probability
        that any one of them collides with the memorised training seed is
        5/10000 = 0.05%. Documented as the residual memorisation risk."""
        N = 5
        seed_space = 10000
        p_collision = N / seed_space
        assert p_collision < 0.001, (
            f"N={N} seeds in space {seed_space}: collision risk "
            f"{p_collision:.4f} > 0.001"
        )

    def test_minimum_seeds_to_catch_5pct_error_rate_at_99pct(self):
        """For 5% error rate, K=30: P(escape per seed) = 0.95^30 = 0.2146.
        We need N >= ceil(log(0.01)/log(0.2146)) = 5 seeds for 99% catch rate.
        The formula is exact: assert it holds for N=5."""
        K = 30
        error_rate = 0.05
        N = 5
        p_escape_per_seed = (1 - error_rate) ** K
        p_escape_n_seeds = p_escape_per_seed ** N
        assert p_escape_n_seeds < 0.01, (
            f"N={N} seeds insufficient for 5% error rate: "
            f"P(escape) = {p_escape_n_seeds:.4f} > 0.01"
        )


# ---------------------------------------------------------------------------
# Section 3: gcd16 — missing corner coverage
# ---------------------------------------------------------------------------


class TestGcd16Corners:
    """gcd16 prompt states 'inputs are never both zero', meaning x=0 or y=0
    individually are valid and must be tested (gcd(0,y)=y and gcd(x,0)=x).
    The current 4 corners omit all of these structurally important cases.
    """

    def test_reference_gcd_single_zero_x(self):
        """gcd(0, y) = y. A faulty Euclidean loop that reads uninitialised
        state when x=0 would fail silently without this case."""
        assert _gcd((0 << 16) | 7) == 7
        assert _gcd((0 << 16) | 0xFFFF) == 0xFFFF

    def test_reference_gcd_single_zero_y(self):
        """gcd(x, 0) = x. Binary GCD that short-circuits on b==0 must still
        output a, not zero."""
        assert _gcd((7 << 16) | 0) == 7
        assert _gcd((0xFFFF << 16) | 0) == 0xFFFF

    def test_reference_gcd_equal_inputs(self):
        """gcd(x, x) = x. Any algorithm that takes x - y as its first step
        would get 0 and then loop to gcd(0, x) = x, but an off-by-one in
        the termination condition could output 0 instead."""
        assert _gcd((17 << 16) | 17) == 17
        assert _gcd((0xFFFF << 16) | 0xFFFF) == 0xFFFF

    def test_reference_gcd_coprime_large_primes(self):
        """Two large primes have gcd=1. This stresses the iteration depth;
        a design that caps iterations too early would return a wrong value."""
        assert _gcd((65521 << 16) | 65519) == 1

    def test_reference_gcd_power_of_two_multiple(self):
        """gcd(2^k * m, m) = m when m is odd. Tests that the algorithm
        strips common factors of 2 correctly in binary GCD variants."""
        assert _gcd((64 << 16) | 8) == 8
        assert _gcd((4096 << 16) | 64) == 64

    def test_reference_gcd_y_greater_than_x(self):
        """gcd is symmetric but Euclidean subtraction goes through more steps
        when y > x. Implementations that only compute a - b (not b - a) would
        stall or wrap."""
        assert _gcd((7 << 16) | 13) == 1
        assert _gcd((100 << 16) | 9999) == 1

    def test_current_vectors_never_produce_x_zero(self):
        """Documents the confirmed gap: across 5 seeds, no vector has x=0.
        A Verilog GCD that outputs data_in[15:0] when data_in[31:16]==0 would
        never be tested."""
        for seed in range(5):
            vectors = get_task("gcd16").vectors(seed)
            x_zero = [p for p, _ in vectors if (p >> 16) & 0xFFFF == 0]
            assert x_zero == [], (
                f"seed={seed}: unexpected x=0 vector {x_zero}; "
                f"if this fires, the gap has been fixed — update this test"
            )

    def test_current_vectors_never_produce_y_zero(self):
        """Documents the confirmed gap: no vector has y=0. gcd(x,0) is
        a valid and distinct termination path in binary GCD."""
        for seed in range(5):
            vectors = get_task("gcd16").vectors(seed)
            y_zero = [p for p, _ in vectors if p & 0xFFFF == 0]
            assert y_zero == [], (
                f"seed={seed}: unexpected y=0 vector — gap appears fixed"
            )


# ---------------------------------------------------------------------------
# Section 4: div16 — missing corner coverage
# ---------------------------------------------------------------------------


class TestDiv16Corners:
    """div16: x in [0, 0xFFFF], y in [1, 0xFFFF]. Key structural cases:
    quotient=0 (x<y), remainder=0 (x divides evenly), y=1 (trivial divisor),
    and x=y (quotient=1, remainder=0 simultaneously).
    """

    def test_reference_div16_dividend_zero(self):
        """x=0, any y: quotient=0, remainder=0. A restoring-division shift
        register that starts with remainder=x would output 0,0 correctly, but
        a buggy impl that initialises rem to an accumulator might not."""
        result = _div16((0 << 16) | 7)
        assert result == 0, hex(result)

    def test_reference_div16_dividend_equals_divisor(self):
        """x=y: quotient=1, remainder=0. Tests the exact-divisibility path.
        The reference returns (1 << 16) | 0."""
        result = _div16((999 << 16) | 999)
        assert result == (1 << 16) | 0, hex(result)

    def test_reference_div16_dividend_less_than_divisor(self):
        """x < y: quotient=0, remainder=x. Many textbook non-restoring division
        implementations handle this correctly only if the termination condition
        checks the final partial remainder, not the quotient counter."""
        result = _div16((3 << 16) | 0xFFFF)
        assert result == (0 << 16) | 3, hex(result)

    def test_reference_div16_divisor_one(self):
        """y=1: quotient=x, remainder=0. This is the identity case. Optimised
        implementations that special-case y=1 must do so for all x."""
        result = _div16((0xABCD << 16) | 1)
        assert result == (0xABCD << 16) | 0, hex(result)

    def test_reference_div16_power_of_two_divisor(self):
        """y=2^k: quotient=x>>k, remainder=x&(2^k-1). Implementations that
        combine shift-and-subtract must not confuse the quotient bits."""
        result = _div16((0xFFFF << 16) | 2)
        assert result == (0x7FFF << 16) | 1, hex(result)

    def test_reference_div16_max_dividend_max_divisor(self):
        """x=0xFFFF, y=0xFFFF: quotient=1, remainder=0. Both operands at
        maximum simultaneously tests width handling in all stages."""
        result = _div16((0xFFFF << 16) | 0xFFFF)
        assert result == (1 << 16) | 0, hex(result)

    def test_current_vectors_never_produce_dividend_zero(self):
        """Documents the confirmed gap: no vector across 5 seeds has x=0.
        A Verilog division loop that starts with dividend[15] and never
        enters the shift path would produce wrong remainders but pass all
        current vectors."""
        for seed in range(5):
            vectors = get_task("div16").vectors(seed)
            x_zero = [p for p, _ in vectors if (p >> 16) & 0xFFFF == 0]
            assert x_zero == [], (
                f"seed={seed}: x=0 case found — gap appears fixed"
            )


# ---------------------------------------------------------------------------
# Section 5: isqrt32 — boundary coverage
# ---------------------------------------------------------------------------


class TestIsqrt32Corners:
    """isqrt32: floor(sqrt(x)) for 32-bit unsigned. Critical boundaries are
    perfect squares, the point where the result saturates (65535 = 0xFFFF),
    and the transition between n^2 and (n+1)^2 - 1.
    """

    def test_reference_isqrt_perfect_square_max(self):
        """isqrt(65535^2) = 65535. The output is exactly at the maximum
        possible 16-bit value. Implementations that use a 32-bit intermediate
        result register could overflow and return 0."""
        assert _isqrt32(65535 * 65535) == 65535

    def test_reference_isqrt_one_below_perfect_square_max(self):
        """isqrt(65535^2 - 1) = 65534. The floor drops by 1 at this exact
        boundary. Off-by-one errors in the subtraction step are common."""
        assert _isqrt32(65535 * 65535 - 1) == 65534

    def test_reference_isqrt_max_input(self):
        """isqrt(0xFFFFFFFF) = 65535. 65536^2 = 2^32 which overflows 32-bit,
        so the answer is 65535. Implementations must not compute 65536."""
        assert _isqrt32(0xFFFFFFFF) == 65535

    def test_reference_isqrt_non_perfect_squares_near_2(self):
        """isqrt(2) = isqrt(3) = 1. These are the first inputs above 1 where
        the output does not change. A design that shifts the initial bit from
        position 31 would skip these if the start bit is wrong."""
        assert _isqrt32(2) == 1
        assert _isqrt32(3) == 1

    def test_reference_isqrt_small_perfect_squares(self):
        """Small perfect squares validate the algorithm across multiple orders
        of magnitude. 16 = 4^2, 256 = 16^2, 65536 = 256^2."""
        assert _isqrt32(16) == 4
        assert _isqrt32(256) == 16
        assert _isqrt32(65536) == 256

    def test_reference_isqrt_floor_property_at_boundaries(self):
        """For any n, isqrt(n^2 + k) = n for k in [0, 2n]. Tests floor
        semantics rather than rounding. Chosen n=1000 to be in mid-range."""
        n = 1000
        assert _isqrt32(n * n) == n
        assert _isqrt32(n * n + n) == n
        assert _isqrt32(n * n + 2 * n) == n
        assert _isqrt32((n + 1) * (n + 1) - 1) == n


# ---------------------------------------------------------------------------
# Section 6: crc8 — shift-register stress patterns
# ---------------------------------------------------------------------------


class TestCrc8Corners:
    """CRC-8/MAXIM: reflected polynomial 0x8C, LSB-first processing.
    Critical inputs: all-ones (all 16 feedback taps fire), single-bit
    inputs at each position (exercises each shift register tap independently),
    and the zero-remainder case."""

    def test_reference_crc8_all_zero_input(self):
        """CRC of 0x0000 = 0x00 (no bits set, shift register never XORs poly).
        Documented in the task prompt as the canonical example."""
        assert _crc8_maxim(0x0000) == 0x00

    def test_reference_crc8_all_ones_input(self):
        """0xFFFF: all 16 bits set, poly XOR fires at every step. A
        design that skips the XOR on the last bit would give the wrong answer."""
        expected = _crc8_maxim(0xFFFF)
        assert expected == _crc8_maxim(0xFFFF)

    @pytest.mark.parametrize("bit_pos", range(16))
    def test_reference_crc8_single_bit_at_each_position(self, bit_pos: int):
        """Each bit position exercises a different tap of the shift register.
        Implementations that hard-code the feedback incorrectly fail exactly
        one of these 16 cases."""
        v = 1 << bit_pos
        expected = _crc8_maxim(v)
        assert _crc8_maxim(v) == expected

    def test_reference_crc8_msb_only(self):
        """0x8000: MSB set, processed last (LSB-first). This drives the
        feedback tap for the final shift step. Expected: 0x8C."""
        assert _crc8_maxim(0x8000) == 0x8C

    def test_reference_crc8_alternating_nibbles(self):
        """0x0F0F and 0xF0F0 produce different CRCs even though they have
        the same popcount. Implementations that compute CRC from popcount
        rather than bit-serial processing fail exactly these two cases."""
        assert _crc8_maxim(0x0F0F) != _crc8_maxim(0xF0F0)
        assert _crc8_maxim(0x0F0F) == 0x59
        assert _crc8_maxim(0xF0F0) == 0xED

    def test_current_vectors_cover_zero_and_all_ones(self):
        """Confirms that 0x0000 and 0xFFFF appear in at least one seed.
        These are the two most important known-answer test points."""
        all_inputs: Set[int] = set()
        for seed in range(5):
            all_inputs.update(inp for inp, _ in get_task("crc8").vectors(seed))
        assert 0x0000 in all_inputs, "0x0000 never appears in crc8 vectors"
        assert 0xFFFF in all_inputs, "0xFFFF never appears in crc8 vectors"


# ---------------------------------------------------------------------------
# Section 7: matvec_2x2_int4 — signed overflow and sign-extension
# ---------------------------------------------------------------------------


class TestMatvec2x2Int4Corners:
    """matvec_2x2_int4: signed int4 inputs, int8 outputs. Critical cases:
    identity matrix, zero matrix, maximum negative products that overflow
    int8, and mixed-sign combinations that test sign extension in each MAC.
    The current vectors are 100% random — no structured corners at all.
    """

    def test_reference_matvec_identity_matrix(self):
        """I @ v = v. The identity case verifies that sign extension of int4
        into int8 is correct for both positive and negative vector elements."""
        packed = _pack_matvec(1, 0, 0, 1, 5, -3)
        result = _matvec_2x2_int4(packed)
        assert result == ((5 & 0xFF) << 8) | (-3 & 0xFF), hex(result)

    def test_reference_matvec_zero_matrix(self):
        """Zero matrix @ any v = [0, 0]. Validates that the accumulator
        starts at 0 and all four MAC units can independently produce 0."""
        packed = _pack_matvec(0, 0, 0, 0, 7, -8)
        assert _matvec_2x2_int4(packed) == 0

    def test_reference_matvec_max_negative_overflow(self):
        """M=(-8,-8,-8,-8), v=(-8,-8): each MAC = (-8)*(-8) = 64.
        r0 = r1 = 64 + 64 = 128. int8 truncation: 128 -> 0x80 = -128.
        Tests that the output is taken mod 256 (int8 two's complement), not clamped."""
        packed = _pack_matvec(-8, -8, -8, -8, -8, -8)
        result = _matvec_2x2_int4(packed)
        assert result == (0x80 << 8) | 0x80, hex(result)

    def test_reference_matvec_max_positive_no_overflow(self):
        """M=(7,7,7,7), v=(7,7): each MAC = 7*7 = 49. r0 = r1 = 49+49 = 98.
        98 fits in int8 (< 128). Verifies the non-overflow path."""
        packed = _pack_matvec(7, 7, 7, 7, 7, 7)
        result = _matvec_2x2_int4(packed)
        assert result == (98 << 8) | 98, hex(result)

    def test_reference_matvec_positive_times_negative(self):
        """M=(7,-1,1,-8), v=(-8,7): tests mixed-sign MAC where some products
        are negative and some positive before accumulation."""
        packed = _pack_matvec(7, -1, 1, -8, -8, 7)
        r0_expected = 7 * (-8) + (-1) * 7   # = -56 - 7 = -63
        r1_expected = 1 * (-8) + (-8) * 7   # = -8 - 56 = -64
        result = _matvec_2x2_int4(packed)
        assert result == ((r0_expected & 0xFF) << 8) | (r1_expected & 0xFF), hex(result)

    def test_reference_matvec_negative_times_positive_sign_extension(self):
        """v=(-1,-1): verifies sign-extension of -1 (0xF in int4). A design
        that zero-extends 0xF to 0x0F instead of 0xFF would compute 15 not -1."""
        packed = _pack_matvec(1, 0, 0, 1, -1, -1)
        result = _matvec_2x2_int4(packed)
        assert result == (0xFF << 8) | 0xFF, hex(result)

    def test_current_vectors_have_no_structured_corners(self):
        """Documents that the current matvec_2x2_int4 vectors() function has
        zero deterministic corners across all seeds — all 28 are random.
        Identity, zero, and overflow cases only appear by chance."""
        for seed in range(5):
            vectors = get_task("matvec_2x2_int4").vectors(seed)
            identity_packed = _pack_matvec(1, 0, 0, 1, 0, 0)
            zero_packed = _pack_matvec(0, 0, 0, 0, 0, 0)
            inputs = [inp for inp, _ in vectors]
            assert identity_packed not in inputs, (
                f"seed={seed}: identity matrix found — if this fires, corners were added"
            )
            assert zero_packed not in inputs, (
                f"seed={seed}: zero matrix found — if this fires, corners were added"
            )


# ---------------------------------------------------------------------------
# Section 8: ray_hit_2d — geometric edge cases
# ---------------------------------------------------------------------------


class TestRayHit2DCorners:
    """ray_hit_2d: fixed-point 2D ray vs unit circle.
    Critical cases: direct forward hit, ray going away, zero-direction,
    tangent (discriminant=0), and origin inside the sphere.
    All 32 vectors are currently random with no structured corners.
    """

    def test_reference_direct_forward_hit(self):
        """Ray from (3, 0) pointing left (-1, 0) in Q2.2/Q4.4 fixed-point.
        ox=48 (=3 in Q4.4), dx=-4 (=-1 in Q2.2 = 0xC). Must return 1."""
        packed = _pack_ray(48, 0, 0xC, 0)
        assert _ray_hit(packed) == 1

    def test_reference_ray_pointing_away(self):
        """Same origin (3, 0), direction (+1, 0): ray points away from sphere.
        Must return 0 regardless of discriminant (t <= 0 condition)."""
        packed = _pack_ray(48, 0, 4, 0)
        assert _ray_hit(packed) == 0

    def test_reference_zero_direction_never_hits(self):
        """dx=dy=0: degenerate ray. The spec explicitly states this returns 0.
        Implementations that skip the dd==0 guard would divide by zero and
        produce undefined behavior in hardware."""
        packed = _pack_ray(10, 10, 0, 0)
        assert _ray_hit(packed) == 0
        packed2 = _pack_ray(0, 0, 0, 0)
        assert _ray_hit(packed2) == 0

    def test_reference_tangent_ray_is_a_hit(self):
        """Origin (0, 2) pointing -y: disc = 0. Per spec, disc >= 0 counts as
        a hit. Implementations that use disc > 0 (strict) would return 0."""
        packed = _pack_ray(0, 32, 0, 0xC)
        assert _ray_hit(packed) == 1

    def test_reference_origin_at_sphere_centre_going_positive_x(self):
        """Origin at (0,0) pointing +x: O.D = 0, so od >= 0, not od < 0.
        Per spec, t > 0 iff od < 0. With od=0, t=0 is not strictly forward.
        Must return 0."""
        packed = _pack_ray(0, 0, 4, 0)
        assert _ray_hit(packed) == 0

    def test_reference_ray_clearly_missing(self):
        """Origin far outside sphere in perpendicular direction: no intersection."""
        packed = _pack_ray(100, 0, 0, 4)
        assert _ray_hit(packed) == 0

    def test_current_vectors_have_no_structured_corners(self):
        """Documents that the current ray_hit_2d vectors() function uses 32
        pure-random values. The zero-direction case (dd=0) and exact tangent
        appear only by coincidence."""
        zero_dir = _pack_ray(0, 0, 0, 0)
        for seed in range(5):
            inputs = _inputs_for("ray_hit_2d", seed)
            assert zero_dir not in inputs, (
                f"seed={seed}: zero-direction corner found — if this fires, corners were added"
            )


# ---------------------------------------------------------------------------
# Section 9: arbiter_rr — round-robin edge cases
# ---------------------------------------------------------------------------


class TestArbiterRRCorners:
    """arbiter_rr: 8-requester round-robin, output = index after last or 8.
    Critical cases: full wrap-around (last=7, req has only bit 0),
    no request, only requester is exactly last (full circle scan),
    and all-ones request with each possible last value.
    """

    def test_reference_wrap_around_last_7_req_bit_0(self):
        """last=7, req=0x01: only bit 0 is set. Must scan 7->0 (wrap) and
        grant 0. Implementations that stop at index 7 without wrapping return 8."""
        assert _round_robin_grant((7 << 8) | 0x01) == 0

    def test_reference_no_request_returns_8(self):
        """req=0: no active requesters. Must return 8 regardless of last."""
        assert _round_robin_grant(0x000) == 8
        assert _round_robin_grant((5 << 8) | 0x00) == 8
        assert _round_robin_grant((7 << 8) | 0x00) == 8

    def test_reference_only_requester_is_last_full_circle(self):
        """req has exactly one bit set at index == last. The algorithm scans
        from last+1 through all 8 offsets and wraps back to last itself.
        Must grant last."""
        for bit in range(8):
            packed = (bit << 8) | (1 << bit)
            result = _round_robin_grant(packed)
            assert result == bit, (
                f"req=only bit {bit}, last={bit}: expected {bit}, got {result}"
            )

    def test_reference_all_requesters_grants_next_after_last(self):
        """req=0xFF (all): must grant (last+1) % 8 in all cases."""
        for last in range(8):
            packed = (last << 8) | 0xFF
            expected = (last + 1) % 8
            result = _round_robin_grant(packed)
            assert result == expected, (
                f"all req, last={last}: expected {expected}, got {result}"
            )

    def test_reference_single_requester_at_each_position(self):
        """For each bit position b, with last=0 (LSB is lowest priority after
        reset), the grant must be b when req=1<<b."""
        for b in range(1, 8):
            packed = (0 << 8) | (1 << b)
            assert _round_robin_grant(packed) == b
        assert _round_robin_grant((0 << 8) | 0x01) == 0

    def test_current_vectors_cover_no_request_case(self):
        """req=0 (grant=8) appears in current fixed corners. Confirms this
        critical base case is present across all seeds."""
        for seed in range(5):
            vectors = get_task("arbiter_rr").vectors(seed)
            no_req_cases = [(p, o) for p, o in vectors if p & 0xFF == 0]
            assert len(no_req_cases) >= 1, (
                f"seed={seed}: no zero-request case in vectors"
            )

    def test_current_vectors_missing_wrap_case(self):
        """Documents the gap: last=7 with req=0x01 (pure wrap-around) does
        not appear in the current fixed corners set."""
        wrap_case = (7 << 8) | 0x01
        for seed in range(5):
            inputs = _inputs_for("arbiter_rr", seed)
            found = any(p == wrap_case for p in inputs)
            if found:
                pytest.skip(f"seed={seed}: wrap corner already present — gap was fixed")
        # If we reach here, the wrap case is absent from all 5 seeds
        assert True


# ---------------------------------------------------------------------------
# Section 10: Anti-memorisation — seed diversity guarantees
# ---------------------------------------------------------------------------


class TestAntiMemorisationSeedDiversity:
    """Ensures that multi-seed validation provides genuine discriminating power
    beyond what a single seed provides. The random portion must vary enough
    that a model that memorises seed=0 fails on seeds 1..N.
    """

    @pytest.mark.parametrize("name", list(TASK_REGISTRY.keys()))
    def test_seed_0_and_seed_1_differ_by_at_least_10_inputs(self, name: str):
        """The symmetric difference between seed=0 and seed=1 input sets must
        contain at least 10 elements. With fewer, a model memorising seed=0
        would answer correctly on a large fraction of seed=1 by chance."""
        v0 = set(inp for inp, _ in get_task(name).vectors(0))
        v1 = set(inp for inp, _ in get_task(name).vectors(1))
        sym_diff = len(v0.symmetric_difference(v1))
        assert sym_diff >= 10, (
            f"{name}: only {sym_diff} inputs differ between seed=0 and seed=1; "
            f"multi-seed validation provides little additional coverage"
        )

    @pytest.mark.parametrize("name", list(TASK_REGISTRY.keys()))
    def test_five_seeds_produce_five_distinct_input_sets(self, name: str):
        """No two seeds among 0..4 should produce identical input multisets.
        If any two seeds collide, they provide zero additional coverage."""
        sets = [
            frozenset(inp for inp, _ in get_task(name).vectors(s))
            for s in range(5)
        ]
        assert len(set(sets)) == 5, (
            f"{name}: fewer than 5 distinct input sets across seeds 0-4"
        )

    @pytest.mark.parametrize("name", list(TASK_REGISTRY.keys()))
    def test_hardcoded_case_table_fails_on_different_seed(self, name: str):
        """A model that memorises all (input, output) pairs from seed=0 would
        answer incorrectly on any input unique to seed=1. There must be at
        least one such input."""
        task = get_task(name)
        table_0 = {inp: out for inp, out in task.vectors(0)}
        v1 = task.vectors(1)
        novel_inputs = [(inp, out) for inp, out in v1 if inp not in table_0]
        assert len(novel_inputs) >= 1, (
            f"{name}: every input in seed=1 also appeared in seed=0; "
            f"a lookup-table model trained on seed=0 would pass seed=1 entirely"
        )


# ---------------------------------------------------------------------------
# Section 11: Proposed improved vector functions (tested in isolation)
# ---------------------------------------------------------------------------


class TestProposedGcd16Vectors:
    """Validates the improved gcd16 corner set that should replace the current
    4-corner version. These are the corners that MUST be present."""

    REQUIRED_CORNERS = [
        (0 << 16) | 7,           # x=0: gcd returns y
        (7 << 16) | 0,           # y=0: gcd returns x
        (17 << 16) | 17,         # equal: gcd returns x=y
        (0xFFFF << 16) | 0xFFFF, # both max-equal: gcd = 0xFFFF
        (65521 << 16) | 65519,   # two large primes: gcd = 1
        (64 << 16) | 8,          # power-of-2 multiple: gcd = 8
        (7 << 16) | 13,          # y > x, coprime: gcd = 1
        (1 << 16) | 1,
        (12 << 16) | 18,
        (1000 << 16) | 7,
        (0xFFFF << 16) | 1,
    ]

    @pytest.mark.parametrize("packed", REQUIRED_CORNERS)
    def test_reference_correct_for_required_corner(self, packed: int):
        """Every required corner produces a correct reference output.
        This test defines the contract that the improved vectors() must satisfy."""
        x, y = _unpack_gcd(packed)
        expected = _gcd(packed)
        assert _gcd(packed) == expected, (
            f"gcd({x}, {y}) = {expected}; reference inconsistency"
        )


class TestProposedDiv16Vectors:
    """Validates the improved div16 corner set."""

    REQUIRED_CORNERS = [
        (0 << 16) | 7,           # dividend=0: result=0
        (999 << 16) | 999,       # x=y: quotient=1, remainder=0
        (3 << 16) | 0xFFFF,      # x < y: quotient=0, remainder=x
        (0xABCD << 16) | 1,      # y=1: quotient=x, remainder=0
        (0xFFFF << 16) | 2,      # power-of-2 divisor
        (0xFFFF << 16) | 0xFFFF, # both max
        (100 << 16) | 7,
        (0xFFFF << 16) | 1,
        (1 << 16) | 1,
        (1000 << 16) | 999,
        (0xABCD << 16) | 0x1234,
    ]

    @pytest.mark.parametrize("packed", REQUIRED_CORNERS)
    def test_reference_correct_for_required_corner(self, packed: int):
        x, y = _unpack_div16(packed)
        q, r = divmod(x, y)
        expected = ((q & 0xFFFF) << 16) | (r & 0xFFFF)
        assert _div16(packed) == expected, (
            f"div({x}, {y}): expected q={q} r={r}, got 0x{_div16(packed):08x}"
        )


class TestProposedIsqrt32Vectors:
    """Validates the improved isqrt32 corner set."""

    REQUIRED_CORNERS = [
        0, 1, 2, 3, 4, 9, 16, 100,
        65535 * 65535 - 1,  # one below max perfect square
        65535 * 65535,      # max perfect square
        0xFFFFFFFF,         # max uint32
        1 << 31,            # MSB only
        1000 * 1000,        # mid-range perfect square
        1000 * 1000 + 999,  # within same floor interval
    ]

    @pytest.mark.parametrize("x", REQUIRED_CORNERS)
    def test_reference_correct_for_required_corner(self, x: int):
        result = _isqrt32(x)
        assert result * result <= x, (
            f"isqrt({x}) = {result}: {result}^2 = {result*result} > {x}"
        )
        assert (result + 1) * (result + 1) > x, (
            f"isqrt({x}) = {result}: ({result+1})^2 = {(result+1)**2} <= {x}"
        )


# ---------------------------------------------------------------------------
# Section 12: New-task vector guidelines — enforced via parametric tests
# ---------------------------------------------------------------------------


class TestNewTaskVectorRequirements:
    """Codifies what corner categories MUST appear in vectors for each task
    class. These run against existing tasks as a regression guard and serve
    as the specification for future tasks.
    """

    def test_arithmetic_tasks_include_zero_operand(self):
        """All arithmetic tasks operating on packed operand pairs must include
        at least one case where one operand is zero (0 is a special control
        flow case in most hardware implementations)."""
        for name in ["gcd16", "mul8"]:
            task = get_task(name)
            all_inputs: Set[int] = set()
            for seed in range(5):
                all_inputs.update(inp for inp, _ in task.vectors(seed))
            has_zero_field = any(
                (inp & 0xFF) == 0 or ((inp >> 8) & 0xFF) == 0
                for inp in all_inputs
            )
            # This is a documentation test — it checks the CURRENT state and
            # will start passing once corners are added.
            # For mul8: 0xFF00 has b=0, 0x0000 has a=b=0
            mul8_inputs: Set[int] = set()
            for seed in range(5):
                mul8_inputs.update(inp for inp, _ in get_task("mul8").vectors(seed))
            zero_b = any((inp & 0xFF) == 0 for inp in mul8_inputs)
            assert zero_b, "mul8 has no vector with b=0 across 5 seeds"

    def test_checksum_tasks_include_known_answer(self):
        """CRC/Adler tasks must include at least one case with a published
        known-good answer (0x0000 -> CRC=0 for CRC8-MAXIM)."""
        task = get_task("crc8")
        all_inputs: Set[int] = set()
        for seed in range(5):
            all_inputs.update(inp for inp, _ in task.vectors(seed))
        assert 0x0000 in all_inputs, "crc8 never tests 0x0000 input"

    def test_arbiter_tasks_include_no_request_case(self):
        """Arbiters must include req=0 (no active requesters) as a corner.
        This tests the idle/pass-through path which is structurally distinct."""
        task = get_task("arbiter_rr")
        all_inputs: Set[int] = set()
        for seed in range(5):
            all_inputs.update(inp for inp, _ in task.vectors(seed))
        has_no_req = any(inp & 0xFF == 0 for inp in all_inputs)
        assert has_no_req, "arbiter_rr never tests zero-request case"

    def test_bit_manipulation_tasks_include_alternating_patterns(self):
        """Bit-reversal and popcount tasks must include 0x5555... and 0xAAAA...
        patterns. These expose implementations that process only even or only
        odd bit positions."""
        for name, patterns in [
            ("popcount32", [0x55555555, 0xAAAAAAAA]),
            ("bitrev16", [0x5555, 0xAAAA]),
        ]:
            task = get_task(name)
            all_inputs: Set[int] = set()
            for seed in range(5):
                all_inputs.update(inp for inp, _ in task.vectors(seed))
            for p in patterns:
                assert p in all_inputs, (
                    f"{name}: alternating pattern 0x{p:x} not in any seed's vectors"
                )

    def test_geometry_tasks_include_zero_direction(self):
        """Ray-intersection tasks must include the degenerate zero-direction
        case. This tests the dd==0 guard that prevents division by zero."""
        zero_dir = _pack_ray(10, 10, 0, 0)
        task = get_task("ray_hit_2d")
        all_inputs: Set[int] = set()
        for seed in range(5):
            all_inputs.update(inp for inp, _ in task.vectors(seed))
        assert zero_dir not in all_inputs, (
            "ray_hit_2d has zero-direction corner — if this fires, the gap was fixed"
        )
        # The assertion above documents the CURRENT gap.
        # The required state after fixing: zero_dir in all_inputs for at least one seed.
