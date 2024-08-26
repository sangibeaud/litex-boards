#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2021 Franck Jullien <franck.jullien@collshade.fr>
# Copyright (c) 2021 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.gen import *

from litex_boards.platforms import efinix_ti375_c529_dev_kit

from litex.soc.cores.clock import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.builder import *
from litex.soc.cores.led import LedChaser
from litex.soc.interconnect import axi

from liteeth.phy.trionrgmii import LiteEthPHYRGMII

# CRG ----------------------------------------------------------------------------------------------

class _CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq):
        #self.rst    = Signal()
        self.cd_sys = ClockDomain()

        # # #

        clk25 = platform.request("clk25")
        rst_n = platform.request("user_btn", 0)

        # PLL
        self.pll = pll = TITANIUMPLL(platform)
        self.comb += pll.reset.eq(~rst_n)
        pll.register_clkin(clk25, 25e6)
        # You can use CLKOUT0 only for clocks with a maximum frequency of 4x
        # (integer) of the reference clock. If all your system clocks do not fall within
        # this range, you should dedicate one unused clock for CLKOUT0.
        pll.create_clkout(None, 25e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq, with_reset=True)


# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, sys_clk_freq=100e6,
        **kwargs):
        platform = efinix_ti375_c529_dev_kit.Platform()

        # CRG --------------------------------------------------------------------------------------
        self.crg = _CRG(platform, sys_clk_freq)

        # SoCCore ----------------------------------------------------------------------------------
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on Efinix Ti375 C529 Dev Kit", **kwargs)

        # LPDDR4 SDRAM -----------------------------------------------------------------------------
        if not self.integrated_main_ram_size:
            # DRAM / PLL Blocks.
            # ------------------
            dram_pll_refclk = platform.request("dram_pll_refclk")
            platform.toolchain.excluded_ios.append(dram_pll_refclk)
            self.platform.toolchain.additional_sdc_commands.append(f"create_clock -period {1e9/50e6} dram_pll_refclk")

            from litex.build.efinix import InterfaceWriterBlock, InterfaceWriterXMLBlock
            import xml.etree.ElementTree as et

            class PLLDRAMBlock(InterfaceWriterBlock):
                @staticmethod
                def generate():
                    return """
design.create_block("dram_pll", block_type="PLL")
design.set_property("dram_pll", {"REFCLK_FREQ":"50.0"}, block_type="PLL")
design.gen_pll_ref_clock("dram_pll", pll_res="PLL_BR0", refclk_src="EXTERNAL", refclk_name="dram_pll_clkin", ext_refclk_no="0")
design.set_property("dram_pll","LOCKED_PIN","dram_pll_locked", block_type="PLL")
design.set_property("dram_pll","RSTN_PIN","dram_pll_rst_n", block_type="PLL")
design.set_property("dram_pll", {"CLKOUT0_PIN" : "dram_pll_CLKOUT0"}, block_type="PLL")
design.set_property("dram_pll","CLKOUT0_PHASE","0","PLL")
calc_result = design.auto_calc_pll_clock("dram_pll", {"CLKOUT0_FREQ": "400.0"})
"""
            platform.toolchain.ifacewriter.blocks.append(PLLDRAMBlock())

            class DRAMXMLBlock(InterfaceWriterXMLBlock):
                @staticmethod
                def generate(root, namespaces):
                    # CHECKME: Switch to DDRDesignService?
                    ddr_info = root.find("efxpt:ddr_info", namespaces)

                    ddr = et.SubElement(ddr_info, "efxpt:ddr",
                        name            = "ddr_inst1",
                        ddr_def         = "DDR_0",
                        cs_preset_id    = "173",
                        cs_mem_type     = "LPDDR3",
                        cs_ctrl_width   = "x32",
                        cs_dram_width   = "x32",
                        cs_dram_density = "8G",
                        cs_speedbin     = "800",
                        target0_enable  = "true",
                        target1_enable  = "true",
                        ctrl_type       = "none"
                    )

                    gen_pin_target0 = et.SubElement(ddr, "efxpt:gen_pin_target0")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_wdata",  type_name=f"WDATA_0",  is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_wready", type_name=f"WREADY_0", is_bus="false")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_wid",    type_name=f"WID_0",    is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_bready", type_name=f"BREADY_0", is_bus="false")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_rdata",  type_name=f"RDATA_0",  is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_aid",    type_name=f"AID_0",    is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_bvalid", type_name=f"BVALID_0", is_bus="false")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_rlast",  type_name=f"RLAST_0",  is_bus="false")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_bid",    type_name=f"BID_0",    is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_asize",  type_name=f"ASIZE_0",  is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_atype",  type_name=f"ATYPE_0",  is_bus="false")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_aburst", type_name=f"ABURST_0", is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_wvalid", type_name=f"WVALID_0", is_bus="false")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_wlast",  type_name=f"WLAST_0",  is_bus="false")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_aaddr",  type_name=f"AADDR_0",  is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_rid",    type_name=f"RID_0",    is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_avalid", type_name=f"AVALID_0", is_bus="false")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_rvalid", type_name=f"RVALID_0", is_bus="false")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_alock",  type_name=f"ALOCK_0",  is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_rready", type_name=f"RREADY_0", is_bus="false")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_rresp",  type_name=f"RRESP_0",  is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_wstrb",  type_name=f"WSTRB_0",  is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_aready", type_name=f"AREADY_0", is_bus="false")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi0_alen",   type_name=f"ALEN_0",   is_bus="true")
                    et.SubElement(gen_pin_target0, "efxpt:pin", name="axi_clk",     type_name=f"ACLK_0",   is_bus="false", is_clk="true", is_clk_invert="false")

                    gen_pin_target1 = et.SubElement(ddr, "efxpt:gen_pin_target1")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_wdata",  type_name=f"WDATA_1",  is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_wready", type_name=f"WREADY_1", is_bus="false")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_wid",    type_name=f"WID_1",    is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_bready", type_name=f"BREADY_1", is_bus="false")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_rdata",  type_name=f"RDATA_1",  is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_aid",    type_name=f"AID_1",    is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_bvalid", type_name=f"BVALID_1", is_bus="false")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_rlast",  type_name=f"RLAST_1",  is_bus="false")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_bid",    type_name=f"BID_1",    is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_asize",  type_name=f"ASIZE_1",  is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_atype",  type_name=f"ATYPE_1",  is_bus="false")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_aburst", type_name=f"ABURST_1", is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_wvalid", type_name=f"WVALID_1", is_bus="false")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_wlast",  type_name=f"WLAST_1",  is_bus="false")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_aaddr",  type_name=f"AADDR_1",  is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_rid",    type_name=f"RID_1",    is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_avalid", type_name=f"AVALID_1", is_bus="false")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_rvalid", type_name=f"RVALID_1", is_bus="false")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_alock",  type_name=f"ALOCK_1",  is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_rready", type_name=f"RREADY_1", is_bus="false")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_rresp",  type_name=f"RRESP_1",  is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_wstrb",  type_name=f"WSTRB_1",  is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_aready", type_name=f"AREADY_1", is_bus="false")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi1_alen",   type_name=f"ALEN_1",   is_bus="true")
                    et.SubElement(gen_pin_target1, "efxpt:pin", name="axi_clk",     type_name=f"ACLK_1",   is_bus="false", is_clk="true", is_clk_invert="false")

                    gen_pin_config = et.SubElement(ddr, "efxpt:gen_pin_config")
                    et.SubElement(gen_pin_config, "efxpt:pin", name="", type_name="CFG_SEQ_RST",   is_bus="false")
                    et.SubElement(gen_pin_config, "efxpt:pin", name="", type_name="CFG_SCL_IN",    is_bus="false")
                    et.SubElement(gen_pin_config, "efxpt:pin", name="", type_name="CFG_SEQ_START", is_bus="false")
                    et.SubElement(gen_pin_config, "efxpt:pin", name="", type_name="RSTN",          is_bus="false")
                    et.SubElement(gen_pin_config, "efxpt:pin", name="", type_name="CFG_SDA_IN",    is_bus="false")
                    et.SubElement(gen_pin_config, "efxpt:pin", name="", type_name="CFG_SDA_OEN",   is_bus="false")

                    cs_fpga = et.SubElement(ddr, "efxpt:cs_fpga")
                    et.SubElement(cs_fpga, "efxpt:param", name="FPGA_ITERM", value="120", value_type="str")
                    et.SubElement(cs_fpga, "efxpt:param", name="FPGA_OTERM", value="34",  value_type="str")

                    cs_memory = et.SubElement(ddr, "efxpt:cs_memory")
                    et.SubElement(cs_memory, "efxpt:param", name="RTT_NOM",   value="RZQ/2",     value_type="str")
                    et.SubElement(cs_memory, "efxpt:param", name="MEM_OTERM", value="40",        value_type="str")
                    et.SubElement(cs_memory, "efxpt:param", name="CL",        value="RL=6/WL=3", value_type="str")

                    timing = et.SubElement(ddr, "efxpt:cs_memory_timing")
                    et.SubElement(timing, "efxpt:param", name="tRAS",  value="42.000",  value_type="float")
                    et.SubElement(timing, "efxpt:param", name="tRC",   value="60.000",  value_type="float")
                    et.SubElement(timing, "efxpt:param", name="tRP",   value="18.000",  value_type="float")
                    et.SubElement(timing, "efxpt:param", name="tRCD",  value="18.000",  value_type="float")
                    et.SubElement(timing, "efxpt:param", name="tREFI", value="3.900",   value_type="float")
                    et.SubElement(timing, "efxpt:param", name="tRFC",  value="210.000", value_type="float")
                    et.SubElement(timing, "efxpt:param", name="tRTP",  value="10.000",  value_type="float")
                    et.SubElement(timing, "efxpt:param", name="tWTR",  value="10.000",  value_type="float")
                    et.SubElement(timing, "efxpt:param", name="tRRD",  value="10.000",  value_type="float")
                    et.SubElement(timing, "efxpt:param", name="tFAW",  value="50.000",  value_type="float")

                    cs_control = et.SubElement(ddr, "efxpt:cs_control")
                    et.SubElement(cs_control, "efxpt:param", name="AMAP",             value="ROW-COL_HIGH-BANK-COL_LOW", value_type="str")
                    et.SubElement(cs_control, "efxpt:param", name="EN_AUTO_PWR_DN",   value="Off",                       value_type="str")
                    et.SubElement(cs_control, "efxpt:param", name="EN_AUTO_SELF_REF", value="No",                        value_type="str")

                    cs_gate_delay = et.SubElement(ddr, "efxpt:cs_gate_delay")
                    et.SubElement(cs_gate_delay, "efxpt:param", name="EN_DLY_OVR", value="No", value_type="str")
                    et.SubElement(cs_gate_delay, "efxpt:param", name="GATE_C_DLY", value="3",  value_type="int")
                    et.SubElement(cs_gate_delay, "efxpt:param", name="GATE_F_DLY", value="0",  value_type="int")

            platform.toolchain.ifacewriter.xml_blocks.append(DRAMXMLBlock())

            # DRAM Rst.
            # ---------
            dram_pll_rst_n = platform.add_iface_io("dram_pll_rst_n")
            self.comb += dram_pll_rst_n.eq(platform.request("user_btn", 1))

            # DRAM AXI-Ports.
            # --------------
            for n, data_width in {
                0: 256, # target0: 256-bit.
                1: 128, # target1: 128-bit
            }.items():
                axi_port = axi.AXIInterface(data_width=data_width, address_width=28, id_width=8) # 256MB.
                ios = [(f"axi{n}", 0,
                    Subsignal("wdata",   Pins(data_width)),
                    Subsignal("wready",  Pins(1)),
                    Subsignal("wid",     Pins(8)),
                    Subsignal("bready",  Pins(1)),
                    Subsignal("rdata",   Pins(data_width)),
                    Subsignal("aid",     Pins(8)),
                    Subsignal("bvalid",  Pins(1)),
                    Subsignal("rlast",   Pins(1)),
                    Subsignal("bid",     Pins(8)),
                    Subsignal("asize",   Pins(3)),
                    Subsignal("atype",   Pins(1)),
                    Subsignal("aburst",  Pins(2)),
                    Subsignal("wvalid",  Pins(1)),
                    Subsignal("aaddr",   Pins(32)),
                    Subsignal("rid",     Pins(8)),
                    Subsignal("avalid",  Pins(1)),
                    Subsignal("rvalid",  Pins(1)),
                    Subsignal("alock",   Pins(2)),
                    Subsignal("rready",  Pins(1)),
                    Subsignal("rresp",   Pins(2)),
                    Subsignal("wstrb",   Pins(data_width//8)),
                    Subsignal("aready",  Pins(1)),
                    Subsignal("alen",    Pins(8)),
                    Subsignal("wlast",   Pins(1)),
                )]
                io   = platform.add_iface_ios(ios)
                rw_n = axi_port.ar.valid
                self.comb += [
                    # Pseudo AW/AR Channels.
                    io.atype.eq(~rw_n),
                    io.aaddr.eq(  Mux(rw_n,   axi_port.ar.addr,  axi_port.aw.addr)),
                    io.aid.eq(    Mux(rw_n,     axi_port.ar.id,    axi_port.aw.id)),
                    io.alen.eq(   Mux(rw_n,    axi_port.ar.len,   axi_port.aw.len)),
                    io.asize.eq(  Mux(rw_n,   axi_port.ar.size,  axi_port.aw.size)),
                    io.aburst.eq( Mux(rw_n,  axi_port.ar.burst, axi_port.aw.burst)),
                    io.alock.eq(  Mux(rw_n,   axi_port.ar.lock,  axi_port.aw.lock)),
                    io.avalid.eq( Mux(rw_n,  axi_port.ar.valid, axi_port.aw.valid)),
                    axi_port.aw.ready.eq(~rw_n & io.aready),
                    axi_port.ar.ready.eq( rw_n & io.aready),

                    # R Channel.
                    axi_port.r.id.eq(io.rid),
                    axi_port.r.data.eq(io.rdata),
                    axi_port.r.last.eq(io.rlast),
                    axi_port.r.resp.eq(io.rresp),
                    axi_port.r.valid.eq(io.rvalid),
                    io.rready.eq(axi_port.r.ready),

                    # W Channel.
                    io.wid.eq(axi_port.w.id),
                    io.wstrb.eq(axi_port.w.strb),
                    io.wdata.eq(axi_port.w.data),
                    io.wlast.eq(axi_port.w.last),
                    io.wvalid.eq(axi_port.w.valid),
                    axi_port.w.ready.eq(io.wready),

                    # B Channel.
                    axi_port.b.id.eq(io.bid),
                    axi_port.b.valid.eq(io.bvalid),
                    io.bready.eq(axi_port.b.ready),
                ]

                # Connect AXI interface to the main bus of the SoC.
                axi_lite_port = axi.AXILiteInterface(data_width=data_width, address_width=28)
                self.submodules += axi.AXILite2AXI(axi_lite_port, axi_port)
                self.bus.add_slave(f"target{n}", axi_lite_port, SoCRegion(origin=0x4000_0000 + 0x1000_0000*n, size=0x1000_0000)) # 256MB.

            # Use DRAM's target0 port as Main Ram  -----------------------------------------------------
            self.bus.add_region("main_ram", SoCRegion(
                origin = 0x4000_0000,
                size   = 0x1000_0000, # 256MB.
                linker = True)
            )

# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=efinix_ti375_c529_dev_kit.Platform, description="LiteX SoC on Efinix Ti375 C529 Dev Kit.")
    args = parser.parse_args()

    soc = BaseSoC(
        **parser.soc_argdict)
    builder = Builder(soc, **parser.builder_argdict)
    if args.build:
        builder.build(**parser.toolchain_argdict)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

    # if args.flash:
    #     from litex.build.openfpgaloader import OpenFPGALoader
    #     prog = OpenFPGALoader("titanium_ti375_c529")
    #     prog.flash(0, builder.get_bitstream_filename(mode="flash", ext=".hex")) # FIXME

if __name__ == "__main__":
    main()
