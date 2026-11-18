"""Compile the driver's RX stall watchdog and datapath reset against a stub kernel.

Covers zx_rx_stall_check(), zx_wd_work(), zx_dp_request_reset() and
zx_dp_reset_work(): when a stall is declared, what the watchdog does about it,
and the reset's control flow - rate limit, give-up cap, close/re-init/reopen
order and the software state a reset must leave behind. The hardware side
(whether zx_eth_datapath_init() really revives a wedged TM) is a bench question
this cannot answer.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_eth_rx import DRIVER

MODEL = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint8_t u8;
#define HZ 100
#define MSEC_PER_SEC 1000
#define DIV_ROUND_UP(n, d) (((n) + (d) - 1) / (d))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define time_before(a, b) ((long)((a) - (b)) < 0)
#define ZX_RX_QUEUES 8
#define ZX_RX_RINGS 16
#define ZX_NPORTS 4
#define RING_ENTRIES 1024
#define TMQ_PENDING 0x100
#define TMC_IRQ_MASK 0x104
#define TMD_GO 0x64
#define BM_FREECNT 0xdc
#define ZX_RESET_INTERVAL (10 * HZ)
#define ZX_RESET_MAX_CONSEC 3

struct work_struct { int unused; };
struct delayed_work { struct work_struct work; };
#define to_delayed_work(p) container_of(p, struct delayed_work, work)
struct napi_struct { int unused; };
struct timer_list { int armed; };
struct net_device { bool up; int id; };
struct zx_rx_queue {
    u16 cursor, remaining, buffer;
    u8 pool, class;
    bool debt, buffer_pending, return_sent;
};
struct zx_eth {
    struct net_device *ndev;
    struct net_device *ports[ZX_NPORTS];
    void *tmc, *tmd, *tmq, *bm;
    struct napi_struct napi;
    struct zx_rx_queue rxq[ZX_RX_RINGS];
    unsigned rx_next, dp_users;
    int rx_inflight, irq_lock;
    bool rx_fault, running, removing, rx_seed_eligible;
    u32 tx_outstanding, tx_next;
    struct timer_list tx_timer;
    struct delayed_work wd_work, reset_work;
    const char *reset_reason;
    bool resetting, reset_nagged, reset_manual;
    unsigned wd_stuck, reset_consec, rx_blocked_polls;
    unsigned long wd_rls, reset_rls, last_reset;
    unsigned long n_resets, n_wd_kicks, n_bad_pending;
    unsigned long n_desc_rls, n_desc_busy;
    u32 tx_bp[RING_ENTRIES];
#ifdef CONFIG_ZX279128_PP_TABLES
    void *pp;
#endif
};

static bool zx_rx_recover = true;
static unsigned zx_rx_stall_ms = 3000;
static unsigned long jiffies = 100000;
static unsigned char tmc[512], tmd[512], tmq[512], bm[512];
static struct zx_eth ze;
static struct net_device devs[ZX_NPORTS + 1];

static unsigned locks, rtnl, bh, errs, warns, infos, kicks;
static unsigned wd_armed, resets_queued, inits, closes, opens, protos, swports, seeds;
static char seq[32]; static unsigned seqn;
static int swports_ret;
static unsigned long reset_delay;
static int init_ret, proto_ret, open_ret;
static int close_order[8], open_order[8];
static bool init_leaves_pending, init_leaves_go;

static u32 load(void *p) { u32 v; memcpy(&v, p, 4); return v; }
static void store(void *p, u32 v) { memcpy(p, &v, 4); }
static u32 readl(void *p) { return load(p); }
static void writel(u32 v, void *p) { store(p, v); }
#define spin_lock_irqsave(lock, flags) ((void)(lock), (flags)=0, locks++)
#define spin_unlock_irqrestore(lock, flags) ((void)(lock), (void)(flags), locks--)
static void local_bh_disable(void) { bh++; }
static void local_bh_enable(void) { assert(bh && !locks); bh--; }
static void napi_schedule(struct napi_struct *n) { (void)n; assert(locks && bh); kicks++; }
static void rtnl_lock(void) { assert(!rtnl); rtnl = 1; }
static void rtnl_unlock(void) { assert(rtnl); rtnl = 0; }
#define netdev_err(dev, ...) ((void)(dev), errs++)
#define netdev_warn(dev, ...) ((void)(dev), warns++)
#define netdev_info(dev, ...) ((void)(dev), infos++)
static void schedule_delayed_work(struct delayed_work *w, unsigned long d) {
    if (w == &ze.wd_work) { assert(d == HZ); wd_armed++; }
    else { assert(w == &ze.reset_work); resets_queued++; reset_delay = d; }
}
static bool netif_running(struct net_device *d) { return d->up; }
static void dev_close(struct net_device *d) {
    assert(rtnl && d->up);
    d->up = false; close_order[closes++] = d->id;
    if (!--ze.dp_users) ze.running = false;
}
static int dev_open(struct net_device *d, void *extack) {
    (void)extack; assert(rtnl && !d->up && !ze.resetting);
    open_order[opens++] = d->id;
    if (open_ret) return open_ret;
    if (ze.rx_fault) return -EIO;   /* what zx_dp_start() does */
    d->up = true; ze.dp_users++; ze.running = true;
    return 0;
}
static int del_timer_sync(struct timer_list *t) {
    assert(ze.resetting); t->armed = 0; return 1;
}
static int mod_timer(struct timer_list *t, unsigned long when) {
    assert(!ze.resetting && when == jiffies + 1); t->armed = 1; return 0;
}
static void step(char c) { assert(seqn + 1 < sizeof(seq)); seq[seqn++] = c; seq[seqn] = 0; }
static int zx_eth_datapath_init(struct zx_eth *z) {
    int q;

    step('I');
    assert(z->resetting && !z->dp_users && !z->tx_timer.armed && rtnl);
    inits++;
    for (q = 0; q < ZX_RX_QUEUES; q++)
        store(tmq + TMQ_PENDING + q * 4, init_leaves_pending && !q ? 3 : 0);
    store(tmd + TMD_GO, init_leaves_go);
    return init_ret;
}
/* The probe's post-init order: software port policy, CPU protocols, gap_add,
 * BPPE seed, IRQ mask - all with the fabric still held (resetting). */
static int zx_eth_software_ports(struct zx_eth *z) {
    assert(z->resetting && rtnl && !z->dp_users); swports++; step('S'); return swports_ret;
}
static int zx_eth_cpu_protocols(struct zx_eth *z) {
    assert(z->resetting); protos++; step('P'); return proto_ret;
}
static void zx_bm_seed_freelists(struct zx_eth *z) {
    assert(z->resetting && (load(tmc) & 0x40)); seeds++; step('B');
}
static void zx_tx_origin_init(struct zx_eth *z, bool inited) { assert(inited); z->tx_next = 0; }

static void reset(void) {
    int i;

    memset(&ze, 0, sizeof(ze)); memset(devs, 0, sizeof(devs));
    memset(tmc, 0, sizeof(tmc)); memset(tmd, 0, sizeof(tmd));
    memset(tmq, 0, sizeof(tmq)); memset(bm, 0, sizeof(bm));
    ze.tmc = tmc; ze.tmd = tmd; ze.tmq = tmq; ze.bm = bm;
    for (i = 0; i <= ZX_NPORTS; i++) devs[i].id = i;
    ze.ndev = &devs[0];
    ze.rx_inflight = -1;
    locks = rtnl = bh = errs = warns = infos = kicks = 0;
    wd_armed = resets_queued = inits = closes = opens = protos = swports = seeds = 0;
    seqn = 0; seq[0] = 0; swports_ret = 0;
    reset_delay = 0; init_ret = proto_ret = open_ret = 0;
    init_leaves_pending = init_leaves_go = false;
    zx_rx_recover = true; zx_rx_stall_ms = 3000;
    memset(close_order, -1, sizeof(close_order));
    memset(open_order, -1, sizeof(open_order));
}
/* Bring the primary netdev and port 2's netdev up, as dp_start would. */
static void two_ports_up(void) {
    ze.ports[2] = &devs[3];
    devs[0].up = devs[3].up = true;
    ze.dp_users = 2; ze.running = true; ze.tx_timer.armed = 1;
}
"""

CASES = r"""
int main(void) {
    /* ---- zx_rx_stall_check ---- */
    reset(); ze.running = true;
    assert(zx_rx_stall_check(&ze) == ZX_WD_OK && ze.wd_stuck == 0);   /* idle */
    store(tmq + TMQ_PENDING, 5);
    ze.n_desc_rls = 10;
    assert(zx_rx_stall_check(&ze) == ZX_WD_OK);        /* moved since mark */
    ze.n_desc_rls = 20;
    assert(zx_rx_stall_check(&ze) == ZX_WD_OK);        /* still moving */
    assert(zx_rx_stall_check(&ze) == ZX_WD_KICK && ze.wd_stuck == 1);
    assert(zx_rx_stall_check(&ze) == ZX_WD_KICK && ze.wd_stuck == 2);
    assert(zx_rx_stall_check(&ze) == ZX_WD_RESET && ze.wd_stuck == 3);
    ze.n_desc_rls++;                                    /* any return clears it */
    ze.reset_nagged = true;
    assert(zx_rx_stall_check(&ze) == ZX_WD_OK && ze.wd_stuck == 0 && !ze.reset_nagged);
    zx_rx_stall_ms = 0;                                 /* kicks only */
    for (int i = 0; i < 10; i++)
        assert(zx_rx_stall_check(&ze) == ZX_WD_KICK);
    zx_rx_stall_ms = 1500;                              /* rounds up to 2 s */
    ze.wd_stuck = 0;
    assert(zx_rx_stall_check(&ze) == ZX_WD_KICK);
    assert(zx_rx_stall_check(&ze) == ZX_WD_RESET);
    store(tmq + TMQ_PENDING + 12, 1u << 16);            /* direction 1 counts */
    store(tmq + TMQ_PENDING, 0); ze.wd_stuck = 0; zx_rx_stall_ms = 3000;
    assert(zx_rx_stall_check(&ze) == ZX_WD_KICK);
    ze.rx_fault = true;                                 /* latched overrun */
    assert(zx_rx_stall_check(&ze) == ZX_WD_RESET);

    /* ---- zx_wd_work ---- */
    reset();
    zx_wd_work(&ze.wd_work.work);                       /* not running */
    assert(!wd_armed && !kicks && !resets_queued);
    reset(); ze.running = true; store(tmq + TMQ_PENDING, 1);
    zx_wd_work(&ze.wd_work.work);                       /* first stuck period */
    assert(kicks == 1 && ze.n_wd_kicks == 1 && wd_armed == 1 && bh == 0);
    zx_wd_work(&ze.wd_work.work);
    zx_wd_work(&ze.wd_work.work);                       /* third: reset */
    assert(kicks == 2 && resets_queued == 1 && reset_delay == 0 && wd_armed == 2);
    assert(ze.reset_reason && strstr(ze.reset_reason, "no return"));
    reset(); ze.running = true; ze.rx_fault = true;
    zx_wd_work(&ze.wd_work.work);
    assert(resets_queued == 1 && !wd_armed && strstr(ze.reset_reason, "exceeds"));
    reset(); ze.running = true; ze.rx_fault = true; zx_rx_recover = false;
    zx_wd_work(&ze.wd_work.work);
    zx_wd_work(&ze.wd_work.work);
    assert(!resets_queued && wd_armed == 2 && errs == 1);   /* said once, keeps watching */

    /* ---- zx_dp_request_reset ---- */
    reset();
    assert(zx_dp_request_reset(&ze, "why") && resets_queued == 1 && !strcmp(ze.reset_reason, "why"));
    reset(); ze.reset_consec = ZX_RESET_MAX_CONSEC;
    assert(!zx_dp_request_reset(&ze, "a") && !zx_dp_request_reset(&ze, "b"));
    assert(!resets_queued && errs == 1);
    ze.n_desc_rls = ze.reset_rls + 1;    /* RX moved: a new fault, budget back */
    assert(zx_dp_request_reset(&ze, "c") && resets_queued == 1);

    /* ---- zx_dp_reset_work: the full reset ---- */
    reset(); two_ports_up();
    ze.rx_fault = true; ze.reset_reason = "test";
    ze.rxq[3].cursor = 77; ze.rxq[3].debt = true; ze.rx_inflight = 3;
    ze.rx_next = 5; ze.rx_blocked_polls = 9; ze.rx_seed_eligible = true;
    ze.tx_outstanding = 12; ze.tx_next = 400; ze.n_desc_rls = 1234;
    memset(ze.tx_bp, 0, sizeof(ze.tx_bp));
    zx_dp_reset_work(&ze.reset_work.work);
    assert(closes == 2 && close_order[0] == 0 && close_order[1] == 3);
    assert(inits == 1 && protos == 1 && swports == 1 && seeds == 1);
    assert(!strcmp(seq, "ISPB"));                        /* the probe's order */
    assert((load(tmc + TMC_IRQ_MASK) & 7) == 7);         /* masked until open */
    for (int i = 0; i < RING_ENTRIES; i++) assert(ze.tx_bp[i] == 0xffffffffu);
    assert(opens == 2 && open_order[0] == 0 && open_order[1] == 3);
    assert(devs[0].up && devs[3].up && ze.dp_users == 2);
    assert(!ze.rx_fault && !ze.resetting && ze.tx_timer.armed);
    assert(ze.rxq[3].cursor == 0 && !ze.rxq[3].debt && ze.rx_inflight == -1);
    assert(ze.rx_next == 0 && ze.rx_blocked_polls == 0 && !ze.rx_seed_eligible);
    assert(ze.tx_outstanding == 0 && ze.tx_next == 0);
    assert(ze.n_resets == 1 && ze.last_reset == jiffies && ze.reset_rls == 1234);
    assert(load(tmc) & 0x40);                            /* gap_add restored */
    assert(!rtnl && !locks);

    /* Too soon after the last one: deferred, nothing touched. */
    ze.rx_fault = true; closes = opens = inits = 0;
    jiffies += 3 * HZ;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(!closes && !inits && resets_queued == 1 && reset_delay == 7 * HZ);

    /* No RX since the last reset: counted; three in a row and it stops. */
    for (int i = 0; i < 2; i++) {
        jiffies += ZX_RESET_INTERVAL; closes = opens = inits = 0;
        ze.rx_fault = true;
        zx_dp_reset_work(&ze.reset_work.work);
        assert(inits == 1 && ze.reset_consec == (unsigned)(i + 1));
    }
    jiffies += ZX_RESET_INTERVAL; closes = inits = 0; errs = 0;
    ze.rx_fault = true;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(!closes && !inits && errs == 1 && ze.reset_consec == ZX_RESET_MAX_CONSEC);
    assert(!zx_dp_request_reset(&ze, "again") && errs == 2);

    /* A manual request (/proc/zx_eth_reinit) ignores the give-up count and
     * the rate limit, and does not move the count. */
    {
        unsigned consec = ze.reset_consec;

        ze.reset_manual = true; inits = 0;
        jiffies += 1;                                    /* well inside the interval */
        zx_dp_reset_work(&ze.reset_work.work);
        assert(inits == 1 && ze.reset_consec == consec && !ze.reset_manual);
    }

    /* Progress between resets clears the count. */
    ze.reset_consec = 2; ze.n_desc_rls = ze.reset_rls + 50;
    jiffies += ZX_RESET_INTERVAL; inits = 0;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(inits == 1 && ze.reset_consec == 0);

    /* Re-init failure: fault stays latched and the ports stay down. */
    reset(); two_ports_up(); ze.reset_reason = "t"; init_ret = -ETIMEDOUT;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(closes == 2 && !opens && ze.rx_fault && !devs[0].up && !devs[3].up);
    assert(ze.tx_timer.armed && !ze.resetting && errs == 1);

    /* The probe's own post-init check: a queue not empty after init. */
    reset(); two_ports_up(); ze.reset_reason = "t"; init_leaves_pending = true;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(!opens && ze.rx_fault && errs == 1);

    /* Descriptor return still busy after init: -EBUSY, ports stay down. */
    reset(); two_ports_up(); ze.reset_reason = "t"; init_leaves_go = true;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(!opens && ze.rx_fault && !protos && !swports && errs == 1);

    /* Software port policy that does not apply after init: WAN and LAN would
     * share a hardware bridge, so the ports must stay down. */
    reset(); two_ports_up(); ze.reset_reason = "t"; swports_ret = -ETIMEDOUT;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(swports == 1 && !protos && !seeds && !opens && ze.rx_fault);

    /* SPA protocol selectors that do not latch after init: same outcome. */
    reset(); two_ports_up(); ze.reset_reason = "t"; proto_ret = -EIO;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(protos == 1 && !seeds && !opens && ze.rx_fault);

    /* Removal in progress: nothing. */
    reset(); two_ports_up(); ze.removing = true; ze.rx_fault = true;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(!closes && !inits && ze.rx_fault && !rtnl);

    /* Everything was closed since the request and nothing is latched. */
    reset(); ze.reset_reason = "t";
    zx_dp_reset_work(&ze.reset_work.work);
    assert(!closes && !inits && !ze.n_resets);

    /* All ports closed but the fault is latched: re-init with none open, so
     * the next ifup does not meet -EIO. */
    reset(); ze.rx_fault = true; ze.reset_reason = "t";
    zx_dp_reset_work(&ze.reset_work.work);
    assert(inits == 1 && !opens && !ze.rx_fault && ze.n_resets == 1);

    /* Manual with every port closed and nothing latched: still re-inits. */
    reset(); ze.reset_manual = true; ze.reset_reason = "t";
    zx_dp_reset_work(&ze.reset_work.work);
    assert(inits == 1 && !opens && ze.n_resets == 1 && !ze.reset_manual);

    /* A reopen that fails is reported per port, the rest still reopen. */
    reset(); two_ports_up(); ze.reset_reason = "t"; open_ret = -ENODEV;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(opens == 2 && errs == 2 && !ze.rx_fault);
#ifdef CONFIG_ZX279128_PP_TABLES
    /* Diagnostic builds: never reset under live packet-processor tables. */
    reset(); two_ports_up(); ze.rx_fault = true; ze.reset_reason = "t";
    ze.pp = &ze;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(!closes && !inits && errs == 1 && devs[0].up && !rtnl);
    ze.pp = NULL; errs = 0;
    zx_dp_reset_work(&ze.reset_work.work);
    assert(closes == 2 && inits == 1 && opens == 2);
#endif
    return 0;
}
"""


class RecoverTests(unittest.TestCase):
    def test_watchdog_and_reset_control_flow(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        source = DRIVER.read_text()

        def section(start, end):
            offset = source.index(start)
            return source[offset:source.index(end, offset)]

        pending = section("static bool zx_rx_any_pending(",
                          "static bool zx_rx_software_pending(")
        request = section("static bool zx_dp_request_reset(",
                          "static int zx_eth_poll(")
        watchdog = section("enum zx_wd_verdict {",
                           "/* Cursors, cached counts and release debt survive")
        worker = section("static void zx_dp_reset_work(",
                         "static int zx_eth_probe(")
        for defines in ([], ["-DCONFIG_ZX279128_PP_TABLES"]):
            with self.subTest(defines=defines), tempfile.TemporaryDirectory() as directory:
                cfile, binary = Path(directory) / "recover.c", Path(directory) / "recover"
                cfile.write_text(MODEL + pending + request + watchdog + worker + CASES)
                result = subprocess.run(
                    [compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                     "-Wno-unused-parameter", *defines, str(cfile), "-o", str(binary)],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                subprocess.run([str(binary)], check=True, timeout=10)

    def test_recovery_is_wired_in(self):
        """Structural checks the compiled harness cannot see."""
        source = DRIVER.read_text()
        # rx_fault is no longer a dead end: the poll asks for a reset.
        poll = source[source.index("static int zx_eth_poll("):]
        poll = poll[:poll.index("static void zx_eth_adjust_link(")]
        self.assertIn("zx_dp_request_reset(ze,", poll)
        # The watchdog starts with the datapath and stops with it.
        start = source[source.index("static int zx_dp_start("):]
        start = start[:start.index("static int zx_eth_open(")]
        self.assertIn("schedule_delayed_work(&ze->wd_work, HZ)", start)
        self.assertIn("cancel_delayed_work_sync(&ze->wd_work)", start)
        params = source[:source.index("static int zx_eth_poll(")]
        knob = params.index("module_param_named(rx_recover,")
        # It is compiled in and ON by default in every build; only the knob is
        # debug-only, because a release object carries no parameters at all.
        self.assertIn("static bool zx_rx_recover = true;", params)
        self.assertIn("#if IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG)",
                      params[params.rindex("static bool zx_rx_recover", 0, knob):knob])
        # The release TX path never spins: the drain probe is opt-in.
        xmit = source[source.index("static netdev_tx_t zx_eth_xmit("):]
        xmit = xmit[:xmit.index("static bool zx_rx_any_pending(")]
        self.assertIn("if (zx_tx_drain_probe && zx_tx_drain_us)", xmit)
        # Teardown cancels the reset before the TX timer it re-arms.
        teardown = source[source.index("static void zx_napi_delete("):]
        teardown = teardown[:teardown.index("static void zx_eth_close_ports(")]
        self.assertLess(teardown.index("reset_work"), teardown.index("timer_shutdown_sync"))
        # The TX timer is set up before the devm action that deletes it.
        probe = source[source.index("static int zx_eth_probe("):]
        self.assertLess(probe.index("timer_setup(&ze->tx_timer"),
                        probe.index("zx_napi_delete, ze"))
        self.assertEqual(probe.count("timer_setup(&ze->tx_timer"), 1)
        # Every TM source is masked before the line is requested.
        self.assertLess(probe.index("writel(0xffffffff, ze->tmc + TMC_IRQ_MASK)"),
                        probe.index("devm_request_irq(dev, ze->irq"))
        # /proc/zx_eth_reinit now queues the reset instead of refusing.
        reinit = source[source.index("static ssize_t zx_reinit_write("):]
        reinit = reinit[:reinit.index("\n}\n")]
        self.assertNotIn("EOPNOTSUPP", reinit)
        self.assertIn("reset_manual, true", reinit)
        self.assertIn("mod_delayed_work(system_wq, &ze->reset_work, 0)", reinit)
        # The TX timer never re-arms into a reset in progress.
        timer = source[source.index("static void zx_tx_done_timer("):]
        timer = timer[:timer.index("\n}\n")]
        self.assertIn("resetting", timer)


if __name__ == "__main__":
    unittest.main()
