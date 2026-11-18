"""Execute init gate writes/readbacks with ignored-write fault injection."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import SOURCE, function
from dt_fixture import eth_reg_prelude

MODEL = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
typedef uint32_t u32;
#define ZX_NPORTS 4
#define MAC_CTRL 0
#define MAC_CTRL_EN 1U
#define TMC_IRQ_MASK 0x104
#define BM_ENABLE 0
struct zx_eth { void *macs[4],*tmc,*bm; };
static u32 mac[4],tmc[128],bm;
static unsigned writes,fault;
static u32 readl(void *p) { return *(u32 *)p; }
static void writel(u32 value,void *p) {
 writes++;
 if(writes==fault)return;
 if(p==&tmc[TMC_IRQ_MASK/4]) {
  assert(value==UINT32_MAX);*(u32 *)p=value&7; /* Only supported mask bits read back. */
 } else if(p==&bm) {
  assert(value==0);*(u32 *)p=0x80000000; /* Unrelated read-only status is ignored. */
 } else *(u32 *)p=value;
}
'''

CASES = r'''
int main(void) {
 struct zx_eth z={.tmc=tmc,.bm=&bm};
 for(unsigned f=0;f<=6;f++) {
  writes=0;fault=f;bm=1;memset(tmc,0,sizeof(tmc));
  for(unsigned i=0;i<4;i++) { mac[i]=0x00bb6003;z.macs[i]=&mac[i]; }
  assert(zx_eth_quiesce_init(&z)==(f?-EIO:0));
  assert(writes==6); /* All gates are written before any failure return. */
  for(unsigned i=0;i<4;i++)assert(mac[i]==(f==i+1?0x00bb6003:0x00bb6002));
 }
 writes=0;z.macs[2]=0;assert(zx_eth_quiesce_init(&z)==-EINVAL && !writes);
 z.macs[2]=&mac[2];z.bm=0;assert(zx_eth_quiesce_init(&z)==-EINVAL && !writes);
 z.bm=&bm;z.tmc=0;assert(zx_eth_quiesce_init(&z)==-EINVAL && !writes);
 return 0;
}
'''

INIT_MODEL = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#define __iomem
#define SZ_4K 4096
#define SZ_128K 131072
#define ZXI_RESET 1
#define ZXI_MASK 1
/*ETH_REGS*/
struct zx_eth { bool alloc_pending;unsigned free_credit;phys_addr_t phys[ZX_NREGS]; };
static uint32_t maps[5][4];
static bool alive[5],zx_skip_reset;
static unsigned calls,fail_map,gates,fail_gate,resets,delays,unmaps;
static int zx_eth_quiesce_init(struct zx_eth *z) {
 (void)z;gates++;
 if(gates==1)assert(!calls && !resets);
 else assert(gates==2 && calls==5 && !alive[0] && resets==(zx_skip_reset?0U:2U));
 return gates==fail_gate?-EIO:0;
}
static void *ioremap(unsigned address,unsigned size) {
 static const unsigned addresses[]={0x92000000,0x92040000,0x921d4000,0x921c0000,0x923a0000};
 assert(gates==1 && calls<5 && address==addresses[calls]);
 assert(size==(calls==3?SZ_128K:SZ_4K));calls++;
 if(calls==fail_map)return 0;
 alive[calls-1]=true;return maps[calls-1];
}
static void iounmap(void *p) {
 for(unsigned i=0;i<5;i++)if(p==maps[i]) { assert(alive[i]);alive[i]=false;unmaps++;return; }
 assert(!"unknown mapping");
}
static void writel(uint32_t value,void *p) {
 assert(p==&maps[0][2] && alive[0] && calls==5 && gates==1);
 assert(resets<2 && value==(resets?UINT32_MAX:0));resets++;
}
static void msleep(unsigned n) { assert(n==100 && resets==1 && !delays);delays++; }
static void mdelay(unsigned n) { assert(n==10 && resets==2 && delays==1);delays++; }
'''

INIT_CASES = r'''
static void run(unsigned map_failure,unsigned gate_failure,bool skip) {
 struct zx_eth z={.alloc_pending=true,.free_credit=99};
 /* Fallback bases: the addresses below are the ones this init always used. */
 zx_test_fallback_phys(z.phys);
 memset(alive,0,sizeof(alive));calls=gates=resets=delays=unmaps=0;
 fail_map=map_failure;fail_gate=gate_failure;zx_skip_reset=skip;
 int result=zx_eth_datapath_init(&z);
 if(gate_failure==1)assert(result==-EIO && !calls && !unmaps && z.alloc_pending);
 else if(map_failure)assert(result==-ENOMEM && calls==5 && unmaps==4 && !resets);
 else if(gate_failure==2)assert(result==-EIO && unmaps==5 && z.alloc_pending && z.free_credit==99);
 else {
  assert(result==123 && gates==2 && unmaps==1 && !z.alloc_pending && !z.free_credit);
  /* Prefix reached reconstruction; later production code owns these maps. */
  for(unsigned i=1;i<5;i++)iounmap(maps[i]);
 }
 for(unsigned i=0;i<5;i++)assert(!alive[i]);
}
int main(void) {
 run(0,1,false);
 for(unsigned i=1;i<=5;i++)run(i,0,false);
 run(0,2,false);run(0,2,true);run(0,0,false);run(0,0,true);
 return 0;
}
'''


class InitQuiesceTests(unittest.TestCase):
    def test_known_gate_bits_and_every_ignored_write(self):
        source = SOURCE.read_text()
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp) / 'quiesce.c', Path(tmp) / 'quiesce'
            src.write_text(MODEL + function(source, 'zx_eth_quiesce_init') + CASES)
            run = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                  str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_actual_init_prefix_stops_before_reconstruction_and_unmaps_once(self):
        text = SOURCE.read_text()
        source = function(text, 'zx_eth_datapath_init')
        boundary = '\tif (glb && (ZXI_MASK & ZXI_GLOBAL)) {'
        self.assertEqual(source.count(boundary), 1)
        prefix = source.split(boundary)[0] + '\n(void)i; (void)qmap; return 123;\n}\n'
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp) / 'init.c', Path(tmp) / 'init'
            src.write_text(INIT_MODEL.replace('/*ETH_REGS*/', eth_reg_prelude(text)) +
                           prefix + INIT_CASES)
            run = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                  str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
