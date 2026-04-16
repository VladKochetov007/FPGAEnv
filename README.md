# rlvr-envs

OpenEnv-compatible RLVR/GRPO environments for training LLMs to write synthesizable Verilog. The primary environment grades Verilog submissions via Verilator simulation and returns a scalar reward in [0, 1].

Built for reinforcement learning with verifiable rewards -- the score is deterministic, reproducible, and impossible to game without solving the actual problem.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# requires verilator (apt install verilator / dnf install verilator)
pytest tests/ -x -q           # 255 tests, ~45s
pytest tests/ -m verilator    # E2E tests only (need verilator installed)
```

## Architecture

```
src/rlvr_envs/
    core/                    # env-agnostic framework
        base_env.py          # RLVREnvironment -- abstract reset/step/grade loop
        models.py            # SubmissionAction, SubmissionObservation, Verdict
        scoring.py           # S = baseline/(baseline+measured), scale-invariant
        sandbox.py           # SubprocessSandbox (setrlimit+SIGKILL), MockSandbox
    envs/fpga/               # Verilog/Verilator environment
        environment.py       # FPGAEnvironment -- lint -> build -> simulate -> score
        tasks.py             # 12 task definitions with Python oracles and vector generators
        references.py        # handwritten Verilog reference implementations per task
        harness.py           # C++ testbench and vectors.h generator
        verilator.py         # verilator CLI wrapper + simulation output parser
        verilog_guard.py     # anti-reward-hack pre-checks ($system, $readmemh, etc.)
        models.py            # FPGATask dataclass
        client.py            # OpenEnv HTTP/WS client
        server/app.py        # FastAPI server entrypoint
    runtime/
        local.py             # LocalEnv -- in-process wrapper for GRPO rollouts
```

## How it works

Each episode is a single-shot grading:

```
reset(seed, task_id)  -->  prompt (Verilog module spec)
step(source)          -->  observation (verdict, score, cycles, ...)
```

The grading pipeline runs three sandbox-isolated stages:

1. **Lint** -- `verilator --lint-only` catches syntax/structural errors fast
2. **Build** -- `verilator --cc --exe --build` compiles DUT + generated testbench
3. **Simulate** -- runs the binary, testbench applies all (input, expected) vectors

If any stage fails, the verdict maps to the appropriate category (COMPILE_ERROR, TIMEOUT, INCORRECT, FORBIDDEN). Only on OK is a performance score computed.

## Scoring

```
S = baseline / (baseline + measured)
```

| Property | Value |
|----------|-------|
| At baseline | S = 0.5 |
| Measured -> 0 (perfect) | S -> 1.0 |
| Measured -> inf (terrible) | S -> 0.0 |
| Scale-invariant | same ratio = same score regardless of absolute values |
| Tuning parameters | none |

Baselines come from handwritten reference implementations (shift-and-add multiplier, binary GCD, bit-serial CRC, etc.) in `references.py`. A combinational solution that finishes in 1 cycle/case scores close to 1.0; a solution matching the reference scores 0.5.

## Tasks

12 tasks across 6 domains. All share the same DUT interface:

```verilog
module dut(
    input              clk,
    input              rst,      // synchronous, active-high
    input              start,    // pulse high for one cycle
    input  [IW-1:0]    data_in,  // packed task-specific payload
    output reg [OW-1:0] data_out, // packed task-specific result
    output reg         done      // high when data_out is valid
);
```

| Task | Domain | data_in | data_out | Baseline (cy) | Reference approach |
|------|--------|---------|----------|---------------|--------------------|
| popcount32 | Bit manipulation | 32b | 6b | 1056 | Shift-and-count, 33 cy/case |
| bitrev16 | Bit manipulation | 16b | 16b | 510 | Shift-in/shift-out, 17 cy/case |
| gcd16 | Arithmetic | 32b (x,y) | 16b | 500 | Binary GCD with factor-of-2 |
| mul8 | Arithmetic | 16b (a,b) | 16b | 288 | Shift-and-add, 9 cy/case |
| div16 | Arithmetic | 32b (x,y) | 32b (q,r) | 450 | Restoring division, 18 cy/case |
| isqrt32 | Arithmetic | 32b | 16b | 576 | Non-restoring digit-by-digit |
| crc8 | Crypto/checksum | 16b | 8b | 540 | Bit-serial LFSR, 18 cy/case |
| xor_cipher16 | Crypto/checksum | 16b | 16b | 31 | Combinational XOR, 1 cy/case |
| adler32 | Checksum | 32b | 16b (s2,s1) | 174 | Byte-serial with mod-251 |
| matvec_2x2_int4 | Matrix math | 24b | 16b | 168 | Sequential 4-step MAC |
| ray_hit_2d | Geometry | 24b | 1b | 192 | Sequential fixed-point |
| arbiter_rr | Networking | 11b | 4b | 105 | Sequential priority scan |

## Anti-reward-hack defenses

1. **Verilog guard** -- blocks `$system`, `$fopen`, `$readmemh`, `$readmemb`, `` `include `` before compilation
2. **Pin-level checking** -- testbench reads `data_out`/`done` directly from DUT pins, not stdout
3. **Randomized vectors** -- test vectors are seeded per episode, hardcoded lookup tables fail on different seeds
4. **Sandbox isolation** -- wall-clock, CPU, memory limits via `setrlimit` + SIGKILL

## Usage modes

### In-process (GRPO training)

```python
from rlvr_envs.envs.fpga.environment import FPGAEnvironment
from rlvr_envs.core.models import SubmissionAction

env = FPGAEnvironment()
obs = env.reset(seed=42, task_id="popcount32")
print(obs.prompt)  # shows the task spec

obs = env.step(SubmissionAction(source="module dut(...); ... endmodule"))
print(obs.verdict, obs.score, obs.raw_metric)
```

### HTTP server (OpenEnv)

```bash
uvicorn rlvr_envs.envs.fpga.server.app:app --host 0.0.0.0 --port 8001
```

### Client

```python
from rlvr_envs.envs.fpga.client import FPGAEnvClient

client = FPGAEnvClient(base_url="http://localhost:8001")
```

## LLM vibe tests

Sends task prompts to real LLM models via OpenRouter, runs responses through the environment, reports results. Validates that the environment produces meaningful signal for actual model outputs.

```bash
cp .env.example .env  # add your OpenRouter API key
python tests/llm_vibe/run.py
python tests/llm_vibe/run.py --models "anthropic/claude-sonnet-4.6" --tasks "popcount32,mul8"
```

### Results

**Cheap models** (gemma-3-27b, mistral-nemo, llama-3.1-8b, phi-4, qwen-2.5-7b):

| Model | Task | Verdict | Score | Cycles | Baseline |
|-------|------|---------|-------|--------|----------|
| google/gemma-3-27b-it | popcount32 | timeout | 0.000 | - | 1056 |
| google/gemma-3-27b-it | xor_cipher16 | ok | 0.500 | 31 | 31 |
| google/gemma-3-27b-it | mul8 | compile_error | 0.000 | - | 288 |
| google/gemma-3-27b-it | bitrev16 | ok | 0.944 | 30 | 510 |
| mistralai/mistral-nemo | popcount32 | compile_error | 0.000 | - | 1056 |
| mistralai/mistral-nemo | xor_cipher16 | ok | 0.500 | 31 | 31 |
| mistralai/mistral-nemo | mul8 | incorrect | 0.000 | - | 288 |
| mistralai/mistral-nemo | bitrev16 | compile_error | 0.000 | - | 510 |
| meta-llama/llama-3.1-8b | xor_cipher16 | ok | 0.500 | 31 | 31 |
| microsoft/phi-4 | mul8 | ok | 0.429 | 384 | 288 |
| **5/20 OK** | | | **avg 0.144** | | |

**Mid-tier models** (deepseek-v3.2, gemini-2.0-flash, gpt-4.1-nano, qwen-2.5-72b):

| Model | Task | Verdict | Score | Cycles | Baseline |
|-------|------|---------|-------|--------|----------|
| deepseek/deepseek-v3.2 | popcount32 | ok | 0.514 | 1000 | 1056 |
| deepseek/deepseek-v3.2 | xor_cipher16 | ok | 0.500 | 31 | 31 |
| deepseek/deepseek-v3.2 | bitrev16 | ok | 0.944 | 30 | 510 |
| google/gemini-2.0-flash | xor_cipher16 | ok | 0.500 | 31 | 31 |
| google/gemini-2.0-flash | bitrev16 | ok | 0.944 | 30 | 510 |
| openai/gpt-4.1-nano | xor_cipher16 | ok | 0.500 | 31 | 31 |
| openai/gpt-4.1-nano | bitrev16 | ok | 0.944 | 30 | 510 |
| **9/16 OK** | | | **avg 0.393** | | |

**Claude Sonnet 4.6** (frontier):

| Task | Verdict | Score | Cycles | Baseline |
|------|---------|-------|--------|----------|
| popcount32 | ok | 0.971 | 32 | 1056 |
| xor_cipher16 | ok | 0.500 | 31 | 31 |
| mul8 | ok | 0.900 | 32 | 288 |
| bitrev16 | ok | 0.944 | 30 | 510 |
| div16 | ok | 0.947 | 25 | 450 |
| adler32 | ok | 0.857 | 29 | 174 |
| **6/6 OK** | | | **avg 0.853** | | |

Key observations:
- xor_cipher16 (trivial XOR) is solvable by all models -- good sanity check
- popcount32 separates weak from strong models -- only DeepSeek-v3.2 and Claude solve it
- mul8 is a trap -- most models write buggy shift-add multipliers
- Scores produce clean gradient: 0.5 at baseline, 0.94+ for combinational solutions
- No model attempted reward hacking (no FORBIDDEN verdicts)

## Test suite

```
tests/
    core/
        test_scoring.py          # speed_score formula, edge cases, score_submission
        test_sandbox.py          # SubprocessSandbox limits, timeouts, OOM
    envs/fpga/
        test_environment.py      # full pipeline with MockSandbox
        test_e2e.py              # real Verilator compilation and simulation
        test_tasks.py            # vector generators, Python oracles
        test_harness.py          # C++ testbench generation
        test_verilator_parse.py  # simulation output parsing
        test_verilog_guard.py    # reward-hack detection
    adversarial/
        test_reward_hacking.py   # $system, $readmemh, hardcoded outputs, etc.
    llm_vibe/
        run.py                   # OpenRouter LLM integration test runner
```

255 tests total. Tests marked `@pytest.mark.verilator` require Verilator installed.

## Dependencies

- Python >= 3.10
- [openenv-core](https://github.com/open-env/openenv-core) >= 0.2.2
- [Verilator](https://www.veripool.org/verilator/) (for E2E tests and actual grading)
- GCC/G++ with C++17 support (for Verilator compilation)
