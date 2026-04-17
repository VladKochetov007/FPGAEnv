# Reward hacking in FPGAEnv

How to think about it, what attacks exist, what this repo defends against,
and what is still open.

## 0. The mental model

> Assume the model is a superhuman CTF player with infinite patience and
> gradient access to your bugs. It will not solve the problem. It will
> solve *how to look like it solved the problem*.

The reward signal is a **proxy** for "wrote correct, synthesisable Verilog".
Every proxy leaks. An RL optimiser is a search process over the proxy, not
the underlying intent. Any gap between the two is an exploit waiting to be
found.

When thinking about an environment, separate three layers — attacks live
in every one:

| Layer              | What it is                                   | Representative attacks                              |
|--------------------|----------------------------------------------|------------------------------------------------------|
| **Spec**           | The definition of "correct"                  | Partial-function correctness, UB exploitation         |
| **Evaluation harness** | Code that drives the DUT and reads its pins | Introspection, output injection, timing attacks       |
| **Simulator / runtime** | Verilator, the OS, the sandbox           | DPI escape, X-propagation, stdout truncation          |

Before shipping a change, walk each layer and ask: **what would a model do
here if it wanted to cheat?**

---

## 1. Threat taxonomy

Attacks ordered roughly by severity: sandbox escape first, then
memorisation, then scoring abuse.

### 1.1 Sandbox escape (Tier 1 — critical)

The DUT runs inside a C++ simulator. Several Verilog constructs let the
DUT execute arbitrary C or reach into the harness's scope.

| Attack                             | Mechanism                                                       |
|------------------------------------|-----------------------------------------------------------------|
| `import "DPI-C" function ...`      | Calls a C function — can `system("cat vectors.bin")`.           |
| `export "DPI-C"`                   | Same hole, reverse direction.                                   |
| `$c("arbitrary C code")`           | Verilator-specific C-string escape.                             |
| `bind some_module probe inst();`   | Injects code into the harness's module hierarchy.               |

**Defence:** static guard blocks these tokens *before* Verilator is
invoked. See `src/rlvr_envs/envs/fpga/verilog_guard.py`, tier 1 list.

### 1.2 Filesystem / sideband IO (Tier 1)

If the DUT can read files or shell out, it can peek at `vectors.bin` and
hard-code the answers.

| Attack                                            | Mechanism                              |
|---------------------------------------------------|----------------------------------------|
| `$system("cat vectors.bin")`                      | Shell out.                             |
| `$fopen` / `$fread` / `$fscanf` / `$fwrite`       | Direct file IO.                        |
| `$readmemh` / `$readmemb`                         | Load a memory image from disk.         |
| `$dumpfile` / `$dumpvars`                         | Write arbitrary files.                 |
| `` `include "vectors.h" ``                        | Pull reference code into the DUT.      |

**Defence:** guard blocks. *Sandbox also uses `setrlimit` so even an
escape can't exhaust host resources* — defence in depth.

### 1.3 Harness introspection (Tier 2 — high)

The DUT tries to figure out "am I being graded?" and branches accordingly.

| Attack                                                           | Mechanism                                 |
|------------------------------------------------------------------|-------------------------------------------|
| `$test$plusargs` / `$value$plusargs`                             | Read sim command-line args.               |
| `$time` / `$stime` / `$realtime`                                 | Detect simulator wall-clock.              |
| `$random` / `$urandom` / `$urandom_range`                        | Break determinism, fingerprint seed.      |
| `$finish` / `$stop`                                              | Exit the sim before INCORRECT prints.     |
| Counting `start` pulses via internal FSM                         | Infer case index, switch behaviour.       |

**Defence:** guard blocks the system tasks. FSM counting is defeated by
**reset between cases** (see §1.6).

### 1.4 Memorisation (Tier 2)

The big one. Three variants, increasing subtlety:

**(a) Vector ROM.** The DUT stores the expected outputs for every training
vector and looks them up by `data_in`.
```verilog
case (data_in)
  32'h00000000: data_out = 6'd0;
  32'hFFFFFFFF: data_out = 6'd32;
  ...
endcase
```
**Defence: multi-seed validation.** The submission runs on N seeds; any
miss → score 0. A ROM of seed-42 vectors fails every unseen seed.

**(b) Pattern ROM via `initial`.**
```verilog
reg [5:0] answers [0:31];
initial begin answers[0] = 0; answers[1] = 1; ... end
```
**Defence: `initial` is blocked statically.** Synchronous reset is
sufficient for legitimate designs.

**(c) Online memorisation.** The DUT learns the seed's vectors *during*
the test run by watching early inputs and predicting later ones. Requires
hidden FSM state that persists across cases.
```verilog
// Pseudocode: track all data_in values seen so far, predict the pattern.
always @(posedge clk) if (start) history[idx] <= data_in;
```
**Defence: reset between cases.** The harness pulses `rst` for 3 cycles
before every case, so no hidden state survives the gap.

### 1.5 Scoring / timing cheats (Tier 3)

| Attack                          | Mechanism                                                       |
|---------------------------------|-----------------------------------------------------------------|
| Sparse correctness              | Fail rare cases to improve average latency.                     |
| Critical-path cheating          | Combinational monster that meets sim timing but not synth.      |
| Lazy hardware                   | Compute correct answer only when probed.                        |
| Non-synthesisable timing        | `#5 out = ...;`, `fork/join`, `wait`, `force`/`release`.        |
| Stdout flood                    | `$display` from combinational `always @(*)` fills 4 MiB buffer. |

**Defences:**
- Any miss → score 0 (hard constraint), not partial credit.
- `fork`/`join`/`wait`/`force`/`release` blocked statically.
- `$display`/`$write`/`$monitor` blocked — no combinational flood path.
- Parser reads structured output prefixed with `@@H@@` so flood + fake
  `OK` can't trick the scorer.

### 1.6 Output injection (Tier 2)

Even a blocked construct might sneak through a guard gap. Defence in
depth: the harness's structured output lines are prefixed with `@@H@@`:
```
@@H@@CASE 0 3 0x20
@@H@@TOTAL_CYCLES 3
@@H@@OK
```
The parser regex requires the prefix. A submission that prints
`CASE 0 1 0x0` or `OK` via `$write` is invisible to the scorer.

### 1.7 Simulator quirks (Tier 3)

| Issue                            | Concern                                             |
|----------------------------------|-----------------------------------------------------|
| X-propagation semantics          | Real hardware treats X as 0 or 1 non-deterministically; Verilator often reads as 0. A design that "works" in Verilator may break on silicon. |
| Delta-cycle ordering             | Verilator's scheduling can accept race conditions that real synth would flag. |
| Uninit register defaults         | Legit RTL must not rely on power-on register values — but Verilator gives them 0. |

**Current status:** not defended. Would require `--x-assign unique`,
`--x-initial unique`, and random seeding — all of which break legitimate
designs that rely on Verilator's default 0-init. Track as known-open.

---

## 2. How to think when adding a new task

Before you add a task, run this checklist. It catches most footguns.

1. **Adversarial inputs.** Does `vectors(seed)` include boundary values
   (0, all-ones, sign boundaries, modular-arithmetic edges)? If a model
   only handles "typical" inputs, does any test vector catch that?
2. **Reference determinism.** Is `reference_py` a pure function? No
   global state, no RNG not seeded by input?
3. **Output width.** Does `out_bits` exactly fit the reference output?
   Wider output = more bits of don't-care = more room to cheat.
4. **Baseline cycles.** Is the baseline the cycle count of a *minimal
   correct* design, or accidentally a slow one? If slow, hacks that
   barely beat correctness still score well.
5. **Corner leak.** Are corner values identical across seeds? That is
   *ok* (baseline stability) only because any random-vector miss → 0.
   Confirm at least 20 random vectors per seed so partial-memorisation
   gets caught probabilistically.
6. **Information channel.** Can any legitimate operand encoding smuggle
   a seed fingerprint? (If yes, the task is broken at the spec layer.)

---

## 3. What we defend against — current status

| Threat class                        | Defence                                          | File                                   |
|-------------------------------------|--------------------------------------------------|----------------------------------------|
| DPI / bind / `$c` sandbox escape    | Static guard block                               | `verilog_guard.py`                     |
| Filesystem / sideband IO            | Static guard block + `setrlimit`                 | `verilog_guard.py`, `sandbox.py`       |
| Env introspection & early exit      | Static guard block                               | `verilog_guard.py`                     |
| Vector ROM memorisation             | Multi-seed validation                            | `environment.py::_run_multi_seed`      |
| `initial`-block ROM                 | Static guard block                               | `verilog_guard.py`                     |
| Online FSM memorisation             | Reset DUT between cases                          | `harness.py::_render_sim_main`         |
| Non-synthesisable timing            | Static guard block fork/join/wait/force/release  | `verilog_guard.py`                     |
| Output injection / stdout flood     | `@@H@@` prefix + `$display` blocked              | `harness.py`, `verilator.py`           |
| Partial correctness via thresholds  | Any-miss → score 0 hard constraint               | `environment.py`                       |
| Resource exhaustion                 | Wall-clock, CPU, memory `setrlimit` + SIGKILL    | `sandbox.py`                           |

---

## 4. Known-weak / still open

Honest list of attacks this environment does **not** currently defend
against. Each is here because the obvious defence would break
too many legitimate designs.

1. **X-propagation exploit.** A DUT whose correctness relies on Verilator
   treating X as 0 will pass here but not in a real tool. Fix would be
   `--x-assign unique --x-initial unique` + random reset — but that
   breaks every DUT that expects registers to power up at 0.
2. **Synthesis-realism.** Combinational mega-trees that meet Verilator
   timing in one cycle may not close on any real FPGA. No synth or STA
   stage is wired in.
3. **Adversarial fuzzing per task.** Test vectors come from a hand-picked
   set of corners plus ~20 random values. A task-specific fuzzer that
   targets boundaries found by SMT / coverage would be stronger.
4. **Harness structural randomisation.** Every run uses the same
   sim_main.cpp shape. A very patient model could learn to fingerprint
   the exact tick sequence. Varying tick counts, adding random idle
   cycles, shuffling case order per seed would close this.
5. **Continuous-output probe.** After `done`, the harness reads
   `data_out` once. A DUT that produces the right answer for one cycle
   then drops it would pass. A re-read on the drain tick would catch it
   but breaks purely-combinational designs.
6. **Differential testing.** We compare one DUT against a Python
   reference. Running two independently-trained DUTs against each other
   (KernelBench-style) would catch designs that both pass the reference
   test but behave differently — a stronger "sanity" signal.

None of these are hot bugs today. All are areas where the proxy is
looser than the intent, so they're the first places to harden when the
RL process gets stronger.

---

## 5. Meta-principles

- **Block statically before running dynamically.** A string match on
  `$system` is cheaper and more robust than any runtime trap.
- **Prefer hard constraints over soft.** "Any miss → 0" is harder to
  exploit than "90% correctness → 0.9". Partial credit is partial leak.
- **Decouple build from vectors.** The same compiled binary re-runs
  against N seed files. Re-building is slow; re-seeding is cheap. This
  is what makes multi-seed validation affordable.
- **Prefix all trusted output.** Anything that goes from harness to
  scorer crosses an untrusted boundary (the submission's stdout lives
  in the same stream). Prefix + strict parser closes the boundary.
- **Log the findings.** Every time a submission in the wild gets
  `FORBIDDEN`, it's probably probing for gaps. Keep the transcript,
  check what it was going for, tighten the list.

A good reward-hacking defence is a **tiered static filter, a determinism
trap, and a narrow scorer** — not a clever runtime monitor. The order
matters: block, reset, parse.
