"""Execute current probe/cleanup C with devres and publication fault injection.

The model instruments kernel API boundaries and register storage, not the probe
sequence. It checks software lifetime/order; it cannot prove physical DMA drain.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import SOURCE, exact_enum, exact_struct, function


MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef unsigned spinlock_t;
typedef uint32_t phys_addr_t;
typedef int phy_interface_t;
#define __iomem
#define ETH_ALEN 6
#define IFNAMSIZ 16
#define SZ_4K 4096
#define IORESOURCE_MEM 0
#define ZX_NPORTS 4
#define ZX_RX_QUEUES 8
#define ZX_RX_RINGS 16
#define RING_ENTRIES 1024
#define DESC_SIZE 16
#define ZX_RX_RING_SIZE (RING_ENTRIES * DESC_SIZE)
#define ZX_RX_MAP_SIZE (ZX_RX_RINGS * ZX_RX_RING_SIZE)
#define BUF_SIZE 2048
#define BUF_COUNT 2048
#define BUF2_COUNT 512
#define ZX_DDR_BASE 0x41000000
#define ZX_DDR_SIZE 0x1000000
#define ZX_DDR_POOL 0x000000
#define ZX_DDR_POOL2 0x400000
#define ZX_DDR_FREELIST 0x800000
#define ZX_DDR_RX_RING 0xa00000
#define ZX_DDR_TX_RING 0xc00000
#define BM_BASE 0x92348000
#define TMC_BASE 0x92340000
#define TMD_BASE 0x92344000
#define TMQ_BASE 0x92350000
#define ZX_MAC_BASE 0x92200000
#define ZX_MAC_STRIDE 0x40000
#define BM_ENABLE 0
#define MAC_CTRL 0
#define TMC_RING_BASE 0xf0
#define TMC_CFG 0x04
#define TMC_IRQ_MASK 0x104
#define TMD_GO 0x64
#define TMQ_TXRING 0x60
#define TMQ_TXIDX 0x6c
#define TMQ_CREDIT 0x68
#define TMQ_PENDING 0x100
#define IS_ENABLED(option) (option)
#define ZX_IRQ_PROBE_MAX 5
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define min(a,b) ((a)<(b)?(a):(b))
#define IS_ERR(p) ((intptr_t)(p)<0 && (intptr_t)(p)>-4096)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define cpu_to_be16(v) __builtin_bswap16((u16)(v))
#define wmb() ((void)0)
struct device_node { int unused; };
struct device { struct device_node *of_node; };
struct resource { unsigned long start; };
struct platform_device { struct device dev; void *data; };
struct napi_struct { bool initialized; };
struct work_struct { int unused; };
struct delayed_work { bool initialized; struct work_struct work; };
struct timer_list { bool initialized, shutdown; void (*callback)(struct timer_list *); };
struct net_device_ops { int unused; };
struct net_device {
    struct device *parent;
    const struct net_device_ops *netdev_ops;
    char name[IFNAMSIZ]; u8 dev_addr[ETH_ALEN];
    bool registered, running;
};
static const struct net_device_ops zx_eth_netdev_ops, zx_port_netdev_ops;
#define SET_NETDEV_DEV(n,d) ((n)->parent=(d))
#define netdev_priv(n) ((void *)((n)+1))
#define from_timer(v,t,m) ((struct zx_eth *)((char *)(t)-offsetof(struct zx_eth,m)))
#define INIT_DELAYED_WORK(w,fn) ((void)(fn),(w)->initialized=true)
#define spin_lock_init(p) (*(p)=1)
#define spin_lock_irqsave(p,f) do { assert(*(p)); (f)=0; } while(0)
#define spin_unlock_irqrestore(p,f) do { assert(*(p)); (void)(f); } while(0)
#define timer_setup(t,fn,flags) do { (void)(flags); (t)->initialized=true; (t)->callback=(fn); } while(0)
static void quiet_log(void *d, const char *fmt, ...) { (void)d; (void)fmt; }
#define dev_info quiet_log
#define dev_warn quiet_log
static int dev_err_probe(void *d,int err,const char *fmt,...) { (void)d; (void)fmt; return err; }
'''

BOUNDARIES = r'''
struct allocation { void *ptr; size_t size; bool alive; };
struct action { void (*fn)(void *); void *arg; };
static struct allocation memory[96];
static struct action actions[160];
static unsigned nmem, nactions, calls, fail_at, seed_writes, active_ports;
static unsigned registrations, irq_requests, irq_releases, disarms, proc_entries;
static bool in_timer, hardware_started, inherited_warm;
static unsigned init_calls;
static struct zx_eth *live, *zx_dbg_ze, *zx_eth_singleton;
static struct device_node node;
static bool zx_split_ports=true, zx_skip_dp_init, zx_irq_probe;
static unsigned zx_tx_slot_mode, zx_irq_probe_n;
static int zx_irq_nums[ZX_IRQ_PROBE_MAX];
static const int zx_regs_pops, zx_packets_pops, zx_poke_pops, zx_reinit_pops,
	zx_spa_ram_pops;
static unsigned long jiffies;
static bool failed(void) { return ++calls==fail_at; }
static void add(void (*fn)(void *),void *arg) {
    assert(nactions<160); actions[nactions++]=(struct action){fn,arg};
}
static struct allocation *owned(void *p) {
    for(unsigned i=0;i<nmem;i++)
        if((uintptr_t)p>=(uintptr_t)memory[i].ptr &&
           (uintptr_t)p<(uintptr_t)memory[i].ptr+memory[i].size) return &memory[i];
    assert(!"unowned memory access"); return NULL;
}
static void alive(void *p) { assert(owned(p)->alive); }
static void release_memory(void *p) { struct allocation *m=owned(p); assert(m->alive); m->alive=false; }
static void *allocate(size_t n) {
    if(failed()) return NULL;
    assert(nmem<96); void *p=calloc(1,n); assert(p);
    memory[nmem++]=(struct allocation){p,n,true}; add(release_memory,p); return p;
}
static void *devm_alloc_etherdev(struct device *d,size_t n) {
    (void)d; struct net_device *p=allocate(sizeof(*p)+n);
    if(p && !live) live=netdev_priv(p);
    return p;
}
static u32 readl(void *p) { u32 v; alive(p); memcpy(&v,p,4); return v; }
static void writel(u32 v,void *p) {
    alive(p); memcpy(p,&v,4);
    if(live && p==live->bm && !v && live->removing) disarms++;
}
static u16 readw(void *p) { u16 v; alive(p); memcpy(&v,p,2); return v; }
static void writew(u16 v,void *p) { alive(p); memcpy(p,&v,2); seed_writes++; }
static void *devm_ioremap(struct device *d,unsigned long pa,size_t n) {
    (void)d;void *p=allocate(n);
    if(p && inherited_warm) {
        if(pa==TMC_BASE)writel(0x41a00000,p+TMC_RING_BASE);
        if(pa==TMQ_BASE) { writel(0x41c00000,p+TMQ_TXRING);writel(45,p+TMQ_TXIDX); }
        if(pa>=ZX_MAC_BASE && pa<ZX_MAC_BASE+ZX_NPORTS*ZX_MAC_STRIDE)writel(0x00bb6003,p);
    }
    return p;
}
static void *devm_ioremap_wc(struct device *d,unsigned long pa,size_t n) { return devm_ioremap(d,pa,n); }
static void *devm_platform_ioremap_resource(struct platform_device *p,unsigned n) {
    (void)p; (void)n; void *v=allocate(SZ_4K); return v?v:(void *)(intptr_t)-ENOMEM;
}
static int platform_get_irq_byname(struct platform_device *p,const char *n) { (void)p;(void)n;return failed()?-ENXIO:36; }
static int platform_get_irq_byname_optional(struct platform_device *p,const char *n) { (void)p;(void)n;return -ENXIO; }
static struct resource *platform_get_resource(struct platform_device *p,int kind,unsigned n) {
    (void)p;(void)kind;(void)n;static struct resource r={ZX_MAC_BASE};return &r;
}
static const char *dev_name(struct device *d) { (void)d;return "test"; }
static void platform_set_drvdata(struct platform_device *p,void *data) { p->data=data; }
static void *platform_get_drvdata(struct platform_device *p) { return p->data; }
static int devm_add_action_or_reset(struct device *d,void (*fn)(void *),void *arg) {
    (void)d; if(failed()) { fn(arg);return -ENOMEM; } add(fn,arg);return 0;
}
static struct device_node *zx_port_node(struct device *d,int p) { (void)d;(void)p;return &node; }
/* Resource resolution and phy-mode parsing have their own tests
 * (test_eth_dt_resources.py); here they are failure points with today's map. */
static int zx_eth_resolve_regs(struct zx_eth *z,struct platform_device *p) {
    (void)p;if(failed())return -EINVAL;
    for(int i=0;i<ZX_NPORTS;i++)z->phys[ZX_REG_MAC0+i]=ZX_MAC_BASE+i*ZX_MAC_STRIDE;
    z->phys[ZX_REG_BM]=BM_BASE;z->phys[ZX_REG_TMC]=TMC_BASE;
    z->phys[ZX_REG_TMD]=TMD_BASE;z->phys[ZX_REG_TMQ]=TMQ_BASE;return 0;
}
static int zx_eth_phy_modes(struct zx_eth *z) {
    if(failed())return -EINVAL;
    for(int i=0;i<ZX_NPORTS;i++)z->phy_modes[i]=1;
    z->phy_mode=1;return 0;
}
/* memory-region resolution: test_eth_memory_region.py. */
static int zx_eth_resolve_ddr(struct zx_eth *z) {
    if(failed())return -EINVAL;
    z->ddr_phys=ZX_DDR_BASE;return 0;
}
static struct device_node *of_parse_phandle(struct device_node *n,const char *s,unsigned i) { (void)n;(void)s;(void)i;return &node; }
static void of_node_put(void *p) { (void)p; }
static void zx_set_mac_from_dt(struct zx_eth *z,struct net_device *n,struct device_node *p,int i) {
    (void)z;(void)p;memset(n->dev_addr,i+1,ETH_ALEN);
}
static void zx_mac_enable(struct zx_eth *z,int p,bool enable) {
    alive(z->macs[p]);writel(enable?3:0,z->macs[p]);
}
static bool zx_datapath_warm(struct zx_eth *z);
static int zx_eth_datapath_init(struct zx_eth *z) {
    if(inherited_warm)assert(zx_datapath_warm(z));
    init_calls++;
    assert(z->bufs && z->freelists); hardware_started=true;
    writel(1,z->bm); if(failed()) return -EIO;
    writel(0x41a00000,z->tmc+TMC_RING_BASE);writel(0x41c00000,z->tmq+TMQ_TXRING);return 0;
}
static int zx_eth_cpu_protocols(struct zx_eth *z) { (void)z;return failed()?-EIO:0; }
static int zx_eth_software_ports(struct zx_eth *z) { (void)z;return failed()?-EIO:0; }
static void zx_rx_retry_work(struct work_struct *w) { (void)w; }
/* Datapath recovery work: set up in probe, cancelled (initialized-checked) by
 * zx_napi_delete(); never run by a probe. */
static void zx_wd_work(struct work_struct *w) { (void)w; assert(0); }
static void zx_dp_reset_work(struct work_struct *w) { (void)w; assert(0); }
static int zx_eth_poll(struct napi_struct *n,int b) { (void)n;(void)b;return 0; }
static void netif_napi_add(struct net_device *d,struct napi_struct *n,int (*fn)(struct napi_struct *,int)) {
    (void)d;(void)fn;assert(!n->initialized);n->initialized=true;
}
static void netif_napi_del(struct napi_struct *n) { assert(n->initialized && !active_ports);n->initialized=false; }
static void cancel_delayed_work_sync(struct delayed_work *w) { assert(w->initialized); }
static void timer_shutdown_sync(struct timer_list *t) { assert(t->initialized);t->shutdown=true; }
static void ready(struct zx_eth *z) {
    assert(z->bm_lock && z->tx_lock && z->irq_lock && z->tx_timer.initialized);
    assert(z->ring && z->txring && z->bufs && z->bufs2 && z->freelists);
    assert(seed_writes==BUF_COUNT+BUF2_COUNT);
    for(unsigned i=0;i<RING_ENTRIES;i++) assert(z->tx_bp[i]==UINT32_MAX);
    for(int p=0;p<ZX_NPORTS;p++) if(p!=z->bound_port) {
        assert(z->ports[p]);alive(z->ports[p]);
        struct zx_port_priv *pp=netdev_priv(z->ports[p]);assert(pp->ze==z && pp->port==p);
    }
}
static void mod_timer(struct timer_list *t,unsigned long deadline) {
    (void)deadline;assert(t->initialized && !t->shutdown);ready(live);
    if(!in_timer) { in_timer=true;t->callback(t);in_timer=false; }
}
static int zx_eth_irq(int n,void *arg) {
    (void)n;struct zx_eth *z=arg;assert(z->napi.initialized && z->tx_timer.initialized);
    alive(z->ring);alive(z->txring);assert(!z->running);return 0;
}
static int zx_irq_probe_handler(int n,void *arg) { (void)n;(void)arg;return 0; }
static void release_irq(void *p) { (void)p;assert(!active_ports);irq_releases++; }
static int devm_request_irq(struct device *d,int n,int (*fn)(int,void *),unsigned f,const char *s,void *arg) {
    (void)d;(void)f;(void)s;if(failed())return -EBUSY;
    irq_requests++;fn(n,arg);add(release_irq,arg);return 0;
}
static void rtnl_lock(void) { }
static void rtnl_unlock(void) { }
static void dev_close(struct net_device *d) {
    alive(d);
    if(d->running) { assert(active_ports);d->running=false;active_ports--; }
}
static void unregister_netdev(void *arg) {
    struct net_device *d=arg;alive(d);assert(d->registered);
    /* An immediate callback can inspect all port pointers during unregister. */
    for(int i=0;i<ZX_NPORTS;i++) if(live->ports[i]) alive(live->ports[i]);
    dev_close(d);d->registered=false;
}
static int devm_register_netdev(struct device *d,struct net_device *n) {
    (void)d;ready(live);if(failed())return -EIO;
    n->registered=n->running=true;active_ports++;registrations++;
    add(unregister_netdev,n);return 0;
}
static void zx_rx_seed_publish(struct zx_eth *z) { ready(z);assert(registrations==4);zx_dbg_ze=z; }
static void zx_rx_seed_unpublish(struct zx_eth *z) { if(zx_dbg_ze==z)zx_dbg_ze=NULL; }
static void *proc_create(const char *s,unsigned mode,void *parent,const void *ops) {
    (void)s;(void)mode;(void)parent;(void)ops;
    /* Model a reader as soon as the file becomes visible. */
    assert(zx_dbg_ze==live);ready(zx_dbg_ze);proc_entries++;return &node;
}
static void remove_proc_entry(const char *s,void *parent) { (void)s;(void)parent;assert(proc_entries);proc_entries--; }
'''

CASES = r'''
static unsigned exercise(unsigned failure) {
    memset(memory,0,sizeof(memory));memset(actions,0,sizeof(actions));
    nmem=nactions=calls=seed_writes=active_ports=registrations=0;
    irq_requests=irq_releases=disarms=proc_entries=init_calls=0;fail_at=failure;
    in_timer=hardware_started=false;live=zx_dbg_ze=zx_eth_singleton=NULL;
    struct platform_device p={.dev={.of_node=&node}};
    int result=zx_eth_probe(&p);unsigned total=calls;
    if(!failure) {
        assert(result==0 && registrations==4 && proc_entries==(CONFIG_ZX279128_ETH_DEBUG?5:0));
        assert(init_calls==1 && live->tx_next==0);
        assert(live->phy_mode==1 && live->phy_modes[ZX_NPORTS-1]==1); /* DT parsed */
        zx_eth_remove(&p);
    } else {
        assert(result<0 && !proc_entries && !zx_dbg_ze && !zx_eth_singleton);
    }
    while(nactions) { struct action a=actions[--nactions];a.fn(a.arg); }
    assert(!active_ports && irq_requests==irq_releases);
    if(hardware_started)assert(disarms==1);
    for(unsigned i=0;i<nmem;i++) { assert(!memory[i].alive);free(memory[i].ptr); }
    return total;
}
int main(void) {
    unsigned total=exercise(0);
    assert(total>25);
    for(unsigned failure=1;failure<=total;failure++)exercise(failure);
    inherited_warm=true;
    exercise(0); /* Real warm detector sees inherited rings/MACs, without a boot override. */
    if(!CONFIG_ZX279128_ETH_DEBUG) {
        zx_force_dp_init=false;zx_skip_dp_init=true;
        exercise(0); /* Debug escape variables cannot bypass a release rebuild. */
    }
    printf("PASS current probe: %u injected failure points and immediate callbacks\n",total);
    return 0;
}
'''


class ProbeTests(unittest.TestCase):
    def test_current_probe_publication_and_every_acquisition_failure(self):
        source = SOURCE.read_text()
        structs = '\n'.join([exact_enum(source, 'zx_eth_reg')] +
                            [exact_struct(source, name) for name in
                             ('zx_rx_queue', 'zx_eth', 'zx_port_priv')])
        functions = '\n'.join(function(source, name) for name in (
            'zx_datapath_warm',
            'zx_phy_node_put', 'zx_eth_prepare_port_ndev', 'zx_eth_add_port_ndev',
            'zx_tx_done_timer', 'zx_bm_seed_freelists', 'zx_napi_delete',
            'zx_eth_disarm', 'zx_eth_close_ports', 'zx_tx_origin_init',
            'zx_eth_probe', 'zx_eth_remove'))
        with tempfile.TemporaryDirectory() as directory:
            cfile, executable = Path(directory)/'probe.c', Path(directory)/'probe'
            gate = next(line for line in source.splitlines() if line.startswith('#define ZX_HAVE_DEBUG_IFACES '))
            force_default = re.search(r'static bool zx_force_dp_init[^;]*;', source).group()
            cfile.write_text(MODEL + '\n' + gate + '\n' + structs + force_default +
                             BOUNDARIES + functions + CASES)
            for debug in (0, 1):
                with self.subTest(debug=debug):
                    built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                            '-Wno-unused-function', f'-DCONFIG_ZX279128_ETH_DEBUG={debug}',
                                            str(cfile), '-o', str(executable)],
                                           capture_output=True, text=True, timeout=30)
                    self.assertEqual(built.returncode, 0, built.stderr)
                    run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            print(run.stdout.strip())


if __name__ == '__main__':
    unittest.main()
