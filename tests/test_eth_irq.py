"""Exercise actual IRQ/rearm and first-open/last-close lifecycle helpers."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_eth_rx import DRIVER

MODEL = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef int irqreturn_t;
#define IRQ_NONE 0
#define IRQ_HANDLED 1
#define ZX_RX_QUEUES 8
#define ZX_RX_RINGS 16
#define TMQ_PENDING 0x100
#define TMC_IRQ_STATUS 0x100
#define TMC_IRQ_MASK 0x104
#define READ_ONCE(x) (x)
#define HZ 100
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; };
#define to_delayed_work(p) container_of(p,struct delayed_work,work)
struct napi_struct { int unused; };
struct zx_rx_queue { unsigned cursor, remaining; bool debt; };
struct zx_eth {
    void *tmc, *tmq;
    int irq_lock, irq;
    bool running, rx_fault, removing;
    unsigned dp_users;
    struct zx_rx_queue rxq[ZX_RX_RINGS];
    struct napi_struct napi;
    struct delayed_work rx_retry;
    struct delayed_work wd_work;
    unsigned long n_desc_rls, wd_rls;
    unsigned wd_stuck;
};
static unsigned char tmc[512], tmq[512];
static unsigned locks, schedules, enabled, stage, pending_reads, wd_armed, bh;
static bool inject_on_unmask;
static int seed_result;
static unsigned seed_calls;
static struct zx_eth ze;
static int zx_rx_seed_start(struct zx_eth *z) { assert(z==&ze); seed_calls++; return seed_result; }
#define spin_lock_irqsave(lock, flags) ((void)(lock), (flags)=0, locks++)
#define spin_unlock_irqrestore(lock, flags) ((void)(lock), (void)(flags), locks--)
static u32 load(void *p) { u32 v; memcpy(&v,p,4); return v; }
static void store(void *p, u32 v) { memcpy(p,&v,4); }
static u32 readl(void *p) {
    if ((uintptr_t)p >= (uintptr_t)tmq && (uintptr_t)p < (uintptr_t)tmq+sizeof(tmq)) pending_reads++;
    return load(p);
}
static void writel(u32 value, void *p) {
    assert(locks && p==tmc+TMC_IRQ_MASK); store(p,value);
    if(!(value&3) && inject_on_unmask) {
        store(tmq+TMQ_PENDING,1); inject_on_unmask=false;
    }
}
static void napi_schedule(struct napi_struct *n) { (void)n; assert(locks); schedules++; }
static void napi_schedule_irqoff(struct napi_struct *n) { napi_schedule(n); }
static void napi_enable(struct napi_struct *n) { (void)n; assert(!locks && !enabled); enabled=1; }
static void synchronize_irq(int irq) {
    assert(irq==36 && !locks && (load(tmc+TMC_IRQ_MASK)&7)==7); stage=1;
}
static void napi_disable(struct napi_struct *n) { (void)n; assert(stage==1 && enabled); enabled=0; stage=2; }
/* Last close: IRQ quiesced, NAPI disabled, then the retry work, then the
 * watchdog, then synchronize_net, in that order. */
static void cancel_delayed_work_sync(struct delayed_work *w) {
    if (w==&ze.rx_retry) { assert(stage==2); stage=3; }
    else { assert(w==&ze.wd_work && stage==3); stage=4; }
}
static void synchronize_net(void) { assert(stage==4 && !locks && !enabled && !ze.running); stage=5; }
static void schedule_delayed_work(struct delayed_work *w, unsigned long d) {
    assert(w==&ze.wd_work && d==HZ && !locks && ze.running); wd_armed++;
}
static void local_bh_disable(void) { bh++; }
static void local_bh_enable(void) { assert(bh && !locks); bh--; }
static void reset(void) {
    memset(&ze,0,sizeof(ze)); memset(tmc,0,sizeof(tmc)); memset(tmq,0,sizeof(tmq));
    ze.tmc=tmc; ze.tmq=tmq; ze.irq=36;
    store(tmc+TMC_IRQ_MASK,0xffffffff);
    locks=schedules=enabled=stage=pending_reads=wd_armed=bh=0; inject_on_unmask=false;
    seed_result=0; seed_calls=0;
}
"""

CASES = r"""
int main(void) {
    reset(); store(tmc+TMC_IRQ_STATUS,1);
    assert(zx_eth_irq(36,&ze)==IRQ_NONE && schedules==0);
    ze.n_desc_rls=77; ze.wd_stuck=5;
    assert(zx_dp_start(&ze)==0 && enabled && ze.running && ze.dp_users==1);
    assert(wd_armed==1 && ze.wd_rls==77 && ze.wd_stuck==0);
    assert(load(tmc+TMC_IRQ_MASK)==0xfffffffc);
    assert(zx_eth_irq(36,&ze)==IRQ_HANDLED && schedules==1);
    assert(load(tmc+TMC_IRQ_MASK)==0xffffffff);
    assert(zx_eth_irq(36,&ze)==IRQ_NONE && schedules==1);
    assert(zx_dp_start(&ze)==0 && ze.dp_users==2 && wd_armed==1);
    zx_dp_stop(&ze); assert(ze.running && enabled && ze.dp_users==1 && stage==0);
    zx_dp_stop(&ze); assert(!ze.running && !enabled && !ze.dp_users && stage==5);
    zx_rx_retry_work(&ze.rx_retry.work); assert(schedules==1 && bh==0);

    reset(); ze.rxq[0].cursor=53; ze.rxq[0].remaining=7; ze.rxq[0].debt=true;
    assert(zx_dp_start(&ze)==0 && schedules==1 && !pending_reads);
    assert(load(tmc+TMC_IRQ_MASK)==0xffffffff);
    zx_dp_stop(&ze);
    assert(ze.rxq[0].cursor==53 && ze.rxq[0].remaining==7 && ze.rxq[0].debt);
    assert(zx_dp_start(&ze)==0 && schedules==2);
    zx_dp_stop(&ze);

    reset(); inject_on_unmask=true;
    assert(zx_dp_start(&ze)==0 && schedules==1);
    assert(load(tmc+TMC_IRQ_MASK)==0xffffffff && load(tmq+TMQ_PENDING)==1);
    zx_dp_stop(&ze);

    reset(); ze.removing=true;
    assert(zx_dp_start(&ze)==-ENODEV && !ze.dp_users && !enabled);
    ze.removing=false; ze.rx_fault=true;
    assert(zx_dp_start(&ze)==-EIO && !ze.dp_users && !enabled && !locks);
    assert(seed_calls==0);
    reset(); seed_result=-EINVAL;
    assert(zx_dp_start(&ze)==-EINVAL && seed_calls==1);
    assert(!ze.dp_users && !enabled && !ze.running && !schedules && !locks);
    assert(load(tmc+TMC_IRQ_MASK)==0xffffffff);
    return 0;
}
"""


class IrqTests(unittest.TestCase):
    def test_mask_rearm_and_lifecycle(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        source = DRIVER.read_text()
        def section(start, end):
            offset = source.index(start)
            return source[offset:source.index(end, offset)]
        helpers = section("static bool zx_rx_any_pending(", "/* Called only by NAPI.")
        irq = section("static void zx_rx_rearm(", "static struct net_device *zx_rxdev(")
        lifecycle = section("static int zx_dp_start(", "static int zx_eth_open(")
        with tempfile.TemporaryDirectory() as directory:
            cfile, binary = Path(directory) / "irq.c", Path(directory) / "irq"
            cfile.write_text(MODEL + helpers + irq + lifecycle + CASES)
            result = subprocess.run([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                                     "-Wno-unused-parameter", str(cfile), "-o", str(binary)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, timeout=10)
