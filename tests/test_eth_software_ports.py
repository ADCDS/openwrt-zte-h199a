"""Execute the actual port-policy initializer against checked register boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import function
from dt_fixture import eth_reg_prelude

SOURCE = Path(__file__).resolve().parents[1] / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c'

MODEL = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <stddef.h>
typedef uint32_t u32;
#define __iomem
#define BIT(n) (1U<<(n))
#define GENMASK(h,l) ((~0U<<(l)) & (~0U>>(31-(h))))
#define ZX_NPORTS 4
#define SZ_4K 4096
#define MAC_CTRL 0
#define MAC_CTRL_EN BIT(0)
#define SPA_BASE 0x921d4000
/*ETH_REGS*/
struct device { int dummy; };
struct zx_eth { struct device *dev; void *macs[4]; phys_addr_t phys[ZX_NREGS]; };
static unsigned char brg[4096],spa[4096],mac[4][4096];
static unsigned maps,map_calls,unmaps,writes,polls,flushes,seeds,fail_map,fail_poll,fail_seed;
static void *ignored;
static void log_message(struct device *d,const char *fmt,...) { (void)d;(void)fmt; }
#define dev_info log_message
#define dev_err log_message
static u32 readl(void *p) { u32 value;memcpy(&value,p,4);return value; }
static int inside(void *p,void *base) { return (uintptr_t)p>=(uintptr_t)base && (uintptr_t)p<(uintptr_t)base+4096; }
static void writel(u32 value,void *p) {
 writes++;
 if(inside(p,brg) || inside(p,spa))for(unsigned i=0;i<4;i++)assert(!(readl(mac[i])&1));
 if(p==brg+4 && (value&BIT(16))) {
  assert(!flushes && !(readl(brg+0x1c4)&0x3fc) && ((value>>8)&255)==255);
  for(unsigned i=1;i<=4;i++)assert(!(readl(brg+0x3c0+4*i)&0x1e));
  flushes++;
 }
 if(p!=ignored)memcpy(p,&value,4);
}
static void *ioremap(unsigned long address,unsigned length) {
 assert(!writes && length==4096);map_calls++;
 if(map_calls==fail_map)return NULL;
 maps++;
 if(address==0x92388000)return brg;
 assert(address==SPA_BASE);return spa;
}
static void iounmap(void *p) { assert((p==brg || p==spa) && maps);maps--;unmaps++; }
static void poll_register(void *p,u32 *value,unsigned delay,unsigned timeout) {
 assert(delay==1);
 if(p==brg+0x18)assert(!flushes && timeout==1000);
 else assert(p==brg+0x190 && flushes==1 && timeout==20000);
 polls++;*value=polls==fail_poll?0:1;
}
#define readl_poll_timeout(p,v,condition,delay,timeout) \
 (poll_register(p,&v,delay,timeout),(condition)?0:-ETIMEDOUT)
static int zx_pp_seed_vlans(void *base,unsigned count) {
 assert(base==brg && count==4096 && flushes==1 && polls==2);
 seeds++;return fail_seed?-EIO:0;
}
static struct zx_eth ze;
static void init_word(void *p,u32 v) { memcpy(p,&v,4); }
static void reset(void) {
 assert(!maps);memset(brg,0,sizeof(brg));memset(spa,0,sizeof(spa));memset(mac,0,sizeof(mac));
 maps=map_calls=unmaps=writes=polls=flushes=seeds=fail_map=fail_poll=fail_seed=0;ignored=NULL;
 zx_test_fallback_phys(ze.phys); /* SBRG and SPA must resolve to the old addresses. */
 for(unsigned i=0;i<4;i++) {
  ze.macs[i]=mac[i];init_word(mac[i],0xbae003);
  init_word(brg+0x3c4+4*i,0x123400ff);init_word(spa+0x2b4+4*i,0xdeadffbf);
 }
 init_word(brg+0x1c4,0xa5a55555);init_word(brg+0x340,0xff5555ff);
 init_word(brg+8,0xcafeffff);init_word(brg+4,0x200ff);init_word(spa+0x2a8,0xcafea5a5);
}
'''

CASES = r'''
int main(void) {
 reset();assert(zx_eth_software_ports(&ze)==0 && !maps && unmaps==2 && seeds==1);
 for(unsigned i=0;i<4;i++) {
  assert(readl(mac[i])==0xbae002);
  assert(readl(brg+0x3c4+4*i)==0x123400e1);
  assert(readl(spa+0x2b4+4*i)==0xdeadff80);
 }
 assert(readl(brg+0x1c4)==0xa5a55401 && readl(brg+0x340)==0xff57fdff);
 assert(readl(brg+8)==(0xcafeffff&~0x1e1e));
 assert(readl(spa+0x2a8)==((0xcafea5a5&~0x3fc)|0x154));
 assert(readl(brg+4)==0x3ffff); /* Flush completion did not require start to self-clear. */
 for(unsigned n=1;n<=2;n++) {
  reset();fail_map=n;assert(zx_eth_software_ports(&ze)==-ENOMEM);
  assert(!writes && !maps && unmaps==1);
  reset();fail_poll=n;assert(zx_eth_software_ports(&ze)==-ETIMEDOUT);
  assert(!maps && unmaps==2 && !seeds && polls==n);
 }
 void *targets[]={mac[0],mac[3],brg+0x1c4,brg+0x3c4,brg+0x3d0,brg+0x340,brg+8,spa+0x2a8,spa+0x2b4,spa+0x2c0,brg+4};
 for(unsigned n=0;n<sizeof(targets)/sizeof(targets[0]);n++) {
  reset();ignored=targets[n];assert(zx_eth_software_ports(&ze)==-EIO);
  assert(!maps && unmaps==2 && !seeds && !flushes);
 }
 reset();fail_seed=1;assert(zx_eth_software_ports(&ze)==-EIO && seeds==1 && !maps);
 reset();ze.macs[2]=NULL;assert(zx_eth_software_ports(&ze)==-EINVAL && !maps && !map_calls && !writes);
 return 0;
}
'''


class SoftwarePortsTests(unittest.TestCase):
    def test_masks_order_completion_and_failure_cleanup(self):
        source = SOURCE.read_text()
        code = (MODEL.replace('/*ETH_REGS*/', eth_reg_prelude(source)) +
                function(source, 'zx_eth_update_bits') +
                function(source, 'zx_eth_software_ports') + CASES)
        with tempfile.TemporaryDirectory() as directory:
            src, exe = Path(directory) / 'ports.c', Path(directory) / 'ports'
            src.write_text(code)
            run = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', str(src), '-o', str(exe)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
