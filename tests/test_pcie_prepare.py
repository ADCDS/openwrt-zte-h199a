"""Exercise the actual two-host preparation code with failed resource/lifecycle paths."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import exact_define, function

SOURCE = Path(__file__).resolve().parents[1] / 'files/target/linux/armsr/files-6.6/drivers/pci/controller/dwc/pcie-zx279128.c'

MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef uintptr_t resource_size_t;
#define __iomem
#define BIT(n) (1U << (n))
#define SZ_4K 4096
#define SZ_16K 16384
#define GFP_KERNEL 0
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define DEFINE_MUTEX(n) int n
#define EPROBE_DEFER 517
#define ZX_PERST_GPIO0 53
#define ZX_PERST_GPIO1 55
#define ZX_CRM1_RST 0x74
struct device { int ignored; };
static void dev_info(struct device *d,const char *fmt,...) {}
#define dev_err dev_info
#define dev_warn dev_info
/* port selects the node's dbi/app addresses; legacy is a zte,pcie-port value. */
struct device_node { unsigned port; bool enabled,bad_resource,has_legacy,hold_perst_prop,serdes_prop; u32 legacy;
 struct device_node *next; };
struct resource { resource_size_t start,end; };
struct dw_pcie { struct device *dev; void *dbi_base; };
struct gpio_desc { bool held; };
struct reset_control { unsigned port; bool held; };
struct zx_pcie { struct dw_pcie pci; unsigned port; void *glue,*crm0,*crm1,*crm2;
 struct gpio_desc *perst; void *gpio; unsigned perst_pin; bool serdes_override; struct reset_control *rst; };
static struct device_node nodes[3],*head;
static struct gpio_desc descs[2];
static unsigned map_calls,maps,fail_map,events[32],nevents,wait_fail,allocations,fail_pin;
static unsigned held,perst_calls,fail_perst;
static struct reset_control rsts[2];
static unsigned rst_calls,rst_held,fail_rst,no_resets;
static bool alloc_fail, zx_hold_perst;
static int held_error;
static unsigned char crm[256];
static struct zx_pcie owner={.crm1=crm};
static void mutex_lock(int *m) { assert(!*m);*m=1; }
static void mutex_unlock(int *m) { assert(*m);*m=0; }
static void *kcalloc(unsigned n,unsigned size,int flags) {
 if(alloc_fail)return NULL;allocations++;return calloc(n,size);
}
static void kfree(void *p) { assert(allocations);allocations--;free(p); }
#define for_each_compatible_node(np,a,b) for(np=head;np;np=np->next)
static bool of_device_is_available(struct device_node *n) { return n->enabled; }
static bool of_property_read_bool(struct device_node *n,const char *prop) {
 if(!strcmp(prop,"zte,hold-perst"))return n->hold_perst_prop;
 assert(!strcmp(prop,"zte,port0-serdes-init"));return n->serdes_prop;
}
static bool of_property_present(struct device_node *n,const char *prop) {
 assert(!strcmp(prop,"zte,pcie-port"));return n->has_legacy;
}
static int of_property_read_u32(struct device_node *n,const char *prop,u32 *v) {
 assert(!strcmp(prop,"zte,pcie-port"));
 if(!n->has_legacy)return -EINVAL;*v=n->legacy;return 0;
}
static int of_property_match_string(struct device_node *n,const char *prop,const char *v) {
 return !strcmp(v,"dbi")?0:1;
}
static int of_address_to_resource(struct device_node *n,int index,struct resource *r) {
 r->start=(index?0x09500000:0x0f000000)+n->port*0x100000;
 r->end=r->start+(index?SZ_4K:SZ_16K)-1;
 if(n->bad_resource)r->start++;return 0;
}
static resource_size_t resource_size(struct resource *r) { return r->end-r->start+1; }
static void *of_iomap(struct device_node *n,int index) {
 assert(!nevents);if(++map_calls==fail_map)return NULL;maps++;return malloc(1);
}
static void iounmap(void *p) { assert(p && !IS_ERR(p) && maps);maps--;free(p); }
static void of_node_put(struct device_node *n) { assert(n); }
static void event(unsigned id) { assert(maps==4 && held==2);assert(nevents<32);events[nevents++]=id; }
/* Each port's PERST# is resolved after its own windows, before any mutation. */
static int zx_pcie_get_perst(struct zx_pcie *p,struct device_node *n) {
 assert(!nevents && n->port==p->port && p->glue && p->pci.dbi_base && !p->perst);
 if(++perst_calls==fail_perst)return -EPROBE_DEFER;
 assert(!descs[p->port].held);descs[p->port].held=true;held++;p->perst=&descs[p->port];return 0;
}
static void gpiod_put(struct gpio_desc *d) { assert(d->held && held);d->held=false;held--; }
/* Each port's reset line is resolved after its PERST#, before any mutation;
 * a missing provider defers. no_resets models a device tree without them. */
static struct reset_control *of_reset_control_get_optional_exclusive(struct device_node *n,const char *id) {
 assert(!nevents && !id && descs[n->port].held);
 if(++rst_calls==fail_rst)return ERR_PTR(-EPROBE_DEFER);
 if(no_resets)return NULL;
 assert(!rsts[n->port].held);rsts[n->port].held=true;rsts[n->port].port=n->port;rst_held++;
 return &rsts[n->port];
}
static void reset_control_put(struct reset_control *r) {
 if(!r)return;assert(!IS_ERR(r) && r->held && rst_held);r->held=false;rst_held--;
}
static int zx_pcie_perst(struct zx_pcie *p) {
 unsigned gpio=p->port?ZX_PERST_GPIO1:ZX_PERST_GPIO0;
 assert(p->perst==&descs[p->port] && p->perst->held);
 event(gpio);return gpio==fail_pin?-ETIMEDOUT:0;
}
static int zx_pcie_prepare_held_perst(struct zx_pcie *p) { (void)p;event(500);return held_error; }
static void zx_pcie_domain_enable(struct zx_pcie *p) {
 /* The domain sequence sees the port's own reset line, or none. */
 assert(no_resets ? !p->rst : (p->rst==&rsts[p->port] && p->rst->held));
 event(100+p->port);
}
static void zx_pcie_train(struct zx_pcie *p) { event(200+p->port); }
static int zx_pcie_wait_l0(struct zx_pcie *p) {
 event(300+p->port);return (wait_fail&BIT(p->port))?-ETIMEDOUT:0;
}
static void writel(u32 val,void *p) { assert(val==0x3f && p==crm+0x74);event(400); }
static u32 readl(void *p) { assert(p==crm+0x74);return 0x1b; }
'''

CASES = r'''
static void reset(void) {
 assert(!maps && !allocations && !held && !rst_held && !zx_prepare_lock);
 rst_calls=fail_rst=no_resets=0;
 memset(nodes,0,sizeof(nodes));nodes[0].enabled=nodes[1].enabled=true;
 nodes[0].port=0;nodes[1].port=1;nodes[0].next=&nodes[1];head=&nodes[0];
 map_calls=fail_map=nevents=wait_fail=fail_pin=perst_calls=fail_perst=0;alloc_fail=false;
 zx_hold_perst=false;held_error=0;
 zx_prepare_state=ZX_PREPARE_NEW;zx_prepare_error=0;
}
static void clean(void) { assert(!maps && !allocations && !held && !rst_held && !zx_prepare_lock); }
int main(void) {
 unsigned expected[]={53,55,100,200,300,101,201,400,301,300,301};
 for(unsigned reverse=0;reverse<2;reverse++) {
  reset();if(reverse) { nodes[1].next=&nodes[0];nodes[0].next=NULL;head=&nodes[1]; }
  owner.port=reverse;assert(zx_pcie_prepare_pair(&owner)==0);clean();
  assert(zx_prepare_state==ZX_PREPARE_READY && nevents==11);
  assert(!memcmp(events,expected,sizeof(expected)));
  /* The first host may fail after common preparation and lose its devres.
   * A different owner with no valid MMIO must use only the cached outcome. */
  struct zx_pcie second={0};
  assert(zx_pcie_prepare_pair(&second)==0 && nevents==11 && map_calls==4);clean();
 }
 for(unsigned f=1;f<=4;f++) {
  reset();fail_map=f;assert(zx_pcie_prepare_pair(&owner)==-ENOMEM);clean();
  assert(!nevents && zx_prepare_state==ZX_PREPARE_NEW);
  fail_map=0;map_calls=0;assert(zx_pcie_prepare_pair(&owner)==0);clean();
 }
 /* A deferred or failed PERST# lookup (either port) releases everything taken
  * so far and leaves the shared sequence unstarted, so a later probe retries. */
 for(unsigned f=1;f<=2;f++) {
  reset();fail_perst=f;assert(zx_pcie_prepare_pair(&owner)==-EPROBE_DEFER);clean();
  assert(!nevents && zx_prepare_state==ZX_PREPARE_NEW && map_calls==2*f);
  fail_perst=0;map_calls=0;assert(zx_pcie_prepare_pair(&owner)==0);clean();
  assert(zx_prepare_state==ZX_PREPARE_READY && nevents==11);
 }
 /* A reset provider that has not probed yet defers, either port, before any
  * mutation, releasing everything taken so far; the retry runs normally. */
 for(unsigned f=1;f<=2;f++) {
  reset();fail_rst=f;assert(zx_pcie_prepare_pair(&owner)==-EPROBE_DEFER);clean();
  assert(!nevents && zx_prepare_state==ZX_PREPARE_NEW && map_calls==2*f);
  fail_rst=0;map_calls=0;rst_calls=0;assert(zx_pcie_prepare_pair(&owner)==0);clean();
  assert(zx_prepare_state==ZX_PREPARE_READY && nevents==11);
  assert(!memcmp(events,expected,sizeof(expected)));
 }
 /* A device tree without resets: same sequence, the fallback path. */
 reset();no_resets=1;assert(zx_pcie_prepare_pair(&owner)==0);clean();
 assert(zx_prepare_state==ZX_PREPARE_READY && nevents==11 && rst_calls==2);
 assert(!memcmp(events,expected,sizeof(expected)));
 reset();alloc_fail=true;assert(zx_pcie_prepare_pair(&owner)==-ENOMEM);clean();
 assert(!map_calls && !nevents);
 /* Deprecated zte,pcie-port naming the node's own port: accepted, same run. */
 reset();for(unsigned i=0;i<2;i++) { nodes[i].has_legacy=true;nodes[i].legacy=i; }
 assert(zx_pcie_prepare_pair(&owner)==0);clean();
 assert(zx_prepare_state==ZX_PREPARE_READY && nevents==11 && map_calls==4);
 assert(!memcmp(events,expected,sizeof(expected)));
 for(unsigned f=0;f<5;f++) {
  reset();if(f==0)nodes[1].port=0;if(f==1)nodes[1].enabled=false;
  if(f==2) { nodes[1].has_legacy=true;nodes[1].legacy=0; }   /* disagrees with dbi */
  if(f==3)nodes[1].bad_resource=true;                       /* dbi of neither port */
  if(f==4) { nodes[0].has_legacy=true;nodes[0].legacy=2; }  /* out of range */
  assert(zx_pcie_prepare_pair(&owner)==-EINVAL);clean();
  assert(!nevents && zx_prepare_state==ZX_PREPARE_NEW);
  assert(map_calls==(f==4?0U:2U));  /* node 0 is mapped before node 1 fails */
 }
 for(unsigned f=1;f<=3;f++) {
  reset();wait_fail=f;assert(zx_pcie_prepare_pair(&owner)==0);clean();
  assert(zx_prepare_state==ZX_PREPARE_READY && nevents==11);
  wait_fail=0;assert(zx_pcie_prepare_pair(&owner)==0);clean();
  assert(nevents==11 && map_calls==4);
 }
 for(unsigned pin=53;pin<=55;pin+=2) {
  reset();fail_pin=pin;assert(zx_pcie_prepare_pair(&owner)==-ETIMEDOUT);clean();
  unsigned count=pin==53?1:2;
  assert(zx_prepare_state==ZX_PREPARE_FAILED && nevents==count);
  fail_pin=0;assert(zx_pcie_prepare_pair(&owner)==-ETIMEDOUT);clean();
  assert(nevents==count && map_calls==4);
 }
 reset();zx_hold_perst=true;
 assert(zx_pcie_prepare_pair(&owner)==0);clean();
 assert(nevents==3 && events[0]==500 && events[1]==300 && events[2]==301);
 assert(zx_pcie_prepare_pair(&owner)==0 && nevents==3);clean();
 reset();zx_hold_perst=true;held_error=-EIO;
 assert(zx_pcie_prepare_pair(&owner)==-EIO);clean();
 assert(nevents==1 && zx_prepare_state==ZX_PREPARE_FAILED);
 held_error=0;assert(zx_pcie_prepare_pair(&owner)==-EIO && nevents==1);clean();
 reset();nodes[1].hold_perst_prop=true;
 assert(zx_pcie_prepare_pair(&owner)==0);clean();
 assert(nevents==3 && events[0]==500);
 return 0;
}
'''


class PciePrepareTests(unittest.TestCase):
    def test_resource_failure_order_and_no_reset_replay(self):
        source = SOURCE.read_text()
        state = source[source.index('static DEFINE_MUTEX(zx_prepare_lock);'):
                       source.index('static void __iomem *zx_map_named')]
        code = (MODEL + exact_define(source, 'ZX_DBI_PHYS(port)') +
                exact_define(source, 'ZX_APP_PHYS(port)') + state +
                function(source, 'zx_map_named') + function(source, 'zx_pcie_port_of') +
                function(source, 'zx_pcie_prepare_pair') + CASES)
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp) / 'prepare.c', Path(tmp) / 'prepare'
            src.write_text(code)
            run = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                  '-Wno-unused-parameter', '-Wno-misleading-indentation',
                                  str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
