# ✅ anthropic/claude-sonnet-4-6 — subset_sum_4x6

> **Verdict:** `ok`  **Score:** `0.914`  **Cycles:** `30` / `320` baseline  **API:** `5.9s`  **Tokens:** `750`
> Timestamp: `2026-04-19T20:46:55Z`  Seed: `42`

---

## Prompt

**System:**
```
You are an expert Verilog RTL designer. Write synthesizable Verilog that compiles with Verilator. Output ONLY the complete module source inside a single ```verilog code block. No explanations outside the code block.
```

**User:**
```
Subset-sum decision. `data_in[23:0]` holds four 6-bit unsigned values
with `v[i] = data_in[6*i +: 6]`, i=0..3. `data_in[31:24]` is an 8-bit
target. Output `data_out[0] = 1` iff some subset S of {v0,v1,v2,v3}
satisfies sum(S) == target. The empty set sums to 0, so target=0 is
always satisfiable. With 2^4 = 16 subsets, a fully combinational
16-way adder tree + OR-reduction of 16 equality comparators fits in
one cycle.

module dut(
    input              clk,
    input              rst,
    input              start,
    input  [31:0]      data_in,
    output reg [0:0]   data_out,
    output reg         done
);
```

---

## Model response

```verilog
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [31:0]      data_in,
    output reg [0:0]   data_out,
    output reg         done
);

    wire [5:0] v0 = data_in[5:0];
    wire [5:0] v1 = data_in[11:6];
    wire [5:0] v2 = data_in[17:12];
    wire [5:0] v3 = data_in[23:18];
    wire [7:0] target = data_in[31:24];

    reg found;
    integer s;
    reg [7:0] subset_sum;

    always @(*) begin
        found = 1'b0;
        for (s = 0; s < 16; s = s + 1) begin
            subset_sum = 8'd0;
            if (s[0]) subset_sum = subset_sum + {2'b00, v0};
            if (s[1]) subset_sum = subset_sum + {2'b00, v1};
            if (s[2]) subset_sum = subset_sum + {2'b00, v2};
            if (s[3]) subset_sum = subset_sum + {2'b00, v3};
            if (subset_sum == target) found = 1'b1;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            data_out <= 1'b0;
            done <= 1'b0;
        end else if (start) begin
            data_out <= found;
            done <= 1'b1;
        end else begin
            done <= 1'b0;
        end
    end

endmodule
```

---

## Extracted Verilog

```verilog
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [31:0]      data_in,
    output reg [0:0]   data_out,
    output reg         done
);

    wire [5:0] v0 = data_in[5:0];
    wire [5:0] v1 = data_in[11:6];
    wire [5:0] v2 = data_in[17:12];
    wire [5:0] v3 = data_in[23:18];
    wire [7:0] target = data_in[31:24];

    reg found;
    integer s;
    reg [7:0] subset_sum;

    always @(*) begin
        found = 1'b0;
        for (s = 0; s < 16; s = s + 1) begin
            subset_sum = 8'd0;
            if (s[0]) subset_sum = subset_sum + {2'b00, v0};
            if (s[1]) subset_sum = subset_sum + {2'b00, v1};
            if (s[2]) subset_sum = subset_sum + {2'b00, v2};
            if (s[3]) subset_sum = subset_sum + {2'b00, v3};
            if (subset_sum == target) found = 1'b1;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            data_out <= 1'b0;
            done <= 1'b0;
        end else if (start) begin
            data_out <= found;
            done <= 1'b1;
        end else begin
            done <= 1'b0;
        end
    end

endmodule
```

---

## Simulation result

**Verdict:** `ok`

**Simulator stdout:**
```
@@H@@CASE 0 1 0x1
@@H@@CASE 1 1 0x1
@@H@@CASE 2 1 0x1
@@H@@CASE 3 1 0x0
@@H@@CASE 4 1 0x1
@@H@@CASE 5 1 0x0
@@H@@CASE 6 1 0x1
@@H@@CASE 7 1 0x0
@@H@@CASE 8 1 0x1
@@H@@CASE 9 1 0x1
@@H@@CASE 10 1 0x1
@@H@@CASE 11 1 0x1
@@H@@CASE 12 1 0x1
@@H@@CASE 13 1 0x1
@@H@@CASE 14 1 0x1
@@H@@CASE 15 1 0x0
@@H@@CASE 16 1 0x0
@@H@@CASE 17 1 0x1
@@H@@CASE 18 1 0x1
@@H@@CASE 19 1 0x1
@@H@@CASE 20 1 0x1
@@H@@CASE 21 1 0x1
@@H@@CASE 22 1 0x1
@@H@@CASE 23 1 0x1
@@H@@CASE 24 1 0x0
@@H@@CASE 25 1 0x0
@@H@@CASE 26 1 0x1
@@H@@CASE 27 1 0x1
@@H@@CASE 28 1 0x1
@@H@@CASE 29 1 0x0
@@H@@TOTAL_CYCLES 30
@@H@@OK
```
