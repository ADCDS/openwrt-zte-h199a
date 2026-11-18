"""Test the actual BRG initializer with a checked indirect-RAM model."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_eth_rx import DRIVER

STUBS = r"""
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
#define __iomem
#define BIT(n) (1u << (n))
#define GENMASK(h,l) ((0xffffffffu >> (31-(h))) & (0xffffffffu << (l)))
static unsigned char regs[64];
static u32 table[4096][3], stage[3];
static unsigned selected, writes, phase, polls, fail_poll, ignore_write;
static u32 readl(void *p) { u32 v; memcpy(&v,p,4); return v; }
#define readl_poll_timeout(addr, value, condition, delay, timeout) \
    ((void)(addr), (void)(delay), (void)(timeout), polls++, \
     (value)=polls==fail_poll?0:1, (condition)?0:-ETIMEDOUT)
static void writel(u32 value, void *p) {
    unsigned off=(unsigned)((unsigned char *)p-regs);
    memcpy(p,&value,4);
    if (off==0x14) {
        assert(((value>>22)&31)==4);
        selected=value&0xfff; assert(selected<4096);
        if(value&BIT(27)) {
            memcpy(regs+0x1c,table[selected],12);
        } else phase=2;
    } else {
        assert(off==0x1c+phase*4);
        stage[phase]=value;
        if(phase) phase--;
        else { if(!ignore_write) memcpy(table[selected],stage,12); writes++; }
    }
}
static void reset(void) {
    memset(regs,0,sizeof(regs));
    for(unsigned i=0;i<4096;i++) {
        table[i][0]=0xa5000000u; table[i][1]=0x12345678u+i; table[i][2]=0x87654321u-i;
    }
    writes=phase=polls=fail_poll=ignore_write=0;
}
"""

CASES = r"""
int main(void) {
    reset(); assert(zx_pp_seed_vlans(regs,4096)==0); assert(writes==4096);
    for(unsigned i=0;i<4096;i++) {
        assert(table[i][0]==0xa501ffffu);
        assert(table[i][1]==0x12345678u+i && table[i][2]==0x87654321u-i);
    }
    for(unsigned n=1;n<=10;n++) {
        reset(); fail_poll=n;
        assert(zx_pp_seed_vlans(regs,2)==-ETIMEDOUT && polls==n);
    }
    reset(); ignore_write=1;
    assert(zx_pp_seed_vlans(regs,2)==-EIO && writes==1);
    reset();assert(zx_pp_seed_vlans(regs,0)==-EINVAL && !polls && !writes);
    assert(zx_pp_seed_vlans(regs,4097)==-EINVAL && !polls && !writes);
    for(unsigned n=20476;n<=20480;n++) {
        reset();fail_poll=n;
        assert(zx_pp_seed_vlans(regs,4096)==-ETIMEDOUT && polls==n);
    }
    return 0;
}
"""


class BridgeInitTests(unittest.TestCase):
    def test_transaction_order_and_failure(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        source = DRIVER.read_text()
        start = source.index("static int zx_pp_seed_vlans(")
        end = source.index("static int zx_eth_datapath_init(", start)
        with tempfile.TemporaryDirectory() as directory:
            cfile, binary = Path(directory) / "bridge.c", Path(directory) / "bridge"
            cfile.write_text(STUBS + source[start:end] + CASES)
            result = subprocess.run([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                                     str(cfile), "-o", str(binary)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, timeout=10)
