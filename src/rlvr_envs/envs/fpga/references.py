"""Reference Verilog implementations for all FPGA tasks.

Each reference is what a competent engineer writes in 15-30 minutes:
simple, correct, not optimized. These establish baseline cycle count (ref)
used in scoring formula S = ref / (ref + measured).

baseline_cycles values are total cycles across all test vectors at seed=0.
Validate by running references through environment.
"""

from __future__ import annotations

REFERENCES: dict[str, str] = {

    # ---- Bit manipulation ------------------------------------------------

    "popcount32": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [31:0]      data_in,
    output reg [5:0]   data_out,
    output reg         done
);
    reg [31:0] shift;
    reg [5:0]  count;
    reg [5:0]  idx;
    reg        active;

    always @(posedge clk) begin
        if (rst) begin
            done   <= 0;
            active <= 0;
        end else if (start) begin
            shift  <= data_in;
            count  <= 0;
            idx    <= 0;
            active <= 1;
            done   <= 0;
        end else if (active) begin
            count <= count + {5'd0, shift[0]};
            shift <= shift >> 1;
            if (idx == 31) begin
                data_out <= count + {5'd0, shift[0]};
                done     <= 1;
                active   <= 0;
            end
            idx <= idx + 1;
        end else begin
            done <= 0;
        end
    end
endmodule
""",

    "bitrev16": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [15:0]      data_in,
    output reg [15:0]  data_out,
    output reg         done
);
    reg [15:0] in_sr, out_sr;
    reg [4:0]  idx;
    reg        active;

    always @(posedge clk) begin
        if (rst) begin
            done   <= 0;
            active <= 0;
        end else if (start) begin
            in_sr  <= data_in;
            out_sr <= 0;
            idx    <= 0;
            active <= 1;
            done   <= 0;
        end else if (active) begin
            out_sr <= {out_sr[14:0], in_sr[0]};
            in_sr  <= in_sr >> 1;
            if (idx == 15) begin
                data_out <= {out_sr[14:0], in_sr[0]};
                done     <= 1;
                active   <= 0;
            end
            idx <= idx + 1;
        end else begin
            done <= 0;
        end
    end
endmodule
""",

    # ---- Arithmetic / math pipelines ------------------------------------

    "gcd16": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [31:0]      data_in,
    output reg [15:0]  data_out,
    output reg         done
);
    reg [15:0] a, b;
    reg [3:0]  k;
    reg        active;

    always @(posedge clk) begin
        if (rst) begin
            done   <= 0;
            active <= 0;
        end else if (start) begin
            a      <= data_in[31:16];
            b      <= data_in[15:0];
            k      <= 0;
            active <= 1;
            done   <= 0;
        end else if (active) begin
            if (a == 0) begin
                data_out <= b << k;
                done     <= 1;
                active   <= 0;
            end else if (b == 0) begin
                data_out <= a << k;
                done     <= 1;
                active   <= 0;
            end else if (!a[0] && !b[0]) begin
                a <= a >> 1;
                b <= b >> 1;
                k <= k + 1;
            end else if (!a[0]) begin
                a <= a >> 1;
            end else if (!b[0]) begin
                b <= b >> 1;
            end else if (a >= b) begin
                a <= (a - b) >> 1;
            end else begin
                b <= (b - a) >> 1;
            end
        end else begin
            done <= 0;
        end
    end
endmodule
""",

    "mul8": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [15:0]      data_in,
    output reg [15:0]  data_out,
    output reg         done
);
    reg [15:0] product, mcand;
    reg [7:0]  mplier;
    reg [3:0]  idx;
    reg        active;

    always @(posedge clk) begin
        if (rst) begin
            done   <= 0;
            active <= 0;
        end else if (start) begin
            product <= 0;
            mcand   <= {8'd0, data_in[15:8]};
            mplier  <= data_in[7:0];
            idx     <= 0;
            active  <= 1;
            done    <= 0;
        end else if (active) begin
            if (mplier[0])
                product <= product + mcand;
            mcand  <= mcand << 1;
            mplier <= mplier >> 1;
            if (idx == 7) begin
                if (mplier[0])
                    data_out <= product + mcand;
                else
                    data_out <= product;
                done   <= 1;
                active <= 0;
            end
            idx <= idx + 1;
        end else begin
            done <= 0;
        end
    end
endmodule
""",

    "div16": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [31:0]      data_in,
    output reg [31:0]  data_out,
    output reg         done
);
    reg [15:0] dividend, divisor, quot, rem;
    reg [4:0]  idx;
    reg [1:0]  state;

    always @(posedge clk) begin
        if (rst) begin
            done  <= 0;
            state <= 0;
        end else case (state)
            2'd0: begin
                done <= 0;
                if (start) begin
                    dividend <= data_in[31:16];
                    divisor  <= data_in[15:0];
                    rem      <= 0;
                    quot     <= 0;
                    idx      <= 0;
                    state    <= 1;
                end
            end
            2'd1: begin
                if ({rem[14:0], dividend[15]} >= divisor) begin
                    rem  <= {rem[14:0], dividend[15]} - divisor;
                    quot <= {quot[14:0], 1'b1};
                end else begin
                    rem  <= {rem[14:0], dividend[15]};
                    quot <= {quot[14:0], 1'b0};
                end
                dividend <= {dividend[14:0], 1'b0};
                if (idx == 15)
                    state <= 2;
                idx <= idx + 1;
            end
            2'd2: begin
                data_out <= {quot, rem};
                done     <= 1;
                state    <= 0;
            end
            default: state <= 0;
        endcase
    end
endmodule
""",

    "isqrt32": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [31:0]      data_in,
    output reg [15:0]  data_out,
    output reg         done
);
    reg [31:0] n, bit_val, result;
    reg [4:0]  idx;
    reg [1:0]  state;

    always @(posedge clk) begin
        if (rst) begin
            done  <= 0;
            state <= 0;
        end else case (state)
            2'd0: begin
                done <= 0;
                if (start) begin
                    n       <= data_in;
                    bit_val <= 32'h40000000;
                    result  <= 0;
                    idx     <= 0;
                    state   <= 1;
                end
            end
            2'd1: begin
                if (n >= result + bit_val) begin
                    n      <= n - (result + bit_val);
                    result <= (result >> 1) + bit_val;
                end else begin
                    result <= result >> 1;
                end
                bit_val <= bit_val >> 2;
                if (idx == 15)
                    state <= 2;
                idx <= idx + 1;
            end
            2'd2: begin
                data_out <= result[15:0];
                done     <= 1;
                state    <= 0;
            end
            default: state <= 0;
        endcase
    end
endmodule
""",

    # ---- Crypto / checksum / network framing ----------------------------

    "crc8": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [15:0]      data_in,
    output reg [7:0]   data_out,
    output reg         done
);
    reg [15:0] shift;
    reg [7:0]  crc;
    reg [4:0]  idx;
    reg [1:0]  state;

    always @(posedge clk) begin
        if (rst) begin
            done  <= 0;
            state <= 0;
        end else case (state)
            2'd0: begin
                done <= 0;
                if (start) begin
                    shift <= data_in;
                    crc   <= 8'h00;
                    idx   <= 0;
                    state <= 1;
                end
            end
            2'd1: begin
                if (crc[0] ^ shift[0])
                    crc <= (crc >> 1) ^ 8'h8C;
                else
                    crc <= crc >> 1;
                shift <= shift >> 1;
                if (idx == 15)
                    state <= 2;
                idx <= idx + 1;
            end
            2'd2: begin
                data_out <= crc;
                done     <= 1;
                state    <= 0;
            end
            default: state <= 0;
        endcase
    end
endmodule
""",

    "xor_cipher16": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [15:0]      data_in,
    output reg [15:0]  data_out,
    output reg         done
);
    always @(posedge clk) begin
        if (rst) begin
            data_out <= 0;
            done     <= 0;
        end else if (start) begin
            data_out <= data_in ^ 16'hA55A;
            done     <= 1;
        end else begin
            done <= 0;
        end
    end
endmodule
""",

    "adler32": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [31:0]      data_in,
    output reg [15:0]  data_out,
    output reg         done
);
    reg [7:0]  s1, s2;
    reg [31:0] data;
    reg [2:0]  byte_idx;
    reg [1:0]  state;

    wire [8:0] s1_sum = {1'b0, s1} + {1'b0, data[7:0]};
    wire [8:0] s1_mod = (s1_sum >= 9'd502) ? s1_sum - 9'd502 :
                        (s1_sum >= 9'd251) ? s1_sum - 9'd251 : s1_sum;
    wire [8:0] s2_sum = {1'b0, s2} + s1_mod;
    wire [8:0] s2_mod = (s2_sum >= 9'd502) ? s2_sum - 9'd502 :
                        (s2_sum >= 9'd251) ? s2_sum - 9'd251 : s2_sum;

    always @(posedge clk) begin
        if (rst) begin
            done  <= 0;
            state <= 0;
        end else case (state)
            2'd0: begin
                done <= 0;
                if (start) begin
                    data     <= data_in;
                    s1       <= 8'd1;
                    s2       <= 8'd0;
                    byte_idx <= 0;
                    state    <= 1;
                end
            end
            2'd1: begin
                s1   <= s1_mod[7:0];
                s2   <= s2_mod[7:0];
                data <= data >> 8;
                if (byte_idx == 3)
                    state <= 2;
                byte_idx <= byte_idx + 1;
            end
            2'd2: begin
                data_out <= {s2, s1};
                done     <= 1;
                state    <= 0;
            end
            default: state <= 0;
        endcase
    end
endmodule
""",

    # ---- Matrix math / geometry -----------------------------------------

    "matvec_2x2_int4": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [23:0]      data_in,
    output reg [15:0]  data_out,
    output reg         done
);
    reg signed [7:0] m00, m01, m10, m11, v0, v1;
    reg signed [7:0] r0, r1;
    reg [2:0]  step;
    reg        active;

    always @(posedge clk) begin
        if (rst) begin
            done   <= 0;
            active <= 0;
        end else if (start) begin
            m00    <= {{4{data_in[23]}}, data_in[23:20]};
            m01    <= {{4{data_in[19]}}, data_in[19:16]};
            m10    <= {{4{data_in[15]}}, data_in[15:12]};
            m11    <= {{4{data_in[11]}}, data_in[11:8]};
            v0     <= {{4{data_in[7]}},  data_in[7:4]};
            v1     <= {{4{data_in[3]}},  data_in[3:0]};
            r0     <= 0;
            r1     <= 0;
            step   <= 0;
            active <= 1;
            done   <= 0;
        end else if (active) begin
            case (step)
                0: r0 <= m00 * v0;
                1: r0 <= r0 + m01 * v1;
                2: r1 <= m10 * v0;
                3: r1 <= r1 + m11 * v1;
                4: begin
                    data_out <= {r0[7:0], r1[7:0]};
                    done     <= 1;
                    active   <= 0;
                end
            endcase
            step <= step + 1;
        end else begin
            done <= 0;
        end
    end
endmodule
""",

    "ray_hit_2d": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [23:0]      data_in,
    output reg [0:0]   data_out,
    output reg         done
);
    reg signed [31:0] ox, oy, dx, dy;
    reg signed [31:0] dd, od, oo, disc;
    reg [2:0]  step;
    reg        active;

    always @(posedge clk) begin
        if (rst) begin
            done   <= 0;
            active <= 0;
        end else if (start) begin
            ox     <= {{24{data_in[23]}}, data_in[23:16]};
            oy     <= {{24{data_in[15]}}, data_in[15:8]};
            dx     <= {{28{data_in[7]}},  data_in[7:4]};
            dy     <= {{28{data_in[3]}},  data_in[3:0]};
            step   <= 0;
            active <= 1;
            done   <= 0;
        end else if (active) begin
            case (step)
                0: dd <= dx * dx + dy * dy;
                1: od <= ox * dx + oy * dy;
                2: oo <= ox * ox + oy * oy;
                3: disc <= od * od - dd * (oo - 32'sd1024);
                4: begin
                    data_out <= (|dd) && !disc[31] && od[31];
                    done     <= 1;
                    active   <= 0;
                end
            endcase
            step <= step + 1;
        end else begin
            done <= 0;
        end
    end
endmodule
""",

    # ---- Arbitration / load balancing -----------------------------------

    "arbiter_rr": """\
module dut(
    input              clk,
    input              rst,
    input              start,
    input  [10:0]      data_in,
    output reg [3:0]   data_out,
    output reg         done
);
    reg [2:0] last;
    reg [7:0] req;
    reg [3:0] offset;
    reg       active;

    wire [2:0] scan_idx = (last + offset[2:0]) & 3'b111;

    always @(posedge clk) begin
        if (rst) begin
            done   <= 0;
            active <= 0;
        end else if (start) begin
            last <= data_in[10:8];
            req  <= data_in[7:0];
            done <= 0;
            if (data_in[7:0] == 8'd0) begin
                data_out <= 4'd8;
                done     <= 1;
            end else begin
                offset <= 1;
                active <= 1;
            end
        end else if (active) begin
            if (req[scan_idx]) begin
                data_out <= {1'b0, scan_idx};
                done     <= 1;
                active   <= 0;
            end else if (offset == 4'd8) begin
                data_out <= 4'd8;
                done     <= 1;
                active   <= 0;
            end
            offset <= offset + 1;
        end else begin
            done <= 0;
        end
    end
endmodule
""",

}
