# ✅ anthropic/claude-sonnet-4-6 — binsearch_8x4

> **Verdict:** `ok`  **Score:** `0.889`  **Cycles:** `30` / `240` baseline  **API:** `11.2s`  **Tokens:** `1217`
> Timestamp: `2026-04-19T20:47:28Z`  Seed: `42`

---

## Prompt

**System:**
```
You are an expert Verilog RTL designer. Write synthesizable Verilog that compiles with Verilator. Output ONLY the complete module source inside a single ```verilog code block. No explanations outside the code block.
```

**User:**
```
Binary search. `data_in[31:0]` holds 8 non-decreasing 4-bit unsigned
values `arr[i] = data_in[4*i +: 4]` for i=0..7. `data_in[35:32]` is
the 4-bit target. Output `data_out[3:0]` = the lowest index i with
`arr[i] == target`, or 8 if not present. The array is guaranteed
sorted; exploit it. A combinational 3-level compare tree is optimal.

module dut(
    input              clk,
    input              rst,
    input              start,
    input  [35:0]      data_in,
    output reg [3:0]   data_out,
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
    input  [35:0]      data_in,
    output reg [3:0]   data_out,
    output reg         done
);

    wire [3:0] target = data_in[35:32];
    wire [3:0] arr[0:7];
    
    genvar g;
    generate
        for (g = 0; g < 8; g = g + 1) begin : arr_assign
            assign arr[g] = data_in[4*g +: 4];
        end
    endgenerate
    
    // Binary search combinational logic
    // Level 1: compare with arr[3] (mid of 0..7)
    // Level 2: compare with arr[1] or arr[5]
    // Level 3: compare with arr[0], arr[2], arr[4], arr[6]
    
    reg [3:0] result;
    
    always @(*) begin
        // Binary search tree
        // lo=0, hi=7, mid=3
        if (target <= arr[3]) begin
            // search 0..3, mid=1
            if (target <= arr[1]) begin
                // search 0..1, mid=0
                if (target <= arr[0]) begin
                    // check arr[0]
                    if (arr[0] == target)
                        result = 4'd0;
                    else
                        result = 4'd8; // target < arr[0], not found
                end else begin
                    // arr[0] < target <= arr[1]
                    if (arr[1] == target)
                        result = 4'd1;
                    else
                        result = 4'd8;
                end
            end else begin
                // arr[1] < target <= arr[3], search 2..3, mid=2
                if (target <= arr[2]) begin
                    if (arr[2] == target)
                        result = 4'd2;
                    else
                        result = 4'd8;
                end else begin
                    // arr[2] < target <= arr[3]
                    if (arr[3] == target)
                        result = 4'd3;
                    else
                        result = 4'd8;
                end
            end
        end else begin
            // target > arr[3], search 4..7, mid=5
            if (target <= arr[5]) begin
                // search 4..5, mid=4
                if (target <= arr[4]) begin
                    if (arr[4] == target)
                        result = 4'd4;
                    else
                        result = 4'd8;
                end else begin
                    // arr[4] < target <= arr[5]
                    if (arr[5] == target)
                        result = 4'd5;
                    else
                        result = 4'd8;
                end
            end else begin
                // target > arr[5], search 6..7, mid=6
                if (target <= arr[6]) begin
                    if (arr[6] == target)
                        result = 4'd6;
                    else
                        result = 4'd8;
                end else begin
                    // target > arr[6]
                    if (arr[7] == target)
                        result = 4'd7;
                    else
                        result = 4'd8;
                end
            end
        end
    end
    
    always @(posedge clk) begin
        if (rst) begin
            data_out <= 4'd0;
            done <= 1'b0;
        end else if (start) begin
            data_out <= result;
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
    input  [35:0]      data_in,
    output reg [3:0]   data_out,
    output reg         done
);

    wire [3:0] target = data_in[35:32];
    wire [3:0] arr[0:7];
    
    genvar g;
    generate
        for (g = 0; g < 8; g = g + 1) begin : arr_assign
            assign arr[g] = data_in[4*g +: 4];
        end
    endgenerate
    
    // Binary search combinational logic
    // Level 1: compare with arr[3] (mid of 0..7)
    // Level 2: compare with arr[1] or arr[5]
    // Level 3: compare with arr[0], arr[2], arr[4], arr[6]
    
    reg [3:0] result;
    
    always @(*) begin
        // Binary search tree
        // lo=0, hi=7, mid=3
        if (target <= arr[3]) begin
            // search 0..3, mid=1
            if (target <= arr[1]) begin
                // search 0..1, mid=0
                if (target <= arr[0]) begin
                    // check arr[0]
                    if (arr[0] == target)
                        result = 4'd0;
                    else
                        result = 4'd8; // target < arr[0], not found
                end else begin
                    // arr[0] < target <= arr[1]
                    if (arr[1] == target)
                        result = 4'd1;
                    else
                        result = 4'd8;
                end
            end else begin
                // arr[1] < target <= arr[3], search 2..3, mid=2
                if (target <= arr[2]) begin
                    if (arr[2] == target)
                        result = 4'd2;
                    else
                        result = 4'd8;
                end else begin
                    // arr[2] < target <= arr[3]
                    if (arr[3] == target)
                        result = 4'd3;
                    else
                        result = 4'd8;
                end
            end
        end else begin
            // target > arr[3], search 4..7, mid=5
            if (target <= arr[5]) begin
                // search 4..5, mid=4
                if (target <= arr[4]) begin
                    if (arr[4] == target)
                        result = 4'd4;
                    else
                        result = 4'd8;
                end else begin
                    // arr[4] < target <= arr[5]
                    if (arr[5] == target)
                        result = 4'd5;
                    else
                        result = 4'd8;
                end
            end else begin
                // target > arr[5], search 6..7, mid=6
                if (target <= arr[6]) begin
                    if (arr[6] == target)
                        result = 4'd6;
                    else
                        result = 4'd8;
                end else begin
                    // target > arr[6]
                    if (arr[7] == target)
                        result = 4'd7;
                    else
                        result = 4'd8;
                end
            end
        end
    end
    
    always @(posedge clk) begin
        if (rst) begin
            data_out <= 4'd0;
            done <= 1'b0;
        end else if (start) begin
            data_out <= result;
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
@@H@@CASE 0 1 0x0
@@H@@CASE 1 1 0x8
@@H@@CASE 2 1 0x0
@@H@@CASE 3 1 0x0
@@H@@CASE 4 1 0x7
@@H@@CASE 5 1 0x8
@@H@@CASE 6 1 0x4
@@H@@CASE 7 1 0x8
@@H@@CASE 8 1 0x0
@@H@@CASE 9 1 0x0
@@H@@CASE 10 1 0x4
@@H@@CASE 11 1 0x4
@@H@@CASE 12 1 0x5
@@H@@CASE 13 1 0x7
@@H@@CASE 14 1 0x5
@@H@@CASE 15 1 0x8
@@H@@CASE 16 1 0x8
@@H@@CASE 17 1 0x8
@@H@@CASE 18 1 0x6
@@H@@CASE 19 1 0x8
@@H@@CASE 20 1 0x8
@@H@@CASE 21 1 0x7
@@H@@CASE 22 1 0x4
@@H@@CASE 23 1 0x3
@@H@@CASE 24 1 0x0
@@H@@CASE 25 1 0x6
@@H@@CASE 26 1 0x3
@@H@@CASE 27 1 0x0
@@H@@CASE 28 1 0x6
@@H@@CASE 29 1 0x4
@@H@@TOTAL_CYCLES 30
@@H@@OK
```
