// SPDX-License-Identifier: GPL-2.0
/*
 * Ethernet driver for the ZTE/Sanechips ZX279128S (ZXHN H199A).
 *
 * Reverse-engineered from vendor U-Boot and the stock Linux modules
 * (see docs/ETHERNET.md and docs/ZX279128S-DATAPATH.md).
 *
 * A hardware buffer manager supplies two reserved DDR pools. RX uses sixteen
 * 1024-entry descriptor rings, bounded by per-queue hardware pending counts.
 * TM IRQs schedule NAPI; each ring retains a sequential cursor and release
 * debt. Buffers and descriptors are returned separately after payload copy.
 * Probe resets the bootloader's queue state and initializes the pools before
 * enabling ingress. Interface stop/reopen preserves ownership and cursors.
 */
#include <linux/etherdevice.h>
#include <linux/bitfield.h>
#include <linux/in.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_mdio.h>
#include <linux/of_net.h>
#include <linux/of_reserved_mem.h>
#include <linux/phy.h>
#include <linux/platform_device.h>
#include <linux/sizes.h>
#include <linux/timer.h>
#include <linux/ktime.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/rtnetlink.h>
#include <linux/rcupdate.h>
#include <linux/delay.h>
#include <linux/workqueue.h>
#include <linux/interrupt.h>
#include <linux/slab.h>

#include "zx279128-pp.h"

static u32 sp_last_alloc_raw;	/* debug: last BM+0x0c value seen */

/* buffer manager */
#define BM_BASE		0x92348000
#define BM_ENABLE	0x00
/* +0x04 and +0x08 are the BPPI / BPO thresholds, named from the ZX279133
 * sibling's BMU (its BMU_ENABLE / BMU_BPPI_THRESH / BMU_BPO_THRESH sit at the
 * same three offsets from its own block base). Both read 0x0104c040 here, which
 * is the sibling's PRE-enable value; it writes 0x01058080 to BPPI after
 * enabling. The H199A initialization uses its own vendor sequence.
 */
#define BM_BPPI_THRESH	0x04
#define BM_ALLOC_IDX	0x0c
#define BM_FREE		0x10
#define BM_REQUEST	0x14
#define BM_FREECNT	0xdc

/* Explicit bring-up builds expose instrumentation. Datapath default values
 * stay the same in either configuration; this controls access to experiments.
 */
#define ZX_HAVE_DEBUG_IFACES IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)

/* Descriptor-release block, TM + 0x4000.
 *
 * Recovered from the vendor U-Boot's rls_rx_desc() at 0x47f2fb14. This block
 * has never been characterised by this project and the driver has never
 * written to it. The vendor releases TWO things per received frame - the
 * DESCRIPTOR here, and only then the BUFFER at BM+0x10 - and on a bad buffer
 * index it releases the descriptor and deliberately skips the buffer, so they
 * are genuinely independent resources.
 *
 * Handshake: poll +0x64 bit0 clear, write the payload to +0x68, write 1 to
 * +0x64. Payload fields are bits[2:0] queue, bit3, bits[13:4], bits[31:14];
 * both vendor call sites pass queue | (1 << 4), i.e. 0x10 | q.
 */
#define TMD_BASE	0x92344000
#define TMD_GO		0x64	/* bit0 = busy */
#define TMD_PAYLOAD	0x68

/* traffic manager: config block and queue block */
#define TMC_BASE	0x92340000
#define TMC_CFG		0x04
#define TMC_RING_BASE	0xf0
#define TMC_IRQ_STATUS	0x100
#define TMC_IRQ_MASK	0x104
#define TMQ_PENDING	0x100

#define TMQ_BASE	0x92350000
#define TMQ_TXIDX	0x6c	/* TX ring index: two 16-bit halves that both
				 * advance by one per doorbell */
#define TMQ_TXRING	0x60	/* TX ring base (DDR); sits next to the
				 * doorbell and credit registers */
#define TMQ_DOORBELL	0x64
#define TMQ_CREDIT	0x68
#define TMQ_STATUS	0x1fc

/* H199A vendor spaRegTable: four eight-bit IP protocol trap selectors.
 * U-Boot selects UDP only. Add TCP for the software networking stack on
 * both cold initialization and warm attachment to U-Boot's datapath.
 *
 * The SPA block (0x921d4000) and the port attach register block (0x921d9000)
 * sit inside the NPP window, as in the vendor's npp node.
 */
#define ZX_NPP_SPA		0x14000
#define ZX_NPP_ATTACH		0x19000
#define SPA_TRAP_PROTOCOLS	0x1c0
#define SPA_TRAP_PROTOCOL0	GENMASK(31, 24)
#define SPA_TRAP_PROTOCOL1	GENMASK(23, 16)
#define SPA_CPU_PROTOCOLS	(FIELD_PREP(SPA_TRAP_PROTOCOL0, IPPROTO_UDP) | \
				 FIELD_PREP(SPA_TRAP_PROTOCOL1, IPPROTO_TCP))

/* SPA protocol-parser match RAM + hash RAM, reached through the indirect
 * read/modify/write interface the vendor's spa_set_match/hashram() use.
 *
 * tm.ko tm_pon_npp_spa_initial() loads these two RAMs after match_mode=1, and
 * our zx_eth_datapath_init() never did (only SPA +0/+4/+40/+44 + the trap
 * selector). PP-KEY.md §23.5/§26 left the RAM loads as the one untested piece:
 * if the parser never builds a lookup key, the CLA inner-hash exact-match can
 * never be consulted. This is the diagnostic trigger to install them and
 * measure, gated behind the same poke_allow_write as /proc/zx_eth_poke.
 *
 * Addresses decoded from tm.ko spaRegTable (word 0x75000+n -> 0x921d4000+4n):
 *   id4 CMD    word 0x75005 -> SPA+0x14   cmd = rw_en<<27 | ram_id<<22 | addr
 *   id5 STATUS word 0x75006 -> SPA+0x18   bit0 = access_done (0 = idle)
 *   id6 DATA0..5 word 0x75007 (stride 1)  -> SPA+0x1c .. +0x30
 *   id0x12 match_mode word 0x7501f -> SPA+0x7c (2 bits)
 */
#define SPA_IND_CMD		0x14
#define SPA_IND_STATUS		0x18
#define SPA_IND_DATA0		0x1c
#define SPA_MATCH_MODE		0x7c
#define SPA_IND_RW_READ		BIT(27)		/* cmd rw_en: 1 = read */
#define SPA_IND_RAMID_MATCH	0		/* match RAM id in cmd */
#define SPA_IND_RAMID_HASH	5		/* hash RAM id in cmd */

/* Golden word images, validated byte-for-byte against the vendor packer and
 * its inverse (spa_get_matchram field expressions) for all 11 rules; see the
 * decode in PP-KEY.md. Match RAM = 3 lines of 6 u32 (four protocol-parser
 * rules packed per 192-bit line). Each line is written DATA5..DATA0 then
 * cmd(rw=0, ram_id=0, ram_addr=line).
 */
static const u32 zx_spa_match_ram[3][6] = {
	{ 0xffff013e, 0xe0ed962d, 0x22c59fff, 0xb3fffc08, 0x7f8008d8, 0x000b0800 },
	{ 0xffff0043, 0xe008962c, 0x0ec51fff, 0xa3fffc01, 0xff80a0d8, 0x000b177f },
	/* word 3 is the packed RAM value 0x4003fc00; split into halves so it is
	 * not mistaken for a DDR-window address by the memory-region literal scan.
	 */
	{ 0x00000000, 0xe0166000, 0x1ac59fff, (0x4003u << 16) | 0xfc00u,
	  0xff802258, 0x000b167f },
};

/* Hash RAM = 8 entries, each (word0, word1); the hardware latches word1 & 0xffff
 * (valid/action/matcharray). Written DATA1=word1, DATA0=word0 then
 * cmd(rw=0, ram_id=5, ram_addr=entry). Derived from the vendor's contiguous
 * 48-byte source via spa_set_hashram (word0 = *(u32)p, word1 = *(u32)(p+4)).
 */
static const u32 zx_spa_hash_ram[8][2] = {
	{ 0x000016a9, 0x1aa50200 }, { 0x00001aa5, 0x328d0200 },
	{ 0x0000328d, 0x62750200 }, { 0x00026275, 0xa2750200 },
	{ 0x0001a275, 0x62750200 }, { 0x00016275, 0xa2750200 },
	{ 0x0002a275, 0x20a10200 }, { 0x000c20a1, 0x00000200 },
};

/* MAC per-port control; bit0 of +0x00 is the port enable. The vendor halt()
 * clears it for every port, and U-Boot runs halt() after each TFTP transfer,
 * so the ports are left DISABLED by the time Linux starts. TX still works
 * (it goes through the BM/TM doorbell) but nothing is ever received.
 */
/* Four GE ports: MAC window 0x92200000 + N * 0x40000, PHY at MDIO 10 + N.
 * Measured 2026-09-06 (docs/ETHERNET.md "PHY / MAC / jack map").
 */
#define ZX_MAC_BASE	0x92200000
#define ZX_MAC_STRIDE	0x40000
#define ZX_NPORTS	4

#define MAC_CTRL	0x00
#define MAC_CTRL_EN	BIT(0)

/* Register blocks, each taken from the named reg entry of the same name. A
 * device tree without the entry gets the block's fixed address on this SoC.
 * reg index 0 stays the bound port's MAC window (mac0 on the H199A). size is
 * what the driver maps; the reg entry must cover at least that much.
 */
enum zx_eth_reg {
	ZX_REG_MAC0,
	ZX_REG_MAC1,
	ZX_REG_MAC2,
	ZX_REG_MAC3,
	ZX_REG_FABRIC,
	ZX_REG_GLB,
	ZX_REG_NPP,
	ZX_REG_TMC,
	ZX_REG_TMD,
	ZX_REG_BM,
	ZX_REG_QMG,
	ZX_REG_TMQ,
	ZX_REG_PP,
	ZX_REG_SBRG,
	ZX_REG_CLA,
	ZX_REG_PONPP,
	ZX_NREGS
};

static const struct zx_eth_reg_desc {
	const char *name;
	phys_addr_t fallback;
	resource_size_t size;
} zx_eth_reg_desc[ZX_NREGS] = {
	[ZX_REG_MAC0]	= { "mac0",   ZX_MAC_BASE + 0 * ZX_MAC_STRIDE, SZ_4K },
	[ZX_REG_MAC1]	= { "mac1",   ZX_MAC_BASE + 1 * ZX_MAC_STRIDE, SZ_4K },
	[ZX_REG_MAC2]	= { "mac2",   ZX_MAC_BASE + 2 * ZX_MAC_STRIDE, SZ_4K },
	[ZX_REG_MAC3]	= { "mac3",   ZX_MAC_BASE + 3 * ZX_MAC_STRIDE, SZ_4K },
	[ZX_REG_FABRIC]	= { "fabric", 0x92000000, SZ_4K },	/* datapath reset */
	[ZX_REG_GLB]	= { "glb",    0x92040000, SZ_4K },
	[ZX_REG_NPP]	= { "npp",    0x921c0000, SZ_128K },	/* + SPA, attach */
	[ZX_REG_TMC]	= { "tmc",    TMC_BASE,   SZ_4K },
	[ZX_REG_TMD]	= { "tmd",    TMD_BASE,   SZ_4K },
	[ZX_REG_BM]	= { "bm",     BM_BASE,    SZ_4K },
	[ZX_REG_QMG]	= { "qmg",    0x9234c000, SZ_4K },
	[ZX_REG_TMQ]	= { "tmq",    TMQ_BASE,   SZ_4K },
	[ZX_REG_PP]	= { "pp",     0x92380000, SZ_4K },
	[ZX_REG_SBRG]	= { "sbrg",   0x92388000, SZ_4K },
	[ZX_REG_CLA]	= { "cla",    0x9238c000, SZ_4K },
	[ZX_REG_PONPP]	= { "ponpp",  0x923a0000, SZ_4K },
};

#ifdef CONFIG_ZX279128_PP_TABLES
/* TOPCRM, the top clock/reset manager (0x94000000, stock DTS topcrm@94000000).
 * These are the datapath reset/gate words decoded from plat-zxylzb_9128S.ko,
 * NOT modelled by clk-zx279128-crm.c: that driver only owns the LSP0/LSP1
 * peripheral gates and PCIe resets, every one of which is on at boot and so
 * CLK_IS_CRITICAL. The PON datapath gate at +0xc bits 5..8 reads CLEAR at boot
 * (0x00517800, measured) and only latches after a reset pulse on +0x8 bits 4,5,
 * so it cannot be a critical always-on clock and its ordering cannot be
 * expressed by the clock core. It is driven here, inline, as one ordered
 * sequence. See docs/PP-KEY.md §15, §18 and docs/PP-OFFLOAD.md.
 *
 * GATE MASK CORRECTION (§18, measured 2026-11-17). Both zx_pon_clk_reset and
 * the tail of zx_pon_clk_reset_init arm the gate with the ARM instruction
 * e3833e1e = `orr r3, r3, #0x1e` ROR #28 = 0x1e0 (bits 5..8), NOT 0x1e
 * (bits 1..4). An earlier decode read the raw imm8 (0x1e) and missed the
 * barrel-shifter rotation. That single error explains every negative in §17.4:
 * the old `|= 0x1e` set bit 4 (a writable non-gate bit, which latched) and
 * bits 1..3 (strap/status, read-only, refused) and NEVER TOUCHED the real
 * gate bits 5..8 - so the DPA stayed gated. The gate is bits 5..8 = 0x1e0.
 */
#define ZX_TOPCRM_PHYS		0x94000000
#define ZX_TOPCRM_RESET		0x08	/* datapath reset, bits 4,5 (pulse) */
#define ZX_TOPCRM_RESET_BITS	0x30
#define ZX_TOPCRM_GATE		0x0c	/* datapath clock gate, bits 5..8 */
#define ZX_TOPCRM_GATE_BITS	0x1e0	/* 0x1e ROR 28, §18 - NOT 0x1e */

/* sys_ctrl_base, the one step zx_pon_clk_reset_init does that §17/§18's port
 * omitted: clear bit 11 of sys_ctrl_base +0x10, issued immediately BEFORE the
 * gate arm (vendor init decode c028..c054: ldr [r1,#16]; bic #0x800; str;
 * then +0xc |= 0x1e0). Recovered (§19, measured 2026-11-17):
 *   - of_iomap order in init_module stores results at [r6+0,+16,+20,+24,+28],
 *     i.e. reg indices 0,1,2,3,4 -> pon_base, top_crm_base, SYS_CTRL_BASE,
 *     pin_mux_base, pon_serdes_base. So sys_ctrl_base = of_iomap(pon, reg[2]).
 *   - The vendor DTB recovered from the flash dump gives the pon node's reg as
 *     <0x92000000 0x400000, 0x94000000 0x100000, 0x94100000 0x100000,
 *      0x94200000 0x100000, 0x9fe00000 0x100000>. reg[1]=0x94000000 matches the
 *     known top_crm_base (cross-check), so reg[2] = 0x94100000. That is CRM1.
 *   - The op is e3c22b02 = `bic r2, r2, #0x800` (imm8 0x02 ROR 2*0xb=22 = 0x800,
 *     bit 11). Sanity-checked against the §18 rotation trap: here the operand is
 *     small and objdump prints no rotate comment, but it was decoded by hand
 *     anyway.
 *
 * §19 MEASURED (2026-11-17): on this board 0x94100010 reads 0x00000000 at boot
 * AND live, so bit 11 is ALREADY CLEAR and this bic is a NO-OP here. It is kept
 * only so the cold sequence matches the vendor init byte-for-byte (vendor-faithful,
 * harmless); it is NOT the DPA unlock. The "frozen DPA window" it was meant to
 * free does not exist: 0x92398000 implements only bits 6,7,12 and already holds
 * its maximum 0x10c0 (§19.3). Kept, with eyes open, not as a fix.
 */
#define ZX_SYSCTRL_PHYS		0x94100000	/* pon reg[2], = CRM1, measured */
#define ZX_SYSCTRL_HOLD		0x10		/* ldr/str [+0x10] in init decode */
#define ZX_SYSCTRL_HOLD_BIT	0x800		/* bic #0x800 = bit 11 (already 0 here) */

/* The data-path analyser (DPA) sits at 0x92398000, inside the PP super-region
 * (pp base 0x92380000 + 0x18000). Reached as an offset from ZX_REG_PP, the way
 * the SPA and port-attach blocks are reached as offsets from ZX_REG_NPP.
 * +0x000 protocol_pkt_aly_en; +0x014 protocol_cpu_pps_en. dpaRegTable decode
 * (id i -> bit 6+i), docs/PP-KEY.md §13, §19.
 *
 * §19 MEASURED (2026-11-17): tm.ko's dpa loop ATTEMPTS bits 6..12 (0x1fc0), but
 * on this SoC 0x92398000 physically implements ONLY bits 6,7,12. Walking-bit
 * proof on hardware: writel(0xffffffff)->0x10c0, writel(0xaaaaaaaa)->0x80,
 * writel(0x55555555)->0x1040. Bits 8,9,10,11 (protocol slots 2,3,4,5) are
 * unimplemented read-as-zero (this is the cost-reduced GE ZX279128S, not the
 * 7-slot GPON part the vendor loop targets). So the register's maximum is 0x10c0,
 * which it already holds at boot. The §13-§18 "four protocols off / frozen window"
 * was unimplemented bits mistaken for refused writes. We OR the full 0x1fc0 (a
 * no-op for the 4 absent bits, exactly as the vendor loop is) and check only the
 * implemented bits so the log tells the truth instead of warning on silicon that
 * cannot exist. 0x92398014 (cpu_pps_en) likewise implements only bits 0..4
 * (writel(0xffffffff)->0x1f), already set.
 */
#define ZX_PP_DPA_OFFSET	0x18000
#define ZX_DPA_PKT_ALY_EN	0x000
#define ZX_DPA_PKT_ALY_BITS	0x1fc0	/* vendor attempts 6..12; HW has 6,7,12 */
#define ZX_DPA_PKT_ALY_IMPL	0x10c0	/* bits 6,7,12 = only slots this SoC has */
#define ZX_DPA_CPU_PPS_EN	0x014
#define ZX_DPA_CPU_PPS_BITS	0x1
#define ZX_DPA_CPU_PPS_IMPL	0x1f	/* bits 0..4 = only pps bits this SoC has */

/* PonPp (ZX_REG_PONPP, 0x923a0000) PM/ACL DRAM-table base registers. These
 * mirror ZX_PP_{PM,ACL}_BASE_REG, which are file-local to zx279128-pp.c
 * (zx_pp_tables_init() is the owner of the real allocation). Named locally so
 * the §16 base-parking after the reset does not couple across translation
 * units; zx279128-pp.c remains the single source for its own copy.
 */
#define ZX_PONPP_PM_BASE_REG	0x20
#define ZX_PONPP_ACL_BASE_REG	0x24

/* PonPp WAN-port declaration (ZX_REG_PONPP +0x1c = 0x923a001c). This is the
 * PP datapath's "which ingress port is the WAN/uplink" bitmap, and §20 (PP-KEY)
 * identifies it as the L3-flow-candidate gate that every prior round missed.
 *
 * DECODE (tm.ko / switch.ko, measured from the unstripped modules):
 *   - tm_set_pp_wan_cfg(port) (tm.ko 0x36094) is a bare fpga RMW on word index
 *     0xe8007 -> phys 0x92000000 + 0xe8007*4 = 0x923a001c, OR-ing bit (port+25).
 *     Its only caller is tm_set_p2pmode (0x360f0), which stores the port into
 *     the global `lan_up_port` and passes it straight through. The vendor boot
 *     log carries `si_gpon_lanup_set_db lan_up_mode=0x0 lan_up_port=4`
 *     (docs/zx279128s-vendor/VENDOR-ARCHAEOLOGY-R2.md): a specific uplink port
 *     is declared at bring-up.
 *   - switch.ko sw_other_set_wan_lan_switch (0x6254) writes the SAME register:
 *     it first clears bits 25..29 (`bic #0x3e000000`) then calls tm_set_pp_wan_cfg
 *     to set bit (port+25). The companion `sw_set_uni_as_wan uni=%d` string and
 *     ethdrv_set_wanportid (0x4a0, stores g_sw_cap[0x68]=port) prove the WAN
 *     port is a software-settable field and a GE/UNI port can be the WAN.
 *
 * MEASURED on our boot (logs/probe-i-pp-ddr-config.txt, OpenWrt image):
 *   0x923a001c = 0x01200000  -> bits 25..29 (the WAN-port field) ALL CLEAR.
 * So NO ingress port is declared WAN. The CLA classifies every GE-ingress frame
 * (PP-KEY §10, trap 1:1) but, with no WAN/uplink port declared, the parse stage
 * never marks a GE->GE routed frame as an upstream L3-flow candidate, so the
 * CLA exact-match is never consulted for a hit (PP-KEY §11/§12: traps even with
 * winmask zeroed; §19: traps with the DPA at its implemented max). This is the
 * one bring-up register upstream of the CLA that our port leaves unset and the
 * vendor sets.
 *
 * ENABLE: declare the routed-traffic ingress port (the WAN jack, eth3 == mac3)
 * as WAN by setting bit (3+25) = bit 28 = 0x10000000, mirroring the vendor's
 * tm_set_pp_wan_cfg(3). Bits 20,21 (0x300000, non-WAN-field) are preserved.
 */
#define ZX_PONPP_WAN_CFG_REG	0x1c		/* 0x923a001c, PP WAN-port bitmap */
#define ZX_PONPP_WAN_PORT_SHIFT	25		/* bit = (port + 25), tm_set_pp_wan_cfg */
#define ZX_PONPP_WAN_FIELD_MASK	0x3e000000	/* bits 25..29, cleared by switch.ko */
#define ZX_PP_WAN_PORT		3		/* eth3 == mac3, the WAN jack (routed in) */
#endif /* CONFIG_ZX279128_PP_TABLES */

/* Packet buffers, free lists and descriptor rings live in a reserved DDR
 * window, the node's memory-region (no-map: the driver ioremaps parts of it).
 * The hardware is programmed with fixed offsets from the window base, the
 * layout U-Boot uses at ZX_DDR_BASE. A device tree without memory-region gets
 * that window.
 *
 * The TM alone uses the area at ZX_DDR_TMQ and its extent is unknown, so the
 * region must hold the whole ZX_DDR_SIZE window the board has always
 * reserved, not just the structures the driver maps. A 1 MiB aligned base
 * keeps every structure at the alignment it has at ZX_DDR_BASE.
 */
#define ZX_DDR_BASE	0x41000000	/* without memory-region */
#define ZX_DDR_SIZE	SZ_16M
#define ZX_DDR_ALIGN	SZ_1M
#define ZX_DDR_POOL	0x000000	/* TMC+0xf4: pool 0 buffers */
#define ZX_DDR_POOL2	0x400000	/* TMC+0xf8: pool 1 buffers */
#define ZX_DDR_FREELIST	0x800000	/* TMC+0xe8: pool 0 free list */
#define ZX_DDR_FREELIST2 0x808000	/* TMC+0xec: pool 1 free list */
#define ZX_DDR_RX_RING	0xa00000	/* TMC+0xf0: ZX_RX_RINGS RX rings */
#define ZX_DDR_TMQ	0xb00000	/* TMQ+0x50: TM only, extent unknown */
#define ZX_DDR_TX_RING	0xc00000	/* TMQ+0x60: TX ring */
#define BUF_SIZE	SZ_2K
#define BUF_HDR		16
#define BUF_COUNT	2048
#define BUF2_COUNT	512
#define RING_ENTRIES	1024
#define DESC_SIZE	16
#define ZX_RX_QUEUES	8
#define ZX_RX_RINGS	16
#define ZX_RX_RING_SIZE	(RING_ENTRIES * DESC_SIZE)
#define ZX_RX_MAP_SIZE	(ZX_RX_RINGS * ZX_RX_RING_SIZE)

/* Every mapping of the window (probe, datapath init) stays inside it and
 * clear of the next structure.
 */
static_assert(ZX_DDR_POOL + BUF_COUNT * BUF_SIZE <= ZX_DDR_POOL2);
static_assert(ZX_DDR_POOL2 + BUF2_COUNT * BUF_SIZE <= ZX_DDR_FREELIST);
static_assert(ZX_DDR_FREELIST + SZ_8K <= ZX_DDR_FREELIST2);
static_assert(ZX_DDR_FREELIST2 == ZX_DDR_FREELIST + 0x8000);	/* seeding */
static_assert(ZX_DDR_FREELIST2 + SZ_4K <= ZX_DDR_RX_RING);
static_assert(ZX_DDR_RX_RING + ZX_RX_MAP_SIZE <= ZX_DDR_TMQ);
static_assert(ZX_DDR_TMQ < ZX_DDR_TX_RING);
static_assert(ZX_DDR_TX_RING + RING_ENTRIES * DESC_SIZE <= ZX_DDR_SIZE);

struct zx_rx_queue {
	u16 cursor;
	u16 remaining;
	u16 buffer;
	u8 pool;
	u8 class;
	bool debt;
	bool buffer_pending;
	bool return_sent;
};


struct zx_eth {
	void __iomem *freelists;
	struct net_device *ndev;
	struct device *dev;
	struct napi_struct napi;
	struct phy_device *phy;
	struct device_node *phy_np;

	phys_addr_t phys[ZX_NREGS];	/* register block bases, see zx_eth_reg */
	phy_interface_t phy_modes[ZX_NPORTS];	/* per port, from the DT */
	phy_interface_t phy_mode;	/* primary netdev's PHY interface */
	void __iomem *mac;	/* per-port MAC window (DT reg) */
	void __iomem *macs[ZX_NPORTS];	/* all four, for per-port enable */
	struct net_device *ports[ZX_NPORTS];	/* per-port netdevs (split_ports) */
	int bound_port;		/* which MAC index the DT reg selects, -1 unknown */
	u8 base_mac[ETH_ALEN];	/* the one factory address left for Ethernet */
	bool have_base_mac;
	void __iomem *bm;
	void __iomem *tmc;
	void __iomem *tmd;	/* descriptor release, TM+0x4000 */
	unsigned int free_credit;	/* vendor's software BM+0x10 write credit */
	unsigned long n_desc_rls;	/* descriptor releases issued */
	unsigned long n_desc_busy;	/* descriptor releases that timed out */
	unsigned long n_free_nocredit;	/* frees dropped for want of BM+0xdc credit */
	void __iomem *tmq;
	u32 ddr_phys;		/* DDR window base, see ZX_DDR_BASE */
	void __iomem *bufs;	/* pool 0, ZX_DDR_POOL */
	void __iomem *bufs2;	/* pool 1, ZX_DDR_POOL2 */
	void __iomem *ring;	/* RX descriptor ring (TMC+0xf0) */
	void __iomem *txring;	/* TX descriptor ring (TMQ+0x60) */
	u32 rx_ring_phys;
	u32 tx_ring_phys;
	bool dp_inited;		/* datapath init deferred to first link-up */
#ifdef CONFIG_ZX279128_PP_TABLES
	bool pp_bring_up;	/* this probe ran the packet-processor bring-up */
	struct zx_pp *pp;	/* PP table access, docs/PP-OFFLOAD.md; may be NULL */
#endif

	struct zx_rx_queue rxq[ZX_RX_RINGS];
	unsigned int rx_next;
	int rx_inflight;
	/* ZX_RX_SEED_R202_FIELDS_BEGIN */
	int rx_q0_seed;		/* requested first-open cursor, -1 means unchanged */
	bool rx_seed_eligible;	/* positively warm and NAPI never started */
	/* ZX_RX_SEED_R202_FIELDS_END */
	int irq;
	bool rx_fault;
	spinlock_t irq_lock;
	struct delayed_work rx_retry;
	/* Datapath recovery; see zx_rx_stall_check() and zx_dp_reset_work(). */
	struct delayed_work wd_work;	/* 1 Hz RX stall watchdog */
	struct delayed_work reset_work;	/* full datapath re-initialisation */
	const char *reset_reason;
	bool resetting;		/* hardware is being re-initialised */
	bool reset_nagged;	/* "left stopped" already logged for this stall */
	bool reset_manual;	/* requested through /proc/zx_eth_reinit */
	unsigned int wd_stuck;	/* periods with descriptors pending and no release */
	unsigned int reset_consec;	/* resets with no RX release in between */
	unsigned int rx_blocked_polls;	/* empty polls blocked on a refused return */
	unsigned long wd_rls;	/* n_desc_rls at the previous watchdog period */
	unsigned long reset_rls;	/* n_desc_rls when the last reset finished */
	unsigned long last_reset;	/* jiffies */
	unsigned long n_resets, n_wd_kicks, n_bad_pending;
	/* ROUND 39: the vendor's TX reclaim cadence. See zx_tx_done_timer(). */
	struct timer_list tx_timer;
	/* Serialises the shared buffer-manager handshake between TX and NAPI.
	 * These no longer rely on maxcpus=1 - SMP is enabled;
	 * this makes the driver correct independently of that.
	 */
	spinlock_t bm_lock;
	spinlock_t tx_lock;
	bool alloc_pending;
	/* Descriptors rejected by the ownership test despite carrying a
	 * non-zero length, histogrammed by status byte. Added because the old
	 * exact-match test dropped frames with no counter at all.
	 */
	unsigned long c_icmp, c_udp, c_tcp_bare, c_tcp_data, c_report;
	/* ROUND 36. c_icmp alone could not answer the question it was being used
	 * to answer. It counts ip_proto==1 without ever reading the ICMP TYPE
	 * byte, and the RX path has no destination-MAC filter, so an echo
	 * REQUEST from the host, an echo REPLY the device itself sent and had
	 * looped back, and ICMP from any other station on the segment are all
	 * the same event to it. Every "the device receives essentially
	 * everything" claim rested on that counter. Splitting on the type byte
	 * (frame offset 34 = 14 eth + 20 ip + 0) makes the two distinguishable
	 * for the first time, at the cost of two increments.
	 */
	unsigned long c_icmp_req;	/* type 8  - the host asking */
	unsigned long c_icmp_rep;	/* type 0  - the device (or anyone) answering */
	/* ROUND 73: frames the census classified as IPv4 but whose skb->protocol
	 * was NOT IPv4 after eth_type_trans(). If this is non-zero it accounts
	 * for the driver-to-IP gap measured in rounds 69-72 directly.
	 */
	unsigned long c_proto_mismatch;
	unsigned long n_nocredit;	/* frees issued with no BM credit */
	/* ROUND 36. n_zerolen was declared in round 30 and never incremented, so
	 * for six rounds the "zerolen" numbers quoted in analysis were coming
	 * from the FLASHED generation's counter and not from this tree at all.
	 * It is now a real counter: an owned slot whose decoded length is 0.
	 */
	unsigned long n_zerolen;	/* owned slots with a zero length decode */
	/* ROUND 36, producer-side. The R129 freeze showed census frozen for 13 s
	 * while the poll demonstrably kept running. That decomposes into exactly
	 * two possibilities - the hardware published no work, or it published
	 * work that decoded as nothing - and until now no counter could tell the
	 * two apart. n_prodzero counts polls that found the producer's published
	 * count already 0 for the ring they were about to serve.
	 */
	unsigned long n_prodzero;	/* ring served with pending count 0 */
	/* Which way a buffer allocation failed. The wedge has always been
	 * described as "allocation is serviced but yields no VALID index",
	 * and these separate that from the other possibility - that the
	 * request is never accepted at all, because BM_REQUEST was left
	 * asserted by an earlier failure and reads back non-zero forever.
	 * Without them the two are indistinguishable from outside. */
	unsigned long n_alloc_busy;	/* retries exhausted, index never read */
	unsigned long n_alloc_invalid;	/* index read, VALID bit clear */
	unsigned long n_dump;
	unsigned long n_badproto;	/* frames whose ethertype is nonsense */
	unsigned long n_biggood;	/* large frames that demuxed correctly */
	unsigned long n_rej;
	unsigned long n_odd_st;
	unsigned long rej_st[256];
	u32 tx_outstanding;	/* frames handed to the TM but not yet drained */
	/* ROUND 38: is the reply gated on the next inbound frame?
	 *
	 * Both teammates converged on that as the only mechanism that produces
	 * latency(N) = t_rx(N+1) - t_rx(N), and the vendor gave the arithmetic.
	 * The discriminator is how long the hardware takes to CONSUME the TX
	 * descriptor after the doorbell is rung. If it consumes in microseconds,
	 * nothing is gated and the delay is after the ring (egress scheduling).
	 * If it does not consume until an RX event happens, the gate is real.
	 *
	 * Measured with a bounded spin on the hardware's own index, because the
	 * alternative - observing the advance at the NEXT xmit - would just
	 * re-measure the interval to the next frame, which is the very quantity
	 * under test.
	 */
	u64 tx_drain_ns_max;
	unsigned long tx_drain_n, tx_drain_fast, tx_drain_slow;
	/* ROUND 65: the buffer index each TX slot currently holds, so the buffer
	 * can be returned to the BM when the slot is reused. 0xffffffff = unused.
	 *
	 * The vendor returns a frame's buffer on completion
	 * (pon_tm_check_tx_done_nolock reads TMQ+0x68 and calls pp_bmu_free_bp).
	 * This driver never has: zx_bm_free() has exactly one call site and it is
	 * on the RX path, so every transmitted frame permanently consumed a pool
	 * buffer. That was masked while the allocator returned 0 for ever (R140-
	 * R158); now that R159 seeds the BPPE free lists and the allocator hands
	 * out distinct indices, an unbounded TX leak would exhaust the pool.
	 *
	 * Freeing on slot REUSE rather than on completion is deliberate: this
	 * driver has no trustworthy completion signal - tx_outstanding is a
	 * phantom, TMQ_TXIDX is not a consume index, and TMQ+0x68 is read-clear
	 * and read by our own reclaim timer (R161). Slot reuse needs no signal at
	 * all: the TM services the ring in order, so by the time tx_next has
	 * advanced a full RING_ENTRIES the frame that previously occupied this
	 * slot has necessarily been consumed.
	 */
	u32 tx_bp[RING_ENTRIES];
	/* ROUND 66: frames enqueued but not yet reclaimed, and the back-pressure
	 * threshold. THE DRIVER HAD NO BACK-PRESSURE AT ALL before this: it never
	 * returned NETDEV_TX_BUSY, never stopped the TX queue from the transmit
	 * path and never woke it. From the stack's point of view the device was
	 * permanently ready, so fq_codel accepted frames faster than the device
	 * drained them and dropped a variable fraction by occupancy - which is
	 * R164's above-driver loss and R150's 4%-44% variance.
	 *
	 * Reclaim uses the completion delta the r39 timer already computes from
	 * the read-clear TMQ+0x68/TMQ+0x58. That is the only completion signal
	 * available, and it is at least self-consistent: one reader (the timer),
	 * consuming the delta once per jiffy.
	 */
	u32 tx_pending;
	unsigned long tx_stall_ticks;
	bool tx_queue_stopped;
	u32 snap[128];			/* TM register snapshot for diffing */
	u32 msnap[256];			/* MAC per-port window snapshot */
	bool snap_valid;
	unsigned long next_scan;
	bool running;
	bool removing;
	/* How many netdevs are up. The RX ring, the buffer pool and the NAPI
	 * poll are ONE datapath shared by all four port netdevs, so the timer
	 * and NAPI must start on the first open and stop on the last close.
	 * Without the count, `ifdown` on the DT-bound netdev silently killed
	 * receive for every other port.
	 */
	unsigned int dp_users;
	u32 dbg_seen;
	u32 tx_dbg;
	u32 tx_next;
};

static inline void *zx_buf(struct zx_eth *ze, u32 idx)
{
	return (u8 *)ze->bufs + ((size_t)idx << 11) + BUF_HDR;
}


/* Allocate a buffer index from the hardware pool (U-Boot: 0x47f2f92c). */
/*
 * The buffer manager is a SHARED hardware resource driven by a multi-step
 * handshake (request -> poll -> read index -> release), so the whole sequence
 * is held under bm_lock.
 *
 * ✗ CORRECTION: this comment used to say "a TX allocation and an RX refill can
 * drive BM_REQUEST concurrently". They cannot. **This function has exactly one
 * caller and it is ndo_start_xmit.** The receive path never allocates through
 * it - the hardware takes RX buffers from the pool itself, which is why the DDR
 * free-list tables and the prime loop exist at all. RX only ever calls
 * zx_bm_free().
 *
 * That wrong sentence has real cost: on 2026-09-07 it made a "BM_REQUEST left
 * asserted jams the receive path" hypothesis look plausible for an hour. It
 * cannot, because RX does not come through here. Do not reintroduce it.
 *
 * The lock is still needed and still irqsave: zx_bm_free() runs in softirq
 * context and touches the same block, and with the second core up a transmit
 * can race a free.
 */
static int zx_bm_alloc(struct zx_eth *ze)
{
	unsigned long flags;
	u32 value;
	int retry, idx = -ENOMEM;

	spin_lock_irqsave(&ze->bm_lock, flags);
	/* Preserve a timed-out request: it may finish after this call returns. */
	if (ze->alloc_pending) {
		if (readl(ze->bm + BM_REQUEST) & 1)
			goto busy;
		value = readl(ze->bm + BM_ALLOC_IDX);
		ze->alloc_pending = false;
		if (value & BIT(31))
			goto allocated;
	}

	writel(readl(ze->bm + BM_REQUEST) | 1, ze->bm + BM_REQUEST);
	for (retry = 0; retry < 200; retry++) {
		if (!(readl(ze->bm + BM_REQUEST) & 3)) {
			value = readl(ze->bm + BM_ALLOC_IDX);
			sp_last_alloc_raw = value;
			if (value & BIT(31))
				goto allocated;
			ze->n_alloc_invalid++;
			break;
		}
		cpu_relax();
	}
	ze->alloc_pending = true;
busy:
	ze->n_alloc_busy++;
	goto out;
allocated:
	sp_last_alloc_raw = value;
	ze->alloc_pending = false;
	idx = value & 0xffff;
out:
	spin_unlock_irqrestore(&ze->bm_lock, flags);
	return idx;
}
/* Return a buffer to the pool (U-Boot: 0x47f2f99c).
 *
 * This used to read BM_FREECNT up to four times per freed buffer, decode
 * `(v >> 3) & 0x3f` as a free credit, decrement a software copy and count a
 * `nocredit` event when it hit zero. All of that is gone, and deleting it
 * changes no behaviour: the `writel(idx, BM_FREE)` below was unconditional in
 * both branches, so the credit block could never gate a free. It was pure cost -
 * up to four uncached register reads on every received frame.
 *
 * It was also measuring nothing. BM_FREECNT's low bits read 0x111 in every
 * state this hardware can be in - the vendor bootloader mid-transfer at
 * 10 MiB/s, a healthy idle Linux, and a wedged datapath - so the "34 free
 * credits" that decode produced is a constant, and `nocredit` was gated on a
 * value that is never zero. That is why it read 0 in every run ever recorded
 * here, including runs that ended with the datapath dead. Confirmed by logging
 * the full word at poll rate through a flood: exactly two distinct values
 * appeared, 0x00000111 and 0x40000111, differing only in bit 30.
 *
 * The state actually lives in the HIGH half, which that mask discarded. Bit 30
 * is a live wedge indicator (it does not clear on a write-1-to-clear, so it is
 * status rather than a latch), and the vendor's working datapath carries 0x5 in
 * the top nibble where ours carries 0x0. See docs/ETHERNET.md, 2026-09-07.
 */
/* A failed credit acquisition leaves the caller owning the buffer. */
static bool zx_bm_free(struct zx_eth *ze, u32 idx)
{
	unsigned long flags;
	int tries = 32;

	spin_lock_irqsave(&ze->bm_lock, flags);
	while (!ze->free_credit && tries--)
		ze->free_credit = (readl(ze->bm + BM_FREECNT) >> 3) & 0x3f;
	if (!ze->free_credit) {
		ze->n_free_nocredit++;
		spin_unlock_irqrestore(&ze->bm_lock, flags);
		return false;
	}
	ze->free_credit--;
	writel(idx, ze->bm + BM_FREE);
	spin_unlock_irqrestore(&ze->bm_lock, flags);
	return true;
}

/* Descriptor field packing, mirroring the vendor layout exactly. */
static void zx_desc_pack(void __iomem *d, u32 idx, u32 len)
{
	u8 b7, b8;
	u16 h12;
	u32 w8;

	b7 = readb(d + 7);
	b7 = (b7 & ~(0x7f << 1)) | ((idx & 0x7f) << 1);
	writeb(b7, d + 7);

	b8 = (idx >> 7) & 0xff;
	writeb(b8, d + 8);

	h12 = readw(d + 12);
	h12 = (h12 & ~(0x3fff << 2)) | ((len & 0x3fff) << 2);
	writew(h12, d + 12);

	w8 = readl(d + 8);
	w8 = (w8 & ~(0x3fffu << 9)) | ((len & 0x3fff) << 9);
	writel(w8, d + 8);
}



/* TX descriptor words 0..2. Defaults reproduce the values copied from U-Boot;
 * one of them may carry the destination port. See the comment at the write site.
 */
/* Keep the PHYs this driver does NOT attach powered up.
 *
 * The SoC has four GE PHYs (MDIO 10-13, one per MAC at 0x92200000 + N*0x40000)
 * and this driver attaches exactly one. phylib registers all four from the DT
 * and then suspends every PHY that has no attached netdev, which powers its
 * port down. Measured 2026-09-06: with the driver on phy1, a host cabled to the
 * phy3 jack sees NO-CARRIER under Linux while U-Boot has the same cable at
 * 1Gbps - so an unattached port cannot even INGRESS, and the fabric never gets
 * a chance to carry its frames to the CPU.
 *
 * This resumes the unattached PHYs so their ports stay electrically up. It does
 * not make them separate netdevs; it is the minimum needed to test whether the
 * NPP fabric delivers frames from a non-attached port to the CPU, which decides
 * whether a DSA-style single-conduit model is possible here at all.
 */

/* Enable MAC_CTRL_EN on every port, not just the one the DT binds.
 *
 * MEASURED 2026-09-06: setting bit 0 of a port's own MAC_CTRL is exactly what
 * lets that port deliver frames to the CPU. With it clear the port ingresses
 * NOTHING even with link up and the NPP port-attach mask set to 0xf; with it
 * set, frames arrive immediately. Two ports were then run concurrently -
 * 6/6 pings each, 0% loss, both directions - from this single netdev, which is
 * what retired the old "single-port driver by construction" conclusion.
 *
 * Egress needs no per-port work: the fabric delivers a CPU-injected frame to
 * the port its destination MAC lives on, verified by replying correctly to a
 * host on a port the driver was NOT bound to.
 *
 * Frames from all enabled ports still land on this one netdev. Splitting them
 * into per-port netdevs needs the ingress-port field (w1 bits 20/21) decoded
 * for more than two ports - see docs/ETHERNET.md.
 */
static bool zx_all_ports = true;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(all_ports, zx_all_ports, bool, 0644);
MODULE_PARM_DESC(all_ports, "enable MAC_CTRL_EN on all four ports, not just the bound one");
#endif

static bool zx_phy_keepalive = true;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(phy_keepalive, zx_phy_keepalive, bool, 0644);
MODULE_PARM_DESC(phy_keepalive,
	"resume the PHYs this driver does not attach, so their ports stay up");
#endif

/* Datapath recovery (docs/WEDGE-ANALYSIS.md).
 *
 * Two RX failures used to be silent until a power cycle: an out-of-range
 * pending count latched rx_fault for the life of the boot, and a release path
 * that stopped retiring returns left descriptors pending with nothing noticing.
 * With rx_recover the driver re-runs the cold datapath initialisation instead,
 * bracketed by the same close/open path `ip link set down/up` takes, so the
 * hardware, the ring cursors and the buffer pool all restart from the state a
 * cold probe leaves. 0 restores the old stop-and-stay-stopped behaviour.
 *
 * rx_stall_ms is how long descriptors may stay pending with no return issued
 * before that counts as a stall. The watchdog kicks NAPI after one second of
 * it; the reset is the second step. 0 disables stall resets but keeps the
 * kicks and the rx_fault reset.
 */
/* Recovery is compiled in and on in every build. Like every other knob in
 * this driver, the two parameters exist only in debug builds: a release
 * object carries no module parameters at all (tools/verify-eth-debug.py).
 */
static bool zx_rx_recover = true;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(rx_recover, zx_rx_recover, bool, 0644);
MODULE_PARM_DESC(rx_recover,
	"re-initialise the datapath after an RX overrun or stall (0 = leave it stopped)");
#endif

static unsigned int zx_rx_stall_ms = 3000;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(rx_stall_ms, zx_rx_stall_ms, uint, 0644);
MODULE_PARM_DESC(rx_stall_ms,
	"descriptors pending with no return for this long count as a stall (0 = never reset for one)");
#endif

#define ZX_RESET_INTERVAL	(10 * HZ)	/* minimum spacing of resets */
#define ZX_RESET_MAX_CONSEC	3	/* resets with no RX in between, then stop */
#define ZX_RX_BLOCKED_POLLS	8	/* empty polls on a refused return, then back off */

static unsigned int zx_tx_w0 = 0x00000080;
static unsigned int zx_tx_w1 = 0x00010000;
static unsigned int zx_tx_w2 = 0x01000000;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(tx_w0, zx_tx_w0, uint, 0644);
module_param_named(tx_w1, zx_tx_w1, uint, 0644);
module_param_named(tx_w2, zx_tx_w2, uint, 0644);
#endif

/* TX descriptor word 3.
 *
 * This was the ONLY transmit field with no runtime knob, and that is why it is
 * still an open question rather than a measurement: the vendor Linux driver
 * (pon_tm_net_tx @ 0x97c0 in plat-zxylzb_9128S.ko) has THREE paths and they
 * disagree about this word:
 *
 *   raw      (.LANCHOR0+0x114 == 0)  byte0 0x80, word3 = 3, sets a per-port
 *                                    destination in halfword0 bits 9:4
 *   lan_up   (.LANCHOR0+0x110 != 0)  byte0 0x49, word3 = 2
 *   legacy   (.LANCHOR0+0x10c)       byte0 0x80, word3 = 2
 *
 * We have always written 2 with byte0 0x80 - the legacy shape - while the
 * vendor's data path is documented as using the raw shape. Both paths are now
 * reachable in one boot instead of one build per arm.
 */
static unsigned int zx_tx_w3 = 2;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(tx_w3, zx_tx_w3, uint, 0644);
MODULE_PARM_DESC(tx_w3, "TX descriptor word3 (vendor raw path uses 3)");
#endif

/* The stock halfword at desc+2 is the upper half of word0. Raw destinations
 * occupy word0[25:20]; zero here selects the transmitting netdev's MAC index.
 */
static unsigned int zx_tx_dest;
static bool zx_raw_tx = true;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(tx_dest, zx_tx_dest, uint, 0644);
MODULE_PARM_DESC(tx_dest,
	"test: override word0 bits25:20 destination (0 = select from netdev)");
module_param_named(raw_tx, zx_raw_tx, bool, 0644);
MODULE_PARM_DESC(raw_tx, "use per-netdev raw TX; disable only for legacy-template comparison");
#endif

/* MAC+0x00 bit0: CPU-receive mode (1, the historical setting) vs wire mode (0).
 * See the note at the write site - this is the one lever that explains why every
 * transmit disappears while receive works.
 */
static bool zx_cpu_mode = true;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(cpu_mode, zx_cpu_mode, bool, 0644);
MODULE_PARM_DESC(cpu_mode,
	"set MAC+0x00 bit0 on open (1 = CPU RX works, 0 = wire TX egresses)");
#endif

/* Establish driver-owned rings, cursors and buffer pools on every probe.
 * Inherited datapath attachment is an explicit debug experiment only.
 */
static bool zx_force_dp_init = true;
static bool zx_skip_dp_init;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(force_dp_init, zx_force_dp_init, bool, 0644);
MODULE_PARM_DESC(force_dp_init, "rebuild datapath state on probe (default); disable only for warm-attach experiments");
module_param_named(skip_dp_init, zx_skip_dp_init, bool, 0644);
MODULE_PARM_DESC(skip_dp_init, "debug: bypass datapath initialization and attach to existing state");
#endif

/* Which TX ring slot the next doorbell makes the hardware consume.
 *
 * MEASURED on the wire 2026-09-09, on the flashed pre-rewrite image: frames
 * leave the port carrying a PREVIOUS frame's length. A 98-byte echo request
 * went out as 83 bytes, and the 83-byte frame before it went out as 60 - each
 * one padded or truncated to the length of the frame that preceded it, with
 * its own payload intact. Uniform-length traffic therefore looks perfect,
 * which is exactly why ping has always worked here and TFTP, TCP and ARP
 * (whose frames differ in length from their predecessors) have not.
 *
 * That is the signature of writing the descriptor into a slot the hardware
 * has already passed. Which slot it consumes next is not established by any
 * measurement in this project - both "the reported index" and "a private
 * software cursor" are in the history, described as working, and neither was
 * ever checked against the wire. So make it a runtime choice and settle it
 * with a size ramp instead of an argument:
 *
 *   0 = private software cursor, seeded once from TMQ+0x6c (previous default)
 *   1 = the index TMQ+0x6c reports right now
 *   2 = one past the index TMQ+0x6c reports right now
 */
static unsigned int zx_tx_slot_mode;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(tx_slot_mode, zx_tx_slot_mode, uint, 0644);
MODULE_PARM_DESC(tx_slot_mode,
	"TX descriptor slot: 0 software cursor, 1 TMQ+0x6c, 2 TMQ+0x6c + 1");
#endif

/* Bound of the round-38 post-doorbell drain spin, in microseconds, when
 * tx_drain_probe is on (debug builds only; release builds never spin).
 *
 * The spin runs under tx_lock with interrupts off, on every transmitted frame.
 * If TMQ+0x6c advances at doorbell time rather than when the TM consumes the
 * descriptor, every frame burns the whole bound and TX is capped near
 * 1 / bound frames per second - which fits the 14-15 Mbit/s every R204/R206
 * device-side upload measured while the spin was unconditional. TXGATE in
 * /proc/zx_eth_regs settles it: slow ~= n means the bound is dead time.
 * 0 skips the spin even with the probe on.
 */
static unsigned int zx_tx_drain_us = 500;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(tx_drain_us, zx_tx_drain_us, uint, 0644);
MODULE_PARM_DESC(tx_drain_us,
	"bound of the tx_drain_probe spin in us, IRQs off (0 = no spin; see TXGATE)");
#endif

/* R199: isolate forwarding-register inspection from the legacy census dump,
 * which consumes TMQ read-clear counters. PP2 is opt-in, one 4 KiB page at a
 * time; its reserved/command words are NOT established safe to read.
 */
static bool zx_regs_path_only;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(regs_path_only, zx_regs_path_only, bool, 0644);
MODULE_PARM_DESC(regs_path_only,
	"zx_eth_regs: bounded SW/SBRG/attach/reset dump, without legacy counters");
#endif
static int zx_regs_pp2_page = -1;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(regs_pp2_page, zx_regs_pp2_page, int, 0644);
MODULE_PARM_DESC(regs_pp2_page,
	"path dump: -1 skips PP2; 0..63 opts into one unvetted 4 KiB PP2 page");
#endif

/* R200: opt-in, bounded MAC snapshots in the existing driver lifecycle. */
static bool zx_mac_snapshot;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(mac_snapshot, zx_mac_snapshot, bool, 0644);
MODULE_PARM_DESC(mac_snapshot,
	"log five MAC control words at open and link-up using the port's persistent map");
#endif

/* /proc/zx_eth_poke writes are refused unless this is set. See the guard. */
static bool zx_poke_allow_write;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(poke_allow_write, zx_poke_allow_write, bool, 0644);
MODULE_PARM_DESC(poke_allow_write,
	"allow /proc/zx_eth_poke to modify registers (reads never need it)");
#endif

/* How many transmits to describe on the console; the wire capture is the
 * measurement, this is what ties each frame to the slot that produced it.
 */
static unsigned int zx_tx_dbg_max = 24;
/* A timing probe must not serialize every production transmit for 500 us. */
static bool zx_tx_drain_probe;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(tx_drain_probe, zx_tx_drain_probe, bool, 0644);
MODULE_PARM_DESC(tx_drain_probe,
	"diagnostic: busy-wait up to 500 us after each TX doorbell (default off)");
module_param_named(tx_dbg_max, zx_tx_dbg_max, uint, 0644);
#endif

/* Bits cleared in the NPP per-port register; 0 leaves the bootloader value. */
static unsigned int zx_npp_port_mask = 0x3800000;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(npp_port_mask, zx_npp_port_mask, uint, 0644);
#endif


/* R201 packet trace: normal RAM only, no MMIO and no per-packet console I/O.
 * These markers delimit the actual C exercised by the offline stub tests.
 */
/* ZX_PACKET_TRACE_R201_BEGIN */
#define ZX_PACKET_TRACE_MAX 128

struct zx_packet_record {
	u64 ns;
	u32 src, dst, hash, head[6];
	u32 frame, iplen, payloadlen, buf, pool;
	int port, ring, slot;
	u16 ipid, id, seq;
	u8 type;
	bool tx;
};

struct zx_packet_snapshot {
	u32 generation, count;
	u64 dropped;
	int filter_id, armed_id;
	struct zx_packet_record records[ZX_PACKET_TRACE_MAX];
};

static DEFINE_SPINLOCK(zx_packet_trace_lock);
static int zx_packet_trace_id = -1;
static struct zx_packet_snapshot zx_packet_trace = {
	.filter_id = -1,
	.armed_id = -1,
};

static u16 zx_packet_be16(const u8 *p)
{
	return ((u16)p[0] << 8) | p[1];
}

static u32 zx_packet_be32(const u8 *p)
{
	return ((u32)p[0] << 24) | ((u32)p[1] << 16) |
	       ((u32)p[2] << 8) | p[3];
}

/* Ethernet/IPv4 echo only; VLAN and fragments are deliberately not decoded.
 * IHL bounds permit options, whose contents/checksums are not interpreted.
 * IP total length, not skb padding, bounds the ICMP payload fingerprint.
 */
static bool zx_packet_decode(const u8 *frame, u32 len, int id,
			     struct zx_packet_record *r)
{
	const u8 *ip, *icmp, *payload;
	u32 ihl, total, i;

	if (!frame || !r || id < 0 || id > 65535 ||
	    len < ETH_HLEN + 20 || len > BUF_SIZE - BUF_HDR)
		return false;
	if (zx_packet_be16(frame + 12) != 0x0800)
		return false;
	ip = frame + ETH_HLEN;
	ihl = (ip[0] & 15) * 4;
	total = zx_packet_be16(ip + 2);
	if ((ip[0] >> 4) != 4 || ihl < 20 ||
	    ihl > len - ETH_HLEN || total < ihl + 8 ||
	    total > len - ETH_HLEN || ip[9] != IPPROTO_ICMP ||
	    (zx_packet_be16(ip + 6) & 0xbfff))
		return false; /* reserved flag, MF or nonzero fragment offset */
	icmp = ip + ihl;
	if ((icmp[0] != 0 && icmp[0] != 8) || icmp[1] != 0 ||
	    zx_packet_be16(icmp + 4) != id)
		return false;

	memset(r, 0, sizeof(*r));
	r->frame = len;
	r->iplen = total;
	r->payloadlen = total - ihl - 8;
	r->ipid = zx_packet_be16(ip + 4);
	r->src = zx_packet_be32(ip + 12);
	r->dst = zx_packet_be32(ip + 16);
	r->type = icmp[0];
	r->id = zx_packet_be16(icmp + 4);
	r->seq = zx_packet_be16(icmp + 6);
	payload = icmp + 8;
	r->hash = 2166136261U;
	for (i = 0; i < r->payloadlen; i++) {
		r->hash = (r->hash ^ payload[i]) * 16777619U;
		if (i < 24)
			r->head[i / 4] |= (u32)payload[i] << (24 - 8 * (i % 4));
	}
	return true;
}

#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
static int zx_packet_trace_set(const char *value, const struct kernel_param *kp)
{
	unsigned long flags;
	int id, ret;

	(void)kp;
	ret = kstrtoint(value, 0, &id);
	if (ret)
		return ret;
	if (id < -1 || id > 65535)
		return -EINVAL;
	spin_lock_irqsave(&zx_packet_trace_lock, flags);
	if (id >= 0) {
		WRITE_ONCE(zx_packet_trace.generation,
			   zx_packet_trace.generation + 1);
		zx_packet_trace.count = 0;
		zx_packet_trace.dropped = 0;
		zx_packet_trace.armed_id = id;
		memset(zx_packet_trace.records, 0, sizeof(zx_packet_trace.records));
	}
	zx_packet_trace.filter_id = id;
	WRITE_ONCE(zx_packet_trace_id, id);
	spin_unlock_irqrestore(&zx_packet_trace_lock, flags);
	return 0;
}

static const struct kernel_param_ops zx_packet_trace_ops = {
	.set = zx_packet_trace_set,
	.get = param_get_int,
};
module_param_cb(packet_trace_id, &zx_packet_trace_ops, &zx_packet_trace_id, 0644);
MODULE_PARM_DESC(packet_trace_id,
	"ICMP echo id 0..65535 resets/arms 128 RAM records; -1 disables without clearing");
#endif

static void zx_packet_trace_add(const u8 *frame, u32 len, bool tx, int port,
				int ring, int slot, u32 buf, u32 pool)
{
	struct zx_packet_record r;
	unsigned long flags;
	u32 generation;
	u64 ns;

	if (!ZX_HAVE_DEBUG_IFACES || READ_ONCE(zx_packet_trace_id) < 0)
		return;
	generation = READ_ONCE(zx_packet_trace.generation);
	/* Stage timestamp precedes parsing, hashing and any trace-lock wait. */
	ns = ktime_get_ns();
	spin_lock_irqsave(&zx_packet_trace_lock, flags);
	/* Serialize filter/reset with the entire bounded parse and append. A
	 * rearm while this hook waited must not import its old timestamp.
	 */
	if (zx_packet_trace_id < 0 || generation != zx_packet_trace.generation ||
	    !zx_packet_decode(frame, len, zx_packet_trace_id, &r))
		goto out;
	if (zx_packet_trace.count == ZX_PACKET_TRACE_MAX) {
		zx_packet_trace.dropped++;
		goto out;
	}
	r.ns = ns;
	r.tx = tx;
	r.port = port;
	r.ring = ring;
	r.slot = slot;
	r.buf = buf;
	r.pool = pool;
	zx_packet_trace.records[zx_packet_trace.count++] = r;
out:
	spin_unlock_irqrestore(&zx_packet_trace_lock, flags);
}

static int zx_packets_show(struct seq_file *m, void *v)
{
	const struct zx_packet_snapshot *s = m->private;
	u32 i;

	(void)v;
	seq_printf(m, "PKTRACE_HEADER generation=%u enabled=%u filter_id=%d armed_id=%d records=%u dropped=%llu tx_stage=pre-doorbell rx_stage=pre-eth_type_trans\n",
		   s->generation, s->filter_id >= 0, s->filter_id, s->armed_id,
		   s->count, (unsigned long long)s->dropped);
	for (i = 0; i < s->count; i++) {
		const struct zx_packet_record *r = &s->records[i];

		seq_printf(m, "PKTRACE ns=%llu dir=%s port=%d ring=%d slot=%d buf=%u pool=%u frame=%u iplen=%u payloadlen=%u ipid=0x%04x src=0x%08x dst=0x%08x type=%u id=0x%04x seq=%u hash=0x%08x head=%08x%08x%08x%08x%08x%08x\n",
			   (unsigned long long)r->ns, r->tx ? "tx" : "rx",
			   r->port, r->ring, r->slot, r->buf, r->pool,
			   r->frame, r->iplen, r->payloadlen, r->ipid,
			   r->src, r->dst, r->type, r->id, r->seq, r->hash,
			   r->head[0], r->head[1], r->head[2],
			   r->head[3], r->head[4], r->head[5]);
	}
	seq_puts(m, "PKTRACE_END\n");
	return 0;
}

static int zx_packets_open(struct inode *inode, struct file *file)
{
	struct zx_packet_snapshot *snapshot;
	unsigned long flags;
	int ret;

	(void)inode;
	/* Allocate before taking the trace lock; seq retries/seek only format
	 * this immutable per-open copy, never live state or device registers.
	 */
	snapshot = kmalloc(sizeof(*snapshot), GFP_KERNEL);
	if (!snapshot)
		return -ENOMEM;
	spin_lock_irqsave(&zx_packet_trace_lock, flags);
	*snapshot = zx_packet_trace;
	spin_unlock_irqrestore(&zx_packet_trace_lock, flags);
	ret = single_open(file, zx_packets_show, snapshot);
	if (ret)
		kfree(snapshot);
	return ret;
}

static int zx_packets_release(struct inode *inode, struct file *file)
{
	struct seq_file *m = file->private_data;
	struct zx_packet_snapshot *snapshot = m->private;
	int ret;

	ret = single_release(inode, file);
	kfree(snapshot);
	return ret;
}

static const struct proc_ops zx_packets_pops = {
	.proc_open = zx_packets_open,
	.proc_read = seq_read,
	.proc_lseek = seq_lseek,
	.proc_release = zx_packets_release,
};
/* ZX_PACKET_TRACE_R201_END */

/* Set at probe so the /proc recovery hooks can reach the device. */
static struct zx_eth *zx_eth_singleton;
static struct zx_eth *zx_dbg_ze;	/* for /proc ring dump */


/* ---- RX interrupt probe (BRINGUP only) --------------------------------
 *
 * This driver has never requested an interrupt. RX is driven by a 500 us
 * hrtimer poll, and measurement on 2026-09-07 showed that poll interval is a
 * real throughput ceiling (500 us -> 5.79 Mbit/s, 100 us -> 11.65 Mbit/s).
 *
 * The stock DTS declares five datapath interrupts nobody here has ever tried:
 * IDM (0x26) and one per GE port from the gephy block (0x27-0x2a). This probe
 * requests them and does nothing but count, to answer one question: does any
 * of them assert in proportion to received frames? If one does, the hrtimer
 * can be retired.
 *
 * SAFETY: these lines are declared level-triggered and we do not know how to
 * acknowledge them at source. A level-triggered line we never clear re-asserts
 * immediately and livelocks the CPU with no console. So each handler counts and
 * then, past a bounded number of hits, disables its own line and says so. The
 * worst case is a muzzled line and a log message, not a dead board.
 */
#define ZX_IRQ_PROBE_MAX	5
#define ZX_IRQ_PROBE_BUDGET	2000

static unsigned long zx_irq_hits[ZX_IRQ_PROBE_MAX];
static int zx_irq_nums[ZX_IRQ_PROBE_MAX];
static unsigned int zx_irq_probe_n;
static bool zx_irq_muzzled;

static bool zx_irq_probe = true;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(irq_probe, zx_irq_probe, bool, 0444);
MODULE_PARM_DESC(irq_probe, "BRINGUP: request the DT-declared datapath IRQs and count them");
#endif

static irqreturn_t zx_irq_probe_handler(int irq, void *data)
{
	unsigned int i = (unsigned int)(uintptr_t)data;

	if (i >= ZX_IRQ_PROBE_MAX)
		return IRQ_NONE;

	if (++zx_irq_hits[i] > ZX_IRQ_PROBE_BUDGET) {
		/* Cannot be acknowledged at source - stop it before it livelocks
		 * the CPU. The count already answers the question.
		 */
		disable_irq_nosync(irq);
		zx_irq_muzzled = true;
	}

	return IRQ_HANDLED;
}


/* Split the physical ports into separate netdevs.
 *
 * All four GE ports arrive on one netdev, which is why the bridge needs hairpin
 * to forward between them and why a WAN/LAN split is impossible: netifd cannot
 * put "the mac3 jack" in one zone and "the mac1 jack" in another when they are
 * the same interface.
 *
 * The RX descriptor does identify the ingress port - w1 bits 20/21, measured
 * 2026-09-06 with single-source traffic per port. This creates ONE secondary
 * netdev and sends frames whose w1 matches `split_bit` to it.
 *
 * Default OFF, and deliberately so: the bit->port encoding is known from only
 * TWO cabled ports, so it is one-hot-vs-index ambiguous (docs/ETHERNET.md).
 * This is enough to prove a WAN/LAN split works; it is not yet a general
 * four-port decoder.
 *
 * TX needs nothing per-port: the fabric routes a CPU-injected frame to the port
 * its destination MAC lives on, so both netdevs share one transmit path.
 */
/* One netdev per physical port. Default ON since 2026-09-06: the ingress-port
 * encoding it depends on is no longer a guess - a third cabled port showed the
 * field is `((w1 >> 19) & 7) - 1`, i.e. +1 indexing rather than the one-hot
 * reading two ports had suggested. Routing and NAT between two physical jacks
 * were verified end to end on hardware with this enabled.
 */
static bool zx_split_ports = true;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(split_ports, zx_split_ports, bool, 0644);
MODULE_PARM_DESC(split_ports,
	"one netdev per physical port, attributed by the descriptor's ingress-port field");
#endif

/* Round 31 instrumentation: trace the next N RX descriptors.
 *
 * The labelled-burst statistics showed the fault is NOT byte corruption - 63
 * consecutive datagrams had payload and source port in perfect agreement - but
 * the wrong SEQUENCE of perfect frames, including a later frame arriving early.
 * That is the signature of consuming descriptors out of step with the producer,
 * so the question to answer is narrow and factual: does a descriptor's buffer
 * index (`idx`) repeat within one lap, or arrive out of order, relative to the
 * software cursor?
 *
 * Print all fields needed to settle that - ring, cursor BEFORE the increment,
 * the pending count that gated the iteration, idx, pool, length and validity -
 * plus byte 42 of the buffer, which is the UDP payload's first byte for the
 * 64-byte labelled frames the bench sends (14 eth + 20 ip + 8 udp).
 *
 * It is a countdown, not a boolean: write a number to arm it, and it decrements
 * as it prints. Reading the parameter back shows what is left, and writing 0
 * stops it. That bounds the console output by construction - this driver has
 * flooded the UART before, and a flood corrupts the transfer path.
 */
static unsigned int zx_rx_trace;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(rx_trace, zx_rx_trace, uint, 0644);
MODULE_PARM_DESC(rx_trace, "print this many RX descriptors then stop (0=off)");
#endif

/* ROUND 52 test knob: do not return RX buffers to the BM pool.
 *
 * The buffer manager behaves as a stack. zx_bm_alloc() returns index 0 for every
 * TX frame, and RX returns its buffer straight back through zx_bm_free(), so the
 * pool head never advances: whichever side asks next is handed 0 again. Measured
 * during a TCP transfer - 12/12 transmits and 22/30 receives all used buffer 0.
 *
 * If the pool head cannot advance, the two sides must collide. Withholding the
 * RX return should force the allocator to hand out *different* indices, which is
 * both the proof of the mechanism and possibly the fix.
 *
 * It leaks buffers by construction, so it is a test knob, not a fix: after
 * BUF_COUNT frames the pool would be empty and RX would stall. Default off.
 */
static bool zx_rx_no_free;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(rx_no_free, zx_rx_no_free, bool, 0644);
MODULE_PARM_DESC(rx_no_free,
	"test: withhold RX buffer returns so the BM pool head must advance");
#endif

/* ROUND 70: bypass GRO for received frames.
 *
 * Round 69 measured 12 frames in 100 vanishing between the driver's census and
 * Ip: InReceives, with no error counter anywhere - i.e. the driver hands the
 * stack an skb that the stack discards silently. The standing suspect is the
 * descriptor length, which reads a constant 1514 against 98-byte ping frames,
 * and GRO is the stage immediately after the driver's hand-off and a
 * well-known place for inconsistent skbs to disappear uncounted.
 *
 * Routing around GRO is a one-line way to falsify or confirm that. Switchable
 * at runtime so both arms can be measured in a single boot, which is the only
 * way to compare two conditions on this bench.
 */
static bool zx_no_gro;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(no_gro, zx_no_gro, bool, 0644);
MODULE_PARM_DESC(no_gro, "test: deliver RX frames with netif_receive_skb instead of GRO");
#endif

/* ROUND 57: dedicated TX scratch buffer index.
 *
 * zx_bm_alloc() returns index 0 for every transmit, and RX also uses index 0
 * for most receives (22 of 30, measured round 50), so TX and RX copy through
 * the same 2 KiB. One-way UDP never shows it (the device transmits nothing) and
 * TCP is destroyed by it (the device transmits constantly).
 *
 * The whole investigation so far has tried to move the RX side - free list,
 * BM pool, and descriptor priming - and all three were ruled out, the last one
 * by breaking receive outright. This is the other half: leave RX completely
 * alone and stop TX from using RX's buffer.
 *
 * Default BUF_COUNT-1 (2047), which the RX free list does not offer.
 *
 * REMOVED 2026-09-10 (round 97). The experiment was run and lost - see the
 * ROUND 57 REVERTED note in the TX path. The parameter then survived the
 * round unused, which is worse than useless: a tunable that does nothing
 * invites a future round to sweep it and read meaning into the noise.
 */

/* Decode the ingress port from an RX descriptor.
 *
 * MEASURED 2026-09-06 across THREE cabled ports, single-source traffic per
 * phase, two of them confirmed again in one boot:
 *
 *   mac1 -> w1[23:16] = 0x10, mac2 -> 0x19, mac3 -> 0x21/0x20
 *
 * 16 / 25 / 32 looks irregular until you take bits [21:19], which give 2 / 3 / 4
 * -- the MAC index PLUS ONE. That is the same "getPort(n) = n + 1" convention
 * the sibling ZX279133 documents for its switch UNI -> PPU port mapping, which
 * is good corroboration for a field recovered empirically.
 *
 * Bit 16 is NOT part of it: it is set on some frames of every port and clear on
 * others. Bits [31:24] are a rolling counter.
 *
 * Returns 0..ZX_NPORTS-1, or -1 if the field is 0 or out of range.
 */
#define ZX_RX_PORT_SHIFT	19
#define ZX_RX_PORT_MASK		0x7

static int zx_rx_port_of(u32 w1)
{
	int p = ((w1 >> ZX_RX_PORT_SHIFT) & ZX_RX_PORT_MASK) - 1;

	return (p >= 0 && p < ZX_NPORTS) ? p : -1;
}

struct zx_port_priv {
	struct zx_eth *ze;
	int port;
	struct device_node *phy_np;	/* this port's own PHY */
};

static const struct net_device_ops zx_port_netdev_ops;

/* Both netdev types share one zx_eth. */
static struct zx_eth *zx_ze_of(struct net_device *ndev)
{
	if (ndev->netdev_ops == &zx_port_netdev_ops)
		return ((struct zx_port_priv *)netdev_priv(ndev))->ze;
	return netdev_priv(ndev);
}

/* Which physical MAC index this netdev represents. */
static int zx_port_index_of(struct net_device *ndev)
{
	if (ndev->netdev_ops == &zx_port_netdev_ops)
		return ((struct zx_port_priv *)netdev_priv(ndev))->port;
	return ((struct zx_eth *)netdev_priv(ndev))->bound_port;
}

/* Sample only the selected port through its already-owned mapping. No fresh
 * ioremap, fallback to the bound MAC, register sweep, or MMIO write belongs here.
 * Values are sequential reads, not an atomic hardware snapshot.
 */
static void zx_mac_snapshot_log(struct net_device *ndev, const char *stage)
{
	struct zx_eth *ze;
	void __iomem *mac;
	u32 ctrl, cfg4, b00, d00, d30;
	int port;

	if (!READ_ONCE(zx_mac_snapshot) || !ndev)
		return;
	ze = zx_ze_of(ndev);
	port = zx_port_index_of(ndev);
	if (!ze || port < 0 || port >= ZX_NPORTS)
		return;
	mac = ze->macs[port];
	if (!mac)
		return;

	ctrl = readl(mac + 0x000);
	cfg4 = readl(mac + 0x004);
	b00 = readl(mac + 0xb00);
	d00 = readl(mac + 0xd00);
	d30 = readl(mac + 0xd30);
	netdev_info(ndev,
		    "MACSNAP stage=%s port=%d ctrl=%08x cfg4=%08x b00=%08x d00=%08x d30=%08x\n",
		    stage, port, ctrl, cfg4, b00, d00, d30);
}

/* The `ethernet-ports/port@N` node describing one physical port: its PHY and
 * its MAC address. Returns a reference the caller must of_node_put().
 */
static struct device_node *zx_port_node(struct device *dev, int port)
{
	struct device_node *ports, *child;

	if (port < 0)
		return NULL;
	ports = of_get_child_by_name(dev->of_node, "ethernet-ports");
	if (!ports)
		return NULL;

	for_each_available_child_of_node(ports, child) {
		u32 idx;

		if (!of_property_read_u32(child, "reg", &idx) && idx == port) {
			of_node_put(ports);
			return child;
		}
	}
	of_node_put(ports);
	return NULL;
}

static bool zx_has_phy_mode(const struct device_node *np)
{
	return np && (of_property_present(np, "phy-mode") ||
		      of_property_present(np, "phy-connection-type"));
}

/* PHY interface of one port: its own phy-mode, else the legacy node-level one,
 * else RGMII. RGMII is the only mode this MAC is known to run, so any other
 * value is refused rather than silently attached as RGMII.
 */
static int zx_eth_phy_mode(struct device *dev, struct device_node *np,
			   phy_interface_t *mode)
{
	struct device_node *src = zx_has_phy_mode(np) ? np : dev->of_node;

	*mode = PHY_INTERFACE_MODE_RGMII;
	if (!zx_has_phy_mode(src))
		return 0;
	if (of_get_phy_mode(src, mode) || *mode != PHY_INTERFACE_MODE_RGMII)
		return dev_err_probe(dev, -EINVAL, "%pOF: unsupported phy-mode, only rgmii\n",
				     src);
	return 0;
}

/* Every port's PHY interface, parsed before probe touches the hardware. */
static int zx_eth_phy_modes(struct zx_eth *ze)
{
	int port, ret;

	for (port = 0; port < ZX_NPORTS; port++) {
		struct device_node *np = zx_port_node(ze->dev, port);

		ret = zx_eth_phy_mode(ze->dev, np, &ze->phy_modes[port]);
		of_node_put(np);
		if (ret)
			return ret;
	}
	if (ze->bound_port >= 0) {
		ze->phy_mode = ze->phy_modes[ze->bound_port];
		return 0;
	}
	return zx_eth_phy_mode(ze->dev, NULL, &ze->phy_mode);
}

/* Resolve every block in zx_eth_reg_desc. The blocks overlap other users (the
 * MDIO driver's debug dump, the PP table code) and each other's mappings, so
 * they are only ever ioremapped, never claimed.
 */
static int zx_eth_resolve_regs(struct zx_eth *ze, struct platform_device *pdev)
{
	char missing[96] = "";
	size_t len = 0;
	int i;

	for (i = 0; i < ZX_NREGS; i++) {
		const struct zx_eth_reg_desc *d = &zx_eth_reg_desc[i];
		struct resource *res;

		res = platform_get_resource_byname(pdev, IORESOURCE_MEM, d->name);
		if (!res) {
			ze->phys[i] = d->fallback;
			len += scnprintf(missing + len, sizeof(missing) - len, " %s",
					 d->name);
			continue;
		}
		if (resource_size(res) < d->size)
			return dev_err_probe(ze->dev, -EINVAL, "'%s' reg region too small\n",
					     d->name);
		ze->phys[i] = res->start;
	}
	if (len)
		dev_info(ze->dev, "no reg-names entry for%s; using built-in addresses\n",
			 missing);
	return 0;
}

/* Resolve the DDR window (see ZX_DDR_BASE) from memory-region. The TM takes
 * 32-bit addresses, and the driver maps parts of the window with ioremap, so
 * the region must be no-map and lie below 4 GiB.
 */
static int zx_eth_resolve_ddr(struct zx_eth *ze)
{
	struct device_node *np;
	struct reserved_mem *rmem;
	bool nomap;

	np = of_parse_phandle(ze->dev->of_node, "memory-region", 0);
	if (!np) {
		ze->ddr_phys = ZX_DDR_BASE;
		dev_info(ze->dev, "no memory-region; using built-in DDR window %#x+%#x\n",
			 ZX_DDR_BASE, ZX_DDR_SIZE);
		return 0;
	}
	rmem = of_reserved_mem_lookup(np);
	nomap = of_property_read_bool(np, "no-map");
	of_node_put(np);
	if (!rmem || !nomap)
		return dev_err_probe(ze->dev, -EINVAL,
				     "memory-region is not a no-map reserved-memory region\n");
	if (rmem->size < ZX_DDR_SIZE || !IS_ALIGNED(rmem->base, ZX_DDR_ALIGN) ||
	    upper_32_bits((u64)rmem->base + ZX_DDR_SIZE - 1))
		return dev_err_probe(ze->dev, -EINVAL,
				     "memory-region %pa+%pa: need %#x bytes, %#x aligned, below 4 GiB\n",
				     &rmem->base, &rmem->size, ZX_DDR_SIZE, ZX_DDR_ALIGN);
	ze->ddr_phys = rmem->base;
	return 0;
}

/* Derive port N's address from the base, the way the vendor derives its extra
 * BSSIDs: set the locally-administered bit and put the index in byte 3's high
 * nibble, so 02:00:00:00:00:05 becomes 06:20:84:1f:87:b5, :2f:, :3f:.
 *
 * The `tag` partition holds four factory addresses and the first two are spoken
 * for - the stock web UI names them as the 2.4 GHz and 5 GHz BSSIDs. The DT
 * gives record 2 to eth0 (and so br-lan) and record 3 to the WAN port, so only
 * the two LAN member ports need a derived address. Incrementing the last octet
 * instead would walk into 02:00:00:00:00:07, which belongs to somebody else's
 * unit; the locally-administered range does not. A port with its own nvmem
 * cell never derives (see zx_set_mac_from_dt()).
 */
static void zx_derive_mac(u8 *dst, const u8 *base, int idx)
{
	ether_addr_copy(dst, base);
	if (!idx)
		return;
	dst[0] |= 0x02;
	dst[3] = (dst[3] & 0x0f) | ((idx & 0xf) << 4);
}

/* Per-unit MAC, from the `tag` flash partition via an nvmem cell in the DT,
 * falling back to a derivation from the base address for the ports that have no
 * cell of their own.
 *
 * The addresses are factory data unique to the unit, so a random address here is
 * a real failure and not a cosmetic one: it changes every boot, which breaks
 * DHCP reservations, bridge learning and any ARP cache that outlives a reboot.
 * Random is the last resort, and it says so.
 */
static void zx_set_mac_from_dt(struct zx_eth *ze, struct net_device *ndev,
			       struct device_node *np, int port)
{
	u8 addr[ETH_ALEN];

	if (np && !of_get_ethdev_address(np, ndev)) {
		if (!ze->have_base_mac) {
			ether_addr_copy(ze->base_mac, ndev->dev_addr);
			ze->have_base_mac = true;
		}
		return;
	}

	if (ze->have_base_mac && port > 0) {
		zx_derive_mac(addr, ze->base_mac, port);
		eth_hw_addr_set(ndev, addr);
		return;
	}

	eth_hw_addr_random(ndev);
	netdev_warn(ndev, "no MAC in DT (nvmem cell missing or unreadable), using random %pM\n",
		    ndev->dev_addr);
}

/* Is the datapath already configured by the bootloader?
 *
 * RESTORED VERBATIM from the revision that worked
 * (artifacts/2026-09-08/h199a-tm-state-eth.c:840). This driver lost it in the
 * IRQ rewrite and round 12 replaced it with a ring-base-only check, which is
 * NOT equivalent: the original requires BOTH a valid ring base pair AND at least
 * one MAC with a configured control word.
 *
 * The MAC half is the part that matters and the part that got dropped. U-Boot
 * configures the MACs it uses; the DT-bound MAC can stay cold while another port
 * carried the kernel over TFTP - which is exactly this bench, where the cable is
 * on eth2 but eth0 is the port the device tree binds.
 *
 * A valid ring base lies in the DDR window (0x41000000..0x41ffffff on the
 * H199A, as in that revision).
 */
static bool zx_datapath_warm(struct zx_eth *ze)
{
	u32 rx = readl(ze->tmc + TMC_RING_BASE);
	u32 tx = readl(ze->tmq + TMQ_TXRING);
	int port;

	if (rx - ze->ddr_phys >= ZX_DDR_SIZE || tx - ze->ddr_phys >= ZX_DDR_SIZE)
		return false;

	for (port = 0; port < ZX_NPORTS; port++)
		if (ze->macs[port] &&
		    (readl(ze->macs[port] + MAC_CTRL) & 0xffff0000))
			return true;
	return false;
}

/* MAC+0x00 bit0 gates ingress on a port. Setting it is what makes a port
 * receive at all; see the note in zx_eth_open().
 */
static void zx_mac_enable(struct zx_eth *ze, int port, bool on)
{
	void __iomem *m;
	u32 v;

	if (port < 0 || port >= ZX_NPORTS)
		return;
	m = ze->macs[port];
	if (!m)
		return;

	v = readl(m + MAC_CTRL);
	/* `zx_cpu_mode` has to be honoured HERE, not only at the bound-port
	 * write in zx_eth_open().
	 *
	 * Round 8 found the A/B was never actually running on the cabled port:
	 * zx_port_open() calls this with on=true for eth2 itself, so MAC2's bit0
	 * was set on every boot regardless of the parameter, and the "wire mode"
	 * arm measured nothing. The port-mode log line only ever named eth0,
	 * which is the tell - if the parameter is visibly working, it appears on
	 * the port the cable is in.
	 */
	if (on && zx_cpu_mode) {
		if (v & MAC_CTRL_EN)
			return;
		writel(v | MAC_CTRL_EN, m + MAC_CTRL);
	} else {
		writel(v & ~MAC_CTRL_EN, m + MAC_CTRL);
	}
}

static int zx_eth_cpu_protocols(struct zx_eth *ze)
{
	void __iomem *spa;
	u32 value, actual;

	spa = ioremap(ze->phys[ZX_REG_NPP] + ZX_NPP_SPA, SZ_4K);
	if (!spa)
		return -ENOMEM;

	value = readl(spa + SPA_TRAP_PROTOCOLS);
	value &= ~(SPA_TRAP_PROTOCOL0 | SPA_TRAP_PROTOCOL1);
	value |= SPA_CPU_PROTOCOLS;
	writel(value, spa + SPA_TRAP_PROTOCOLS);
	actual = readl(spa + SPA_TRAP_PROTOCOLS);
	iounmap(spa);
	if (actual != value)
		return dev_err_probe(ze->dev, -EIO,
			"SPA protocol selectors did not latch (%08x != %08x)\n",
			actual, value);

	dev_info(ze->dev, "SPA CPU protocol selectors=%08x (UDP/TCP)\n", actual);
	return 0;
}


static netdev_tx_t zx_eth_xmit(struct sk_buff *skb, struct net_device *ndev)
{
	struct zx_eth *ze = zx_ze_of(ndev);
	unsigned long flags;
	void __iomem *desc;
	u32 len = skb->len, completed, txidx_before, txidx_after, slot;
	u32 control, destination;
	bool raw = !ZX_HAVE_DEBUG_IFACES || READ_ONCE(zx_raw_tx);
	int idx;

	/* Own-stock raw format: GE/MAC index + 0x28 in word0[25:20], paired
	 * with word3 control value 3. VID6 maps logical ports to MAC indices
	 * [3,2,1,0]; our netdev indices are already those physical MAC indices.
	 */
	int txport = zx_port_index_of(ndev);

	if (txport < 0 || txport >= ZX_NPORTS ||
	    len > BUF_SIZE - BUF_HDR || skb_linearize(skb))
		goto drop;
	if (skb_put_padto(skb, ETH_ZLEN)) {
		ndev->stats.tx_dropped++;
		return NETDEV_TX_OK;
	}

	/* All port queues share this ring, allocator and completion counter. */
	spin_lock_irqsave(&ze->tx_lock, flags);
	/* ROUND 66 REVERTED: TMQ_TXIDX-derived back-pressure did not help.
	 *
	 * Replacing the constant TMQ_CREDIT term with the distance between the
	 * driver's tx_next and TMQ_TXIDX changed nothing: the 200-ping
	 * distribution was 46 samples over 10 ms and 13 duplicates against 25 and
	 * 10 before, with the median unchanged at 0.25 ms and the maximum still
	 * ~22 s. So the ring-overrun hypothesis is not supported, or the half of
	 * TMQ_TXIDX used is not the TX ring index and the guard never engaged.
	 * Reverted rather than left in unproven.
	 */
	if (ze->tx_outstanding) {
		completed = readl(ze->tmq + TMQ_CREDIT) & 0xffff;
		ze->tx_outstanding -= min(completed, ze->tx_outstanding);
	}
	/* ROUND 41: the drop below was a TIME BOMB and is removed.
	 *
	 * tx_outstanding is fed by TMQ+0x68 (and, since r39, TMQ+0x58) and both
	 * read 0 on this silicon - measured directly: `credit=00000000` in the
	 * TXDRAIN line while frames were demonstrably leaving the ring. So the
	 * decrement above never fires and the counter climbs monotonically with
	 * every transmit. Measured this round: 725 -> 947 over 200 s at 5/s, and
	 * R133 recorded 5 -> 81 -> 142 -> 173 -> 177.
	 *
	 * The guard that used to sit here dropped EVERY frame once the counter
	 * reached RING_ENTRIES (1024), and because the counter can never come
	 * back down, that state was permanent: a guaranteed total TX failure
	 * after enough traffic, with tx_fifo_errors as its only announcement.
	 * The run above ended 77 short of it.
	 *
	 * Removing the guard is safe because the counter was never measuring a
	 * real backlog in the first place: TXDRAIN shows the hardware's consume
	 * index in lockstep with sw_next (`delta=0`), i.e. the ring is empty.
	 * The counter is kept as a diagnostic only. If a real back-pressure test
	 * is ever needed it must be derived from TMQ_TXIDX against sw_next, not
	 * from this register.
	 */
	idx = zx_bm_alloc(ze);
	if (idx < 0)
		goto unlock_drop;
	if (idx >= BUF_COUNT) {
		net_ratelimited_function(netdev_warn, ndev,
			"tx: buffer index %d out of range, dropping\n", idx);
		goto unlock_drop;
	}
	/* ROUND 57 REVERTED: moving TX off buffer 0 BREAKS RECEIVE.
	 *
	 * Measured within a single boot, no rebuild, by flipping the (since
	 * removed, round 97) tx_scratch module parameter:
	 *
	 *   tx_scratch = 2047 -> ping 100% loss, RXCENSUS icmp=0 udp=3
	 *   tx_scratch = 0    -> ping 2 of 3,    RXCENSUS icmp=2 udp=4
	 *
	 * So TX must keep using the index the allocator returns (0). Writing the
	 * transmit frame anywhere else stops the device receiving. The collision
	 * between TX and RX on buffer 0 is therefore not resolvable by moving TX,
	 * which was the one direction this investigation had not tried.
	 */
	/* ROUND 43 REVERTED: moving TX to pool 1 BROKE RECEIVE, and it reproduced
	 * round 57's result exactly.
	 *
	 * The reasoning was sound and the measurement was unambiguous: R144 showed
	 * no wire loss in either direction (host TX 65 == board RX 65, board TX 44
	 * == host NIC RX 44) with the host accepting the replies as valid
	 * (InEchoReps +40), yet the board classified only 47 of the 60 requests it
	 * demonstrably received - so frames are being CORRUPTED, and TX and RX
	 * sharing one 2 KiB buffer is the only mechanism in this driver that can
	 * do that (`zx_buf()` can only ever address pool 0; RX selects per
	 * descriptor with `pool = desc[9] & 1`; TX had no selector at all).
	 *
	 * So TX was moved to pool 1 (`bufs2`) with the descriptor's pool bit set:
	 *
	 *     memcpy_toio((u8 *)ze->bufs2 + ((size_t)idx << 11) + BUF_HDR, ...)
	 *     ... and after zx_desc_pack: writeb(readb(desc + 9) | 1, desc + 9);
	 *
	 * Measured, same boot, same probe, against the r41 baseline:
	 *
	 *     r41: p50 = 0.318 ms, loss 68.3%
	 *     r43: p50 = 11290 ms, loss 88.3%   <- pool 1 for TX
	 *
	 * So the hardware does not honour the pool bit on the transmit path, or
	 * pool 1 is not a valid transmit source. This is the same wall round 57 hit
	 * from the other side, and it settles the question: the collision is real
	 * but it is NOT fixable by moving TX, in either the index or the pool.
	 *
	 * Kept as a comment rather than deleted because the measurement is the
	 * point - the corruption stands, the next attempt must attack the RX side
	 * or the allocator, not the TX buffer.
	 */
	memcpy_toio(zx_buf(ze, idx), skb->data, skb->len);
	/* ROUND 68: the R65 free-on-slot-reuse is REVERTED, and the reason is
	 * worth keeping.
	 *
	 * The leak it fixed was real: zx_bm_free() had exactly one call site, on
	 * the RX path, so every transmitted frame permanently consumed a pool
	 * buffer - invisible while the allocator returned 0 for ever, unbounded
	 * once R159 seeded the free lists. But freeing on reuse means freeing
	 * BEFORE there is any evidence the hardware has finished reading that
	 * buffer, and it was placed here - before the new descriptor is written
	 * and before the doorbell - which is the earliest possible instant and
	 * therefore the largest possible window.
	 *
	 * It is safe ONLY if the ring never laps the hardware, and that was the
	 * entire job of the R66/R67 back-pressure, which is itself now reverted
	 * because it had to gate on a read-clear register with four destructive
	 * readers. So the free inherited an unreliable guarantee, and its failure
	 * mode is not a stall - it is DMA use-after-free, i.e. silent corruption
	 * of a buffer the TM may still be reading. That is strictly worse than
	 * the pool leak, and worse than the delivery defect, which R164 measured
	 * to be ABOVE the driver and which no TX-side change can recover.
	 *
	 * Reverted together with the back-pressure for that reason. Reinstating
	 * it needs a consumption guarantee first - a trustworthy completion
	 * signal with a single reader, not a read-clear register shared with
	 * three diagnostics.
	 */

	/* The frame length the hardware uses comes from the descriptor it reads,
	 * not from the one we wrote, unless the two are the same slot. Record
	 * the reported index on both sides of the doorbell so a wire capture can
	 * be matched against the slot that actually produced each frame.
	 */
	txidx_before = readl(ze->tmq + TMQ_TXIDX);
	switch (zx_tx_slot_mode) {
	case 1:
		slot = (txidx_before & 0xffff) % RING_ENTRIES;
		break;
	case 2:
		slot = ((txidx_before & 0xffff) + 1) % RING_ENTRIES;
		break;
	default:
		slot = ze->tx_next;
		break;
	}

	desc = (u8 *)ze->txring + (size_t)slot * DESC_SIZE;
	/* Direct transmission must not depend on hardware MAC learning. The
	 * old halfword experiment retained legacy word3=2, so it did not test
	 * the complete vendor raw template. Keep that comparison debug-only.
	 */
	control = zx_tx_w0;
	destination = READ_ONCE(zx_tx_dest);
	if (!destination && raw)
		destination = 0x28 + txport;
	if (destination)
		control = (control & ~(0x3fu << 20)) |
			  ((destination & 0x3f) << 20);
	writel(control, desc);
	writel(zx_tx_w1, desc + 4);
	writel(zx_tx_w2, desc + 8);
	writel(raw ? 3 : zx_tx_w3, desc + 12);
	zx_desc_pack(desc, idx, skb->len);
	/* ROUND 43 REVERTED: the pool-1 descriptor bit is removed with the pool-1
	 * buffer above - the hardware does not honour it on the transmit path.
	 */
	writeb((readb(desc + 11) & 1) | 0x20, desc + 11);
	wmb(); /* Publish payload and descriptor before the enqueue doorbell. */

	if (readl(ze->tmq + TMQ_STATUS) & 3)
		netdev_warn_once(ndev, "TM status error before enqueue\n");
	/* R201 TX-pre-doorbell: skb is linear normal RAM; descriptors and
	 * payload are published. Timestamp before the hardware can transmit.
	 */
	zx_packet_trace_add(skb->data, skb->len, true, txport, -1, slot, idx, 0);
	writel(1, ze->tmq + TMQ_DOORBELL);
	/* ROUND 38: bounded spin on the hardware's own TX consume index, to ask
	 * directly whether the descriptor is picked up promptly or only when
	 * something else (an RX event) happens. Bounded by tx_drain_us (500 by
	 * default) so a frame that is NOT drained promptly is recorded as slow
	 * rather than hanging the transmit path under tx_lock.
	 */
	if (zx_tx_drain_probe && zx_tx_drain_us) {
		u64 bound = (u64)zx_tx_drain_us * NSEC_PER_USEC;
		u32 hw0 = readl(ze->tmq + TMQ_TXIDX) & 0xffff;
		u64 t0 = ktime_get_ns();
		u64 dt = 0;
		bool drained = false;

		do {
			if ((readl(ze->tmq + TMQ_TXIDX) & 0xffff) != hw0) {
				drained = true;
				break;
			}
			dt = ktime_get_ns() - t0;
		} while (dt < bound);

		if (drained) {
			ze->tx_drain_fast++;
			if (dt > ze->tx_drain_ns_max)
				ze->tx_drain_ns_max = dt;
		} else {
			ze->tx_drain_slow++;
		}
		ze->tx_drain_n++;
	}
	txidx_after = readl(ze->tmq + TMQ_TXIDX);
	ze->tx_next = (slot + 1) % RING_ENTRIES;
	ze->tx_outstanding++;
	/* ROUND 68: the R66 back-pressure (tx_pending, netif_stop_queue at
	 * RING_ENTRIES/2, wake at RING_ENTRIES/8, and a stall breaker) is
	 * REVERTED. Two independent reviews found it unsound:
	 *
	 *  - TMQ+0x68 is read-clear, so exactly one consumer may read it, and
	 *    this file had four (here, the DIG dump, the TXDRAIN probe, the
	 *    timer). A 1 Hz /proc read eats an interval's completions for good,
	 *    so the gauge the queue was gated on could be starved by the very
	 *    instrumentation used to watch it - R161's lesson at system level.
	 *  - The stall breaker was bound to `if (c)`, so any spurious credit
	 *    reset its clock; with CONFIG_HZ_100 the 1000-tick threshold was
	 *    10 s, not the ~1 s its comment claimed; and at its worst it set
	 *    tx_pending = 0 while frames were still queued, which CREATES the
	 *    ring-lapping condition rather than preventing it.
	 *
	 * A stopped queue that is never woken is a total transmit failure, and
	 * the back-pressure was a bet on a register this project has retracted
	 * three times. The legitimate observation - that the driver never applies
	 * back-pressure - stands, and is recorded; acting on it needs a
	 * trustworthy consumption signal with a single reader first.
	 */
	ndev->stats.tx_packets++;
	ndev->stats.tx_bytes += len;
	if (ZX_HAVE_DEBUG_IFACES && ze->tx_dbg < zx_tx_dbg_max) {
		ze->tx_dbg++;
		netdev_info(ndev,
			    "txdbg mode=%u slot=%u len=%u buf=%d idx %08x->%08x desc %08x %08x %08x %08x\n",
			    zx_tx_slot_mode, slot, skb->len, idx,
			    txidx_before, txidx_after,
			    readl(desc), readl(desc + 4),
			    readl(desc + 8), readl(desc + 12));
	}
	spin_unlock_irqrestore(&ze->tx_lock, flags);
	dev_kfree_skb_any(skb);
	return NETDEV_TX_OK;

unlock_drop:
	spin_unlock_irqrestore(&ze->tx_lock, flags);
drop:
	ndev->stats.tx_dropped++;
	dev_kfree_skb_any(skb);
	return NETDEV_TX_OK;
}
static bool zx_rx_any_pending(struct zx_eth *ze)
{
	int q;

	for (q = 0; q < ZX_RX_QUEUES; q++)
		if (readl(ze->tmq + TMQ_PENDING + q * 4))
			return true;
	return false;
}

static bool zx_rx_software_pending(struct zx_eth *ze)
{
	int ring;

	for (ring = 0; ring < ZX_RX_RINGS; ring++)
		if (ze->rxq[ring].debt || ze->rxq[ring].remaining)
			return true;
	return false;
}

/* Called only by NAPI. GO completion belongs to the recorded command owner. */
static bool zx_rx_retire(struct zx_eth *ze)
{
	struct zx_rx_queue *q;

	if (ze->rx_inflight < 0)
		return true;
	if (readl(ze->tmd + TMD_GO) & 1)
		return false;
	q = &ze->rxq[ze->rx_inflight];
	q->return_sent = false;
	q->debt = false;
	ze->rx_inflight = -1;
	return true;
}

static bool zx_rx_release(struct zx_eth *ze, unsigned int ring,
			  unsigned int *retries)
{
	struct zx_rx_queue *q = &ze->rxq[ring];

	zx_rx_retire(ze);
	if (!q->debt)
		return true;
	if (q->buffer_pending) {
		/* zx_rx_no_free: skip the return (round 52 test knob). The buffer
		 * is then never offered back to the BM, so the allocator cannot
		 * keep handing the same index to RX and TX.
		 */
		if (!zx_rx_no_free &&
		    !zx_bm_free(ze, q->buffer | (q->pool << 15)))
			return false;
		q->buffer_pending = false;
	}
	if (!q->return_sent) {
		if (ze->rx_inflight >= 0 || (readl(ze->tmd + TMD_GO) & 1))
			return false;
		writel((ring / ZX_RX_QUEUES << 14) | BIT(4) |
		       (q->class << 3) | (ring % ZX_RX_QUEUES),
		       ze->tmd + TMD_PAYLOAD);
		ze->rx_inflight = ring;
		q->return_sent = true;
		writel(1, ze->tmd + TMD_GO);
		ze->n_desc_rls++;
	}
	while (!zx_rx_retire(ze)) {
		if (!*retries) {
			ze->n_desc_busy++;
			return false;
		}
		(*retries)--;
		cpu_relax();
	}
	return !q->debt;
}

/* irq_lock serializes rearming with IRQ entry and the last-port stop. */
static void zx_rx_rearm(struct zx_eth *ze, bool software_pending)
{
	u32 mask;

	if (!ze->running || ze->rx_fault)
		return;
	if (software_pending) {
		napi_schedule(&ze->napi);
		return;
	}
	mask = readl(ze->tmc + TMC_IRQ_MASK);
	writel(mask & ~3U, ze->tmc + TMC_IRQ_MASK);
	/* The counts are nondestructive. Cover an arrival around unmasking. */
	if (zx_rx_any_pending(ze)) {
		writel(mask | 7, ze->tmc + TMC_IRQ_MASK);
		napi_schedule(&ze->napi);
	}
}

static void zx_rx_retry_work(struct work_struct *work)
{
	struct zx_eth *ze = container_of(to_delayed_work(work),
					struct zx_eth, rx_retry);
	unsigned long flags;

	/* Process context: disable BHs so the poll runs at local_bh_enable()
	 * instead of waiting for ksoftirqd to be scheduled.
	 */
	local_bh_disable();
	spin_lock_irqsave(&ze->irq_lock, flags);
	if (ze->running && !ze->rx_fault)
		napi_schedule(&ze->napi);
	spin_unlock_irqrestore(&ze->irq_lock, flags);
	local_bh_enable();
}

static irqreturn_t zx_eth_irq(int irq, void *data)
{
	struct zx_eth *ze = data;
	unsigned long flags;
	u32 mask, status;

	spin_lock_irqsave(&ze->irq_lock, flags);
	mask = readl(ze->tmc + TMC_IRQ_MASK);
	status = readl(ze->tmc + TMC_IRQ_STATUS) & ~mask & 3;
	if (!status) {
		spin_unlock_irqrestore(&ze->irq_lock, flags);
		return IRQ_NONE;
	}
	writel(mask | 7, ze->tmc + TMC_IRQ_MASK);
	if (ze->running && !ze->rx_fault)
		napi_schedule_irqoff(&ze->napi);
	spin_unlock_irqrestore(&ze->irq_lock, flags);
	return IRQ_HANDLED;
}

static struct net_device *zx_rxdev(struct zx_eth *ze, u32 word1)
{
	if (zx_split_ports) {
		int port = zx_rx_port_of(word1);

		if (port >= 0 && ze->ports[port])
			return ze->ports[port];
	}
	return ze->ndev;
}

static void zx_rx_census(struct zx_eth *ze, const u8 *frame, unsigned int len)
{
	const u8 *ip;
	u16 total, fragment;
	unsigned int ihl;

	if (!ZX_HAVE_DEBUG_IFACES || len < ETH_HLEN)
		return;
	if (((frame[12] << 8) | frame[13]) != 0x0800) {
		ze->c_tcp_bare++; /* Historical name: non-IPv4 Ethernet frames. */
		return;
	}
	if (len < ETH_HLEN + 20)
		return;
	ip = frame + ETH_HLEN;
	ihl = (ip[0] & 0xf) * 4;
	total = (ip[2] << 8) | ip[3];
	if ((ip[0] >> 4) != 4 || ihl < 20 || ihl > len - ETH_HLEN ||
	    total < ihl || total > len - ETH_HLEN)
		return;
	switch (ip[9]) {
	case 1:
		ze->c_icmp++;
		fragment = (ip[6] << 8) | ip[7];
		if (!(fragment & 0x3fff) && total >= ihl + 8) {
			if (ip[ihl] == 8)
				ze->c_icmp_req++;
			else if (ip[ihl] == 0)
				ze->c_icmp_rep++;
		}
		break;
	case 17:
		ze->c_udp++;
		break;
	case 6:
		ze->c_tcp_data++;
		break;
	default:
		ze->c_report++;
		break;
	}
}

/* Ask for a full datapath re-initialisation (zx_dp_reset_work()).
 *
 * Safe from any context, including the poll. Returns false, having said so
 * once per stall, when rx_recover is off or the automatic resets are spent -
 * the old behaviour, where the datapath stays stopped until a power cycle.
 * "Spent" lasts only until RX moves again: a stall after any received frame
 * is a new fault and gets the reset budget back.
 */
static bool zx_dp_request_reset(struct zx_eth *ze, const char *why)
{
	bool spent = ze->reset_consec >= ZX_RESET_MAX_CONSEC &&
		     READ_ONCE(ze->n_desc_rls) == ze->reset_rls;

	if (!zx_rx_recover || spent) {
		if (!ze->reset_nagged) {
			ze->reset_nagged = true;
			netdev_err(ze->ndev, "RX datapath stopped (%s); %s\n", why,
				   zx_rx_recover ? "automatic resets exhausted" :
						   "rx_recover=0, leaving it stopped");
		}
		return false;
	}
	WRITE_ONCE(ze->reset_reason, why);
	schedule_delayed_work(&ze->reset_work, 0);
	return true;
}

static int zx_eth_poll(struct napi_struct *napi, int budget)
{
	struct zx_eth *ze = container_of(napi, struct zx_eth, napi);
	unsigned int ring, visited, retries = 64;
	unsigned long flags;
	bool blocked = false, software_pending;
	unsigned int blocked_polls;
	int done = 0;

	if (!budget)
		return 0;
	/* Completion releases NAPI ownership before this callback returns.
	 * Last-port stop waits for this RCU section before releasing resources.
	 */
	rcu_read_lock();
	for (visited = 0; visited < ZX_RX_RINGS && !ze->rx_fault; visited++) {
		struct zx_rx_queue *q;
		u32 pending;
		bool carried;

		ring = ze->rx_next;
		ze->rx_next = (ring + 1) % ZX_RX_RINGS;
		q = &ze->rxq[ring];
		carried = q->debt;
		if (!zx_rx_release(ze, ring, &retries))
			continue;
		if (!q->remaining) {
			/* A return that retired just now, carried over from an
			 * earlier visit, is not known to be reflected in the count
			 * yet: GO clearing is the only completion signal, and
			 * re-reading the count within a microsecond of it could
			 * count that descriptor again - one stale slot consumed,
			 * and a count that later underflows. Refresh on the next
			 * visit instead; rearm reschedules if work is pending.
			 */
			if (carried)
				continue;
			pending = readl(ze->tmq + TMQ_PENDING +
					(ring % ZX_RX_QUEUES) * 4);
			q->remaining = (pending >> (ring / ZX_RX_QUEUES * 16)) & 0xffff;
			if (!q->remaining)
				ze->n_prodzero++;
			if (q->remaining > RING_ENTRIES) {
				/* One bad read is not a lost ring. Read it again
				 * before treating the ring as overrun.
				 */
				ze->n_bad_pending++;
				udelay(1);
				pending = readl(ze->tmq + TMQ_PENDING +
						(ring % ZX_RX_QUEUES) * 4);
				q->remaining = (pending >> (ring / ZX_RX_QUEUES * 16)) & 0xffff;
			}
			if (q->remaining > RING_ENTRIES) {
				/* More descriptors than the ring has slots: the
				 * producer has lapped the consumer and the slots
				 * between them are unrecoverable. Stop RX and ask
				 * for a full re-initialisation.
				 */
				spin_lock_irqsave(&ze->irq_lock, flags);
				ze->rx_fault = true;
				writel(readl(ze->tmc + TMC_IRQ_MASK) | 7,
				       ze->tmc + TMC_IRQ_MASK);
				spin_unlock_irqrestore(&ze->irq_lock, flags);
				netdev_err(ze->ndev, "RX ring %u invalid pending count %u\n",
					   ring, q->remaining);
				q->remaining = 0;
				zx_dp_request_reset(ze, "RX pending count exceeds the ring");
				break;
			}
		}
		while (q->remaining && done < budget) {
			struct net_device *rxdev;
			struct sk_buff *skb = NULL;
			u8 desc[DESC_SIZE];
			u32 idx, len, word1, pool;
			u32 cur = q->cursor;
			bool valid;

			/* The pending count publishes the next descriptor, not its length. */
			rmb();
			memcpy_fromio(desc, ze->ring + ring * ZX_RX_RING_SIZE +
				      q->cursor * DESC_SIZE, sizeof(desc));
			idx = (desc[7] >> 1) | ((u32)desc[8] << 7);
			len = ((desc[12] | ((u32)desc[13] << 8)) >> 2) & 0x3fff;
			pool = desc[9] & 1;
			word1 = desc[4] | (desc[5] << 8) |
				(desc[6] << 16) | ((u32)desc[7] << 24);
			rxdev = zx_rxdev(ze, word1);
			valid = idx < (pool ? BUF2_COUNT : BUF_COUNT);
			/* ROUND 36: make n_zerolen real. An owned slot whose length
			 * decodes to 0 is the signature the red team's mechanism
			 * predicts during a freeze - the poll walking the ring's
			 * consumer region and finding nothing published. Counted
			 * separately from the rx_errors bucket below, which folds
			 * zero length together with short and out-of-range frames
			 * and therefore could never distinguish the cases.
			 */
			if (!len)
				ze->n_zerolen++;
			/* Round 31: see the rx_trace module parameter. Reads the
			 * buffer directly rather than the skb so that invalid
			 * descriptors are traced too - an out-of-range idx is
			 * itself evidence, and it never reaches an skb.
			 */
			if (zx_rx_trace) {
				u32 b42 = 0;

				zx_rx_trace--;
				if (valid && len > 42)
					b42 = readb((pool ? ze->bufs2 : ze->bufs) +
						    (size_t)idx * BUF_SIZE +
						    BUF_HDR + 42);
				pr_info("RXTRACE r=%u cur=%u rem=%u idx=%u pool=%u len=%u valid=%u b42=%02x\n",
					ring, cur, q->remaining, idx, pool,
					len, valid, b42);
			}
			if (!valid || len < ETH_HLEN || len > BUF_SIZE - BUF_HDR) {
				rxdev->stats.rx_errors++;
			} else if (!netif_running(rxdev)) {
				rxdev->stats.rx_dropped++;
			} else {
				/* napi_alloc_skb already reserves NET_IP_ALIGN. */
				skb = napi_alloc_skb(napi, len);
				if (skb) {
					memcpy_fromio(skb_put(skb, len),
						      (pool ? ze->bufs2 : ze->bufs) +
						      idx * BUF_SIZE + BUF_HDR, len);
				} else {
					rxdev->stats.rx_dropped++;
				}
			}
			/* Snapshot debt before handing either resource back. */
			q->buffer = idx;
			q->pool = pool;
			q->class = desc[6] & 1;
			q->buffer_pending = valid;
			q->return_sent = false;
			q->debt = true;
			q->cursor = (q->cursor + 1) % RING_ENTRIES;
			q->remaining--;
			done++;
			mb(); /* Finish descriptor/payload reads before returning ownership. */
			if (skb) {
				u16 proto = ((u8 *)skb->data)[12] << 8 |
					    ((u8 *)skb->data)[13];

				zx_rx_census(ze, skb->data, len);
				/* R201 RX-pre-eth_type_trans: trace the copied skb's
				 * full Ethernet frame before the stack pulls its header.
				 * cur/idx/pool are the already-copied descriptor identity.
				 */
				zx_packet_trace_add(skb->data, skb->len, false,
						    zx_rx_port_of(word1), ring, cur, idx, pool);
				skb->protocol = eth_type_trans(skb, rxdev);
				if (ZX_HAVE_DEBUG_IFACES && proto == 0x0800 &&
				    skb->protocol != cpu_to_be16(0x0800))
					ze->c_proto_mismatch++;
				if (zx_no_gro)
					netif_receive_skb(skb);
				else
					napi_gro_receive(napi, skb);
				rxdev->stats.rx_packets++;
				rxdev->stats.rx_bytes += len;
			}
			if (!zx_rx_release(ze, ring, &retries))
				break;
		}
		if (done == budget)
			goto out;
	}

	/* A later ring may have retired the command that blocked an earlier one. */
	zx_rx_retire(ze);
	blocked = false;
	for (ring = 0; ring < ZX_RX_RINGS; ring++)
		blocked |= ze->rxq[ring].debt;
	/* Count polls that received nothing because a return was refused. */
	if (!blocked || done)
		ze->rx_blocked_polls = 0;
	else if (ze->rx_blocked_polls < UINT_MAX)
		ze->rx_blocked_polls++;
	blocked_polls = ze->rx_blocked_polls;
	software_pending = zx_rx_software_pending(ze);
	/* GRO completion can forward packets into another device's TX path.
	 * Keep IRQs enabled and driver locks released throughout that delivery.
	 */
	if (napi_complete_done(napi, done)) {
		spin_lock_irqsave(&ze->irq_lock, flags);
		if (ze->running && !ze->rx_fault) {
			/* A new poll may already own rxq: use only local snapshots.
			 *
			 * One exception to the unconditional rearm (ROUND 43), for
			 * a return port that has stopped retiring: if every return
			 * has been refused for several polls in a row and nothing
			 * was received, rearming would put NAPI straight back on the
			 * poll list - zx_rx_rearm() reschedules on any software
			 * debt - and pin a CPU in softirq with no progress and no log
			 * line. Wait on the retry work instead, backing off from one
			 * jiffy to HZ/10 with the TM interrupt left masked. The next
			 * poll that moves anything clears the count and rearms; a
			 * return that never retires is the RX watchdog's to reset
			 * (zx_rx_stall_check()). A poll that ran out of `retries`
			 * while frames were flowing has done > 0 and never takes
			 * this branch.
			 */
			if (blocked_polls >= ZX_RX_BLOCKED_POLLS) {
				unsigned int shift = min(blocked_polls -
							 ZX_RX_BLOCKED_POLLS, 4u);

				mod_delayed_work(system_wq, &ze->rx_retry,
						 min_t(unsigned long, 1UL << shift,
						       HZ / 10));
			} else {
				zx_rx_rearm(ze, software_pending);
				if (blocked)
					mod_delayed_work(system_wq, &ze->rx_retry, 1);
			}
		}
		spin_unlock_irqrestore(&ze->irq_lock, flags);
	}
out:
	rcu_read_unlock();
	/* No ze or napi access after the lifetime section. */
	return done;
}

static void zx_eth_adjust_link(struct net_device *ndev);
static int zx_eth_datapath_init(struct zx_eth *ze);

/* Program the station MAC address into the hardware.
 *
 * From the vendor routine at 0x47f2f6c8 (called via 0x47f3031c during U-Boot's
 * network init):
 *   0x923a0078 + port*8 = mac[2]<<24 | mac[3]<<16 | mac[4]<<8 | mac[5]
 *   0x923a007c + port*8 = mac[0]<<8  | mac[1]
 *
 * DISPROVED (round 83): this does nothing. The writes are discarded (the whole
 * pp@92380000 range, which contains 0x923a0078, is read-only to the CPU), and
 * on a boot where receive works perfectly the register still reads zero - so
 * the station MAC is not what arms RX. U-Boot cannot write it either. Kept as a
 * documented negative; it logs the discarded write and changes nothing.
 */
static void zx_eth_set_hw_mac(struct net_device *ndev, int port)
{
	const u8 *m = ndev->dev_addr;
	void __iomem *base = ioremap(zx_ze_of(ndev)->phys[ZX_REG_PONPP], SZ_4K);

	if (!base)
		return;
	writel((m[2] << 24) | (m[3] << 16) | (m[4] << 8) | m[5],
	       base + 0x78 + port * 8);
	writel((m[0] << 8) | m[1], base + 0x7c + port * 8);
	netdev_info(ndev, "hw mac port%d: +%02x=%08x +%02x=%08x\n", port,
		    0x78 + port * 8, readl(base + 0x78 + port * 8),
		    0x7c + port * 8, readl(base + 0x7c + port * 8));
	iounmap(base);
}

/* Resume every PHY on our MDIO bus that we are not attaching.
 *
 * phylib registers all four from the DT and leaves the unattached ones powered
 * down, which takes their ports off the wire entirely - see the comment on
 * zx_phy_keepalive. Clearing BMCR_PDOWN directly is enough to get the port
 * electrically up: the PHY autonegotiates on its own even though no state
 * machine is polling it. We deliberately do NOT phy_start() them, because they
 * are not attached to a netdev and phylib would rightly complain.
 */
static void zx_eth_phys_keepalive(struct zx_eth *ze)
{
	struct device_node *mdio, *child;
	int woken = 0;

	if (!zx_phy_keepalive)
		return;

	mdio = of_find_compatible_node(NULL, NULL, "zte,zx279128s-mdio");
	if (!mdio)
		return;

	for_each_available_child_of_node(mdio, child) {
		struct phy_device *pd = of_phy_find_device(child);

		if (!pd)
			continue;
		/* Skip any PHY phylib has attached to a netdev - it owns their
		 * power state. Since each port netdev drives its own PHY this
		 * normally skips all four and the helper does nothing, which is
		 * the intended end state; it stays for device trees that
		 * describe fewer ports than the four the SoC has.
		 */
		if (pd != ze->phy && !pd->attached_dev) {
			int old = phy_read(pd, MII_BMCR);

			if (old >= 0 && (old & BMCR_PDOWN)) {
				phy_modify(pd, MII_BMCR, BMCR_PDOWN, 0);
				woken++;
			}
		}
		put_device(&pd->mdio.dev);
	}
	of_node_put(mdio);

	if (woken)
		netdev_info(ze->ndev, "phy_keepalive: powered up %d unattached PHY(s)\n",
			    woken);
}

/* ZX_RX_SEED_R202_DECL_BEGIN */
static int zx_rx_seed_start(struct zx_eth *ze);
/* ZX_RX_SEED_R202_DECL_END */

enum zx_wd_verdict { ZX_WD_OK, ZX_WD_KICK, ZX_WD_RESET };

/* One watchdog period (one second) of RX stall detection.
 *
 * A stall is "the hardware counts descriptors pending and the driver has not
 * issued a single return since the previous period". Nothing else can hold the
 * return counter still while work is pending: every consumed descriptor is
 * returned (invalid ones included), so a flat counter means the consumer is
 * stopped - a return that never retires, a free the BM keeps refusing, or a
 * NAPI instance nobody schedules. An idle link has nothing pending and never
 * counts. Only the non-destructive pending registers and the driver's own
 * counter are read.
 */
static enum zx_wd_verdict zx_rx_stall_check(struct zx_eth *ze)
{
	unsigned long rls = READ_ONCE(ze->n_desc_rls);

	if (READ_ONCE(ze->rx_fault))
		return ZX_WD_RESET;
	if (rls != ze->wd_rls || !zx_rx_any_pending(ze)) {
		ze->wd_rls = rls;
		ze->wd_stuck = 0;
		ze->reset_nagged = false;
		return ZX_WD_OK;
	}
	ze->wd_stuck++;
	if (zx_rx_stall_ms &&
	    ze->wd_stuck >= DIV_ROUND_UP(zx_rx_stall_ms, MSEC_PER_SEC))
		return ZX_WD_RESET;
	return ZX_WD_KICK;
}

static void zx_wd_work(struct work_struct *work)
{
	struct zx_eth *ze = container_of(to_delayed_work(work), struct zx_eth,
					 wd_work);
	unsigned long flags;

	if (!READ_ONCE(ze->running))
		return;
	switch (zx_rx_stall_check(ze)) {
	case ZX_WD_KICK:
		/* First step: a NAPI instance nobody scheduled. */
		ze->n_wd_kicks++;
		local_bh_disable();
		spin_lock_irqsave(&ze->irq_lock, flags);
		if (ze->running && !ze->rx_fault)
			napi_schedule(&ze->napi);
		spin_unlock_irqrestore(&ze->irq_lock, flags);
		local_bh_enable();
		break;
	case ZX_WD_RESET:
		if (zx_dp_request_reset(ze, READ_ONCE(ze->rx_fault) ?
					"RX pending count exceeds the ring" :
					"RX descriptors pending with no return issued"))
			return;	/* the reopen restarts the watchdog */
		break;
	default:
		break;
	}
	schedule_delayed_work(&ze->wd_work, HZ);
}

/* Cursors, cached counts and release debt survive ordinary interface closes. */
static int zx_dp_start(struct zx_eth *ze)
{
	unsigned long flags;
	bool software_pending;

	if (ze->removing)
		return -ENODEV;
	if (READ_ONCE(ze->rx_fault))
		return -EIO;
	/* ZX_RX_SEED_R202_START_BEGIN */
	{
		int ret = zx_rx_seed_start(ze);

		if (ret)
			return ret;
	}
	/* ZX_RX_SEED_R202_START_END */
	if (ze->dp_users++)
		return 0;
	software_pending = zx_rx_software_pending(ze);
	napi_enable(&ze->napi);
	spin_lock_irqsave(&ze->irq_lock, flags);
	ze->running = true;
	zx_rx_rearm(ze, software_pending);
	spin_unlock_irqrestore(&ze->irq_lock, flags);
	ze->wd_rls = READ_ONCE(ze->n_desc_rls);
	ze->wd_stuck = 0;
	schedule_delayed_work(&ze->wd_work, HZ);
	return 0;
}

static void zx_dp_stop(struct zx_eth *ze)
{
	unsigned long flags;

	if (!ze->dp_users || --ze->dp_users)
		return;
	spin_lock_irqsave(&ze->irq_lock, flags);
	ze->running = false;
	writel(readl(ze->tmc + TMC_IRQ_MASK) | 7, ze->tmc + TMC_IRQ_MASK);
	spin_unlock_irqrestore(&ze->irq_lock, flags);
	synchronize_irq(ze->irq);
	napi_disable(&ze->napi);
	cancel_delayed_work_sync(&ze->rx_retry);
	/* The watchdog never takes RTNL, so this cannot deadlock against a
	 * close issued under it - including the reset work's own closes.
	 */
	cancel_delayed_work_sync(&ze->wd_work);
	/* napi_disable may finish before a completed poll's rearm tail. */
	synchronize_net();
}

static int zx_eth_open(struct net_device *ndev)
{
	struct zx_eth *ze = netdev_priv(ndev);
	int ret;

	zx_mac_snapshot_log(ndev, "open-pre");
	ret = zx_dp_start(ze);
	if (ret)
		return ret;

	/* MAC+0x00 bit0 is a MODE bit, not an enable. Measured A/B on port 0:
	 *   bit0=0 -> frames egress to the wire; nothing reaches the CPU
	 *   bit0=1 -> CPU receives wire traffic (verified 25/25 frames), but
	 *             our transmits no longer appear on the wire
	 * Port 4 (0x92300000) reads all-zero, so it is not a separate CPU port.
	 * Since the wire->CPU direction works in mode 1, the port is not
	 * detached; our TX descriptor most likely needs a destination-port
	 * field (the constant control words 0x200001ca / 0x20008000) that
	 * currently still says "to CPU". Keep mode 1 so RX works while that is
	 * decoded.
	 */
/* CPU mode must be set on port 0 - the only port with real register
	 * content (0x00bb6002). Ports 1 and 4 both read 0x00000000, i.e. they
	 * are unconfigured, so neither can serve as a separate CPU port.
	 */
	if (ze->mac) {
		u32 v = readl(ze->mac + MAC_CTRL);

		/* MAC+0x00 bit0 is a MODE bit, not a plain enable.
		 *
		 * The A/B recorded in the comment above was measured on port 0:
		 *   bit0=0 -> frames egress to the wire; nothing reaches the CPU
		 *   bit0=1 -> CPU receives wire traffic, but our transmits no
		 *             longer appear on the wire
		 * and this driver has always forced bit0=1 so that RX works at all.
		 *
		 * Round 8 reading of the same evidence: if bit0 really is a
		 * CPU-vs-wire selector, then forcing it on is *exactly* why every
		 * transmit disappears, and no amount of descriptor, slot, doorbell
		 * or destination work could ever have fixed TX - which is precisely
		 * what rounds 3-7 found, six arms at a time.
		 *
		 * Made runtime-selectable so the two halves can be measured
		 * separately instead of assumed: 1 keeps today's behaviour (RX), 0
		 * is the wire mode that this project's own note says egresses.
		 */
		if (zx_cpu_mode)
			writel(v | MAC_CTRL_EN, ze->mac + MAC_CTRL);
		else
			writel(v & ~MAC_CTRL_EN, ze->mac + MAC_CTRL);
		netdev_info(ndev, "port mode: MAC+0x00 %08x -> %08x (cpu_mode=%d)\n",
			    v, readl(ze->mac + MAC_CTRL), zx_cpu_mode);
	}

	/* Every other port too - this is what makes them ingress at all.
	 * Skipped in wire mode: the point of that mode is to leave the MACs the
	 * way the bootloader had them, so setting the CPU bit on the other three
	 * would reintroduce exactly what is being tested.
	 */
	/* ROUND 83: the `!zx_split_ports` term is REMOVED.
	 *
	 * It made this whole block conditional on a mode that is OFF by
	 * default - `split_ports` ships true ("one netdev per physical port") -
	 * so with the shipping defaults the driver enabled NO port's MAC. Only
	 * the bootloader's port worked, because the warm path preserves what
	 * U-Boot configured, and three of the four ports have therefore never
	 * been functional in any build of this driver.
	 *
	 * The block's own comment states its purpose plainly: "Every other port
	 * too - this is what makes them ingress at all." That is a requirement
	 * of the hardware, not of the netdev topology, so it must not depend on
	 * how many netdevs are registered.
	 */
	if (zx_all_ports && zx_cpu_mode) {
		int p;

		for (p = 0; p < ZX_NPORTS; p++) {
			u32 v;

			if (!ze->macs[p] || ze->macs[p] == ze->mac)
				continue;
			v = readl(ze->macs[p] + MAC_CTRL);
			if (v & MAC_CTRL_EN)
				continue;
			writel(v | MAC_CTRL_EN, ze->macs[p] + MAC_CTRL);
			netdev_info(ndev, "port %d enabled: MAC+0x00 %08x -> %08x\n",
				    p, v, readl(ze->macs[p] + MAC_CTRL));
		}
	}

	/* PP steering was already enabled by the bootloader (+0xcc reads 1 and
	 * +0x80 ignores writes), so it is not the missing piece. Instead scan
	 * the TM window for whatever register reacts to incoming traffic.
	 */
	ze->snap_valid = false;
	ze->next_scan = jiffies + msecs_to_jiffies(2000);

	/* NOTE: the vendor queue/pool config (0x47f30528: queue enables at
	 * 0x921d428c and pool base/size at 0x921d4000 +0x000/+0x004/+0x040/
	 * +0x044/+0x1c0) was tried here and is also a no-op - the registers
	 * already read 0x30000000 / 0x8800 / 0x11000000 before we write them.
	 */
	/* NOTE: the vendor NPP enable (0x47f308c4: all-ones to 0x921c0000+0x08
	 * and +0x0c) was tried here and is a no-op - those registers read back
	 * unchanged (+0x0c = 0x0003ffff before and after), i.e. the bootloader
	 * has already enabled the packet processor.
	 */
	if (ze->phy_np && !ze->phy) {
		ze->phy = of_phy_connect(ndev, ze->phy_np, zx_eth_adjust_link,
					 0, ze->phy_mode);
		if (!ze->phy)
			netdev_warn(ndev, "could not attach to PHY\n");
	}

	if (ze->phy)
		phy_start(ze->phy);

	/* After the attach, so ze->phy is set and gets skipped. */
	zx_eth_phys_keepalive(ze);

	netif_start_queue(ndev);

	/* NOTE: a full non-zero register dump of BM/TMC/TMQ/QP/MAC was tried
	 * here for host-side diffing. It emits ~240 pr_info lines in a burst,
	 * which console rate-limiting silently drops (the flash boot logged
	 * none at all while the TFTP boot logged 243), so it is not a reliable
	 * comparison method. Use the compact digest below instead.
	 */
	/* Register digest, for diffing a working TFTP boot against a flash
	 * boot. Same registers, same point in the sequence.
	 */
	if (ze->mac)
		netdev_info(ndev, "DIG mac %08x %08x %08x %08x %08x %08x %08x\n",
			    readl(ze->mac + 0x00), readl(ze->mac + 0x70),
			    readl(ze->mac + 0xb4), readl(ze->mac + 0xe0),
			    readl(ze->mac + 0xb00), readl(ze->mac + 0xd00),
			    readl(ze->mac + 0xd30));
	netdev_info(ndev, "DIG bm  %08x %08x %08x %08x\n",
		    readl(ze->bm + 0x00), readl(ze->bm + 0x0c),
		    readl(ze->bm + 0x14), readl(ze->bm + 0xdc));
	netdev_info(ndev, "DIG tmc %08x %08x %08x %08x %08x %08x\n",
		    readl(ze->tmc + 0x04), readl(ze->tmc + 0xe8),
		    readl(ze->tmc + 0xec), readl(ze->tmc + 0xf0),
		    readl(ze->tmc + 0xf4), readl(ze->tmc + 0xf8));
	netdev_info(ndev, "DIG tmq %08x %08x %08x %08x %08x %08x %08x\n",
		    readl(ze->tmq + 0x50), readl(ze->tmq + 0x60),
		    readl(ze->tmq + 0x64), readl(ze->tmq + 0x68),
		    readl(ze->tmq + 0x6c), readl(ze->tmq + 0x11c),
		    readl(ze->tmq + 0x1fc));

	zx_eth_set_hw_mac(ndev, 0);

	return 0;
}

static int zx_eth_stop(struct net_device *ndev)
{
	struct zx_eth *ze = netdev_priv(ndev);

	netif_stop_queue(ndev);
	if (ze->phy) {
		phy_stop(ze->phy);
		phy_disconnect(ze->phy);
		ze->phy = NULL;
	}
	zx_mac_enable(ze, ze->bound_port, false);
	zx_dp_stop(ze);
	return 0;
}

/* A per-port netdev.
 *
 * It shares the datapath - one RX ring, one NAPI, one transmit path, because
 * the fabric picks the egress port by destination MAC - but it owns its own
 * MAC window and its own PHY. Owning the PHY is what makes carrier, speed and
 * duplex real per port: before this, phylib registered all four PHYs and
 * phy_start()ed only the DT-bound one, so the other three stayed powered down
 * and a cabled jack reported "Link is Down" for no better reason than that.
 */
static int zx_port_open(struct net_device *ndev)
{
	struct zx_port_priv *pp = netdev_priv(ndev);
	struct zx_eth *ze = pp->ze;
	int ret;

	zx_mac_snapshot_log(ndev, "open-pre");
	ret = zx_dp_start(ze);
	if (ret)
		return ret;
	/* Ingress gate for THIS port. */
	zx_mac_enable(ze, pp->port, true);

	if (pp->phy_np && !ndev->phydev) {
		struct phy_device *phy;

		phy = of_phy_connect(ndev, pp->phy_np, zx_eth_adjust_link, 0,
				     ze->phy_modes[pp->port]);
		if (!phy)
			netdev_warn(ndev, "could not attach to PHY\n");
	}

	if (ndev->phydev)
		phy_start(ndev->phydev);
	netif_start_queue(ndev);
	return 0;
}

static int zx_port_stop(struct net_device *ndev)
{
	struct zx_port_priv *pp = netdev_priv(ndev);

	netif_stop_queue(ndev);
	if (ndev->phydev) {
		phy_stop(ndev->phydev);
		phy_disconnect(ndev->phydev);
	}
	zx_mac_enable(pp->ze, pp->port, false);
	zx_dp_stop(pp->ze);
	return 0;
}

static const struct net_device_ops zx_port_netdev_ops = {
	.ndo_open = zx_port_open,
	.ndo_stop = zx_port_stop,
	.ndo_start_xmit = zx_eth_xmit,
	.ndo_set_mac_address = eth_mac_addr,
	.ndo_validate_addr = eth_validate_addr,
};

static void zx_phy_node_put(void *node)
{
	of_node_put(node);
}

static int zx_eth_prepare_port_ndev(struct zx_eth *ze, int port)
{
	struct net_device *ndev;
	struct zx_port_priv *pp;
	struct device_node *np;
	int ret;

	ndev = devm_alloc_etherdev(ze->dev, sizeof(*pp));
	if (!ndev)
		return -ENOMEM;

	SET_NETDEV_DEV(ndev, ze->dev);
	pp = netdev_priv(ndev);
	pp->ze = ze;
	pp->port = port;
	ndev->netdev_ops = &zx_port_netdev_ops;

	np = zx_port_node(ze->dev, port);
	pp->phy_np = np ? of_parse_phandle(np, "phy-handle", 0) : NULL;
	zx_set_mac_from_dt(ze, ndev, np, port);
	of_node_put(np);
	ret = devm_add_action_or_reset(ze->dev, zx_phy_node_put, pp->phy_np);
	if (ret)
		return ret;

	/* Name by PHYSICAL port index, not by whatever `eth%d` happens to be
	 * free. eth0..eth3 then always mean mac0..mac3, which is what board.d
	 * and the jack labels refer to, and it stays true no matter which port
	 * the device tree binds as primary.
	 */
	snprintf(ndev->name, IFNAMSIZ, "eth%d", port);

	ze->ports[port] = ndev;
	return 0;
}

static int zx_eth_add_port_ndev(struct zx_eth *ze, int port)
{
	struct net_device *ndev = ze->ports[port];
	int ret;

	ret = devm_register_netdev(ze->dev, ndev);
	if (ret)
		return ret;

	dev_info(ze->dev, "port %d -> %s (descriptor id %d) %pM\n",
		 port, ndev->name, port + 1, ndev->dev_addr);
	return 0;
}

static const struct net_device_ops zx_eth_netdev_ops = {
	.ndo_open = zx_eth_open,
	.ndo_stop = zx_eth_stop,
	.ndo_start_xmit = zx_eth_xmit,
	.ndo_set_mac_address = eth_mac_addr,
	.ndo_validate_addr = eth_validate_addr,
};

/* Program the MAC for the negotiated speed/duplex.
 *
 * Decoded from the vendor's link-change path (0x47f30578 / 0x47f305c4), which
 * runs whenever the PHY reports a new mode:
 *   1000M : MAC+0x00 &= ~0x8000, |= 0x2000
 *   else  : half -> &= ~0x2000, |= 0x8000 ; full -> |= 0xa000
 *           100M -> |= 0x4000 ; else &= ~0x4000
 *   then  : MAC+0x00 |= 3   (enable)
 * Previously this callback only printed the link state, so the MAC kept
 * whatever mode the bootloader left - fine after a TFTP boot, wrong otherwise.
 */
static void zx_eth_adjust_link(struct net_device *ndev)
{
	struct zx_eth *ze = zx_ze_of(ndev);
	struct phy_device *phy = ndev->phydev;
	void __iomem *mac;
	int port = zx_port_index_of(ndev);
	u32 v;

	/* Each port netdev drives its own PHY, so the speed/duplex programming
	 * must land in that port's MAC window. Using ze->mac here would have
	 * programmed the DT-bound port from every port's link event.
	 */
	mac = (port >= 0 && port < ZX_NPORTS && ze->macs[port]) ? ze->macs[port]
								: ze->mac;

	if (!phy || !mac)
		return;

	if (phy->link) {
		zx_mac_snapshot_log(ndev, "link-pre");
		v = readl(mac + MAC_CTRL);
		if (phy->speed == SPEED_1000) {
			/* ROUND 75: clear bit14 (0x4000) as well as bit15.
			 *
			 * From the vendor U-Boot (F610GV9, the ungated smac_init at
			 * 0x47f358b4 writing this exact window, and
			 * smac_set_speed_duplex at 0x47f33120):
			 *
			 *     bit13 = full duplex
			 *     bit14 = 100 M
			 *     bit15 = 1 for 10/100 M, 0 for 1000 M
			 *
			 * The inherited word on this board is 0x00bb6002/0x00bb6003,
			 * which already carries bit14 SET - i.e. "100 M". This branch
			 * cleared bit15 but never bit14, so on a 1 Gbps link the word
			 * ended up with bit13 (full duplex), bit14 (100 M) AND bit15
			 * clear (1000 M) all at once: two contradictory speed fields
			 * in the same register.
			 *
			 * The vendor's own sequence clears bit14 explicitly for the
			 * non-100M case (`bicne r3, r3, #0x4000` @0x47f33160), which
			 * is what this line restores.
			 *
			 * Why this is a plausible cause of the defect: a 1000M PHY
			 * talking to a MAC configured for 100M is exactly the kind of
			 * mismatch that loses frames while every counter stays clean -
			 * the driver enqueues, the link carries what it can, and no
			 * layer records a drop. It is also consistent with the loss
			 * being bimodal (R170) rather than a fixed fraction.
			 */
			v &= ~(0x8000 | 0x4000);
			v |= 0x2000;
		} else {
			if (phy->duplex == DUPLEX_FULL)
				v |= 0xa000;
			else
				v = (v & ~0x2000) | 0x8000;
			if (phy->speed == SPEED_100)
				v |= 0x4000;
			else
				v &= ~0x4000;
		}
		writel(v, mac + MAC_CTRL);
		writel(readl(mac + MAC_CTRL) | 3, mac + MAC_CTRL);
		zx_mac_snapshot_log(ndev, "link-post");

		/* PLACEHOLDER-ATTACH */
	/* Re-assert the port attach mask now that the link is actually
		 * up.
		 *
		 * The vendor's per-port init sets this bit *conditionally on
		 * PHY link status* (0x47f305e4 reads reg 26 first), and U-Boot
		 * runs eth_init only once the link is established. Our
		 * datapath init runs at probe, ~8 s into boot, while the PHY is
		 * still negotiating - so the attach may be latched at the wrong
		 * moment. Re-apply it here, on the link-up transition, matching
		 * the vendor's ordering.
		 */
		/* Disabled: eth_init changes no registers at 0x921d9000. */
	}

	phy_print_status(phy);
}

/* Full datapath bring-up.
 *
 * The bootloader only initialises Ethernet when it actually uses it (a TFTP
 * transfer). On a plain flash boot nothing is configured - MAC+0x00 reads 0 and
 * there is no link - so the driver must do it. Values are the vendor's, taken
 * from U-Boot's eth_init chain and previously verified by observing them
 * already in place after a TFTP boot.
 */
/* Bisection mask: which init steps run. Edit and rebuild to isolate the step
 * that disturbs a working datapath (see docs/ETHERNET.md round 48).
 */
#define ZXI_RESET	BIT(0)
#define ZXI_GLOBAL	BIT(1)
#define ZXI_NPP		BIT(2)
#define ZXI_QCFG	BIT(3)
#define ZXI_FREELIST	BIT(4)
#define ZXI_BMREGS	BIT(5)
#define ZXI_BMFILL	BIT(6)
#define ZXI_RINGS	BIT(7)
#define ZXI_QTABLE	BIT(8)
#define ZXI_MACREGS	BIT(9)

/* everything except the BM index fill */
/* Everything EXCEPT the reset.
 *
 * Bisected on a working TFTP boot (round 49):
 *   MAC + GLOBAL          -> 0% packet loss
 *   MAC + GLOBAL + RESET  -> 100% loss
 * so writing 0x92000008 tears down a datapath that the rest of this init
 * cannot rebuild. (Round 48 had inferred the opposite from a test that left
 * every other step enabled - confounded.)
 */
/* All steps, INCLUDING the reset.
 *
 * Round 49 bisected the reset as "destructive" and removed it - but that
 * bisection forced our init to run on a TFTP boot, i.e. on a datapath the
 * bootloader had already brought up and was actively using. Resetting a live
 * datapath is obviously harmful; that says nothing about a cold boot, which is
 * the only case where this init actually runs.
 *
 * Round 70 showed the packet processor does not even accept writes from cold
 * (PP+0x00 stays 0), i.e. those blocks are held in reset. Releasing them is
 * exactly what 0x92000008 does in the vendor's eth_init.
 */
/* Which datapath_init stages run. Was a hard-coded 0x3ff.
 *
 * Made a parameter to test one specific thing: the vendor NEVER writes BM+0x10
 * (ZXI_BMFILL) - its pool is fed purely by the DDR free-list tables - and this
 * driver's own note observes that because we DO write it, "our tables are never
 * consumed, matching BM+0xdc never gaining its pool-loaded bits". Those
 * pool-loaded bits are now measured: the vendor's BM_FREECNT carries 0x5 in the
 * top nibble on a working datapath and ours carries 0x0.
 *
 * Combined with /proc/zx_eth_reinit this can be re-run at runtime with a stage
 * masked out, so "vendor order without the fill" is finally testable without a
 * rebuild per arm. Round 70 tried it but lost the fill and the ordering change
 * together, so neither was isolated.
 */
static unsigned int zx_init_mask = 0x3ff & ~ZXI_BMFILL;
#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
module_param_named(init_mask, zx_init_mask, uint, 0644);
MODULE_PARM_DESC(init_mask, "datapath_init stage mask (default excludes duplicate BM fill)");
#endif

#define ZXI_MASK	zx_init_mask

static bool zx_skip_reset;	/* bisection knob */

/* Verify the known control gates, without claiming an undocumented DMA drain. */
static int zx_eth_quiesce_init(struct zx_eth *ze)
{
	int i;

	if (!ze->tmc || !ze->bm)
		return -EINVAL;
	for (i = 0; i < ZX_NPORTS; i++)
		if (!ze->macs[i])
			return -EINVAL;

	for (i = 0; i < ZX_NPORTS; i++)
		writel(readl(ze->macs[i] + MAC_CTRL) & ~MAC_CTRL_EN,
		       ze->macs[i] + MAC_CTRL);
	writel(0xffffffff, ze->tmc + TMC_IRQ_MASK);
	writel(0, ze->bm + BM_ENABLE);

	for (i = 0; i < ZX_NPORTS; i++)
		if (readl(ze->macs[i] + MAC_CTRL) & MAC_CTRL_EN)
			return -EIO;
	if ((readl(ze->tmc + TMC_IRQ_MASK) & 7) != 7 ||
	    (readl(ze->bm + BM_ENABLE) & 1))
		return -EIO;
	return 0;
}

static int zx_tm_queue_state_init(struct zx_eth *ze)
{
	u32 value;
	int ret;

	/* Vendor tm_pon_tm_init issues both commands before its 1 ms wait.
	 * Fabric reset alone retains RED queue occupancy from the bootloader.
	 */
	writel(0x1fff, ze->tmc + 0x128);
	writel(0x1fffff, ze->tmc + 0x130);
	usleep_range(1000, 2000);
	ret = readl_poll_timeout(ze->tmc + 0x128, value,
				 !(value & 0x1fff), 1, 20000);
	if (ret) {
		dev_err(ze->dev, "TM state init +0x128 timed out: %08x\n", value);
		return ret;
	}
	ret = readl_poll_timeout(ze->tmc + 0x130, value,
				 !(value & 0x1fffff), 1, 20000);
	if (ret)
		dev_err(ze->dev, "TM state init +0x130 timed out: %08x\n", value);
	return ret;
}

/* Vendor BRG RAM type 4: VLAN valid bit and eight two-bit port modes. */
static int zx_pp_seed_vlans(void __iomem *brg, unsigned int count)
{
	u32 status, data[3], actual[3];
	unsigned int vid;
	int ret;

	if (!count || count > 4096)
		return -EINVAL;
	for (vid = 0; vid < count; vid++) {
		ret = readl_poll_timeout(brg + 0x18, status, status & 1, 1, 1000);
		if (ret)
			return ret;
		writel(BIT(27) | (4 << 22) | vid, brg + 0x14);
		ret = readl_poll_timeout(brg + 0x18, status, status & 1, 1, 1000);
		if (ret)
			return ret;
		data[2] = readl(brg + 0x24);
		data[1] = readl(brg + 0x20);
		data[0] = readl(brg + 0x1c) | GENMASK(16, 0);
		writel((4 << 22) | vid, brg + 0x14);
		ret = readl_poll_timeout(brg + 0x18, status, status & 1, 1, 1000);
		if (ret)
			return ret;
		writel(data[2], brg + 0x24);
		writel(data[1], brg + 0x20);
		writel(data[0], brg + 0x1c);
		ret = readl_poll_timeout(brg + 0x18, status, status & 1, 1, 1000);
		if (ret)
			return ret;
		writel(BIT(27) | (4 << 22) | vid, brg + 0x14);
		ret = readl_poll_timeout(brg + 0x18, status, status & 1, 1, 1000);
		if (ret)
			return ret;
		actual[2] = readl(brg + 0x24);
		actual[1] = readl(brg + 0x20);
		actual[0] = readl(brg + 0x1c);
		if (actual[0] != data[0] || actual[1] != data[1] ||
		    actual[2] != data[2])
			return -EIO;
	}
	return 0;
}

static int zx_eth_datapath_init(struct zx_eth *ze)
{
	void __iomem *rst, *glb, *q, *npp, *misc;
	static const int qmap[8] = { 0, 1, 2, 3, 4, -1, 5, 6 };
	int i, ret;

	ret = zx_eth_quiesce_init(ze);
	if (ret)
		return ret;
	rst = ioremap(ze->phys[ZX_REG_FABRIC], SZ_4K);
	glb = ioremap(ze->phys[ZX_REG_GLB], SZ_4K);
	q = ioremap(ze->phys[ZX_REG_NPP] + ZX_NPP_SPA, SZ_4K);
	npp = ioremap(ze->phys[ZX_REG_NPP], SZ_128K);
	misc = ioremap(ze->phys[ZX_REG_PONPP], SZ_4K);

	if (!rst || !glb || !q || !npp || !misc) {
		if (rst)
			iounmap(rst);
		if (glb)
			iounmap(glb);
		if (q)
			iounmap(q);
		if (npp)
			iounmap(npp);
		if (misc)
			iounmap(misc);
		return -ENOMEM;
	}

	if (rst && (ZXI_MASK & ZXI_RESET) && !zx_skip_reset) {	/* 0x47f2f770 */
		/* The vendor's delay here is mdelay(10), not udelay(10):
		 * 0x47f25380 loops udelay(1000) r0 times. Using microseconds
		 * gave the reset 1000x too little time to propagate, which is
		 * consistent with the whole datapath island still rejecting
		 * register writes afterwards.
		 */
		writel(0, rst + 0x08);
		msleep(100);
		writel(0xffffffff, rst + 0x08);
		mdelay(10);
		iounmap(rst);
	} else if (rst) {
		iounmap(rst);
	}
	/* Reset may restore gates; verify them again before rebuilding tables. */
	ret = zx_eth_quiesce_init(ze);
	if (ret) {
		iounmap(glb);
		iounmap(q);
		iounmap(npp);
		iounmap(misc);
		return ret;
	}
	ze->alloc_pending = false;
	ze->free_credit = 0;
	if (glb && (ZXI_MASK & ZXI_GLOBAL)) {	/* 0x47f2f7a8 */
		writel(readl(glb + 0x18) & ~3u, glb + 0x18);
		writel(15, glb + 0x1c);
		writel(0xffffff7f, glb + 0x44);
		mdelay(20);		/* vendor: mdelay(20), not udelay */
	}
	iounmap(glb);
	/* NPP bring-up (0x47f308c4), now complete.
	 *
	 * Round 81 disabled this because a readback diff showed "0 registers
	 * changed" at 0x921c0000. That was wrong twice over: the diff cannot see
	 * write-only registers, and U-Boot demonstrably references this block.
	 * The full vendor sequence is:
	 *   NPP+0x08 = 0xffffffff ; mdelay(1)
	 *   NPP+0x0c = 0xffffffff ; mdelay(1)
	 *   <queue config at 0x921d4000>
	 *   for port 0..3: NPP+0x60+port*4 &= ~0x3800000   (0x47f30854)
	 *   [0x921cc000] = 17                              (0x47f308b0)
	 *   NPP+0x48 = 0
	 *
	 * 0x921cc000 is the NPP node's SECOND register range
	 * (reg = <0x921c0000 0x8000 0x921cc000 0x34000>) and had never been
	 * written by this driver at all.
	 */
	if (npp) {
		int port;

		writel(0x00ffffff, npp + 0x08);
		mdelay(1);
		writel(0x000fffff, npp + 0x0c);
		mdelay(1);

		/* Round 161: the per-port mask is now tunable.
		 *
		 * Round 160 proved the fault is a CLASSIFIER: a TCP segment with
		 * zero payload is delivered, one with a single byte is not, and
		 * checksum validity is irrelevant. Nothing about buffers or
		 * rates can do that. These bits (23..25 of an NPP per-port
		 * register) are the only per-port classification-shaped field
		 * this driver touches, and they were being cleared on the basis
		 * of a vendor trace, never tested.
		 */
		for (port = 0; port < 4; port++) {
			u32 v = readl(npp + 0x60 + port * 4);

			if (port == 0)
				pr_info("zx-eth: npp[0x%02x] before=%08x mask=%08x\n",
					0x60 + port * 4, v, zx_npp_port_mask);
			writel(v & ~zx_npp_port_mask, npp + 0x60 + port * 4);
		}

		writel(17, npp + 0xc000);

		writel(0, npp + 0x48);
		writel(0xffffffff, npp + 0x04);
		writel(0x0b, npp + 0x10000);
		writel(0x0b, npp + 0x10004);
		writel(0x3810, npp + 0x10010);
		writel(readl(npp + 0x40) | 0x300, npp + 0x40);
		writel(0x80, npp + 0x10008);
		writel(readl(npp + 0x18000) | 8, npp + 0x18000);
		iounmap(npp);
		pr_info("zx-eth: npp bring-up done\n");
	}
	/* KEPT: 0x921d4000 has never been diffed across eth_init (round 76
	 * diffed 0x92344000, a different block), so there is no evidence this
	 * is redundant. Disabling it was unjustified.
	 */
	if (q && (ZXI_MASK & ZXI_QCFG)) {	/* 0x47f30528 */
		for (i = 0; i < 8; i++)
			if (qmap[i] >= 0)
				writel(1, q + 0x28c + qmap[i] * 4);
		writel(0x30000000, q + 0x000);
		writel(0x00008800, q + 0x004);
		writel(0x30000000, q + 0x040);
		writel(0x00008800, q + 0x044);
		writel(SPA_CPU_PROTOCOLS, q + SPA_TRAP_PROTOCOLS);
	}
	iounmap(q);
	if (misc) {		/* 0x923a0000 is inside the PP range and ignores writes */
		iounmap(misc);
	}
	ret = zx_tm_queue_state_init(ze);
	if (ret)
		return ret;

	/* NOTE: the working datapath carries ~80 extra TMQ registers
	 * (TMQ+0x240..0x33c: DDR pointers such as 0x41c03100 / 0x41a03000, plus
	 * per-queue counts). Replaying all of them verbatim was tried and did
	 * NOT enable RX, which indicates they are hardware-maintained runtime
	 * state rather than configuration - do not hard-code them.
	 */

	/* Vendor ordering, WITH the BM+0x10 fill retained.
	 *
	 * U-Boot never writes BM+0x10 (it is absent from the eth_init diff) yet
	 * its pool works - it is fed purely by the DDR free-list tables. We
	 * need the explicit fill, which means our tables are never consumed,
	 * matching BM+0xdc never gaining its pool-loaded bits.
	 *
	 * Round 70 tried vendor ordering but at the same time lost the fill, so
	 * "vendor order + fill" has never actually been tested. Order here is
	 * the vendor's: BM config -> free lists -> TMC pointers -> BM enable.
	 */
	if (ze->bm && (ZXI_MASK & ZXI_BMREGS)) {
		writel(0, ze->bm + 0x00);
		writel(0x0104c040, ze->bm + 0x04);
		writel(0x0104c040, ze->bm + 0x08);
		writel(63, ze->bm + 0x58);	/* reads back 0x40 */
		writel(15, ze->bm + 0x5c);	/* reads back 0x10 */

	}

	/* Populate the buffer pool the way the vendor does.
	 *
	 * The pool is NOT filled by writing indices to BM+0x10. The bootloader
	 * builds free-list TABLES in DDR (0x47f2f800):
	 *   0x41800000: 2048 entries, big-endian u16, values 0..2047
	 *   0x41808000:  512 entries, big-endian u16, values 0..511
	 * and points TMC+0xe8 / TMC+0xec at them. Without the tables the
	 * hardware has no free buffers, which is why RX stayed dead on a flash
	 * boot while TX (which allocates explicitly) worked.
	 */
	{
		void __iomem *fl1 = ioremap_wc(ze->ddr_phys + ZX_DDR_FREELIST, SZ_8K);
		void __iomem *fl2 = ioremap_wc(ze->ddr_phys + ZX_DDR_FREELIST2, SZ_4K);

		if (!fl1 || !fl2) {
			if (fl1)
				iounmap(fl1);
			if (fl2)
				iounmap(fl2);
			return -ENOMEM;
		}

		if (fl1 && (ZXI_MASK & ZXI_FREELIST)) {
			/* Round 153: do NOT hand buffer 0 to the RX free list.
			 *
			 * zx_bm_alloc() always returns raw 0x80000000, i.e.
			 * index 0, so every TX frame is memcpy_toio()'d into
			 * buffer 0. If the hardware also delivers a received
			 * frame into buffer 0, RX reads back whatever TX just
			 * wrote there.
			 *
			 * That fits the whole symptom set, which no size or rate
			 * threshold explains: a UDP blast works (the device
			 * transmits nothing), ping works (strict ping-pong),
			 * pure ACKs work (device idle) - but a TCP transfer
			 * fails precisely because the device is transmitting its
			 * request and retransmissions while the reply arrives.
			 *
			 * Start the list at 1 and keep 0 as the TX scratch
			 * buffer. One entry fewer costs nothing.
			 */
			/* Stop at BUF_COUNT-1: index 2047 is the dedicated TX
			 * scratch buffer (zx_tx_buf_idx). Leaving it in the RX
			 * free list merely moved the TX/RX aliasing from index
			 * 0 to index 2047 instead of removing it.
			 */
			/* ROUND 34 - UNRESOLVED, AND REVERTED TO THE ORIGINAL.
			 *
			 * Round 33 changed this to `writew(i, ...)` (little-
			 * endian) on the strength of a comparison that was
			 * CONFOUNDED, and that change has been reverted.
			 *
			 * What is actually known:
			 *
			 *  1. This whole block is inside datapath_init(), which
			 *     the WARM path SKIPS. Every recent RAM boot logged
			 *     "datapath warm (...) - init skipped", so this code
			 *     has not executed in any recent test. Neither the
			 *     big-endian nor the little-endian version has been
			 *     exercised on the bench.
			 *
			 *  2. The round-32 evidence was a constant big-endian
			 *     fill vs a SEQUENTIAL little-endian fill, and the
			 *     sequential one "advanced". A constant cannot
			 *     advance, so that compared the wrong two things.
			 *     It does not show that little-endian is correct.
			 *
			 *  3. U-Boot's own datapath WORKS (its TFTP transfers
			 *     fine), and the table it leaves behind reads back
			 *     as big-endian u16 entries - entry 1 is 0x0100 when
			 *     read little-endian, i.e. byte order 00 01. So the
			 *     working reference is consistent with big-endian,
			 *     which is what this line originally did.
			 *
			 * Until the cold path is forced (force_dp_init=1) and a
			 * SEQUENTIAL big-endian list is compared against a
			 * SEQUENTIAL little-endian list, the correct encoding is
			 * unknown. Do not flip this on the strength of the
			 * round-32/33 evidence - it does not support it.
			 */
			for (i = 0; i < BUF_COUNT; i++)
				writew(cpu_to_be16(i),
				       (u8 *)fl1 + i * 2);
			/* The tables live in a write-combining mapping; make sure
			 * they have actually reached DDR before the buffer
			 * manager is told to use them, and verify by reading
			 * back. If the BM sees stale memory it has no free
			 * buffers, which would explain BM+0xdc never gaining
			 * its "pool ready" bits.
			 */
			wmb();
			pr_info("zx-eth: freelist1 readback [0]=%04x [1]=%04x [2047]=%04x\n",
				readw((u8 *)fl1 + 0), readw((u8 *)fl1 + 2),
				readw((u8 *)fl1 + 2047 * 2));
		}
		/* Free list 2 is DELIBERATELY left empty.
		 *
		 * TMC+0xf8 points it at a second pool base (0x41400000) while
		 * zx_buf() always computes from 0x41000000, and its indices
		 * 0..511 alias list 1's. A frame delivered out of pool 2 would
		 * therefore be read from the wrong 2 KiB and handed up as
		 * valid-looking data with a valid ethertype - which no detector
		 * in this driver can catch. Nothing here can tell which pool a
		 * descriptor came from, so the only safe action is not to offer
		 * the hardware those buffers at all.
		 */
		if (fl2 && (ZXI_MASK & ZXI_FREELIST)) {
			/* Second list left populated from 1 for the same reason.
			 * NOTE (latent, not yet fixed): list 2 indices address a
			 * different pool base (TMC+0xf8 = 0x41400000) while
			 * zx_buf() always computes from 0x41000000, so a frame
			 * delivered via list 2 is read from the wrong 2 KB.
			 */
			/* Has the identical big-endian defect as list 1 above,
			 * and is fixed the same way - but deliberately NOT in
			 * the same change. Every traced frame reported pool=0,
			 * so list 2 is not in play on this bench, and this
			 * project has lost rounds to compound edits before.
			 * Fix it once list 1 is verified on hardware.
			 */
			for (i = 0; i < BUF2_COUNT; i++)
				writew(cpu_to_be16(i),
				       (u8 *)fl2 + i * 2);
			wmb();
			pr_info("zx-eth: freelist2 readback [0]=%04x [511]=%04x\n",
				readw((u8 *)fl2 + 0), readw((u8 *)fl2 + 511 * 2));
		}
		iounmap(fl1);
		iounmap(fl2);
	}




	if (ze->tmc && (ZXI_MASK & ZXI_RINGS)) {
		writel(ze->ddr_phys + ZX_DDR_FREELIST, ze->tmc + 0xe8);
		writel(ze->ddr_phys + ZX_DDR_FREELIST2, ze->tmc + 0xec);
		writel(ze->ddr_phys + ZX_DDR_RX_RING, ze->tmc + 0xf0);	/* RX ring */
		writel(ze->ddr_phys + ZX_DDR_POOL, ze->tmc + 0xf4);	/* buffer pool */
		writel(ze->ddr_phys + ZX_DDR_POOL2, ze->tmc + 0xf8);
		/* RESTORED (round 85): this write IS in the vendor code, at
		 * 0x47f2fd68 (`mov r2,#16; str r2,[r3,#4]` with r3=0x92340000).
		 * It was disabled in round 81 because it did not appear in a
		 * readback diff - a diff cannot see a write whose value already
		 * matches, which is exactly the blind spot round 84 identified.
		 */
		writel(16, ze->tmc + TMC_CFG);
	}
	if (ze->tmq && (ZXI_MASK & ZXI_RINGS)) {
		/* TMQ+0x00 bits 16-21 (0x47f2fc70, called with arg 1):
		 *   v = (v & ~0xf0000) | 0x2f0000
		 * Never written by this driver before.
		 */
		/* BISECT round 86: this write coincided with "TM status error
		 * before enqueue" appearing on TX. Gated while confirming.
		 */
		writel(readl(ze->tmq + 0x00) | 0x2f0000u, ze->tmq + 0x00);
		writel(1, ze->tmq + 0x28);
		writel(1, ze->tmq + 0x2c);
		writel(50000, ze->tmq + 0x30);
		writel(0x40, ze->tmq + 0x34);
		writel(0x7f, ze->tmq + 0x04);
		writel(0x20, ze->tmq + 0x20);
		writel(0x20, ze->tmq + 0x24);
		writel(0x131217, ze->tmq + 0x388);

		/* Config eth_init writes that we were missing (round 76). */
		writel(0x00400040, ze->tmq + 0x3c);
		writel(0x00000008, ze->tmq + 0x48);
		writel(ze->ddr_phys + ZX_DDR_TMQ, ze->tmq + 0x50);
		writel(ze->ddr_phys + ZX_DDR_TX_RING, ze->tmq + TMQ_TXRING);	/* TX ring */
	}



	if (ze->tmc)
		writel(0x08000800, ze->tmc + 0xfc);

	/* Queue-table initialisation (0x47f2fb9c -> 0x47f2fa04).
	 *
	 * Programming block at 0x92344000: write the 4-word config to
	 * +0x1c..+0x28 and the command (index | type << 22) to +0x14, gated on
	 * +0x18 bit0. The vendor programs 400 entries of type 0 and 384 of
	 * type 2, all with config { 0x00800400, 0, 0, 0 }. Note the write
	 * order: command first, then the data words descending.
	 *
	 * This driver departs from that for type 0, entries 0-15, the sixteen
	 * CPU RX queues. Type 0 is output-queue admission, decoded as guard
	 * space in bits 10:0 and shared space in bits 25:11, so the vendor's
	 * 0x00800400 admits 1024 + 4096 per queue - five times a CPU queue's
	 * 1024-slot ring, if the unit is one descriptor. U-Boot's lock-step
	 * TFTP never builds that backlog; a burst can, and past 1024 the
	 * producer would lap descriptors the consumer has not read. Consistent
	 * with the unit: without descriptor returns the old driver always
	 * stopped at BM+0xb0 = 5121 = 5 x 1024 + 1. 0x400 (guard only) caps
	 * each CPU queue at its ring, so overload should be tail-dropped by RED
	 * rather than overrun the ring - unmeasured under a real burst; see
	 * docs/WEDGE-ANALYSIS.md. A warm attach keeps U-Boot's values; there a
	 * pending count above 1024 trips rx_fault and zx_dp_reset_work() re-runs
	 * this initialisation.
	 */
	{
		void __iomem *qp = ioremap(ze->phys[ZX_REG_TMD], SZ_4K);
		int type, n, k;

		if (!qp)
			return -ENOMEM;
		if (ZXI_MASK & ZXI_QTABLE) {
			for (type = 0; type <= 2; type += 2) {
				n = type ? 384 : 400;
				for (k = 0; k < n; k++) {
					int spin = 0;

					while (!(readl(qp + 0x18) & 1) &&
					       ++spin < 1000)
						cpu_relax();
					if (spin >= 1000) {
						iounmap(qp);
						return -ETIMEDOUT;
					}
					writel(k | (type << 22), qp + 0x14);
					writel(0, qp + 0x28);
					writel(0, qp + 0x24);
					writel(0, qp + 0x20);
					writel(type == 2 ? 0x00200020 :
					       (k < 16 ? 0x400 : 0x00800400), qp + 0x1c);
				}
			}
			/* Third programming call (0x47f2fc00): index 0, TYPE 4,
			 * with a different config. This was missing - our init
			 * only did types 0 and 2 - and it is exactly what a
			 * bootloader-initialised datapath shows:
			 *   QP+0x1c=ff803fff +0x20=0100ff80 +0x24=00100200
			 *   +0x28=00000020
			 */
			/* Type 4 is a 384-entry loop, not a single index.
			 *
			 * After eth_init, QP+0x14 reads 0x0100017f - type 4
			 * (4 << 22) with index 0x17f = 383, i.e. the last of
			 * 384 entries. Round 53 programmed only index 0.
			 */
			for (k = 0; k < 384; k++) {
				int spin = 0;

				while (!(readl(qp + 0x18) & 1) && ++spin < 1000)
					cpu_relax();
				if (spin >= 1000) {
					iounmap(qp);
					return -ETIMEDOUT;
				}
				writel(k | (4 << 22), qp + 0x14);
				writel(0x00000020, qp + 0x28);
				writel(0x00100200, qp + 0x24);
				writel(0x0100ff80, qp + 0x20);
				writel(0xff803fff, qp + 0x1c);
			}
		}
		iounmap(qp);
	}

	/* Port attach mask at 0x921d9000 + 0x68.
	 *
	 * The vendor's per-port init ends with a read-modify-write that sets the
	 * bit for this port (0x47f307dc..0x47f307e8) before enabling the MAC.
	 * This register was previously mistaken for link status and dismissed.
	 * It is what connects a port to the datapath: round 66 showed that on a
	 * cold boot frames reach the MAC (its counters move) but never enter the
	 * BM/TM, which is exactly what an unset attach bit would do.
	 */
	{
		void __iomem *pa = ioremap(ze->phys[ZX_REG_NPP] + ZX_NPP_ATTACH,
					   SZ_4K);

		if (!pa)
			return -ENOMEM;
		if (pa) {
			u32 before = readl(pa + 0x68);

			writel(before | 0xf, pa + 0x68);	/* ports 0-3 */
			pr_info("zx-eth: port attach +68 %08x -> %08x\n",
				before, readl(pa + 0x68));
			iounmap(pa);
		}
	}

	/* NOTE: do NOT try to program the PP (0x92380000) or switch
	 * (0x92300000) blocks from here. Measured on hardware: those register
	 * regions ignore CPU writes in BOTH states - on a cold boot AND on a
	 * bootloader-initialised boot where RX works:
	 *
	 *   PPWRITE probe: +9c 00001a00, wrote 00001a01, reads 00001a00
	 *
	 * They are also not stable configuration - PP+0x9c read 0x2200 on one
	 * working boot and 0x1a00 on another. They are runtime state maintained
	 * by the datapath hardware, so the round-70 reading of "the PP is
	 * unconfigured on a cold boot" was mistaking effect for cause: those
	 * registers are populated *because* traffic is flowing, not in order to
	 * make it flow.
	 */

	/* Packet-processor bring-up (0x47f304b0), never implemented before.
	 *
	 * This whole branch of eth_init was missed: a readback diff cannot see
	 * it, because PP+0x00 is a self-clearing command register. The vendor
	 * sequence is:
	 *   0x47f304d8:  PP+0x00 = 2, then udelay(1000)
	 *   0x47f30440:  configure 0x92388000
	 *   0x47f30404:  PP steering at 0x9238c000 (note +0x80 = 0x309a)
	 *   tail:        0x923a0000 +0x10 = 0, +0x14 = 0
	 */
	{
		void __iomem *pp   = ioremap(ze->phys[ZX_REG_PP], SZ_4K);
		void __iomem *pp8  = ioremap(ze->phys[ZX_REG_SBRG], SZ_4K);
		void __iomem *ppc  = ioremap(ze->phys[ZX_REG_CLA], SZ_4K);
		void __iomem *ppa  = ioremap(ze->phys[ZX_REG_PONPP], SZ_4K);

		if (!pp || !pp8 || !ppc || !ppa) {
			if (pp)
				iounmap(pp);
			if (pp8)
				iounmap(pp8);
			if (ppc)
				iounmap(ppc);
			if (ppa)
				iounmap(ppa);
			return -ENOMEM;
		}

		if (pp) {			/* 0x47f304d8 */
			writel(0x01070104, pp + 0x28);
			writel(2, pp + 0x00);
			udelay(1000);
			iounmap(pp);
		}
#ifdef CONFIG_ZX279128_PP_TABLES
		/* COLD-ONLY datapath reset + gate + DPA enables. docs/PP-KEY.md
		 * §15-§16; owner-authorised 2026-11-16 (the "never gate/reset the
		 * PP block" rule was lifted for this work).
		 *
		 * WHY. Rounds 4-8 proved the CLA classifies every GE-ingress frame
		 * and the exact-match never acts on a hit, with every CLA-side
		 * input ruled out (§10-§14). The one measured difference from the
		 * vendor is upstream, in the DPA parse stage: 0x92398000 reads
		 * 0x000010c0 (protocol_pkt_aly_en, bits 6,7,12). §13-§18 read this
		 * as "indices 0,1,6 set, 2,3,4,5 CLEAR; vendor sets all seven" and
		 * spent six rounds trying to arm the missing four, through a clock
		 * gate (TOPCRM+0xc, §15-§18) and a sys_ctrl clear (§19.1).
		 *
		 * §19 MEASURED CORRECTION (2026-11-17). Those four bits do not
		 * exist. On this SoC 0x92398000 implements ONLY bits 6,7,12:
		 * writel(0xffffffff)->0x10c0, writel(0xaaaaaaaa)->0x80,
		 * writel(0x55555555)->0x1040 (walking-bit proof, live). Bits
		 * 8,9,10,11 are unimplemented read-as-zero. 0x10c0 is the register's
		 * MAXIMUM and it already holds it at boot. There was never a frozen
		 * window - the §13-§18 "refuses the write" was unimplemented bits
		 * mistaken for refused writes (|= can't tell them apart; writel of a
		 * walking pattern can). The gate work below (TOPCRM pulse + 0x1e0
		 * gate) and the §19.1 sys_ctrl bic are kept because they make the
		 * cold sequence match the vendor init exactly and are harmless, but
		 * they are NOT the DPA unlock: the DPA is already maxed and is
		 * measured OUT as the blocker. cla fwd stays 0 with the DPA at max
		 * (§19.5); later work still found no working per-flow offload. This
		 * records the tested states, not a universal hardware limitation.
		 *
		 * §18 (still true): the gate mask is 0x1e0 (bits 5..8), not 0x1e -
		 * e3833e1e = orr #0x1e ROR 28 = 0x1e0. The gate arms fully, cold.
		 *
		 * This is that sequence, placed after the PP command pulse
		 * (PP+0x00=2; udelay above) and before the SBRG/CLA config below,
		 * so those writes and the DPA enables land in a freshly-reset,
		 * now-clocked block. It is COLD-ONLY by construction: it lives in
		 * zx_eth_datapath_init(), used at probe and in gated recovery. Live
		 * PP state prevents that recovery path; debug warm attachment skips
		 * reinitialization. This is not permission for arbitrary live resets.
		 *
		 * NOT modelled as a clk from zte,zx279128s-crm: that provider's
		 * safety rests on every gate being on at boot (CLK_IS_CRITICAL);
		 * this gate is OFF at boot and only latches after an external
		 * pulse this driver drives, an ordering the clock core cannot
		 * express, in a different (PON datapath) domain than the LSP/PCIe
		 * clocks that driver owns. A straight-line inline sequence here is
		 * the task's sanctioned fallback and the reviewable shape for the
		 * cold-boot tuning this will take.
		 *
		 * SERDES SKIPPED (recovered and deliberately omitted, §18). The
		 * vendor interleaves writes on pon_serdes_base during the deassert
		 * half of the pulse. pon_serdes_base was recovered from the module:
		 * it is of_iomap(zte,zx279128s-pon node, reg index 4) - the five
		 * of_iomap results in init_module land on pon_base/top_crm_base/
		 * sys_ctrl_base/pin_mux_base/pon_serdes_base in that order. The
		 * three writes decoded (zx_pon_clk_reset_init): +0x44 clears bits
		 * 21..16 and ORs a 6-bit temperature-trim code (from temp_ctrl_read,
		 * ubfx #18,#6) into 21..16; +0x40 |= 0x04000000; the loop also
		 * gates on a serdes-ready poll (+0x68 & 0x10 and +0x70 bit 24) with
		 * NO timeout. Those are vendor-named PON SERDES operations; their
		 * physical role on the Ethernet H199A was not established here.
		 * No optical connector or universal GE-path exclusion follows from
		 * those names. They remain omitted: (1) §18 shows
		 * the gate-mask error, not a missing serdes write, caused the §17.4
		 * negative, so "change one thing" says fix the mask alone; (2) the
		 * serdes ready-poll has no timeout, so copying it without hardware
		 * justification risks a stalled boot. The residual risk is that
		 * TOPCRM+0x8 bits 4,5 also gate something the GE path needs; if so,
		 * GE TX/RX dies visibly and recovers on a power cycle (nothing here
		 * writes flash) - a measured, recoverable outcome distinct from a
		 * DPA-latch failure.
		 */
		{
			void __iomem *crm = ioremap(ZX_TOPCRM_PHYS, SZ_4K);
			void __iomem *dpa = ioremap(ze->phys[ZX_REG_PP] +
						    ZX_PP_DPA_OFFSET, SZ_4K);
			void __iomem *sysc = ioremap(ZX_SYSCTRL_PHYS, SZ_4K);
			u32 rst_b, rst_a, gate_b, gate_a;
			u32 aly_b, aly_a, pps_b, pps_a;
			u32 sc_b, sc_a, pm_pk, acl_pk;
			u32 wan_b, wan_a;

			if (!crm || !dpa || !sysc) {
				if (crm)
					iounmap(crm);
				if (dpa)
					iounmap(dpa);
				if (sysc)
					iounmap(sysc);
				iounmap(pp8);
				iounmap(ppc);
				iounmap(ppa);
				return -ENOMEM;
			}

			rst_b = readl(crm + ZX_TOPCRM_RESET);
			gate_b = readl(crm + ZX_TOPCRM_GATE);

			/* Reset pulse on +0x8 bits 4,5: assert (clear) both, delay,
			 * deassert (set) both. Sub-steps kept discrete to match the
			 * plat-zxylzb_9128S.ko decode (§15.5) and leave the serdes
			 * interleave point visible for tuning. The delay is inferred
			 * (vendor's nearby resets use mdelay(10)); not yet pinned.
			 */
			writel(readl(crm + ZX_TOPCRM_RESET) & ~0x20,
			       crm + ZX_TOPCRM_RESET);	/* assert bit 5 */
			writel(readl(crm + ZX_TOPCRM_RESET) & ~0x10,
			       crm + ZX_TOPCRM_RESET);	/* assert bit 4 */
			readl(crm + ZX_TOPCRM_RESET);
			mdelay(10);				/* inferred */
			writel(readl(crm + ZX_TOPCRM_RESET) | 0x20,
			       crm + ZX_TOPCRM_RESET);	/* deassert bit 5 */
			/* [serdes writes would go here - PON optics, skipped] */
			writel(readl(crm + ZX_TOPCRM_RESET) | 0x10,
			       crm + ZX_TOPCRM_RESET);	/* deassert bit 4 */
			readl(crm + ZX_TOPCRM_RESET);

			/* §19 CANDIDATE 1: clear sys_ctrl_base +0x10 bit 11, the
			 * one step zx_pon_clk_reset_init performs that §17/§18
			 * omitted. In the vendor this lands AFTER the reset pulse
			 * and BEFORE the gate arm (init decode: bic #0x800 at
			 * c038, then +0xc |= 0x1e0 at c04c). 0x94100010 is CRM1
			 * +0x10 (sys_ctrl_base = pon reg[2], recovered from the
			 * flash DTB). Hypothesis: bit 11 holds the PON datapath
			 * sub-block in reset/gate, which is why 0x92398000 refuses
			 * every write even with the clock gate fully armed (§18.6).
			 * read-modify-write, bic-only, the vendor's exact op.
			 */
			sc_b = readl(sysc + ZX_SYSCTRL_HOLD);
			writel(sc_b & ~ZX_SYSCTRL_HOLD_BIT, sysc + ZX_SYSCTRL_HOLD);
			sc_a = readl(sysc + ZX_SYSCTRL_HOLD);

			/* Arm the datapath clock gate, +0xc bits 5..8 (0x1e0),
			 * AFTER the pulse. orr-only, the vendor's exact op
			 * (e3833e1e = orr #0x1e ROR 28 = 0x1e0, §18).
			 */
			writel(readl(crm + ZX_TOPCRM_GATE) | ZX_TOPCRM_GATE_BITS,
			       crm + ZX_TOPCRM_GATE);
			readl(crm + ZX_TOPCRM_GATE);
			rst_a = readl(crm + ZX_TOPCRM_RESET);
			gate_a = readl(crm + ZX_TOPCRM_GATE);

			/* §16 HAZARD: immediately after the reset the ACL/PM table
			 * base registers point outside DRAM (0x56409000/0x5f600000).
			 * With the gate now armed the classifier could walk them,
			 * and a walk outside DRAM is the real danger (bus error/hang)
			 * - not the reset itself. Park both bases at valid DRAM
			 * (ze->ddr_phys, the reserved window) BEFORE anything walks.
			 * zx_pp_tables_init() reprograms them to the real allocated
			 * PM/ACL tables later in probe, before any netdev opens. ppa
			 * is the PonPp window (0x923a0000); PM base +0x20, ACL +0x24.
			 */
			writel(ze->ddr_phys, ppa + ZX_PONPP_PM_BASE_REG);
			writel(ze->ddr_phys, ppa + ZX_PONPP_ACL_BASE_REG);
			pm_pk = readl(ppa + ZX_PONPP_PM_BASE_REG);
			acl_pk = readl(ppa + ZX_PONPP_ACL_BASE_REG);

			/* DPA protocol-analysis enables, now that the gate is armed.
			 * +0x000 protocol_pkt_aly_en bits 6..12; +0x014
			 * protocol_cpu_pps_en bit 0 (dpaRegTable decode, §13).
			 */
			aly_b = readl(dpa + ZX_DPA_PKT_ALY_EN);
			writel(aly_b | ZX_DPA_PKT_ALY_BITS, dpa + ZX_DPA_PKT_ALY_EN);
			aly_a = readl(dpa + ZX_DPA_PKT_ALY_EN);
			pps_b = readl(dpa + ZX_DPA_CPU_PPS_EN);
			writel(pps_b | ZX_DPA_CPU_PPS_BITS, dpa + ZX_DPA_CPU_PPS_EN);
			pps_a = readl(dpa + ZX_DPA_CPU_PPS_EN);

			/* §20: declare the WAN/uplink ingress port in the PP
			 * datapath (0x923a001c). This is the one bring-up write
			 * upstream of the CLA that the vendor performs
			 * (tm_set_pp_wan_cfg via tm_set_p2pmode) and our port
			 * never has: our boot reads 0x01200000, with the WAN-port
			 * field (bits 25..29) entirely clear. The classifier sees
			 * every GE-ingress frame (PP-KEY §10) but, with no uplink
			 * port declared, a GE->GE routed frame is never marked an
			 * upstream L3-flow candidate, so the exact-match is not
			 * consulted and the frame traps (§11/§12/§19). Mirror the
			 * vendor: clear the field, then OR bit (WAN_PORT+25).
			 * ppa is the live PonPp window; the base-parking below
			 * uses the same mapping, so this write lands in the same
			 * freshly-reset, now-clocked block.
			 */
			wan_b = readl(ppa + ZX_PONPP_WAN_CFG_REG);
			writel((wan_b & ~ZX_PONPP_WAN_FIELD_MASK) |
			       BIT(ZX_PP_WAN_PORT + ZX_PONPP_WAN_PORT_SHIFT),
			       ppa + ZX_PONPP_WAN_CFG_REG);
			wan_a = readl(ppa + ZX_PONPP_WAN_CFG_REG);

			pr_info("zx-eth: sysctrl 0x94100010 %08x -> %08x (want bit 11 clear, &~0x800)\n",
				sc_b, sc_a);
			pr_info("zx-eth: topcrm reset +8 %08x -> %08x, gate +c %08x -> %08x (want bits 5..8, 0x1e0)\n",
				rst_b, rst_a, gate_b, gate_a);
			pr_info("zx-eth: pp table bases parked at ddr %08x: pm +20=%08x acl +24=%08x\n",
				ze->ddr_phys, pm_pk, acl_pk);
			pr_info("zx-eth: dpa pkt_aly_en %08x -> %08x (want bits 6..12), cpu_pps_en %08x -> %08x\n",
				aly_b, aly_a, pps_b, pps_a);
			pr_info("zx-eth: pp wan_cfg 0x923a001c %08x -> %08x (want bit %u, port %d as WAN)\n",
				wan_b, wan_a,
				ZX_PP_WAN_PORT + ZX_PONPP_WAN_PORT_SHIFT,
				ZX_PP_WAN_PORT);
			if (!(wan_a & BIT(ZX_PP_WAN_PORT + ZX_PONPP_WAN_PORT_SHIFT)))
				pr_warn("zx-eth: pp wan_cfg bit %u did not latch (%08x) - write refused\n",
					ZX_PP_WAN_PORT + ZX_PONPP_WAN_PORT_SHIFT,
					wan_a);
			if ((gate_a & ZX_TOPCRM_GATE_BITS) != ZX_TOPCRM_GATE_BITS)
				pr_warn("zx-eth: topcrm gate did not fully arm (%08x & 0x1e0 != 0x1e0) - pulse/ordering wrong\n",
					gate_a);
			/* §19: check only the IMPLEMENTED bits. Bits 8..11 of
			 * pkt_aly_en and bit 5+ of cpu_pps_en are unimplemented
			 * read-as-zero on this SoC (measured), so warning on the
			 * full vendor mask would be a permanent false alarm.
			 */
			if ((aly_a & ZX_DPA_PKT_ALY_IMPL) != ZX_DPA_PKT_ALY_IMPL)
				pr_warn("zx-eth: dpa pkt_aly_en impl bits not set (%08x & 0x10c0 != 0x10c0)\n",
					aly_a);
			if ((pps_a & ZX_DPA_CPU_PPS_BITS) != ZX_DPA_CPU_PPS_BITS)
				pr_warn("zx-eth: dpa cpu_pps_en did not latch (%08x)\n",
					pps_a);
			if (sc_a & ZX_SYSCTRL_HOLD_BIT)
				pr_warn("zx-eth: sysctrl bit 11 did not clear (%08x & 0x800) - write refused\n",
					sc_a);
			iounmap(sysc);
			iounmap(dpa);
			iounmap(crm);
		}
#endif /* CONFIG_ZX279128_PP_TABLES */
		if (pp8) {			/* 0x47f30440 */
			writel(0x000200ff, pp8 + 0x004);
			writel(0x000bf874, pp8 + 0x188);
			writel(0x000000ff, pp8 + 0x1c0);
			writel(0x00005555, pp8 + 0x1c4);
			writel(0x000000ff, pp8 + 0x2c0);
			writel(0x0000ffff, pp8 + 0x300);
			writel(62,         pp8 + 0x304);
			writel(0xff5555ff, pp8 + 0x340);
			writel(62,         pp8 + 0x344);
			writel(63,         pp8 + 0x380);
			writel(0xaaaaaaaa, pp8 + 0x63c);
			writel(0xfffffffa, pp8 + 0x50);
			writel(0xff00, pp8 + 0x08);
			ret = zx_pp_seed_vlans(pp8, 2);
			if (ret) {
				iounmap(pp8);
				iounmap(ppc);
				iounmap(ppa);
				return ret;
			}
			iounmap(pp8);
		}
		if (ppc) {			/* 0x47f30404 */
			writel(0x0000309a, ppc + 0x80);
			writel(0x00000000, ppc + 0x88);
			writel(0x00000001, ppc + 0xcc);
			iounmap(ppc);
		}
		if (ppa) {			/* 0x47f304b0 tail */
			writel(0, ppa + 0x10);
			writel(0, ppa + 0x14);
			iounmap(ppa);
		}
		/* 0x47f303f0: a block we had never touched at all. */
		{
			void __iomem *c = ioremap(ze->phys[ZX_REG_QMG], SZ_4K);

			if (!c)
				return -ENOMEM;
			if (c) {
				writel(0, c + 0x04);
				iounmap(c);
			}
		}
		pr_info("zx-eth: packet processor bring-up done\n");
#ifdef CONFIG_ZX279128_PP_TABLES
		ze->pp_bring_up = true;	/* precondition of zx_pp_tables_init() */
#endif
	}

	/* per-port MAC registers (smac_init, 0x92200000 + port * 0x40000) */
	for (i = 0; i < 4; i++) {
		void __iomem *mac = ioremap(ze->phys[ZX_REG_MAC0 + i], SZ_4K);

		if (!mac)
			return -ENOMEM;
		if (!(ZXI_MASK & ZXI_MACREGS)) {
			iounmap(mac);
			continue;
		}
		/* MAC+0x00 is the main control word. A register diff between a
		 * working TFTP boot and a flash boot showed this as the key
		 * difference: 0x00bb6003 vs 0x00000001, i.e. everything except
		 * the enable bit was missing. Without it the MAC is not
		 * configured, so nothing reaches the wire and nothing is
		 * received.
		 */
		writel(0x00bae002, mac + 0x000);
		/* MAC+0x04 and MAC+0x08 are present on a bootloader-initialised
		 * datapath and completely absent (read 0) after our init - found
		 * by diffing /proc/zx_eth_regs between a working TFTP boot and a
		 * flash boot. MAC+0x08 bit31 looks like an enable.
		 */
		writel(0x0000ffff, mac + 0x004);
		writel(0x80000001, mac + 0x008);
		writel(0x00300002, mac + 0x070);
		writel(0x00004000, mac + 0x0b4);
		writel(0x00011200, mac + 0x0e0);
		writel(readl(mac + 0xd00) & ~BIT(1), mac + 0xd00);
		writel(readl(mac + 0xd30) & ~BIT(5), mac + 0xd30);
		/* These older U-Boot settings are separate from the vendor Linux
		 * +0xd00/+0xd30 fields above; the large offsets were not typos.
		 */
		writel(0x00000020, mac + 0x0b0);
		writel(0x0000000c, mac + 0x0d0);
		iounmap(mac);
	}
	wmb(); /* Publish pool and queue tables before enabling allocation. */
	if (ze->bm && (ZXI_MASK & ZXI_BMREGS)) {
		writel(BUF_COUNT << 16, ze->bm + 0x48);
		writel(BUF2_COUNT << 16, ze->bm + 0x4c);
		writel(1, ze->bm + BM_ENABLE);
	}
	return 0;
}

static int zx_eth_update_bits(void __iomem *base, u32 reg, u32 mask, u32 value)
{
	u32 expected = (readl(base + reg) & ~mask) | (value & mask);

	writel(expected, base + reg);
	return ((readl(base + reg) ^ expected) & mask) ? -EIO : 0;
}

/* Four independent Linux netdevs must not retain the bootloader's hardware
 * bridge. Keep physical GE forwarding in Linux, with direct raw TX selecting
 * the egress MAC. Other hardware-port bits are preserved.
 */
static int zx_eth_software_ports(struct zx_eth *ze)
{
	void __iomem *brg, *spa;
	const char *phase = "quiesce";
	u32 status = 0;
	unsigned int port;
	int ret = 0;

	for (port = 0; port < ZX_NPORTS; port++)
		if (!ze->macs[port])
			return -EINVAL;
	brg = ioremap(ze->phys[ZX_REG_SBRG], SZ_4K);
	spa = ioremap(ze->phys[ZX_REG_NPP] + ZX_NPP_SPA, SZ_4K);
	if (!brg || !spa) {
		ret = -ENOMEM;
		goto out;
	}
	/* Probe has not published a netdev. First open will enable ingress. */
	for (port = 0; port < ZX_NPORTS; port++) {
		ret = zx_eth_update_bits(ze->macs[port], MAC_CTRL, MAC_CTRL_EN, 0);
		if (ret)
			goto out;
	}
	phase = "BRG ready";
	ret = readl_poll_timeout(brg + 0x18, status, status & 1, 1, 1000);
	if (ret)
		goto out;
	phase = "learning and isolation";
	/* Vendor mode0 disables source learning. GE0..3 are BRG ports1..4. */
	ret = zx_eth_update_bits(brg, 0x1c4, 0x3fc, 0);
	if (ret)
		goto out;
	for (port = 1; port <= ZX_NPORTS; port++) {
		ret = zx_eth_update_bits(brg, 0x3c0 + 4 * port, 0x1e, 0);
		if (ret)
			goto out;
	}
	/* Unknown-unicast mode3 traps to CPU; mode1 used to flood to wires. */
	ret = zx_eth_update_bits(brg, 0x340, 0x3fc00, 0x3fc00);
	if (ret)
		goto out;
	phase = "VLAN admission";
	ret = zx_eth_update_bits(brg, 0x008, 0x1e1e, 0);
	if (ret)
		goto out;
	/* Exact stock DISNONE recipe: packet mode1, VLAN filter mask0.
	 * Filter rows2..5 differ from the packet-mode port indices1..4.
	 */
	ret = zx_eth_update_bits(spa, 0x2a8, 0x3fc, 0x154);
	if (ret)
		goto out;
	for (port = 0; port < ZX_NPORTS; port++) {
		ret = zx_eth_update_bits(spa, 0x2b4 + 4 * port, 0x3f, 0);
		if (ret)
			goto out;
	}
	phase = "FDB clear";
	/* The driver owns the ordinary FDB. Clear all inherited destinations,
	 * including entries learned before Linux, after disabling GE learning.
	 * This does not initialize the separate SPA/PP own-MAC tables.
	 */
	ret = zx_eth_update_bits(brg, 0x004, GENMASK(15, 8), 0xff00);
	if (ret)
		goto out;
	writel(readl(brg + 0x004) | BIT(16), brg + 0x004);
	readl(brg + 0x004);
	ret = readl_poll_timeout(brg + 0x190, status, status & 1, 1, 20000);
	if (ret)
		goto out;
	phase = "transparent VLANs";
	/* Linux does not advertise hardware VLAN filtering/stripping. Every
	 * accepted VID therefore needs valid, unmodified CPU/wire delivery.
	 */
	ret = zx_pp_seed_vlans(brg, 4096);
	if (!ret)
		dev_info(ze->dev, "software port policy configured; 4096 transparent VLANs\n");
out:
	if (ret)
		dev_err(ze->dev, "software port setup failed at %s: %d (status=%08x)\n",
			phase, ret, status);
	if (spa)
		iounmap(spa);
	if (brg)
		iounmap(brg);
	return ret;
}

/* /proc/zx_eth_poke - read/modify/write any datapath register at runtime.
 *
 * Round 165. The remaining Ethernet question is which classifier bit makes the
 * hardware swallow TCP segments carrying payload (round 164 proved they never
 * reach the queue engine). Answering it means trying candidate registers in the
 * NPP block, and each candidate previously cost a build + flash + boot cycle of
 * about six minutes - which is why round 161 tested exactly one value, and did
 * so in code that never executed.
 *
 * Usage (physical address, value; second form ORs/ANDs):
 *   echo "0x921c0060 0x00000000"        > /proc/zx_eth_poke   # write
 *   echo "0x921c0060 or 0x03800000"     > /proc/zx_eth_poke   # set bits
 *   echo "0x921c0060 and ~0x03800000"   > /proc/zx_eth_poke   # clear bits
 *   echo "0x921c0060 read"              > /proc/zx_eth_poke   # log current value
 *
 * Deliberately unrestricted: this is a bring-up tool on a board with a UART and
 * a recovery bank, and the alternative is guessing.
 */
static ssize_t zx_poke_write(struct file *f, const char __user *ubuf,
			     size_t len, loff_t *off)
{
	char buf[96], op[24] = "", arg[24] = "";
	unsigned long phys = 0, val = 0;
	bool invert = false, have_val = false;
	void __iomem *m;
	u32 cur;
	int n;

	if (len >= sizeof(buf))
		return -EINVAL;
	if (copy_from_user(buf, ubuf, len))
		return -EFAULT;
	buf[len] = 0;

	/* Parse the value as a STRING, not with %lx.
	 *
	 * This used to be `sscanf(buf, "%lx %23s %lx", ...)`, which cannot read
	 * the `~0x100` form its own usage comment documents: the conversion
	 * fails, n comes back 2, and the "and" branch (which requires n == 3) is
	 * skipped - so `0x94200090 and ~0x2` fell through to the plain-write
	 * branch, where simple_strtoul("and") is 0 and the register was set to
	 * ZERO. Silently. On a live clock/pinmux word.
	 *
	 * That happened on 2026-09-07 and clobbered 0x94200090 from 0xa28a to
	 * 0x00000001 while trying to clear one bit. The log line said
	 * ":= 00000000", which is the only reason it was caught at all.
	 */
	n = sscanf(buf, "%lx %23s %23s", &phys, op, arg);
	if (n < 2)
		return -EINVAL;

	/* Reads are always allowed; writes are opt-in.
	 *
	 * The endpoint is an arbitrary physical read-modify-write primitive, and
	 * the IRQ receive path now owns live DMA state. A stray write from a
	 * script - or from a reader who has not read this file - can duplicate a
	 * buffer that hardware still owns. Make the destructive half something
	 * you have to ask for:
	 *
	 *   echo 0 > /sys/module/zx279128_eth/parameters/poke_allow_write
	 */
	if (!(n == 2 && !strcmp(op, "read")) && !zx_poke_allow_write) {
		pr_info("zx-poke: write to %08lx refused (poke_allow_write=0)\n",
			phys);
		return -EPERM;
	}

	if (n == 3) {
		const char *a = arg;

		if (*a == '~') {
			invert = true;
			a++;
		}
		if (kstrtoul(a, 0, &val))
			return -EINVAL;
		if (invert)
			val = ~val;
		have_val = true;
	}

	m = ioremap(phys & ~0xfffUL, SZ_4K);
	if (!m)
		return -ENOMEM;

	cur = readl((u8 *)m + (phys & 0xfff));

	if (n == 2 && !strcmp(op, "read")) {
		pr_info("zx-poke: [%08lx] = %08x\n", phys, cur);
	} else if (have_val && !strcmp(op, "or")) {
		writel(cur | (u32)val, (u8 *)m + (phys & 0xfff));
		pr_info("zx-poke: [%08lx] %08x |= %08lx -> %08x\n", phys, cur, val,
			readl((u8 *)m + (phys & 0xfff)));
	} else if (have_val && !strcmp(op, "and")) {
		writel(cur & (u32)val, (u8 *)m + (phys & 0xfff));
		pr_info("zx-poke: [%08lx] %08x &= %08lx -> %08x\n", phys, cur, val,
			readl((u8 *)m + (phys & 0xfff)));
	} else if (n == 2) {
		/* "phys value" - plain write. REJECT an unparseable value rather
		 * than writing whatever simple_strtoul() makes of it, which for
		 * a mistyped opcode is 0. */
		unsigned long v2;

		if (kstrtoul(op, 0, &v2)) {
			iounmap(m);
			return -EINVAL;
		}
		writel((u32)v2, (u8 *)m + (phys & 0xfff));
		pr_info("zx-poke: [%08lx] %08x := %08lx -> %08x\n", phys, cur, v2,
			readl((u8 *)m + (phys & 0xfff)));
	} else {
		iounmap(m);
		return -EINVAL;
	}

	iounmap(m);
	return len;
}

static const struct proc_ops zx_poke_pops = {
	.proc_write = zx_poke_write,
};

/* /proc/zx_eth_reinit - re-run the datapath bring-up on a live system.
 *
 * Round 177. The RX path wedges after a few thousand cumulative frames and
 * needs a power cycle. Round 149 recorded that it "survives ifconfig down/up",
 * but that only exercises ndo_open/ndo_stop - it never re-runs
 * zx_eth_datapath_init(), which does the fabric reset AND re-primes the free
 * lists and queue configuration.
 *
 * The DIR-842 port hit a structurally identical wedge and shipped a detect-and-
 * heal recovery rather than a root-cause fix, having found that CPU-engine
 * re-init could not clear it while a fabric-level reset could. This is the
 * equivalent lever, exposed so the ladder can actually be tested:
 *   1. fabric reset alone   - via /proc/zx_eth_poke 0x92000008 (does NOT clear)
 *   2. full datapath init   - this file
 *
 * It returned -EOPNOTSUPP while no complete RX/TX ownership teardown existed.
 * zx_dp_reset_work() is that teardown - every port closed, cold init, software
 * ownership reset to the cold-probe state, ports reopened - so a write here now
 * queues exactly the reset the watchdog would, for testing the recovery on the
 * bench. A manual request skips the automatic rate limit and give-up count;
 * rx_recover=0 still refuses it.
 */
static ssize_t zx_reinit_write(struct file *f, const char __user *ubuf,
			       size_t len, loff_t *off)
{
	struct zx_eth *ze = zx_dbg_ze;

	if (!ze)
		return -ENODEV;
	if (!zx_rx_recover)
		return -EPERM;
	WRITE_ONCE(ze->reset_manual, true);
	WRITE_ONCE(ze->reset_reason, "requested through /proc/zx_eth_reinit");
	mod_delayed_work(system_wq, &ze->reset_work, 0);
	return len;
}

static const struct proc_ops zx_reinit_pops = {
	.proc_write = zx_reinit_write,
};

/* /proc/zx_eth_spa_ram - load the SPA match RAM and hash RAM (diagnostic).
 *
 * The last unreproduced vendor state from tm_pon_npp_spa_initial(). Writing any
 * non-empty string triggers a one-shot load through the SPA indirect interface:
 *   match_mode = 1
 *   for line 0..2: DATA5..0 = match image; cmd(rw=0, ram_id=0, addr=line)
 *   for entry 0..7: DATA1=word1, DATA0=word0; cmd(rw=0, ram_id=5, addr=entry)
 * Each cmd is preceded by the vendor's access_done poll (STATUS bit0 == 1).
 * DATA readback is only a write latch, not independent RAM verification.
 *
 * Gated behind poke_allow_write for the same reason as /proc/zx_eth_poke: it is
 * a direct MMIO write primitive into the classifier and must not act by default.
 */
/* STATUS bit0 is access_done: the vendor's spa_set/get_* poll waits for it to
 * read 1 (ready to accept the next command), up to 0x13 times, then issues the
 * command and moves on without re-checking. Measured on the H199A: the bit sits
 * at 1 and never dips, so this is a readiness gate, not a busy flag. Match the
 * vendor polarity exactly (wait for 1), not its inverse.
 */
static int zx_spa_wait_ready(void __iomem *spa)
{
	unsigned int i;

	for (i = 0; i < 0x13; i++)
		if (readl(spa + SPA_IND_STATUS) & 1)
			return 0;
	return -ETIMEDOUT;
}

static int zx_spa_ram_load(struct zx_eth *ze)
{
	void __iomem *spa;
	u32 rb[6];
	int line, ent, i, ret = 0;

	spa = ioremap(ze->phys[ZX_REG_NPP] + ZX_NPP_SPA, SZ_4K);
	if (!spa)
		return -ENOMEM;

	/* match_mode = 1 (reg 0x12 / SPA+0x7c, 2 bits). Vendor writes it before
	 * the RAM loads; §26 F1 proved the bit alone does nothing.
	 */
	writel((readl(spa + SPA_MATCH_MODE) & ~0x3u) | 1u, spa + SPA_MATCH_MODE);

	for (line = 0; line < 3 && !ret; line++) {
		ret = zx_spa_wait_ready(spa);
		if (ret)
			break;
		for (i = 0; i < 6; i++)
			writel(zx_spa_match_ram[line][i], spa + SPA_IND_DATA0 + i * 4);
		writel((SPA_IND_RAMID_MATCH << 22) | line, spa + SPA_IND_CMD);
	}

	for (ent = 0; ent < 8 && !ret; ent++) {
		ret = zx_spa_wait_ready(spa);
		if (ret)
			break;
		writel(zx_spa_hash_ram[ent][1], spa + SPA_IND_DATA0 + 1 * 4);
		writel(zx_spa_hash_ram[ent][0], spa + SPA_IND_DATA0 + 0 * 4);
		writel((SPA_IND_RAMID_HASH << 22) | ent, spa + SPA_IND_CMD);
	}

	/* Issue a read of line 0 and log the DATA window. NOTE (measured on the
	 * H199A, PP-KEY.md §27): the read command does NOT repopulate the DATA
	 * registers from RAM - they behave as a write latch and retain the last
	 * written value - so this log reflects the last write, not a true RAM
	 * read-back. It is kept only as a liveness marker; the real verification
	 * is the CLA aging[]/up-fwd measurement, not these words.
	 */
	if (!ret && !zx_spa_wait_ready(spa)) {
		writel(SPA_IND_RW_READ | (SPA_IND_RAMID_MATCH << 22) | 0,
		       spa + SPA_IND_CMD);
		if (!zx_spa_wait_ready(spa)) {
			for (i = 0; i < 6; i++)
				rb[i] = readl(spa + SPA_IND_DATA0 + i * 4);
			pr_info("zx-spa: match[0] DATA window %08x %08x %08x %08x %08x %08x (write-latch, not a RAM read)\n",
				rb[0], rb[1], rb[2], rb[3], rb[4], rb[5]);
		}
	}

	iounmap(spa);
	pr_info("zx-spa: RAM load %s (match_mode=1, 3 match lines, 8 hash entries)\n",
		ret ? "TIMED OUT" : "done");
	return ret;
}

static ssize_t zx_spa_ram_write(struct file *f, const char __user *ubuf,
				size_t len, loff_t *off)
{
	struct zx_eth *ze = zx_eth_singleton;
	int ret;

	if (!zx_poke_allow_write) {
		pr_info("zx-spa: refused (poke_allow_write=0)\n");
		return -EPERM;
	}
	if (!ze)
		return -ENODEV;
	ret = zx_spa_ram_load(ze);
	return ret ? ret : len;
}

static const struct proc_ops zx_spa_ram_pops = {
	.proc_write = zx_spa_ram_write,
};

/* /proc/zx_eth_regs - dump the datapath registers for host-side diffing.
 *
 * Emitting this via pr_info() does not work: ~240 lines in a burst are silently
 * dropped by console rate-limiting (round 51), which produced a convincing but
 * entirely false "no differences" result. seq_file output goes through the tty
 * instead, so `cat` returns everything.
 */
static const struct { const char *n; u32 base; int words; } zx_blocks[] = {
	{ "BM",  0x92348000, 128 },
	{ "TMC", 0x92340000, 256 },
	{ "TMQ", 0x92350000, 256 },
	{ "QP",  0x92344000, 64  },
	{ "MAC", 0x92200000, 256 },
	/* Blocks named in the stock device tree that this driver has never
	 * touched. "sw" is the Ethernet switch - note 0x92300000 is NOT a
	 * fifth MAC port as round 32 assumed. "idm" sits next to the NPP and
	 * is a plausible ingress/data manager.
	 */
	{ "SW",  0x92300000, 256 },
	{ "IDM", 0x921c8000, 128 },
	{ "NPP", 0x921c0000, 128 },
	{ "PP",  0x92380000, 128 },
	/* Second apertures, from the vendor DTB embedded in
	 * ref/ZX279127S-Reverse/mtd-img/F610GV9/kernel1.bin (model
	 * "ZTE ZX279128S"). Every node there carries TWO reg ranges and this
	 * driver has only ever mapped one of each:
	 *
	 *   idm@921c8000  reg = <0x92334000 0x4000>, <0x921c8000 0x4000>
	 *   npp@921c0000  reg = <0x921c0000 0x8000>, <0x921cc000 0x34000>
	 *   pp@92380000   reg = <0x92140000 0x40000>, <0x92380000 0x40000>
	 *
	 * Dumped read-only. Nothing here is understood yet; the point is that
	 * three windows the vendor considers part of these blocks have never
	 * been looked at, and a register that does not appear in any dump
	 * cannot be part of any hypothesis.
	 */
	{ "IDM2", 0x92334000, 128 },
	{ "NPP2", 0x921cc000, 128 },
	{ "PP2",  0x92140000, 128 },
	/* The other three MAC apertures, and the two blocks the driver writes
	 * that no dump has ever covered.
	 *
	 * WHY THESE MATTER (2026-09-10): with eth2 UP in a RAM shell, reading
	 * 0x92280000 from userspace through /proc/zx_eth_poke produced
	 *   Unhandled fault: imprecise external abort (0x1406) at 0xb6f3a028
	 *   Internal error: : 1406 [#1] SMP ARM
	 * and halted the board. The driver's own accesses to the same window are
	 * fine - it reproduces only through a fresh ioremap from another context.
	 * A register dump that can kill the board is not an instrument, so the
	 * dump becomes the only path to these windows.
	 */
	{ "MAC1", 0x92240000, 256 },
	{ "MAC2", 0x92280000, 256 },
	{ "MAC3", 0x922c0000, 256 },
	{ "SPA",  0x921d4000, 64 },
	/* MISLABELLED, kept only for dump continuity across rounds.
	 *
	 * This window is NOT the bridge. The vendor block table puts SBRG at
	 * pp_base+0x8000 = 0x92388000 and cla at 0x9238c000 (see the SBRG and
	 * CLA entries below). 0x921d9000 is inside the NPP aperture, and the
	 * vendor reaches +0x68 there only for switch ports >= 5, as a
	 * link/serial handshake bit. Round 96 falsified the old reading on the
	 * bench: clearing every bit of it did not stop eth1 receiving.
	 */
	{ "BRG",  0x921d9000, 64 },
	/* The three sub-blocks the cold-only init writes and that no dump has
	 * ever covered (2026-09-10, round 97). Every one of them is written ONLY
	 * inside zx_eth_datapath_init(), i.e. on the path a warm RAM boot skips -
	 * which is exactly why their values have never been checked against the
	 * product's boot path:
	 *
	 *   SBRG 0x92388000 - port transfer enable (+0x004); SA and DA lookup
	 *                     enables (+0x1c0, +0x2c0); unknown-unicast-forward
	 *                     bit per SBRG port (+0x340).
	 *   CLA  0x9238c000 - classifier block.
	 *   QMG  0x9234c000 - next to TMC; the cold init writes +0x004.
	 *
	 * A stock ZTE vendor boot (logs/uart.log:494066, Linux 4.1.25) reads
	 * DIFFERENT values than this driver writes at roughly fifteen of these
	 * addresses. That list is only actionable once the registers can be read
	 * back on a live boot, which is what these entries are for.
	 */
	{ "SBRG", 0x92388000, 128 },
	{ "CLA",  0x9238c000, 128 },
	{ "QMG",  0x9234c000, 128 },
	/* Top-level clock/reset manager (stock DTS: topcrm@94000000,
	 * "zte,ZX279127-topcrm", syscon). The pp/npp/tm nodes have no clocks
	 * property, so their gating lives here.
	 */
	{ "CRM", 0x94000000, 256 },
	/* DO NOT add the PCIe regions here.
	 *
	 * Round 102: dumping 0x0f000000 / 0x09500000 from a running kernel
	 * HUNG THE BOARD - an unclocked region on this SoC raises an imprecise
	 * external abort that wedges the CPU with no oops. The PCIe block is
	 * not clocked or is held in reset until something enables it, so any
	 * driver must release clocks/resets BEFORE touching DBI or glue.
	 */
};

/* ZX_RX_SEED_R202_BEGIN */
/* Runtime-only, per-device first-open experiment. The caller must measure the
 * relocated U-Boot next cursor AFTER the final image transfer; no index is
 * inferred here. RTNL serializes parameter access, NAPI's first start, and
 * publication/unpublication of the existing late-probe debug pointer.
 */
static bool zx_rx_seed_idle(const struct zx_eth *ze)
{
	unsigned int ring;

	ASSERT_RTNL();
	if (!ze->rx_seed_eligible || ze->removing || ze->running ||
	    ze->dp_users || READ_ONCE(ze->rx_fault) ||
	    ze->rx_inflight != -1 || ze->rx_next)
		return false;
	for (ring = 0; ring < ZX_RX_RINGS; ring++) {
		const struct zx_rx_queue *q = &ze->rxq[ring];

		if (q->cursor || q->remaining || q->debt ||
		    q->buffer_pending || q->return_sent)
			return false;
	}
	return true;
}

#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)
static int zx_rx_q0_seed_set(const char *value, const struct kernel_param *kp)
{
	struct zx_eth *ze;
	int seed, ret;

	(void)kp;
	ret = kstrtoint(value, 0, &seed);
	if (ret)
		return ret;
	if (seed < -1 || seed >= RING_ENTRIES)
		return -EINVAL;
	/* The module-parameter mutex is already held: never block on RTNL. */
	if (!rtnl_trylock())
		return -EBUSY;
	ze = zx_dbg_ze;
	if (!ze) {
		ret = -ENODEV;
		goto out;
	}
	if (!zx_rx_seed_idle(ze)) {
		ret = -EBUSY;
		goto out;
	}
	/* Stage only; -1 cancels before first open, never rewinds a cursor. */
	ze->rx_q0_seed = seed;
	ret = 0;
out:
	rtnl_unlock();
	return ret;
}

static int zx_rx_q0_seed_get(char *buffer, const struct kernel_param *kp)
{
	int seed = -1;

	(void)kp;
	if (!rtnl_trylock())
		return -EBUSY;
	if (zx_dbg_ze && !zx_dbg_ze->removing)
		seed = zx_dbg_ze->rx_q0_seed;
	rtnl_unlock();
	return scnprintf(buffer, PAGE_SIZE, "%d", seed);
}

static const struct kernel_param_ops zx_rx_q0_seed_ops = {
	.set = zx_rx_q0_seed_set,
	.get = zx_rx_q0_seed_get,
};
module_param_cb(rx_q0_seed, &zx_rx_q0_seed_ops, NULL, 0644);
MODULE_PARM_DESC(rx_q0_seed,
	"test: runtime warm RX q0 next cursor (-1 unchanged, 0..1023); set before first open from this boot's final U-Boot handoff");
#endif

static int zx_rx_seed_start(struct zx_eth *ze)
{
	int seed = ze->rx_q0_seed;

	ASSERT_RTNL();
	if (!ze->rx_seed_eligible)
		return 0;
	if (seed < -1 || seed >= RING_ENTRIES)
		return -EINVAL;
	if (seed >= 0) {
		if (!zx_rx_seed_idle(ze))
			return -EBUSY;
		/* The sole experimental datapath mutation, before NAPI is enabled. */
		ze->rxq[0].cursor = seed;
		netdev_info(ze->ndev,
			    "RXSEED_R202 requested=%d applied=%u ring=0 stage=pre-first-open\n",
			    seed, ze->rxq[0].cursor);
	}
	/* Also latch the default -1 arm. Closing/reopening must never reseed. */
	ze->rx_seed_eligible = false;
	return 0;
}

static void zx_rx_seed_publish(struct zx_eth *ze)
{
	rtnl_lock();
	zx_dbg_ze = ze;
	rtnl_unlock();
}

static void zx_rx_seed_unpublish(struct zx_eth *ze)
{
	rtnl_lock();
	if (zx_dbg_ze == ze)
		zx_dbg_ze = NULL;
	rtnl_unlock();
}
/* ZX_RX_SEED_R202_END */

static int zx_regs_show(struct seq_file *m, void *v)
{
	int b, k;

	/* zx_dp_reset_work() holds the fabric in reset: stay off the bus. */
	if (zx_dbg_ze && READ_ONCE(zx_dbg_ze->resetting)) {
		seq_puts(m, "RXRECOVER datapath reset in progress\n");
		return 0;
	}

	/* RX protocol census: what actually reached the netdev, by protocol.
	 * Recorded because UDP from the host was never arriving and the driver
	 * had no way to say whether the frame reached it.
	 *
	 * ROUND 36: the field names in this line were misleading and are now
	 * spelled out. `tcp` was c_tcp_data, which is IP protocol 6 with a
	 * payload, not "TCP" in the sense a reader assumes; `other` was
	 * c_report, which counts any IPv4 frame that is not protocol 1, 17 or 6
	 * (so it is "other IP protocol", not "other ethertype"); and `nonipv4`
	 * was c_tcp_bare, which is the non-IPv4 bucket despite the name. The
	 * analyst found this while being asked to reason about the line, and a
	 * counter whose label misdescribes it is worse than no counter.
	 */
	if (zx_dbg_ze)
		seq_printf(m, "RXCENSUS icmp=%lu icmp_req=%lu icmp_rep=%lu udp=%lu ipproto6=%lu othipproto=%lu nonipv4=%lu protomismatch=%lu\n",
			   zx_dbg_ze->c_icmp, zx_dbg_ze->c_icmp_req,
			   zx_dbg_ze->c_icmp_rep, zx_dbg_ze->c_udp,
			   zx_dbg_ze->c_tcp_data, zx_dbg_ze->c_report,
			   zx_dbg_ze->c_tcp_bare, zx_dbg_ze->c_proto_mismatch);

	/* ROUND 36: producer-side probe, requested by the red team after R129
	 * captured a 13-second stretch in which the census did not move while
	 * the poll demonstrably kept running.
	 *
	 * The two readings answer different halves of the question and must be
	 * taken together:
	 *   RXQPEND  reads the hardware's own published count, TMQ+0x100+4*q,
	 *            one 32-bit register per queue holding TWO 16-bit counts
	 *            (even ring low half, odd ring high half). This is the
	 *            producer's word, untouched by the driver.
	 *   RXQCUR   is the driver's consumer state for each of the 16 rings.
	 * If pend stays 0 while census is frozen, the hardware published no work
	 * and the defect is on the producer side. If pend is nonzero and frozen,
	 * the producer advanced but stopped publishing. If pend advances while
	 * census does not, producer and cursor have diverged and the driver is
	 * reading the wrong slots. zerolen/prodzero are the high-rate versions of
	 * the same two questions, because a 1 Hz sample cannot see a 500 us poll.
	 */
	if (zx_dbg_ze) {
		struct zx_eth *z = zx_dbg_ze;
		int q;

		for (q = 0; q < ZX_RX_QUEUES; q++)
			seq_printf(m, "RXQPEND q=%d pend=%08x\n", q,
				   readl(z->tmq + TMQ_PENDING + q * 4));
		for (b = 0; b < ZX_RX_RINGS; b++)
			seq_printf(m, "RXQCUR ring=%d cursor=%u remaining=%u debt=%u pend0=%u\n",
				   b, z->rxq[b].cursor, z->rxq[b].remaining,
				   z->rxq[b].debt, z->rxq[b].pool);
		seq_printf(m, "RXPROD prodzero=%lu zerolen=%lu nocredit=%lu alloc_busy=%lu alloc_invalid=%lu\n",
			   z->n_prodzero, z->n_zerolen, z->n_nocredit,
			   z->n_alloc_busy, z->n_alloc_invalid);
		/* ROUND 36: the vendor archaeologist's three registers. It showed
		 * that NOTHING in the vendor design can suspend RX - no timer, no
		 * work item, no credit gate, no re-arm - and that the vendor never
		 * lets a failed buffer-free or a failed descriptor-return stop the
		 * ring walk. Our driver does exactly that, so the only RX-stopping
		 * state in the system is ours, and it is a three-way fork that no
		 * counter could previously separate:
		 *
		 *   bm_freecnt   BM+0xdc bits[8:3]: the BM credit our free path
		 *                waits on. Zero through the freeze => credit
		 *                starvation, and n_free_nocredit climbs with it.
		 *   tmd_go       TMD+0x64 bit0: a stuck descriptor-return command.
		 *                One throughout => rx_inflight never clears and the
		 *                return path is wedged above the credit check.
		 *   tmc_mask     TMC+0x104 bits[0:1]: masked while the blocked path
		 *                skips zx_rx_rearm. The vendor unmasks at NAPI exit
		 *                and nowhere else, so a missed unmask is permanent
		 *                until ndo_open.
		 *
		 * bm_freecnt and tmd_go are read live rather than sampled by the
		 * driver precisely because they must be read DURING a freeze.
		 */
		seq_printf(m, "RXSTOP bm_freecnt=%08x tmd_go=%08x tmc_mask=%08x inflight=%d freenocredit=%lu fault=%d desc_rls=%lu desc_busy=%lu\n",
			   readl(z->bm + BM_FREECNT), readl(z->tmd + TMD_GO),
			   readl(z->tmc + TMC_IRQ_MASK), z->rx_inflight,
			   z->n_free_nocredit, READ_ONCE(z->rx_fault),
			   z->n_desc_rls, z->n_desc_busy);
		/* Datapath recovery: resets done, consecutive resets with no RX
		 * between them, watchdog NAPI kicks, pending counts re-read
		 * because the first read exceeded the ring, the current stall
		 * length in seconds and empty polls blocked on a refused return.
		 */
		seq_printf(m, "RXRECOVER resets=%lu consec=%u kicks=%lu badpend=%lu stuck=%u blocked=%u recover=%d stall_ms=%u\n",
			   z->n_resets, z->reset_consec, z->n_wd_kicks,
			   z->n_bad_pending, z->wd_stuck, z->rx_blocked_polls,
			   zx_rx_recover, zx_rx_stall_ms);
	}

	/* ROUND 23: the TX side had NO per-second observable at all, which is why
	 * sixteen rounds of counter correlation had nothing to correlate against
	 * and why a fix could not be judged. Read this file at 1 Hz and the two
	 * sides of the defect are sampled in the same instant.
	 *
	 * tx_packets   frames handed to the traffic manager
	 * tx_dropped   dropped in the driver before submission
	 * tx_fifo_errors  the flashed generation's silent drop at tx_outstanding>=1024
	 * tx_outstanding  the driver's in-flight estimate, which the flashed
	 *                 generation drains by reading TMQ+0x68
	 * tx_next      the software slot cursor
	 */
	if (zx_dbg_ze) {
		/* ROUND 34: sum across ALL netdevs. R129 showed tx_packets reading 0
		 * while the sender received replies, because with split_ports a frame
		 * is transmitted through the per-port netdev it egresses from and the
		 * primary's counter never moves. A TX observable that reads the wrong
		 * netdev is worse than none, because it looks like a result.
		 */
		struct zx_eth *z = zx_dbg_ze;
		unsigned long tp = z->ndev->stats.tx_packets, tb = z->ndev->stats.tx_bytes;
		unsigned long td = z->ndev->stats.tx_dropped, tf = z->ndev->stats.tx_fifo_errors;
		unsigned long te = z->ndev->stats.tx_errors;
		int pi;

		for (pi = 0; pi < ZX_NPORTS; pi++) {
			if (!z->ports[pi] || z->ports[pi] == z->ndev)
				continue;
			tp += z->ports[pi]->stats.tx_packets;
			tb += z->ports[pi]->stats.tx_bytes;
			td += z->ports[pi]->stats.tx_dropped;
			tf += z->ports[pi]->stats.tx_fifo_errors;
			te += z->ports[pi]->stats.tx_errors;
		}
		seq_printf(m, "TXCENSUS tx_packets=%lu tx_bytes=%lu tx_dropped=%lu tx_fifo_errors=%lu tx_errors=%lu tx_outstanding=%u tx_next=%u\n",
			   tp, tb, td, tf, te, z->tx_outstanding, z->tx_next);
		/* ROUND 37: the red team's falsifier for the TX-backlog hypothesis.
		 *
		 * tx_outstanding is a SOFTWARE estimate fed by TMQ+0x68, a register
		 * this project already recorded twice as "not a completion counter"
		 * (R63/R64) - and it climbs monotonically (5 -> 81 -> 142 -> 173 ->
		 * 177) while tx_fifo_errors stays 0, so the drop at RING_ENTRIES was
		 * never reached and cannot have delayed any reply. The estimate is
		 * therefore suspect, and the ground truth is the hardware's own
		 * consume index, which the driver reads at :1034 and :3217 but has
		 * never printed.
		 *
		 * delta is the hardware's un-consumed descriptor count. Three
		 * outcomes, all decisive:
		 *   delta tracks tx_outstanding and both climb -> the hardware really
		 *     is not consuming, the backlog is real, cause is upstream.
		 *   delta stays small while tx_outstanding climbs -> tx_outstanding is
		 *     a phantom, the reclaim hypothesis dies, and the multi-second
		 *     delay is downstream of the ring (hardware egress scheduling).
		 *   delta reaches RING_ENTRIES -> tx_fifo_errors must also increment
		 *     and the frame is ABSENT, not late, which would contradict R132.
		 */
		seq_printf(m, "TXDRAIN tmxidx=%08x credit=%08x sw_next=%u delta=%u\n",
			   readl(z->tmq + TMQ_TXIDX), readl(z->tmq + TMQ_CREDIT),
			   z->tx_next,
			   (z->tx_next - (readl(z->tmq + TMQ_TXIDX) & 0xffff)) & (RING_ENTRIES - 1));
		/* ROUND 38: the gate test. `slow` counts transmits where the
		 * hardware had still not consumed the descriptor 500 us after the
		 * doorbell. If that is near zero, TX is not gated on anything and
		 * the multi-second delay lives after the ring. If it is most of
		 * `n`, the hardware only services the TX doorbell when something
		 * else happens - and the "something else" is the next RX event.
		 */
		seq_printf(m, "TXGATE n=%lu prompt=%lu slow=%lu max_ns=%llu\n",
			   z->tx_drain_n, z->tx_drain_fast, z->tx_drain_slow,
			   z->tx_drain_ns_max);
	}

	/* ROUND 90: per-port MAC_CTRL for all four ports.
	 *
	 * The MAC apertures cannot be read through /proc/zx_eth_poke - doing so
	 * is recorded as hanging the board - and this dump exposed no per-port
	 * MAC state at all, so comparing the working port against the others
	 * was impossible. That comparison is the next step for M7: three of
	 * four ports do not receive, and the per-port MAC registers are
	 * configured by the same warm-skipped init block as everything else.
	 * Reading them here goes through the driver's own ioremap, so it is safe.
	 */
	seq_puts(m, "MACCTRL");
	for (b = 0; b < ZX_NPORTS; b++) {
		unsigned int v = 0;

		/* The proc entry exists before probe publishes zx_dbg_ze. */
		if (zx_dbg_ze && zx_dbg_ze->macs[b])
			v = readl(zx_dbg_ze->macs[b] + MAC_CTRL);
		seq_printf(m, " p%d=%08x", b, v);
	}
	seq_putc(m, '\n');

	/* Ring contents: the decisive question on a cold boot is whether the
	 * hardware writes RX descriptors at all. U-Boot's do (slots 0-1 carry
	 * 0x20 in w2 byte3 after a ping).
	 */
	if (zx_dbg_ze && zx_dbg_ze->ring) {
		for (k = 0; k < 4; k++)
			seq_printf(m, "RXRING %d %08x %08x %08x %08x\n", k,
				   readl((u8 *)zx_dbg_ze->ring + k * 16 + 0),
				   readl((u8 *)zx_dbg_ze->ring + k * 16 + 4),
				   readl((u8 *)zx_dbg_ze->ring + k * 16 + 8),
				   readl((u8 *)zx_dbg_ze->ring + k * 16 + 12));
	}
	if (zx_dbg_ze && zx_dbg_ze->txring) {
		/* ROUND 48: print slots the driver has ACTUALLY written.
		 *
		 * This loop used to print k = 0 and k = 1 unconditionally, and on
		 * this bench both are stale - slot 0 has read `00000080 00010000
		 * 21005c00 000000ba` in every sample ever taken, including runs
		 * with hundreds of transmits. So every conclusion drawn about the
		 * TX descriptor's destination field (rounds 117/46/47) came from
		 * a slot the driver was not using, which is why the round-46 write
		 * was never actually observed.
		 *
		 * `tx_next` is the software cursor and points at the slot about to
		 * be written, so the three slots below it are the three most
		 * recently transmitted - marked with `*` where the descriptor was
		 * enqueued. The trailing marker on the tx_next slot is blank
		 * because that one is not yet written.
		 */
		u32 n = zx_dbg_ze->tx_next;
		int d;

		for (d = -3; d <= 0; d++) {
			u32 s = (u32)((int)n + d) & (RING_ENTRIES - 1);

			seq_printf(m, "TXRING %u%s %08x %08x %08x %08x\n", s,
				   d == 0 ? " " : "*",
				   readl((u8 *)zx_dbg_ze->txring + s * 16 + 0),
				   readl((u8 *)zx_dbg_ze->txring + s * 16 + 4),
				   readl((u8 *)zx_dbg_ze->txring + s * 16 + 8),
				   readl((u8 *)zx_dbg_ze->txring + s * 16 + 12));
		}
	}

	for (b = 0; b < ARRAY_SIZE(zx_blocks); b++) {
		void __iomem *p = ioremap(zx_blocks[b].base, SZ_4K);

		if (!p)
			continue;
		for (k = 0; k < zx_blocks[b].words; k++) {
			u32 val = readl(p + k * 4);

			if (val)
				seq_printf(m, "%s %03x %08x\n",
					   zx_blocks[b].n, k * 4, val);
		}
		iounmap(p);
	}
	return 0;
}

/* R199: fixed, bounded windows; never enlarge a words count past its mapping.
 * Emit zero values too: a missing line must not masquerade as a reset default.
 * Unlike the legacy dump, this path does not read MAC or live TMQ counters.
 */
static void zx_path_dump(struct seq_file *m, const char *name, u32 base,
			 unsigned int first, unsigned int bytes)
{
	void __iomem *p;
	unsigned int off;

	if (first > SZ_4K || bytes > SZ_4K - first) {
		seq_printf(m, "PATH ERROR %s invalid window\n", name);
		return;
	}
	seq_printf(m, "PATH %s %08x..%08x\n", name,
		   base + first, base + first + bytes - 1);
	p = ioremap(base, SZ_4K);
	if (!p) {
		seq_printf(m, "PATH ERROR %s map failed\n", name);
		return;
	}
	for (off = first; off < first + bytes; off += sizeof(u32)) {
		u32 phys = base + off;
		u32 val;

		/* PP2's TMQ instance: conservatively exclude the analogues of
		 * class-0/class-1 read-clear credit registers BEFORE readl.
		 * This is not an exhaustive safe-read whitelist for PP2.
		 */
		if (phys == 0x92164058 || phys == 0x92164068) {
			seq_printf(m, "PATHREG %08x SKIP credit analogue\n", phys);
			continue;
		}
		val = readl(p + off);
		seq_printf(m, "PATHREG %08x %08x\n", phys, val);
		if (phys == 0x921d9068)
			seq_printf(m, "PATHATTACH enable=%02x status=%02x\n",
				   val & 0x1f, (val >> 5) & 0x1f);
	}
	iounmap(p);
}

static int zx_path_regs_show(struct seq_file *m, void *v)
{
	int page = (long)m->private - 1;

	if (zx_dbg_ze && READ_ONCE(zx_dbg_ze->resetting)) {
		seq_puts(m, "PATHDUMP datapath reset in progress\n");
		return 0;
	}
	seq_printf(m, "PATHDUMP R199 pp2_page=%d (sequential read; seek/reopen resamples)\n",
		   page);
	zx_path_dump(m, "SW-SBRG", 0x92310000, 0, 0x800);
	zx_path_dump(m, "PP-SBRG", 0x92388000, 0, 0x800);
	zx_path_dump(m, "NPP-ATTACH", 0x921d9000, 0x68, 4);
	/* 0x92000000 is the fabric reset block, NOT MAC0 (0x92200000).
	 * Read exactly +8, never sweep it and never write it here.
	 */
	zx_path_dump(m, "FABRIC-RESET", 0x92000000, 8, 4);
	if (page >= 0) {
		seq_puts(m, "PATH WARNING PP2 page is unvetted; reads may have side effects\n");
		zx_path_dump(m, "PP2", 0x92140000 + page * SZ_4K, 0, SZ_4K);
	}
	seq_puts(m, "PATHDUMP END\n");
	return 0;
}

static int zx_regs_open(struct inode *i, struct file *f)
{
	int page;

	if (!READ_ONCE(zx_regs_path_only))
		return single_open(f, zx_regs_show, NULL);
	page = READ_ONCE(zx_regs_pp2_page);
	if (page < -1 || page >= 64)
		return -EINVAL;
	/* Snapshot mode and page at open. At most 2050 word lines plus headers
	 * (<64 KiB); preallocate 128 KiB so seq_file need not grow and repeat
	 * MMIO reads during an ordinary sequential read. No persistent snapshot
	 * is promised across lseek or reopen. No MAC/datapath writes are added.
	 */
	return single_open_size(f, zx_path_regs_show, (void *)(long)(page + 1),
				SZ_128K);
}

static const struct proc_ops zx_regs_pops = {
	.proc_open = zx_regs_open,
	.proc_read = seq_read,
	.proc_lseek = seq_lseek,
	.proc_release = single_release,
};

/* /proc/zx_eth_fc - the BM_FREECNT change log filled by zx_eth_poll().
 *
 * One line per change, with the frame count at which it happened. The point is
 * to pin bit 30's transition to an exact rx_packets value: if it sets well
 * before the wedge it is a cause, if it sets at the same frame the datapath
 * stops it is a symptom. Userspace sampling could not tell the two apart.
 */

/* ROUND 39: the vendor's TX reclaim cadence, which this driver did not have.
 *
 * pon_tm_timer_func @0x915c self-rearms every jiffy and calls
 * pon_tm_check_tx_done_nolock @0x900c, which reads TMQ+0x58 (class 0) and
 * TMQ+0x68 (class 1) to reclaim completed descriptors. Our driver read
 * TMQ+0x68 in exactly one place - the TOP of zx_eth_start_xmit - so a reply
 * enqueued at the END of xmit had nothing to release it until the next xmit,
 * i.e. until the next inbound frame. That is why latency tracked the ping
 * interval, and why flooding the link with traffic the board had to ANSWER
 * collapsed the average RTT from 2454 ms to 49.8 ms (R135).
 *
 * A timer is required rather than a hook on the RX path: the reply is
 * enqueued AFTER the RX work for its own request has completed, so any
 * traffic-driven hook reproduces exactly the same one-event lag.
 */
static void zx_tx_done_timer(struct timer_list *t)
{
	struct zx_eth *ze = from_timer(ze, t, tx_timer);
	unsigned long flags;
	u32 c;

	spin_lock_irqsave(&ze->tx_lock, flags);
	/* ROUND 67: use TMQ+0x68 ALONE - this part is right and is kept.
	 *
	 * Our transmit path only ever enqueues on class 1 (doorbell TMQ+0x64), and
	 * TMQ+0x58 is class 0's counter - the vendor reads the two on mutually
	 * exclusive branches and never sums them. Adding a class we never enqueue
	 * on can only over-credit the reclaim.
	 *
	 * ROUND 68: the R66/R67 back-pressure built on this reading is REVERTED.
	 * The vendor archaeologist found that TMQ+0x68 is READ-CLEAR and therefore
	 * may have exactly one consumer, and this file had four - here, the DIG
	 * dump, the TXDRAIN probe and the old xmit reclaim. Any /proc read
	 * between two ticks eats that interval's completions permanently, so the
	 * instrument was consuming the counter the control loop depended on. That
	 * is R161's lesson repeating at the system level, and it means the gauge
	 * is not trustworthy enough to gate a queue on.
	 */
	c = readl(ze->tmq + TMQ_CREDIT) & 0xffff;
	if (c)
		ze->tx_outstanding -= min(c, ze->tx_outstanding);
	spin_unlock_irqrestore(&ze->tx_lock, flags);

	/* Not while zx_dp_reset_work() holds the fabric in reset: a TM register
	 * read then is not known to be safe. The reset re-arms the timer.
	 */
	if (!ze->removing && !READ_ONCE(ze->resetting))
		mod_timer(&ze->tx_timer, jiffies + 1);
}

/* ROUND 57: seed the two BPPE free-list tables. THIS IS THE ROOT-CAUSE FIX.
 *
 * The driver already programs the free-list BASES - TMC+0xe8 = 0x41800000 and
 * TMC+0xec = 0x41808000 - but it never writes a single byte to either table,
 * and the vendor fills both with a big-endian self-index before enabling the
 * BM. Disassembled from ZTE's own U-Boot TM driver inside uboot-F610GV9.bin
 * (load base 0x47EDF800), function 0x47f342ec, ZX279128S path:
 *
 *     47f3438c: rev16 lr, r1          ; big-endian 16-bit index
 *     47f34390: add   r1, r1, #1
 *     47f34394: cmp   r1, #2048
 *     47f34398: strh  lr, [r12, #2]!  ; 2048 entries -> 0x41800000
 *     47f343b0: cmp   r1, #512
 *     47f343b4: strh  lr, [r12, #2]!  ;  512 entries -> 0x41808000
 *
 * Slot i contains the value i, big-endian, for i = 0..BUF_COUNT-1 and
 * i = 0..BUF2_COUNT-1. Semantically identical to the ZX279133 driver's
 * `iowrite16be(i, bmu_mem + 2 * i)` - which is what first predicted this.
 *
 * A zeroed table gives head = 0 and next[0] = 0, so zx_bm_alloc() returns
 * index 0 for ever. That single fact explains the whole symptom chain:
 *
 *   1. bp is always 0, so the TX descriptor (which carries only the bp index)
 *      makes the hardware read its payload from 0x41000000 + 0*2048 + 16 =
 *      0x41000010 AT DRAIN TIME.
 *   2. zx_bm_free() is called only on the RX path, so TX never rotates that
 *      buffer and every reply is built into the same 2 KiB.
 *   3. When the TM drains a descriptor late, it transmits whatever is in the
 *      buffer at that moment - a much later frame, carrying that frame's ICMP
 *      identifier. That is the "stale reply with a foreign id" measured in
 *      R158: reply id 15997 seq 3 arriving before the host sent seq 3.
 *
 * It also explains why moving TX failed twice (round 57 by index, round 43 by
 * pool): the problem was never where TX writes, it was that the allocator
 * could not hand out a second buffer at all, so moving TX off index 0 broke
 * the read path while the collision remained.
 *
 * The vendor's order, which this follows: BM+0x00 = 0 (disable), program
 * thresholds and index-max, SEED THE TABLES, program the bases, then enable.
 * Only the seed and the disable/enable bracket are done here, because the
 * bases and thresholds are already correct in every sample we have read.
 */
static void zx_bm_seed_freelists(struct zx_eth *ze)
{
	void __iomem *fl = ze->freelists;
	u32 i;

	writel(0, ze->bm + BM_ENABLE);
	/* ROUND 82 REVERTED: the BM+0x60/+0x64 "release credit" write is REFUTED.
	 *
	 * The web researcher hypothesised that +0x60/+0x64 (RLS_CFG, COUNT << 16 in
	 * the ZX279133 driver) were missing from our init and that their absence
	 * made the BM swallow BM+0x10 writes. The vendor archaeologist then read
	 * BOTH vendor implementations and found the vendor's complete BM register
	 * set is 0x00, 0x04, 0x08, 0x0c, 0x10, 0x14, 0x48, 0x4c, 0x58, 0x5c, 0xdc
	 * - no 0x60, no 0x64, no 0x20030/0x20034, no 0x78. Those ZX279133 names
	 * belong to a DIFFERENT BM block, so +0x60/+0x64 reading 0 is normal here.
	 *
	 * The free gate is a single thing: a software copy of BM+0xdc bits[8:3],
	 * refilled on demand - byte-for-byte the same algorithm in U-Boot
	 * (0x47f3466c, 4 retries) and in the kernel module (0x82d4, 200 retries).
	 * Our decode of that register is already instruction-identical. And with
	 * freenocredit=0 our zx_bm_free never failed for want of credit, so our
	 * frees ARE being issued - a flat BM+0xdc with traffic flowing is steady
	 * state, not a swallowed write.
	 *
	 * Reverted rather than left in because the vendor never writes these
	 * offsets and we do not know what they alias on this block.
	 */
	for (i = 0; i < BUF_COUNT; i++)
		writew(cpu_to_be16(i), (u8 *)fl + i * 2);
	for (i = 0; i < BUF2_COUNT; i++)
		writew(cpu_to_be16(i), (u8 *)fl + 0x8000 + i * 2);
	/* Publish both tables before the buffer manager is told to use them. */
	wmb();
	writel(1, ze->bm + BM_ENABLE);

	dev_info(ze->dev,
		 "bm: BPPE free lists seeded (%u normal, %u jumbo), readback [0]=%04x [1]=%04x [2047]=%04x\n",
		 BUF_COUNT, BUF2_COUNT,
		 readw((u8 *)fl + 0), readw((u8 *)fl + 2),
		 readw((u8 *)fl + (BUF_COUNT - 1) * 2));
}

static void zx_napi_delete(void *data)
{
	struct zx_eth *ze = data;

	/* The reset work re-arms the TX timer, so it goes first. It bails
	 * without touching the ports once zx_eth_close_ports() set removing.
	 */
	cancel_delayed_work_sync(&ze->reset_work);
	cancel_delayed_work_sync(&ze->wd_work);
	cancel_delayed_work_sync(&ze->rx_retry);
	timer_shutdown_sync(&ze->tx_timer);
	netif_napi_del(&ze->napi);
}

static void zx_eth_disarm(void *data)
{
	struct zx_eth *ze = data;
	int port;

	/* Registered before ring mappings and callbacks: their devres cleanup
	 * runs first. Only the permanent MAC/TM/BM mappings are used here.
	 * These understood operations stop ingress and the known engines; they
	 * do not establish that undocumented egress DMA has completely drained.
	 */
	WRITE_ONCE(ze->removing, true);
	cancel_delayed_work_sync(&ze->rx_retry);
	timer_shutdown_sync(&ze->tx_timer);
	for (port = 0; port < ZX_NPORTS; port++)
		zx_mac_enable(ze, port, false);
	writel(readl(ze->tmc + TMC_IRQ_MASK) | 7, ze->tmc + TMC_IRQ_MASK);
	writel(0, ze->bm + BM_ENABLE);
}

static void zx_eth_close_ports(void *data)
{
	struct zx_eth *ze = data;
	int port;

	/* Close every port while all netdev pointers are still alive. */
	rtnl_lock();
	ze->removing = true;
	for (port = 0; port < ZX_NPORTS; port++)
		if (ze->ports[port])
			dev_close(ze->ports[port]);
	dev_close(ze->ndev);
	rtnl_unlock();
}

/* ZX_TX_ORIGIN_R204_HELPER_BEGIN */
static void zx_tx_origin_init(struct zx_eth *ze, bool datapath_initialized)
{
	/* Keep the existing single read; only the selected software origin
	 * changes after successful full initialization. Warm/skip retain it.
	 */
	u32 raw = readl(ze->tmq + TMQ_TXIDX);
	u32 inherited = (raw & 0xffff) % RING_ENTRIES;

	ze->tx_next = datapath_initialized ? 0 : inherited;
	dev_info(ze->dev,
		 "TXORIGIN_R204 raw=%08x inherited=%u selected=%u initialized=%u slot_mode=%u\n",
		 raw, inherited, ze->tx_next, datapath_initialized ? 1u : 0u,
		 zx_tx_slot_mode);
}
/* ZX_TX_ORIGIN_R204_HELPER_END */

/* Full datapath re-initialisation, the recovery for a stopped RX path.
 *
 * Two things ask for it (zx_dp_request_reset()): a pending count larger than
 * the ring, which means the producer lapped the consumer and the slots in
 * between are gone, and the watchdog finding descriptors pending with no
 * return issued for rx_stall_ms. Neither has an in-place repair - the vendor
 * code has none either, and every comparable driver (mtk_eth_soc, ag71xx)
 * answers a sticky datapath fault with a full reset from a work item.
 *
 * The sequence reuses code that already runs on every boot:
 *
 *   1. dev_close() every open port. The ordinary stop path masks the TM IRQ,
 *      disables NAPI and MAC ingress, and detaches the PHYs.
 *   2. zx_eth_datapath_init(), exactly as a cold probe runs it: fabric reset,
 *      TM queue-state reset (clears RED occupancy and the ring pointers), BM
 *      registers and seeded free lists, rings, RED tables including the
 *      CPU-queue cap, PP and MAC configuration.
 *   3. Reset the software ownership state to what a cold probe leaves: every
 *      ring cursor, count and debt to zero, TX origin 0. Nothing the hardware
 *      held survives the reset, so there is nothing to hand back.
 *   4. dev_open() the same ports. PHYs reattach and adjust_link reprograms
 *      speed and ingress; the first open restarts NAPI and the watchdog.
 *
 * Ports flap for a few seconds and in-flight frames are lost; the alternative
 * was a datapath stopped until a power cycle. Resets are spaced by
 * ZX_RESET_INTERVAL and stop after ZX_RESET_MAX_CONSEC with no RX in between,
 * so a fault the reset cannot clear cannot turn into a reset loop.
 */
static void zx_dp_reset_work(struct work_struct *work)
{
	struct zx_eth *ze = container_of(to_delayed_work(work), struct zx_eth,
					 reset_work);
	struct net_device *open[ZX_NPORTS + 1];
	unsigned int n = 0, i;
	bool manual;
	int port, q, ret;

	rtnl_lock();
	manual = READ_ONCE(ze->reset_manual);
	WRITE_ONCE(ze->reset_manual, false);
	if (ze->removing)
		goto out;
	if (!manual && ze->n_resets &&
	    time_before(jiffies, ze->last_reset + ZX_RESET_INTERVAL)) {
		schedule_delayed_work(&ze->reset_work,
				      ze->last_reset + ZX_RESET_INTERVAL - jiffies);
		goto out;
	}
	if (netif_running(ze->ndev))
		open[n++] = ze->ndev;
	for (port = 0; port < ZX_NPORTS; port++)
		if (ze->ports[port] && netif_running(ze->ports[port]))
			open[n++] = ze->ports[port];
	if (!n && !READ_ONCE(ze->rx_fault) && !manual)
		goto out;	/* closed since the request, and nothing latched */
#ifdef CONFIG_ZX279128_PP_TABLES
	/* Diagnostic builds only. The cold packet-processor bring-up inside
	 * zx_eth_datapath_init() parks the PM/ACL table bases at the reserved
	 * DDR window (PP-KEY.md section 16) and zx_pp_tables_init() owns the
	 * real tables; re-running it under live tables would leave the CLA
	 * walking the parked bases. Do not reset under live tables.
	 */
	if (ze->pp) {
		netdev_err(ze->ndev, "datapath reset refused: packet-processor tables are live (%s)\n",
			   READ_ONCE(ze->reset_reason));
		goto out;
	}
#endif
	if (manual) {
		/* A deliberate reset says nothing about whether the last one
		 * helped: leave the give-up count alone.
		 */
	} else if (ze->n_resets && READ_ONCE(ze->n_desc_rls) == ze->reset_rls) {
		if (++ze->reset_consec >= ZX_RESET_MAX_CONSEC) {
			netdev_err(ze->ndev,
				   "datapath reset: %u in a row with no RX in between, giving up (%s)\n",
				   ze->reset_consec, READ_ONCE(ze->reset_reason));
			goto out;
		}
	} else {
		ze->reset_consec = 0;
	}

	netdev_warn(ze->ndev,
		    "datapath reset #%lu: %s; tmd_go=%08x bm_freecnt=%08x tmc_mask=%08x inflight=%d desc_rls=%lu desc_busy=%lu\n",
		    ze->n_resets + 1, READ_ONCE(ze->reset_reason),
		    readl(ze->tmd + TMD_GO), readl(ze->bm + BM_FREECNT),
		    readl(ze->tmc + TMC_IRQ_MASK), ze->rx_inflight,
		    ze->n_desc_rls, ze->n_desc_busy);
	for (q = 0; q < ZX_RX_QUEUES; q++) {
		u32 pend = readl(ze->tmq + TMQ_PENDING + q * 4);

		if (pend)
			netdev_warn(ze->ndev, "datapath reset: q%d pend=%08x cursor %u/%u\n",
				    q, pend, ze->rxq[q].cursor,
				    ze->rxq[q + ZX_RX_QUEUES].cursor);
	}

	for (i = 0; i < n; i++)
		dev_close(open[i]);
	if (ze->dp_users) {
		/* Not reachable through this driver's own open/stop pairing. */
		netdev_err(ze->ndev, "datapath reset: %u users after closing every port, not resetting\n",
			   ze->dp_users);
		goto reopen;
	}

	WRITE_ONCE(ze->resetting, true);
	del_timer_sync(&ze->tx_timer);
	ret = zx_eth_datapath_init(ze);
	for (q = 0; !ret && q < ZX_RX_QUEUES; q++)
		if (readl(ze->tmq + TMQ_PENDING + q * 4))
			ret = -EIO;	/* the probe's own post-init check */
	if (!ret && (readl(ze->tmd + TMD_GO) & 1))
		ret = -EBUSY;
	/* The rest of the probe's post-init sequence, in the probe's order. The
	 * fabric reset in zx_eth_datapath_init() also resets the switch bridge,
	 * so the software port policy (learning off, per-port isolation,
	 * unknown-unicast to CPU, FDB clear, transparent VLANs) must be
	 * re-applied: without it a reset would leave the WAN and LAN ports
	 * bridged in hardware.
	 */
	if (!ret)
		ret = zx_eth_software_ports(ze);
	if (!ret)
		ret = zx_eth_cpu_protocols(ze);
	if (!ret) {
		writel(readl(ze->tmc + 0x00) | 0x40, ze->tmc + 0x00);	/* gap_add */
		zx_bm_seed_freelists(ze);
		writel(readl(ze->tmc + TMC_IRQ_MASK) | 7, ze->tmc + TMC_IRQ_MASK);
	}
	memset(ze->rxq, 0, sizeof(ze->rxq));
	ze->rx_next = 0;
	ze->rx_inflight = -1;
	ze->rx_blocked_polls = 0;
	ze->rx_seed_eligible = false;
	ze->tx_outstanding = 0;
	memset(ze->tx_bp, 0xff, sizeof(ze->tx_bp));
	zx_tx_origin_init(ze, true);
	WRITE_ONCE(ze->rx_fault, ret != 0);
	WRITE_ONCE(ze->resetting, false);
	mod_timer(&ze->tx_timer, jiffies + 1);
	ze->n_resets++;
	ze->last_reset = jiffies;
	ze->reset_rls = READ_ONCE(ze->n_desc_rls);
	if (ret) {
		netdev_err(ze->ndev, "datapath reset failed (%d); ports left down\n", ret);
		goto out;
	}

reopen:
	for (i = 0; i < n; i++) {
		ret = dev_open(open[i], NULL);
		if (ret)
			netdev_err(open[i], "reopen after datapath reset failed (%d)\n", ret);
	}
	netdev_info(ze->ndev, "datapath reset #%lu done, %u port(s) reopened\n",
		    ze->n_resets, n);
out:
	rtnl_unlock();
}

static int zx_eth_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct net_device *ndev;
	struct zx_eth *ze;
	u32 rxb, txb;
	/* ZX_TX_ORIGIN_R204_LOCAL_BEGIN */
	bool datapath_initialized = false;
	/* ZX_TX_ORIGIN_R204_LOCAL_END */
	int i;
	int ret;

	ndev = devm_alloc_etherdev(dev, sizeof(*ze));
	if (!ndev)
		return -ENOMEM;
	SET_NETDEV_DEV(ndev, dev);

	ze = netdev_priv(ndev);
	ze->ndev = ndev;
	ze->dev = dev;
	ze->rx_inflight = -1;
	/* ZX_RX_SEED_R202_INIT_BEGIN */
	ze->rx_q0_seed = -1;
	/* ZX_RX_SEED_R202_INIT_END */
	spin_lock_init(&ze->bm_lock);
	spin_lock_init(&ze->tx_lock);
	spin_lock_init(&ze->irq_lock);
	INIT_DELAYED_WORK(&ze->rx_retry, zx_rx_retry_work);
	INIT_DELAYED_WORK(&ze->wd_work, zx_wd_work);
	INIT_DELAYED_WORK(&ze->reset_work, zx_dp_reset_work);
	timer_setup(&ze->tx_timer, zx_tx_done_timer, 0);
	memset(ze->tx_bp, 0xff, sizeof(ze->tx_bp));
	ze->irq = platform_get_irq_byname(pdev, "tm");
	if (ze->irq < 0)
		return ze->irq;

	ze->mac = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(ze->mac))
		return PTR_ERR(ze->mac);
	ret = zx_eth_resolve_regs(ze, pdev);
	if (ret)
		return ret;

	/* reg[0] is the bound port's MAC window. */
	ze->bound_port = -1;
	{
		struct resource *r = platform_get_resource(pdev, IORESOURCE_MEM, 0);

		for (i = 0; r && i < ZX_NPORTS; i++)
			if (r->start == ze->phys[ZX_REG_MAC0 + i])
				ze->bound_port = i;
	}
	ret = zx_eth_phy_modes(ze);
	if (ret)
		return ret;
	ret = zx_eth_resolve_ddr(ze);
	if (ret)
		return ret;
	/* Map all four MAC windows. datapath_init() already writes the full
	 * per-port config to each of them through its own temporary ioremaps;
	 * these persistent maps are what let ndo_open enable them.
	 */
	for (i = 0; i < ZX_NPORTS; i++) {
		ze->macs[i] = devm_ioremap(dev, ze->phys[ZX_REG_MAC0 + i], SZ_4K);
		if (!ze->macs[i])
			return -ENOMEM;
	}

	ze->bm = devm_ioremap(dev, ze->phys[ZX_REG_BM], SZ_4K);
	ze->tmc = devm_ioremap(dev, ze->phys[ZX_REG_TMC], SZ_4K);
	ze->tmd = devm_ioremap(dev, ze->phys[ZX_REG_TMD], SZ_4K);
	ze->tmq = devm_ioremap(dev, ze->phys[ZX_REG_TMQ], SZ_4K);
	if (!ze->bm || !ze->tmc || !ze->tmd || !ze->tmq)
		return -ENOMEM;
	ret = devm_add_action_or_reset(dev, zx_eth_disarm, ze);
	if (ret)
		return ret;

	ze->bufs = devm_ioremap_wc(dev, ze->ddr_phys + ZX_DDR_POOL, BUF_COUNT * BUF_SIZE);
	ze->freelists = devm_ioremap_wc(dev, ze->ddr_phys + ZX_DDR_FREELIST, 0x8400);
	if (!ze->bufs || !ze->freelists)
		return -ENOMEM;

	/* Full initialization establishes queue/buffer ownership even after
	 * U-Boot TFTP. The legacy attach paths require a debug build.
	 */
	if (IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG) && zx_skip_dp_init) {
		dev_info(dev, "datapath init SKIPPED (skip_dp_init=1) - attaching\n");
		ze->dp_inited = true;
		goto warm;
	}
	if (IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG) && !zx_force_dp_init && zx_datapath_warm(ze)) {
		dev_info(dev, "datapath warm (rx ring %08x tx ring %08x) - init skipped\n",
			 readl(ze->tmc + TMC_RING_BASE),
			 readl(ze->tmq + TMQ_TXRING));
		/* ZX_RX_SEED_R202_WARM_BEGIN */
		ze->rx_seed_eligible = true;
		/* ZX_RX_SEED_R202_WARM_END */
		ze->dp_inited = true;
		goto warm;
	}
	dev_info(dev, "datapath init at probe (cold)\n");
	/* A warm producer cannot be recovered from the eight-bit counter.
	 * Reset state and pools on every probe before assigning zero cursors.
	 */
	ret = zx_eth_datapath_init(ze);
	if (ret)
		return dev_err_probe(dev, ret, "datapath initialization failed\n");
	ze->dp_inited = true;
	for (i = 0; i < ZX_RX_QUEUES; i++)
		if (readl(ze->tmq + TMQ_PENDING + i * 4))
			return dev_err_probe(dev, -EIO,
					     "RX queues not empty after initialization\n");
	if (readl(ze->tmd + TMD_GO) & 1)
		return dev_err_probe(dev, -EBUSY, "descriptor return busy after initialization\n");
	/* ZX_TX_ORIGIN_R204_INITIALIZED_BEGIN */
	datapath_initialized = true;
	/* ZX_TX_ORIGIN_R204_INITIALIZED_END */
warm:
	/* Reset/setup may change the ring bases; map their final values. */
	rxb = readl(ze->tmc + TMC_RING_BASE);
	txb = readl(ze->tmq + TMQ_TXRING);
	if (rxb != ze->ddr_phys + ZX_DDR_RX_RING || txb != ze->ddr_phys + ZX_DDR_TX_RING)
		return dev_err_probe(dev, -EINVAL, "invalid RX/TX ring bases\n");
	ze->ring = devm_ioremap_wc(dev, rxb, ZX_RX_MAP_SIZE);
	ze->txring = devm_ioremap_wc(dev, txb, RING_ENTRIES * DESC_SIZE);
	ze->rx_ring_phys = rxb;
	ze->tx_ring_phys = txb;
	ze->bufs2 = devm_ioremap_wc(dev, ze->ddr_phys + ZX_DDR_POOL2, BUF2_COUNT * BUF_SIZE);
	if (!ze->bufs || !ze->bufs2 || !ze->ring || !ze->txring)
		return -ENOMEM;
	dev_info(dev, "rx ring=%08x tx ring=%08x\n", rxb, txb);
	/* ROUND 56 REVERTED: rx descriptor priming removed. It made `idx` vary
	 * (1,2,3,...) exactly as intended, but on a CLEAN boot it killed receive
	 * outright: ping 100% loss, RXCENSUS all zeros. Writing buffer indices
	 * into the descriptors is therefore not something the hardware wants in
	 * this configuration. See handoff.md round 56.
	 */
	/* ZX_TX_ORIGIN_R204_ASSIGN_BEGIN */
	zx_tx_origin_init(ze, datapath_initialized);
	/* ZX_TX_ORIGIN_R204_ASSIGN_END */

	ret = zx_eth_software_ports(ze);
	if (ret)
		return ret;
	ret = zx_eth_cpu_protocols(ze);
	if (ret)
		return ret;

	/* Finish the established pool/gap configuration before any netdev can
	 * be opened by hotplug or netifd. Keep IRQs masked until first open.
	 */
	writel(readl(ze->tmc + 0x00) | 0x40, ze->tmc + 0x00);
	zx_bm_seed_freelists(ze);
	writel(readl(ze->tmc + TMC_IRQ_MASK) | 7, ze->tmc + TMC_IRQ_MASK);

	dev_info(dev, "bm=%08x tmc=%08x tmq=%08x ring_base=%08x cfg=%08x\n",
		 (u32)ze->phys[ZX_REG_BM], (u32)ze->phys[ZX_REG_TMC],
		 (u32)ze->phys[ZX_REG_TMQ],
		 readl(ze->tmc + TMC_RING_BASE), readl(ze->tmc + TMC_CFG));

#ifdef CONFIG_ZX279128_PP_TABLES
	/* Only after this probe ran the packet-processor bring-up inside
	 * zx_eth_datapath_init(). Not fatal: the datapath does not use it.
	 */
	if (ze->pp_bring_up)
		ze->pp = zx_pp_tables_init(dev);
	else
		dev_info(dev, "pp: no bring-up by this probe; table access disabled\n");
#endif

	ndev->netdev_ops = &zx_eth_netdev_ops;
	netif_napi_add(ndev, &ze->napi, zx_eth_poll);
	ret = devm_add_action_or_reset(dev, zx_napi_delete, ze);
	if (ret)
		return ret;
	/* Mask every TM source before the line is requested. Cold init already
	 * wrote all ones; a warm attach inherits U-Boot's mask, and a source
	 * left unmasked there is one zx_eth_irq() answers IRQ_NONE to until the
	 * kernel disables the whole line. The first open unmasks bits 0 and 1.
	 */
	writel(0xffffffff, ze->tmc + TMC_IRQ_MASK);
	ret = devm_request_irq(dev, ze->irq, zx_eth_irq, 0, dev_name(dev), ze);
	if (ret)
		return dev_err_probe(dev, ret, "failed to request TM IRQ\n");

	/* Only stash the PHY node here. Connecting a PHY to a netdev that is
	 * not yet registered leaves the device half-initialised, and the
	 * resulting netdev notifier events crashed pppoe_device_event().
	 * Connect in ndo_open() like other drivers do.
	 */
	{
		struct device_node *np = zx_port_node(dev, ze->bound_port);

		/* Prefer the per-port node; fall back to the legacy top-level
		 * phy-handle so an older device tree still probes.
		 */
		ze->phy_np = np ? of_parse_phandle(np, "phy-handle", 0) : NULL;
		if (!ze->phy_np)
			ze->phy_np = of_parse_phandle(dev->of_node,
						      "phy-handle", 0);
		zx_set_mac_from_dt(ze, ndev, np, ze->bound_port);
		if (ze->bound_port >= 0)
			snprintf(ndev->name, IFNAMSIZ, "eth%d", ze->bound_port);
		of_node_put(np);
	}
	ret = devm_add_action_or_reset(dev, zx_phy_node_put, ze->phy_np);
	if (ret)
		return ret;

	/* Populate every ingress lookup before publishing even the first port.
	 * All allocations precede registrations, so devres unregisters every
	 * visible netdev before freeing any pointer used by RX demultiplexing.
	 */
	if (zx_split_ports) {
		for (i = 0; i < ZX_NPORTS; i++) {
			if (i == ze->bound_port)
				continue;
			ret = zx_eth_prepare_port_ndev(ze, i);
			if (ret)
				return dev_err_probe(dev, ret, "port %d allocation failed\n", i);
		}
	}
	ret = devm_add_action_or_reset(dev, zx_eth_close_ports, ze);
	if (ret)
		return ret;
	/* All mappings, pools and software state are now ready for callbacks. */
	mod_timer(&ze->tx_timer, jiffies + 1);

	ret = devm_register_netdev(dev, ndev);
	if (ret)
		return dev_err_probe(dev, ret, "failed to register netdev\n");

	if (zx_split_ports) {
		int p;

		/* One netdev per physical port. The DT-bound port keeps the
		 * primary netdev; the others get their own so the bridge and
		 * netifd can finally express a per-port choice (WAN vs LAN).
		 *
		 * Compare by PORT INDEX, not by pointer: ze->mac and
		 * ze->macs[n] are two independent ioremaps of the same physical
		 * window, so their addresses differ and a pointer test silently
		 * never matches - which gave the bound port two netdevs.
		 */
		for (p = 0; p < ZX_NPORTS; p++) {
			if (p == ze->bound_port)
				continue;
			ret = zx_eth_add_port_ndev(ze, p);
			if (ret) {
				zx_eth_close_ports(ze);
				return dev_err_probe(dev, ret, "port %d netdev failed\n", p);
			}
		}
	}
	platform_set_drvdata(pdev, ndev);
	/* ZX_RX_SEED_R202_DEFER_PUBLISH */
	zx_eth_singleton = ze;
	/* ZX_RX_SEED_R202_PUBLISH_BEGIN */
	/* No failed-probe path may leave a parameter-accessible pointer. */
	zx_rx_seed_publish(ze);
	/* ZX_RX_SEED_R202_PUBLISH_END */
	if (ZX_HAVE_DEBUG_IFACES) {
		/* Bring-up instrumentation only - see Kconfig. zx_eth_poke in
		 * particular is an arbitrary physical read/modify/write
		 * primitive and must not ship enabled.
		 */
		proc_create("zx_eth_regs", 0444, NULL, &zx_regs_pops);
		proc_create("zx_eth_packets", 0444, NULL, &zx_packets_pops);
		proc_create("zx_eth_poke", 0200, NULL, &zx_poke_pops);
		proc_create("zx_eth_reinit", 0200, NULL, &zx_reinit_pops);
		proc_create("zx_eth_spa_ram", 0200, NULL, &zx_spa_ram_pops);

		if (zx_irq_probe) {
			static const char * const names[ZX_IRQ_PROBE_MAX] = {
				"idm", "gephy0", "gephy1", "gephy2", "gephy3",
			};
			unsigned int i;

			for (i = 0; i < ZX_IRQ_PROBE_MAX; i++) {
				int irq = platform_get_irq_byname_optional(pdev,
								names[i]);

				if (irq < 0)
					continue;
				if (devm_request_irq(dev, irq,
						     zx_irq_probe_handler, 0,
						     names[i],
						     (void *)(uintptr_t)i)) {
					dev_warn(dev, "irqprobe: %s (%d) not grantable\n",
						 names[i], irq);
					continue;
				}
				zx_irq_nums[i] = irq;
				zx_irq_probe_n++;
				dev_info(dev, "irqprobe: watching %s = irq %d\n",
					 names[i], irq);
			}
		}
	}
	return 0;
}

static const struct of_device_id zx_eth_of_match[] = {
	{ .compatible = "zte,zx279128s-eth" },
	{ }
};
MODULE_DEVICE_TABLE(of, zx_eth_of_match);

/* Unbind path. Everything acquired in probe is devm-managed EXCEPT the four
 * /proc entries, the phy-handle reference and the two module-global pointers -
 * so without this the driver could only ever be built in.
 *
 * The /proc entries are the ones that matter: their proc_ops live in module
 * text, so leaving them behind across an rmmod turns any later read or write of
 * /proc/zx_eth_* into a jump into freed memory. A second insmod would also find
 * the names already taken.
 *
 * This exists so the driver can be built =m for bring-up, which turns each
 * register experiment from a build-flash-boot cycle into
 *   rmmod zx279128_eth; insmod zx279128_eth.ko force_dp_init=1 tx_w1=0x00050000
 * See Kconfig: the /proc interfaces must still never ship enabled.
 */
static void zx_eth_remove(struct platform_device *pdev)
{
	struct net_device *ndev = platform_get_drvdata(pdev);
	struct zx_eth *ze = netdev_priv(ndev);

	zx_eth_close_ports(ze);
#ifdef CONFIG_ZX279128_PP_TABLES
	/* Clears the PM/ACL bases before their DMA tables are freed. */
	zx_pp_tables_remove(ze->pp);
	ze->pp = NULL;
#endif
	if (ZX_HAVE_DEBUG_IFACES) {
		remove_proc_entry("zx_eth_spa_ram", NULL);
		remove_proc_entry("zx_eth_reinit", NULL);
		remove_proc_entry("zx_eth_poke", NULL);
		remove_proc_entry("zx_eth_regs", NULL);
		remove_proc_entry("zx_eth_packets", NULL);
	}

	/* Both are plain module globals consulted by the /proc handlers and by
	 * zx_eth_reinit; clear them before the devres release frees *ze.
	 */
	/* ZX_RX_SEED_R202_UNPUBLISH */
	zx_rx_seed_unpublish(ze);
	zx_eth_singleton = NULL;


	/* The netdev, its NAPI instance, every ioremap and the buffer mapping
	 * are devm-managed and released after this returns. ndo_stop() runs on
	 * unregister and is what cancels the RX hrtimer and drops MAC_CTRL_EN.
	 */
}

static struct platform_driver zx_eth_driver = {
	.probe = zx_eth_probe,
	.remove_new = zx_eth_remove,
	.driver = {
		.name = "zx279128-eth",
		.of_match_table = zx_eth_of_match,
	},
};
module_platform_driver(zx_eth_driver);

MODULE_DESCRIPTION("ZTE ZX279128S Ethernet driver");
MODULE_LICENSE("GPL");
