# ✅ anthropic/claude-sonnet-4.6 — crc8

> **Verdict:** `ok`  **Score:** `0.500`  **Cycles:** `540` / `540` baseline  **API:** `8.2s`  **Tokens:** `750`
> Timestamp: `2026-04-16T18:34:02Z`  Seed: `42`

---

## Prompt

**System:**
```
You are an expert Verilog RTL designer. Write synthesizable Verilog that compiles with Verilator. Output ONLY the complete module source inside a single ```verilog code block. No explanations outside the code block.
```

**User:**
```
Implement CRC-8/MAXIM over a 16-bit payload (reflected, polynomial
0x31 reflected to 0x8C, initial value 0x00, no final XOR). Bits are
processed LSB-first. Output `data_out[7:0]` is the final CRC.
Example: data_in=0x0000 -> CRC=0x00.

module dut(
    input              clk,
    input              rst,
    input              start,
    input  [15:0]      data_in,
    output reg [7:0]   data_out,
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
    input  [15:0]      data_in,
    output reg [7:0]   data_out,
    output reg         done
);

    // CRC-8/MAXIM: reflected polynomial 0x8C, init 0x00, no final XOR
    // Process 16 bits LSB-first
    
    reg [7:0]  crc;
    reg [15:0] data_reg;
    reg [4:0]  bit_count;
    reg        active;
    
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            crc       <= 8'h00;
            data_reg  <= 16'h0000;
            bit_count <= 5'd0;
            active    <= 1'b0;
            done      <= 1'b0;
            data_out  <= 8'h00;
        end else begin
            done <= 1'b0;
            
            if (start && !active) begin
                crc       <= 8'h00;
                data_reg  <= data_in;
                bit_count <= 5'd0;
                active    <= 1'b1;
            end else if (active) begin
                if (bit_count < 5'd16) begin
                    // Process one bit LSB-first
                    if ((crc[0] ^ data_reg[0]) == 1'b1) begin
                        crc <= {1'b0, crc[7:1]} ^ 8'h8C;
                    end else begin
                        crc <= {1'b0, crc[7:1]};
                    end
                    data_reg  <= {1'b0, data_reg[15:1]};
                    bit_count <= bit_count + 5'd1;
                end else begin
                    data_out <= crc;
                    done     <= 1'b1;
                    active   <= 1'b0;
                end
            end
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
    input  [15:0]      data_in,
    output reg [7:0]   data_out,
    output reg         done
);

    // CRC-8/MAXIM: reflected polynomial 0x8C, init 0x00, no final XOR
    // Process 16 bits LSB-first
    
    reg [7:0]  crc;
    reg [15:0] data_reg;
    reg [4:0]  bit_count;
    reg        active;
    
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            crc       <= 8'h00;
            data_reg  <= 16'h0000;
            bit_count <= 5'd0;
            active    <= 1'b0;
            done      <= 1'b0;
            data_out  <= 8'h00;
        end else begin
            done <= 1'b0;
            
            if (start && !active) begin
                crc       <= 8'h00;
                data_reg  <= data_in;
                bit_count <= 5'd0;
                active    <= 1'b1;
            end else if (active) begin
                if (bit_count < 5'd16) begin
                    // Process one bit LSB-first
                    if ((crc[0] ^ data_reg[0]) == 1'b1) begin
                        crc <= {1'b0, crc[7:1]} ^ 8'h8C;
                    end else begin
                        crc <= {1'b0, crc[7:1]};
                    end
                    data_reg  <= {1'b0, data_reg[15:1]};
                    bit_count <= bit_count + 5'd1;
                end else begin
                    data_out <= crc;
                    done     <= 1'b1;
                    active   <= 1'b0;
                end
            end
        end
    end

endmodule
```

---

## Simulation result

**Verdict:** `ok`

**Simulator stdout:**
```
CASE 0 18 0x0
CASE 1 18 0xb4
CASE 2 18 0x37
CASE 3 18 0xb2
CASE 4 18 0xc4
CASE 5 18 0x8c
CASE 6 18 0x22
CASE 7 18 0xcb
CASE 8 18 0x77
CASE 9 18 0xce
CASE 10 18 0xa9
CASE 11 18 0xb7
CASE 12 18 0x8e
CASE 13 18 0xfa
CASE 14 18 0x3f
CASE 15 18 0xf9
CASE 16 18 0x1e
CASE 17 18 0x8d
CASE 18 18 0x79
CASE 19 18 0x8f
CASE 20 18 0x94
CASE 21 18 0x32
CASE 22 18 0x1d
CASE 23 18 0x29
CASE 24 18 0x93
CASE 25 18 0xd1
CASE 26 18 0xc0
CASE 27 18 0x5b
CASE 28 18 0xcf
CASE 29 18 0x62
TOTAL_CYCLES 540
OK
```
