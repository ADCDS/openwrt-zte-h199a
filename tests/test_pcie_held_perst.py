"""Exercise reset/clock ordering and each pre-publication gate failure."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import function
from test_pcie_prepare import SOURCE

MODEL = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef uint32_t u32;
#define BIT(n) (1U<<(n))
#define ZX_GLUE_CTRL 0
#define ZX_GLUE_LTSSM_EN BIT(5)
#define ZX_CRM1_RST 0x74
struct device { int unused; };
struct zx_pcie { unsigned port;struct { struct device *dev; } pci;void *glue,*crm1; };
static unsigned char glue[2][8],crm[128];
static unsigned pins[2],domains,shared,settled,released,trained,edges,ctrlwrites;
static unsigned fail_edge,fail_ctrl,bad_pin;
static bool hold_wait;
static void dev_info(struct device *d,const char *fmt,...) { (void)d;(void)fmt; }
/* pins[] is the electrical level: PERST# is asserted while it is low. */
static int zx_perst_set(struct zx_pcie *p,bool asserted) {
 assert(p->port<2);edges++;
 if(asserted)assert(!domains && !shared && !hold_wait);
 else assert(domains==3 && shared && settled && !trained);
 if(edges==fail_edge)return -ETIMEDOUT;
 pins[p->port]=!asserted;return 0;
}
static int zx_perst_get(struct zx_pcie *p) {
 assert(shared);return !(pins[p->port] || bad_pin==p->port+1);
}
static void mdelay(unsigned ms) {
 if(ms==10) { assert(edges==2 && !pins[0] && !pins[1] && !domains);hold_wait=true; }
 else if(ms==100) { assert(shared && !pins[0] && !pins[1] && ctrlwrites==4);settled=1; }
 else { assert(ms==200 && pins[0] && pins[1] && settled && !trained);released=1; }
}
static void zx_pcie_domain_enable(struct zx_pcie *p) {
 assert(hold_wait && !pins[0] && !pins[1] && !trained && !shared);
 assert(domains==(p->port?1U:0U));domains|=BIT(p->port);
 *(u32 *)p->glue=0xa0000020;
}
static u32 readl(void *p) {
 if(p==crm+ZX_CRM1_RST) { assert(shared);return 0x1b; }
 for(unsigned i=0;i<2;i++)if(p==glue[i]) { assert(domains&BIT(i));return *(u32 *)p; }
 assert(!"unexpected register read");return 0;
}
static void writel(u32 value,void *p) {
 if(p==crm+ZX_CRM1_RST) {
  assert(value==0x3f && domains==3 && !pins[0] && !pins[1] && ctrlwrites==2);
  shared=1; /* Exercise reset restoring the inherited LTSSM-enable bits. */
  *(u32 *)glue[0]|=BIT(5);*(u32 *)glue[1]|=BIT(5);return;
 }
 for(unsigned i=0;i<2;i++)if(p==glue[i]) {
  assert(domains&BIT(i));assert(value==0xa0000000);ctrlwrites++;
  if(ctrlwrites!=fail_ctrl)*(u32 *)p=value;
  return;
 }
 assert(!"unexpected register write");
}
static void zx_pcie_train(struct zx_pcie *p) {
 assert(released && pins[0] && pins[1] && shared && domains==3);
 assert(trained==p->port);trained++;
}
'''

CASES = r'''
static void reset(void) {
 pins[0]=pins[1]=1;domains=shared=settled=released=trained=edges=ctrlwrites=0;
 fail_edge=fail_ctrl=bad_pin=0;hold_wait=false;memset(glue,0,sizeof(glue));
}
int main(void) {
 struct zx_pcie pair[2]={{.port=0,.glue=glue[0],.crm1=crm},
                         {.port=1,.glue=glue[1],.crm1=crm}};
 reset();assert(zx_pcie_prepare_held_perst(pair)==0 && trained==2 && edges==4);
 for(unsigned i=1;i<=4;i++) {
  reset();fail_edge=i;
  assert(zx_pcie_prepare_held_perst(pair)==-ETIMEDOUT && !trained && edges==i);
 }
 for(unsigned i=1;i<=4;i++) {
  reset();fail_ctrl=i;
  assert(zx_pcie_prepare_held_perst(pair)==-EIO && !trained && !released && ctrlwrites==i);
 }
 for(unsigned i=1;i<=2;i++) {
  reset();bad_pin=i;
  assert(zx_pcie_prepare_held_perst(pair)==-EIO && !trained && !settled && edges==2);
 }
 return 0;
}
'''


class HeldPerstTests(unittest.TestCase):
    def test_hold_through_shared_changes_and_stop_on_every_gate_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp)/'held.c', Path(tmp)/'held'
            src.write_text(MODEL + function(SOURCE.read_text(), 'zx_pcie_prepare_held_perst') + CASES)
            run = subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',str(src),'-o',str(exe)],
                                 capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            run = subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
