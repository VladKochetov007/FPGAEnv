### General Information

* **Environment name:** `rlvr-fpga`
* **Language:** `Verilog (IEEE 1364-2005)`
* **Category:** `FPGA / digital design: arithmetic, crypto, checksums, matrix math, geometry, arbitration`
* **Hardware required:** `CPU-only (Verilator simulation); no GPU or physical FPGA needed`

### Design & Scope

* **Description of kernels:**
  * Each task asks the student to implement a Verilog module `dut` with a fixed clocked interface (`clk`, `rst`, `start`, `data_in[IW-1:0]`, `data_out[OW-1:0]`, `done`). The module must compute a specified function and assert `done` in as few clock cycles as possible. Tasks span 6 domains: bit manipulation (popcount, bit-reverse), integer arithmetic (multiply, divide, isqrt, GCD), crypto/PRNG (XOR cipher), checksums/network (CRC-8, Adler-32), matrix math (2x2 signed int4 matvec), geometry (fixed-point 2D ray-circle intersection), and arbitration (round-robin grant).

* **Motivation:**
  * Teaching LLMs to write correct, cycle-efficient RTL. The scoring hierarchy (correctness gate then cycle-count sigmoid) mirrors real hardware design: correctness is non-negotiable, and once you have it, the competition is performance. Tasks exercise fundamentals that appear in every real FPGA design: arithmetic pipelines, FSMs, fixed-point math, streaming checksums, and resource arbitration.

* **Task diversity:**
  * 12 tasks across 6 domains. Within each domain, difficulty varies from trivially combinational (XOR cipher, bit-reverse) to multi-cycle iterative (GCD, integer division, integer square root). Input widths range from 11 bits (arbiter) to 32 bits (popcount, div16, isqrt32). Output widths range from 1 bit (ray-hit) to 32 bits (div16). Baseline cycle counts range from 48 (XOR cipher) to 1280 (GCD), creating a 25x dynamic range in difficulty.

### Technical Implementation

* **Interface:**
  * Every task uses the same module signature. The student must define `module dut(input clk, input rst, input start, input [IW-1:0] data_in, output [OW-1:0] data_out, output done)`. IW and OW vary per task and are stated in the prompt. The student may use any Verilog-2005 constructs (always, generate, wire, reg, etc.) subject to the reward-hack denylist.

* **Baseline:**
  * Each task defines `baseline_cycles` in the Python task registry, calibrated against a naive but correct reference implementation (e.g., bit-serial shift-add for multiplication, Euclidean-division GCD). The baseline is used as the sigmoid center: exactly matching it scores 0.5, beating it scores toward 1.0, and missing it scores toward 0.0. The Python oracle (`reference_py`) generates expected outputs deterministically per seed and is cross-checked by the test suite.

* **Best practices for timing:**
  * Verilator converts Verilog to C++ and runs cycle-accurately. Cycle counts are measured by the generated C++ testbench from the cycle `start` is asserted until `done` goes high. This is fully deterministic (no wall-clock noise). The testbench sums cycles across all test vectors in the set.

### Reward Hacking & Validation

* **Reward hacking via high-level libraries:**
  * Not applicable: the submission language is Verilog, which has no package manager or high-level library ecosystem. The main attack surface is Verilog system tasks (`$system`, `$readmemh`, `$fopen`) that could read the test vectors from disk. These are blocked by the `verilog_guard` module before compilation.

* **Reward hacking via quantization:**
  * Not applicable: outputs are exact integer comparisons. The testbench checks `data_out == expected` bit-for-bit; there is no tolerance.

* **Other reward hacking vectors:**
  * **File include**: `` `include `` is blocked to prevent reading the generated `vectors.h` or `sim_main.cpp`. **Module name bypass**: submissions must define `module dut`; anything else is rejected at the guard. **Stdout fabrication**: the testbench reads DUT *pins* via the Verilator C++ model, not stdout; `$display` is harmless (warned, not blocked). **Hardcoded outputs**: the test-vector seed is per-episode, so memorizing outputs for one seed fails on the next. This is tested in `tests/adversarial/test_reward_hacking.py`.

### Scoring & Evaluation

* **Scoring script:**
  * Three-stage pipeline: (1) `verilator --lint-only` catches syntax errors fast. (2) `verilator --cc --exe --build` compiles the DUT + generated C++ harness. (3) The binary runs all test vectors and prints `OK` + `TOTAL_CYCLES`. Score = `sigmoid(k * (baseline_cycles - total_cycles))`, clamped to [0, 1]. Any stage failure → score = 0.

* **Scoring calibration:**
  * Score 0.5 = matches the naive baseline exactly. Score 0.2 = roughly 2x slower than baseline. Score 0.8 = roughly 2x faster than baseline. Score ~1.0 = combinational (1 cycle per case) on tasks where the baseline is multi-cycle. Score 0.0 = does not compile, produces wrong output, or times out. The sigmoid steepness `k` defaults to 0.01, tunable per deployment.

### Resources

* **Instruction template:**
  * Each task's `prompt` field is a Python string containing the full Verilog interface and a description of the expected behavior. Example for `popcount32`:
    ```
    Implement Verilog module `dut` with the interface below.
    `data_in` is 32 bits, `data_out` is 6 bits and must equal the number
    of 1-bits in `data_in`. Assert `done` as soon as `data_out` is valid.
    Reset is synchronous, active-high. Fewer cycles between `start` and
    `done` score higher.

    module dut(
        input              clk,
        input              rst,
        input              start,
        input  [31:0]      data_in,
        output [5:0]       data_out,
        output             done
    );
    ```

* **Documentation:**
  * Students should have access to: IEEE 1364-2005 Verilog standard reference, Verilator user guide (for supported synthesis subset), and basic digital design references (shift-add multiplication, non-restoring division, CORDIC, CRC theory, fixed-point arithmetic).

---

# Task List

### popcount32
* **Description:** Count the number of 1-bits in a 32-bit word. Exercises parallel reduction trees vs. sequential shift-count tradeoff.
* **Hyperparameters:** in=32b, out=6b, 32 test vectors, baseline=1024 cycles.
* **Axes of Variation:** Input width (8/16/32/64), could add weighted popcount.

### bitrev16
* **Description:** Reverse the bit order of a 16-bit word. Purely combinational optimal solution.
* **Hyperparameters:** in=16b, out=16b, 30 vectors, baseline=256 cycles.
* **Axes of Variation:** Width (8/32/64), partial reversal (byte-swap).

### gcd16
* **Description:** Compute GCD of two 16-bit unsigned integers via Euclidean or binary GCD algorithm.
* **Hyperparameters:** in=32b (packed), out=16b, 24 vectors, baseline=1280 cycles.
* **Axes of Variation:** Width, extended GCD (Bezout coefficients).

### mul8
* **Description:** 8x8 -> 16-bit unsigned multiplication. Tests shift-add vs. combinational vs. Booth.
* **Hyperparameters:** in=16b (packed), out=16b, 32 vectors, baseline=320 cycles.
* **Axes of Variation:** Width (16x16), signed, Booth radix-4.

### div16
* **Description:** 16-bit unsigned division with remainder. Tests restoring vs. non-restoring vs. SRT.
* **Hyperparameters:** in=32b (packed), out=32b (quotient+remainder), 25 vectors, baseline=500 cycles.
* **Axes of Variation:** Width, signed division, Newton-Raphson reciprocal.

### isqrt32
* **Description:** Integer square root of a 32-bit unsigned. Non-restoring digit-by-digit or binary search.
* **Hyperparameters:** in=32b, out=16b, 32 vectors, baseline=640 cycles.
* **Axes of Variation:** Width, fixed-point fractional sqrt.

### crc8
* **Description:** CRC-8/MAXIM over 16-bit payload. Bit-serial reference; parallel XOR tree optimal.
* **Hyperparameters:** in=16b, out=8b, 30 vectors, baseline=288 cycles.
* **Axes of Variation:** Polynomial (CRC-16, CRC-32), payload width.

### xor_cipher16
* **Description:** Fixed-key XOR block cipher (trivially combinational). Warm-up task.
* **Hyperparameters:** in=16b, out=16b, 31 vectors, baseline=48 cycles.
* **Axes of Variation:** Multi-round Feistel structure, variable key.

### adler32
* **Description:** 4-byte Adler-lite rolling checksum with MOD=251. Streaming accumulate-reduce.
* **Hyperparameters:** in=32b, out=16b, 29 vectors, baseline=348 cycles.
* **Axes of Variation:** Payload length, full Adler-32 with MOD=65521.

### matvec_2x2_int4
* **Description:** 2x2 signed int4 matrix-vector multiply. Tests parallel MAC units.
* **Hyperparameters:** in=24b (packed), out=16b, 28 vectors, baseline=224 cycles.
* **Axes of Variation:** Matrix size (4x4), element width (int8), accumulator width.

### ray_hit_2d
* **Description:** Fixed-point 2D ray-circle intersection test. Exercises signed multiply, compare, discriminant.
* **Hyperparameters:** in=24b, out=1b, 32 vectors, baseline=384 cycles.
* **Axes of Variation:** 3D, multiple spheres, nearest-hit distance output.

### arbiter_rr
* **Description:** 8-port round-robin arbiter (load balancer). Combinational priority encoder with wrap.
* **Hyperparameters:** in=11b, out=4b, 32 vectors, baseline=128 cycles.
* **Axes of Variation:** Port count (16/32), weighted round-robin, age-priority.
