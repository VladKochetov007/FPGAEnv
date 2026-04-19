# ✅ anthropic/claude-sonnet-4-6 — graph_reach_4

> **Verdict:** `ok`  **Score:** `0.925`  **Cycles:** `31` / `384` baseline  **API:** `9.1s`  **Tokens:** `959`
> Timestamp: `2026-04-19T20:47:10Z`  Seed: `42`

---

## Prompt

**System:**
```
You are an expert Verilog RTL designer. Write synthesizable Verilog that compiles with Verilator. Output ONLY the complete module source inside a single ```verilog code block. No explanations outside the code block.
```

**User:**
```
Directed-graph reachability on 4 nodes. `data_in[15:0]` is a 4x4
adjacency bitmap: bit `4*u+v` is 1 iff there is a directed edge from
u to v. `data_in[17:16] = src`, `data_in[19:18] = tgt`. Output
`data_out[0] = 1` iff tgt is reachable from src (src is always
reachable from itself). Fully combinational matrix-closure runs in
one cycle: reach = I + A + A^2 + A^3 over booleans.

module dut(
    input              clk,
    input              rst,
    input              start,
    input  [19:0]      data_in,
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
    input  [19:0]      data_in,
    output reg [0:0]   data_out,
    output reg         done
);

    wire [15:0] A = data_in[15:0];
    wire [1:0]  src = data_in[17:16];
    wire [1:0]  tgt = data_in[19:18];

    // Compute transitive closure using boolean matrix multiplication
    // reach = I | A | A^2 | A^3
    
    // A[u][v] = A[4*u+v]
    
    function automatic [15:0] mat_mul;
        input [15:0] M1, M2;
        integer r, c, k;
        reg val;
        begin
            mat_mul = 16'b0;
            for (r = 0; r < 4; r = r + 1) begin
                for (c = 0; c < 4; c = c + 1) begin
                    val = 1'b0;
                    for (k = 0; k < 4; k = k + 1) begin
                        val = val | (M1[4*r+k] & M2[4*k+c]);
                    end
                    mat_mul[4*r+c] = val;
                end
            end
        end
    endfunction

    // Identity matrix
    wire [15:0] I = 16'b0001_0010_0100_1000; // I[4*i+i] = 1
    // Actually: I[4*0+0]=bit0, I[4*1+1]=bit5, I[4*2+2]=bit10, I[4*3+3]=bit15
    // Let me recalculate: bit 4*u+v
    // u=0,v=0: bit 0; u=1,v=1: bit 5; u=2,v=2: bit 10; u=3,v=3: bit 15
    // So I = (1<<0)|(1<<5)|(1<<10)|(1<<15) = 16'h8421
    
    wire [15:0] identity = 16'h8421;
    
    wire [15:0] A2 = mat_mul(A, A);
    wire [15:0] A3 = mat_mul(A2, A);
    
    wire [15:0] reach = identity | A | A2 | A3;
    
    always @(*) begin
        data_out[0] = reach[4*src + tgt];
        done = start;
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
    input  [19:0]      data_in,
    output reg [0:0]   data_out,
    output reg         done
);

    wire [15:0] A = data_in[15:0];
    wire [1:0]  src = data_in[17:16];
    wire [1:0]  tgt = data_in[19:18];

    // Compute transitive closure using boolean matrix multiplication
    // reach = I | A | A^2 | A^3
    
    // A[u][v] = A[4*u+v]
    
    function automatic [15:0] mat_mul;
        input [15:0] M1, M2;
        integer r, c, k;
        reg val;
        begin
            mat_mul = 16'b0;
            for (r = 0; r < 4; r = r + 1) begin
                for (c = 0; c < 4; c = c + 1) begin
                    val = 1'b0;
                    for (k = 0; k < 4; k = k + 1) begin
                        val = val | (M1[4*r+k] & M2[4*k+c]);
                    end
                    mat_mul[4*r+c] = val;
                end
            end
        end
    endfunction

    // Identity matrix
    wire [15:0] I = 16'b0001_0010_0100_1000; // I[4*i+i] = 1
    // Actually: I[4*0+0]=bit0, I[4*1+1]=bit5, I[4*2+2]=bit10, I[4*3+3]=bit15
    // Let me recalculate: bit 4*u+v
    // u=0,v=0: bit 0; u=1,v=1: bit 5; u=2,v=2: bit 10; u=3,v=3: bit 15
    // So I = (1<<0)|(1<<5)|(1<<10)|(1<<15) = 16'h8421
    
    wire [15:0] identity = 16'h8421;
    
    wire [15:0] A2 = mat_mul(A, A);
    wire [15:0] A3 = mat_mul(A2, A);
    
    wire [15:0] reach = identity | A | A2 | A3;
    
    always @(*) begin
        data_out[0] = reach[4*src + tgt];
        done = start;
    end

endmodule
```

---

## Simulation result

**Verdict:** `ok`

**Simulator stdout:**
```
@@H@@CASE 0 1 0x1
@@H@@CASE 1 1 0x0
@@H@@CASE 2 1 0x1
@@H@@CASE 3 1 0x1
@@H@@CASE 4 1 0x0
@@H@@CASE 5 1 0x1
@@H@@CASE 6 1 0x1
@@H@@CASE 7 1 0x0
@@H@@CASE 8 1 0x1
@@H@@CASE 9 1 0x0
@@H@@CASE 10 1 0x1
@@H@@CASE 11 1 0x1
@@H@@CASE 12 1 0x1
@@H@@CASE 13 1 0x1
@@H@@CASE 14 1 0x1
@@H@@CASE 15 1 0x1
@@H@@CASE 16 1 0x1
@@H@@CASE 17 1 0x1
@@H@@CASE 18 1 0x1
@@H@@CASE 19 1 0x1
@@H@@CASE 20 1 0x0
@@H@@CASE 21 1 0x1
@@H@@CASE 22 1 0x1
@@H@@CASE 23 1 0x1
@@H@@CASE 24 1 0x0
@@H@@CASE 25 1 0x0
@@H@@CASE 26 1 0x0
@@H@@CASE 27 1 0x1
@@H@@CASE 28 1 0x1
@@H@@CASE 29 1 0x1
@@H@@CASE 30 1 0x1
@@H@@TOTAL_CYCLES 31
@@H@@OK
```
