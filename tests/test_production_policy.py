"""Compile and exercise the production write policy's pure decision functions.

The policy is the transport's second protection layer (the first is the device
tree's read-only partitions). These functions are written to be host-testable:
the allow/deny matrix, boundary offsets, feature-write filtering, row aliasing,
the bank-A refusal in qualification mode, and the first-refusal latch are all
asserted here with no hardware.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import function

SOURCE = Path(__file__).resolve().parents[1] / 'files/target/linux/armsr/files-6.6/drivers/spi/spi-zx279128.c'

MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
#define BIT(n) (1U<<(n))
#define BIT_ULL(n) (1ULL<<(n))
enum spi_mem_data_dir { SPI_MEM_NO_DATA, SPI_MEM_DATA_IN, SPI_MEM_DATA_OUT };
struct spi_mem_op {
 struct { unsigned nbytes,buswidth,dtr,opcode; } cmd;
 struct { unsigned nbytes,buswidth,dtr; u64 val; } addr;
 struct { unsigned nbytes,buswidth,dtr; } dummy;
 struct { unsigned buswidth,dtr,ecc,swap16,nbytes; enum spi_mem_data_dir dir;
          union { void *in; const void *out; } buf; } data;
 unsigned max_freq;
};
struct device { int dummy; };
struct zx_spifc {
 void *base; struct device *dev; unsigned long rate; bool failed,write_test,ubi_test;
 u64 attempted_pages; bool production,production_qualify,policy_latched;
 int bank; u8 latch_opcode; u64 latch_addr; u32 policy_refusals,bank_a_refusals;
};
static unsigned logs;
static void diagnostic(void *dev,const char *fmt,...) { (void)dev;(void)fmt;logs++; }
#define dev_err diagnostic

/* The policy helpers are compiled with the production symbol defined. */
#define CONFIG_SPI_ZX279128_PRODUCTION_POLICY 1
'''

# Byte-level op builders for program (0x10) / erase (0xd8) / set-feature (0x1f).
CASES = r'''
static u8 fbuf;
static struct spi_mem_op prog(unsigned op,u64 row) {
 struct spi_mem_op o; memset(&o,0,sizeof(o));
 o.cmd.opcode=op; o.cmd.nbytes=o.cmd.buswidth=1; o.addr.nbytes=3; o.addr.buswidth=1; o.addr.val=row;
 return o;
}
static struct spi_mem_op feat(u64 reg,u8 value) {
 struct spi_mem_op o; memset(&o,0,sizeof(o));
 o.cmd.opcode=0x1f; o.cmd.nbytes=o.cmd.buswidth=1; o.addr.nbytes=1; o.addr.buswidth=1; o.addr.val=reg;
 o.data.dir=SPI_MEM_DATA_OUT; o.data.nbytes=1; o.data.buswidth=1; fbuf=value; o.data.buf.out=&fbuf;
 return o;
}
static struct spi_mem_op bare(unsigned op) {
 struct spi_mem_op o; memset(&o,0,sizeof(o)); o.cmd.opcode=op; o.cmd.nbytes=o.cmd.buswidth=1; return o;
}

int main(void) {
 /* zx_policy_row: program (step 1), production flavour */
 assert(zx_policy_row(false,0,0x10,0x0e00)==ZX_ALLOW);   /* bank A first page */
 assert(zx_policy_row(false,0,0x10,0x0dff)==ZX_DENY);    /* one below bank A */
 assert(zx_policy_row(false,0,0x10,0x2e7f)==ZX_ALLOW);   /* bank A last page */
 assert(zx_policy_row(false,0,0x10,0x2e80)==ZX_DENY);    /* first page past header */
 assert(zx_policy_row(false,0,0x10,0xa800)==ZX_ALLOW);   /* UBI first page */
 assert(zx_policy_row(false,0,0x10,0xa7ff)==ZX_DENY);
 assert(zx_policy_row(false,0,0x10,0xc7ff)==ZX_ALLOW);   /* UBI last page */
 assert(zx_policy_row(false,0,0x10,0xc800)==ZX_DENY);
 assert(zx_policy_row(false,0,0x10,0x10000)==ZX_DENY);   /* aliased row bit */
 assert(zx_policy_row(false,0,0x10,0x1a800)==ZX_DENY);   /* UBI row + alias */
 /* erase (0xd8): must be block aligned (row % 64 == 0) AND inside a window */
 assert(zx_policy_row(false,0,0xd8,0x0e00)==ZX_ALLOW);
 assert(zx_policy_row(false,0,0xd8,0x0e01)==ZX_DENY);    /* unaligned */
 assert(zx_policy_row(false,0,0xd8,0x0e3f)==ZX_DENY);
 assert(zx_policy_row(false,0,0xd8,0x2e40)==ZX_ALLOW);   /* last bank A block */
 assert(zx_policy_row(false,0,0xd8,0x2e80)==ZX_DENY);
 assert(zx_policy_row(false,0,0xd8,0xa800)==ZX_ALLOW);
 assert(zx_policy_row(false,0,0xd8,0xc7c0)==ZX_ALLOW);   /* last UBI block */
 assert(zx_policy_row(false,0,0xd8,0xc800)==ZX_DENY);
 assert(zx_policy_row(false,0,0xd8,0xa820)==ZX_DENY);    /* unaligned in window */
 /* wrong opcode never allowed by row */
 assert(zx_policy_row(false,0,0x02,0xa800)==ZX_DENY);
 /* qualification flavour: bank A is refused, UBI still allowed */
 assert(zx_policy_row(true,0,0x10,0x0e00)==ZX_REFUSE_BANK_A);
 assert(zx_policy_row(true,0,0xd8,0x0e00)==ZX_REFUSE_BANK_A);
 assert(zx_policy_row(true,0,0x10,0xa800)==ZX_ALLOW);
 assert(zx_policy_row(true,0,0x10,0x2e80)==ZX_DENY);

 /* Bank B and unknown metadata cannot grant the inactive firmware. */
 assert(zx_policy_row(false,1,0x10,0x4000)==ZX_ALLOW);
 assert(zx_policy_row(false,1,0x10,0x607f)==ZX_ALLOW);
 assert(zx_policy_row(false,1,0x10,0x3fff)==ZX_DENY);
 assert(zx_policy_row(false,1,0x10,0x6080)==ZX_DENY);
 assert(zx_policy_row(false,1,0xd8,0x4000)==ZX_ALLOW);
 assert(zx_policy_row(false,1,0xd8,0x6040)==ZX_ALLOW);
 assert(zx_policy_row(false,1,0xd8,0x4001)==ZX_DENY);
 assert(zx_policy_row(false,1,0xd8,0x6080)==ZX_DENY);
 assert(zx_policy_row(false,1,0x10,0x0e00)==ZX_DENY);
 assert(zx_policy_row(false,0,0x10,0x4000)==ZX_DENY);
 assert(zx_policy_row(false,-1,0x10,0x0e00)==ZX_DENY);
 assert(zx_policy_row(false,-1,0x10,0x4000)==ZX_DENY);
 assert(zx_policy_row(false,2,0x10,0x4000)==ZX_DENY);
 assert(zx_policy_row(false,-1,0x10,0xa800)==ZX_ALLOW);
 assert(zx_policy_row(true,1,0x10,0x4000)==ZX_REFUSE_BANK_A);
 /* Exhaustive page policy: one firmware window plus UBI, never both. */
 for(int bank=-1;bank<=2;bank++)for(unsigned row=0;row<0x10000;row++) {
  bool firmware=(bank==0 && row>=0xe00 && row<0x2e80) ||
                (bank==1 && row>=0x4000 && row<0x6080);
  bool ubi=row>=0xa800 && row<0xc800;
  assert((zx_policy_row(false,bank,0x10,row)==ZX_ALLOW)==(firmware||ubi));
 }

 /* zx_policy_feature: only unlock(0xa0=0) and non-mode CFG(0xb0) writes */
 assert(zx_policy_feature(0xa0,0x00)==ZX_ALLOW);
 assert(zx_policy_feature(0xa0,0x01)==ZX_DENY);        /* any lock bit */
 assert(zx_policy_feature(0xb0,0x18)==ZX_ALLOW);       /* bootloader B0 = ECC|... */
 assert(zx_policy_feature(0xb0,0x10)==ZX_ALLOW);       /* ECC_EN only */
 assert(zx_policy_feature(0xb0,0x00)==ZX_ALLOW);
 assert(zx_policy_feature(0xb0,0x80)==ZX_DENY);        /* a mode bit */
 assert(zx_policy_feature(0xb0,0x40)==ZX_DENY);
 assert(zx_policy_feature(0xb0,0x02)==ZX_DENY);
 assert(zx_policy_feature(0xc0,0x00)==ZX_DENY);        /* unknown feature reg */
 assert(zx_policy_feature(0xa0,0x100)==ZX_DENY);       /* out of range */

 /* zx_policy_verdict wires opcodes to the helpers and rejects malformed ops */
 {struct spi_mem_op o=prog(0x10,0x0e00); assert(zx_policy_verdict(false,0,&o)==ZX_ALLOW);
  o.addr.nbytes=2; assert(zx_policy_verdict(false,0,&o)==ZX_DENY);}
 {struct spi_mem_op o=feat(0xa0,0); assert(zx_policy_verdict(false,0,&o)==ZX_ALLOW);
  o.data.nbytes=2; assert(zx_policy_verdict(false,0,&o)==ZX_DENY);}
 {struct spi_mem_op o=bare(0x9f); assert(zx_policy_verdict(false,0,&o)==ZX_ALLOW);} /* a read */
 {struct spi_mem_op o=bare(0x06); assert(zx_policy_verdict(false,0,&o)==ZX_ALLOW);} /* WREN */

 /* zx_production_gate: allow path, deny path, and the latch */
 struct zx_spifc sp; struct spi_mem_op o;
 memset(&sp,0,sizeof(sp)); sp.production=true;
 o=prog(0x10,0xa800); assert(zx_production_gate(&sp,&o)==0 && !sp.policy_latched);
 o=bare(0x06);        assert(zx_production_gate(&sp,&o)==0);  /* WREN allowed pre-latch */
 o=feat(0xb0,0x18);   assert(zx_production_gate(&sp,&o)==0);  /* ECC feature allowed */
 o=bare(0x9f);        assert(zx_production_gate(&sp,&o)==0);  /* a read is not gated */
 /* a denied program latches, and then EVERY array op (incl WREN) is refused */
 logs=0;
 o=prog(0x10,0x3000); assert(zx_production_gate(&sp,&o)==-EROFS && sp.policy_latched);
 assert(sp.policy_refusals==1 && sp.bank_a_refusals==0 && sp.latch_opcode==0x10 && sp.latch_addr==0x3000 && logs==1);
 o=prog(0x10,0xa800); assert(zx_production_gate(&sp,&o)==-EROFS); /* allowed row, but latched */
 o=bare(0x06);        assert(zx_production_gate(&sp,&o)==-EROFS); /* WREN now refused */
 o=bare(0x02);        assert(zx_production_gate(&sp,&o)==-EROFS); /* cache load refused */
 assert(logs==1); /* only the first refusal logs */
 /* feature writes stay filtered but do not latch (reads toggle ECC via them) */
 memset(&sp,0,sizeof(sp)); sp.production=true;
 o=feat(0xb0,0x80); assert(zx_production_gate(&sp,&o)==-EROFS && !sp.policy_latched && sp.policy_refusals==1);
 o=feat(0xb0,0x18); assert(zx_production_gate(&sp,&o)==0);

 /* qualification gate: bank A refused and counted, UBI allowed */
 memset(&sp,0,sizeof(sp)); sp.production_qualify=true;
 o=prog(0x10,0xa800); assert(zx_production_gate(&sp,&o)==0 && !sp.policy_latched);
 o=prog(0x10,0x0e00); assert(zx_production_gate(&sp,&o)==-EROFS && sp.policy_latched);
 assert(sp.bank_a_refusals==1 && sp.policy_refusals==1);
 return 0;
}
'''


class ProductionPolicyTests(unittest.TestCase):
    def test_allow_deny_matrix_feature_filter_alias_and_latch(self):
        text = SOURCE.read_text()
        self.assertIn('zx_policy_row', text, 'production policy not present in the driver')
        constants = '\n'.join(line for line in text.splitlines()
                              if line.startswith('#define ZX_'))
        # The verdict enum, needed by every policy function.
        enum = re.search(r'enum zx_verdict \{.*?\};', text, re.S)
        self.assertIsNotNone(enum, 'zx_verdict enum missing')
        names = ('zx_array_write', 'zx_policy_row', 'zx_policy_feature',
                 'zx_policy_verdict', 'zx_production_gate')
        code = (constants + '\n' + MODEL + enum.group() + '\n'
                + '\n'.join(function(text, n) for n in names) + CASES)
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp) / 'policy.c', Path(tmp) / 'policy'
            src.write_text(code)
            r = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                '-Wno-unused-parameter', '-Wno-unused-function',
                                str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_policy_and_failstop_are_absent_from_normal_and_diagnostic_configs(self):
        # The shipped base config must never enable the production symbols; they
        # are added only by build.sh for BOOT_PROFILE=production.
        cfg = (Path(__file__).resolve().parents[1]
               / 'files/target/linux/armsr/config-6.6').read_text()
        self.assertNotIn('CONFIG_SPI_ZX279128_PRODUCTION_POLICY=y', cfg)
        self.assertNotIn('CONFIG_MTD_SPI_NAND_FAIL_STOP=y', cfg)


if __name__ == '__main__':
    unittest.main()
