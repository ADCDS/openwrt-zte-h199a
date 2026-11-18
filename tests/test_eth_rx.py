"""Compile actual RX polling and release against a deterministic MMIO model."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

DRIVER = Path(__file__).resolve().parents[1] / (
    "files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c")

STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <arpa/inet.h>
#include <limits.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
#define BIT(n) (1u << (n))
#define ZX_RX_QUEUES 8
#define ZX_RX_RINGS 16
#define RING_ENTRIES 1024
#define DESC_SIZE 16
#define ZX_RX_RING_SIZE (RING_ENTRIES * DESC_SIZE)
#define BUF_COUNT 2048
#define BUF2_COUNT 512
#define BUF_SIZE 2048
#define BUF_HDR 16
#define ETH_HLEN 14
#define ZX_HAVE_DEBUG_IFACES 1
#define NET_SKB_PAD 32
#define NET_IP_ALIGN 2
#define TMD_GO 0x64
#define TMD_PAYLOAD 0x68
#define TMQ_PENDING 0x100
#define TMC_IRQ_MASK 0x104
#define BM_FREECNT 0xdc
#define BM_FREE 0x10
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define cpu_relax() ((void)0)
#define rmb() ((void)0)
#define cpu_to_be16(v) htons(v)
static void rx_log(const char *fmt, ...) { (void)fmt; }
#define pr_info(...) rx_log(__VA_ARGS__)
#define udelay(us) ((void)(us))
#define HZ 100
#define min(a,b) ((a) < (b) ? (a) : (b))
#define min_t(t,a,b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define ZX_RX_BLOCKED_POLLS 8
#define ZX_RESET_MAX_CONSEC 3
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
static bool zx_rx_recover = true;
static unsigned barrier, locks, reads, frees, submits, completes, rearms, retries;
static unsigned long last_delay;
static unsigned resets, pending_glitch;
static unsigned delivered[256], deliveries, faults, last_free;
static unsigned rcu_depth;
static bool stop_on_complete, stop_waiting, stop_finished, complete_result;
static bool defer_gro, replace_queue_on_complete, completion_pending;
static bool auto_complete;
static bool zx_rx_no_free, zx_no_gro;
static unsigned zx_rx_trace, direct_deliveries;
#define mb() (barrier=1)
#define spin_lock_irqsave(lock, flags) ((void)(lock), (flags)=0, locks++)
#define spin_unlock_irqrestore(lock, flags) ((void)(lock), (void)(flags), locks--)
#define netdev_err(dev, ...) ((void)(dev), faults++)
struct stats { unsigned rx_errors, rx_dropped, rx_packets, rx_bytes; };
struct net_device { struct stats stats; bool running; };
struct napi_struct { int unused; };
struct sk_buff {
    unsigned len, protocol;
    unsigned char *data;
    _Alignas(4) unsigned char storage[2112];
};
static struct sk_buff *pending_gro;
static void rcu_read_lock(void) { assert(!rcu_depth); rcu_depth=1; }
static void rcu_read_unlock(void) {
    assert(rcu_depth==1 && !locks); rcu_depth=0;
    if(stop_waiting) stop_finished=true;
}
static unsigned char tmd[512], tmq[512], tmc[512], bm[512];
static unsigned char rings[ZX_RX_RINGS*ZX_RX_RING_SIZE], buffers[BUF_COUNT*BUF_SIZE];
static unsigned char buffers2[BUF2_COUNT*BUF_SIZE];
static int system_wq;
"""

MODEL = r"""
struct zx_eth {
    struct net_device *ndev;
    struct napi_struct napi;
    void *tmd, *tmq, *tmc, *bm, *ring, *bufs, *bufs2;
    struct zx_rx_queue rxq[ZX_RX_RINGS];
    unsigned rx_next, free_credit, n_free_nocredit, n_desc_rls, n_desc_busy;
    int rx_inflight, irq_lock, bm_lock, rx_retry;
    bool rx_fault, running;
    /* RX protocol census, used by the poll path since the ingress
     * investigation needed to know what actually reached the netdev.
     */
    unsigned long c_icmp, c_udp, c_tcp_bare, c_tcp_data, c_report;
    unsigned long c_icmp_req, c_icmp_rep, c_proto_mismatch, n_prodzero, n_zerolen;
    /* Datapath recovery (zx_dp_request_reset() and the blocked-poll backoff). */
    unsigned long n_bad_pending, reset_rls;
    unsigned rx_blocked_polls, reset_consec;
    bool reset_nagged;
    const char *reset_reason;
    int reset_work;
};
static u32 load(void *p) { u32 v; memcpy(&v,p,4); return v; }
static void store(void *p, u32 v) { memcpy(p,&v,4); }
static u32 readl(void *p) {
    u32 v=load(p); reads++;
    if(p==tmq+TMQ_PENDING && pending_glitch) { pending_glitch--; return 0x7ff; }
    if(p==bm+BM_FREECNT) store(p,0);
    return v;
}
static u8 readb(void *p) { return *(u8 *)p; }
static int zx_rx_port_of(u32 w) { (void)w; return 0; }
static void zx_packet_trace_add(const void *data, unsigned len, bool tx, int port,
                                int rxring, unsigned slot, unsigned idx, unsigned pool) {
    (void)data; (void)len; (void)tx; (void)port; (void)rxring; (void)slot; (void)idx; (void)pool;
}
static void hardware_complete(void) {
    unsigned cmd=load(tmd+TMD_PAYLOAD), q=cmd&7, shift=((cmd>>14)&1)*16;
    u32 count=load(tmq+TMQ_PENDING+q*4);
    assert(((count>>shift)&0xffff)>0);
    store(tmq+TMQ_PENDING+q*4,count-(1u<<shift)); store(tmd+TMD_GO,0);
}
static void writel(u32 v, void *p) {
    if(p==bm+BM_FREE) { assert(barrier); frees++; last_free=v; }
    if(p==tmd+TMD_GO) { assert(v==1 && load(p)==0); submits++; }
    store(p,v);
    if(p==tmd+TMD_GO && auto_complete) hardware_complete();
}
static void memcpy_fromio(void *d, const void *s, size_t n) { memcpy(d,s,n); }
static bool netif_running(struct net_device *dev) { return dev->running; }
static struct net_device *zx_rxdev(struct zx_eth *ze, u32 w) { (void)w; return ze->ndev; }
static void skb_reserve(struct sk_buff *s, unsigned n) { s->data+=n; }
static struct sk_buff *napi_alloc_skb(struct napi_struct *n, unsigned len) {
    (void)n;
    struct sk_buff *s=calloc(1,sizeof(*s)); assert(s);
    assert(len+NET_SKB_PAD+NET_IP_ALIGN<=sizeof(s->storage));
    s->data=s->storage;
    /* Linux __napi_alloc_skb already reserves these bytes, unlike alloc_skb. */
    skb_reserve(s, NET_SKB_PAD+NET_IP_ALIGN);
    return s;
}
static void *skb_put(struct sk_buff *s, unsigned n) { void *p=s->data+s->len; s->len+=n; return p; }
static unsigned eth_type_trans(struct sk_buff *s, struct net_device *d) {
    /* Ethernet delivery must retain aligned network-layer headers. */
    assert(((uintptr_t)(s->data+ETH_HLEN)&3)==0);
    (void)d; return htons(((unsigned)s->data[12]<<8) | s->data[13]);
}
static void deliver(struct sk_buff *s) {
    assert(!locks && rcu_depth); assert(deliveries<256);
    delivered[deliveries++]=s->data[0]; free(s);
}
static void napi_gro_receive(struct napi_struct *n, struct sk_buff *s) {
    (void)n;
    if(defer_gro) { assert(!pending_gro); pending_gro=s; }
    else deliver(s);
}
static void netif_receive_skb(struct sk_buff *s) { direct_deliveries++; napi_gro_receive(NULL,s); }
static bool napi_complete_done(struct napi_struct *n, int done) {
    struct zx_eth *z=container_of(n,struct zx_eth,napi);
    (void)done; assert(!locks && rcu_depth); completes++;
    /* Real completion synchronously delivers any pending GRO list. */
    if(pending_gro) { deliver(pending_gro); pending_gro=NULL; }
    completion_pending=false;
    for(unsigned i=0;i<ZX_RX_RINGS;i++)
        completion_pending |= z->rxq[i].debt || z->rxq[i].remaining;
    if(replace_queue_on_complete) memset(z->rxq,0,sizeof(z->rxq));
    /* Stop can now acquire the IRQ lock and see NAPI ownership released,
     * but must wait for the protected callback tail before freeing state. */
    if(stop_on_complete) {
        z->running=false; stop_waiting=true; assert(!stop_finished);
    }
    return complete_result;
}
static void mod_delayed_work(int w, int *retry, unsigned long delay) {
    (void)w; (void)retry; assert(delay>=1 && delay<=HZ/10 && locks); retries++; last_delay=delay;
}
static void zx_rx_rearm(struct zx_eth *ze, bool software_pending) {
    assert(ze->running && locks && rcu_depth);
    assert(software_pending==completion_pending); rearms++;
}
/* The real zx_dp_request_reset() is compiled; its work queueing is counted. */
static void schedule_delayed_work(int *w, unsigned long delay) {
    (void)w; assert(delay==0); resets++;
}
static struct zx_eth ze;
static struct net_device dev;
static void reset(void) {
    assert(!rcu_depth && !pending_gro);
    memset(&ze,0,sizeof(ze)); memset(&dev,0,sizeof(dev));
    memset(tmd,0,sizeof(tmd)); memset(tmq,0,sizeof(tmq)); memset(tmc,0,sizeof(tmc));
    memset(bm,0,sizeof(bm)); memset(rings,0,sizeof(rings)); memset(buffers,0,sizeof(buffers));
    memset(buffers2,0,sizeof(buffers2));
    ze.ndev=&dev; ze.tmd=tmd; ze.tmq=tmq; ze.tmc=tmc; ze.bm=bm;
    ze.ring=rings; ze.bufs=buffers; ze.bufs2=buffers2; ze.rx_inflight=-1;
    dev.running=ze.running=true; auto_complete=true;
    barrier=locks=reads=frees=submits=completes=rearms=retries=deliveries=faults=0;
    zx_rx_no_free=zx_no_gro=false; zx_rx_trace=direct_deliveries=0;
    stop_on_complete=stop_waiting=stop_finished=defer_gro=false;
    replace_queue_on_complete=completion_pending=false; complete_result=true;
    resets=pending_glitch=0; last_delay=0; zx_rx_recover=true;
    store(bm+BM_FREECNT,32<<3);
}
static void frame(unsigned ring, unsigned slot, unsigned idx, unsigned label) {
    unsigned char *d=rings+ring*ZX_RX_RING_SIZE+slot*DESC_SIZE;
    memset(d,0,16); d[6]=1; d[7]=(idx&127)<<1; d[8]=idx>>7;
    d[12]=0; d[13]=1; /* 64 bytes */
    memset(buffers+idx*BUF_SIZE+BUF_HDR,label,64);
}
"""

CASES = r"""
static int checked_poll(struct napi_struct *n, int budget) {
    int result=zx_eth_poll(n,budget); assert(!rcu_depth); return result;
}
#define zx_eth_poll checked_poll
int main(void) {
    reset(); store(tmq+TMQ_PENDING,8);
    for(unsigned i=0;i<12;i++) frame(0,i,i,i+1);
    assert(zx_eth_poll(&ze.napi,3)==3);
    assert(ze.rxq[0].cursor==3 && ze.rxq[0].remaining==5 && deliveries==3);
    store(tmq+TMQ_PENDING,9); /* Four arrivals after the snapshot. */
    assert(zx_eth_poll(&ze.napi,16)==5);
    assert(ze.rxq[0].cursor==8 && ze.rxq[0].remaining==0 && deliveries==8);
    assert(zx_eth_poll(&ze.napi,16)==4);
    for(unsigned i=0;i<12;i++) assert(delivered[i]==i+1);
    assert(frees==12 && submits==12 && load(tmq+TMQ_PENDING)==0);

    reset(); ze.rxq[0].cursor=1023; store(tmq+TMQ_PENDING,2);
    frame(0,1023,0,101); frame(0,0,1,102);
    assert(zx_eth_poll(&ze.napi,4)==2 && ze.rxq[0].cursor==1);
    assert(delivered[0]==101 && delivered[1]==102);

    reset(); store(tmq+TMQ_PENDING,2); store(bm+BM_FREECNT,0);
    frame(0,0,0,1); frame(0,1,1,2);
    assert(zx_eth_poll(&ze.napi,8)==1);
    assert(ze.rxq[0].debt && ze.rxq[0].remaining==1 && retries==1);
    assert(frees==0 && submits==0 && load(tmq+TMQ_PENDING)==2);
    unsigned old_reads=reads, old_complete=completes;
    assert(zx_eth_poll(&ze.napi,0)==0 && reads==old_reads && completes==old_complete);
    store(bm+BM_FREECNT,32<<3);
    assert(zx_eth_poll(&ze.napi,8)==1);
    assert(ze.rxq[0].cursor==2 && deliveries==2 && frees==2 && submits==2);

    reset(); auto_complete=false; store(tmq+TMQ_PENDING,1); frame(0,0,0,7);
    assert(zx_eth_poll(&ze.napi,8)==1 && frees==1 && submits==1);
    assert(ze.rxq[0].debt && ze.rxq[0].return_sent && !ze.rxq[0].buffer_pending);
    assert(zx_eth_poll(&ze.napi,8)==0 && frees==1 && submits==1);
    hardware_complete(); auto_complete=true;
    assert(zx_eth_poll(&ze.napi,8)==0 && !ze.rxq[0].debt && ze.rx_inflight==-1);
    assert(deliveries==1 && frees==1 && submits==1);

    reset(); store(tmq+TMQ_PENDING+4,1u<<16); frame(9,0,0,99);
    assert(zx_eth_poll(&ze.napi,8)==1 && ze.rxq[9].cursor==1);
    assert(load(tmd+TMD_PAYLOAD)==0x4019 && delivered[0]==99);

    reset(); auto_complete=false; store(tmq+TMQ_PENDING,0x10001);
    frame(0,0,0,11); frame(8,0,1,88);
    assert(zx_eth_poll(&ze.napi,8)==2 && submits==1 && frees==2);
    assert(ze.rx_inflight==0 && ze.rxq[0].debt && ze.rxq[8].debt);
    hardware_complete(); auto_complete=true;
    assert(zx_eth_poll(&ze.napi,8)==0 && submits==2 && frees==2);
    assert(!ze.rxq[0].debt && !ze.rxq[8].debt && load(tmq+TMQ_PENDING)==0);
    assert(deliveries==2 && delivered[0]==11 && delivered[1]==88);

    reset(); store(tmq+TMQ_PENDING,1); frame(0,0,3,1); rings[9]=1;
    memset(buffers2+3*BUF_SIZE+BUF_HDR,77,64);
    assert(zx_eth_poll(&ze.napi,8)==1 && delivered[0]==77 && last_free==0x8003);

    reset(); store(tmq+TMQ_PENDING,1); frame(0,0,0,1); rings[8]=0xff;
    assert(zx_eth_poll(&ze.napi,8)==1 && dev.stats.rx_errors==1);
    assert(frees==0 && submits==1 && deliveries==0);

    reset(); store(tmq+TMQ_PENDING,1025);
    assert(zx_eth_poll(&ze.napi,8)==0 && ze.rx_fault && faults==1);
    assert(deliveries==0 && frees==0 && submits==0 && rearms==0 && locks==0);
    /* Persistent across the re-read: one reset request, count dropped. */
    assert(resets==1 && ze.n_bad_pending==1 && ze.rxq[0].remaining==0);

    /* rx_recover=0: the overrun still latches rx_fault, nothing is queued,
     * and the stop is logged exactly once (the pre-recovery behaviour). */
    reset(); zx_rx_recover=false; store(tmq+TMQ_PENDING,1025);
    assert(zx_eth_poll(&ze.napi,8)==0 && ze.rx_fault && resets==0);
    assert(faults==2 && ze.reset_nagged);

    reset(); zx_no_gro=true; store(tmq+TMQ_PENDING,1); frame(0,0,0,23);
    assert(zx_eth_poll(&ze.napi,8)==1 && deliveries==1 && direct_deliveries==1);
    assert(delivered[0]==23 && frees==1 && submits==1);

    reset(); store(tmq+TMQ_PENDING,1); frame(0,0,0,1); rings[12]=rings[13]=0;
    assert(zx_eth_poll(&ze.napi,8)==1 && ze.n_zerolen==1 && dev.stats.rx_errors==1);
    assert(deliveries==0 && frees==1 && submits==1);

    reset(); defer_gro=true; store(tmq+TMQ_PENDING,1); frame(0,0,0,91);
    assert(zx_eth_poll(&ze.napi,8)==1 && deliveries==1 && delivered[0]==91);
    assert(completes==1 && rearms==1 && !pending_gro);

    reset(); stop_on_complete=true; defer_gro=true;
    store(tmq+TMQ_PENDING,1); frame(0,0,0,92);
    assert(zx_eth_poll(&ze.napi,8)==1 && deliveries==1 && delivered[0]==92);
    assert(stop_waiting && stop_finished && !ze.running && rearms==0 && retries==0);

    reset(); complete_result=false;
    store(tmq+TMQ_PENDING,1); frame(0,0,0,93);
    assert(zx_eth_poll(&ze.napi,8)==1 && deliveries==1 && rearms==0 && retries==0);

    reset(); auto_complete=false; replace_queue_on_complete=true;
    store(tmq+TMQ_PENDING,1); frame(0,0,0,94);
    assert(zx_eth_poll(&ze.napi,8)==1 && deliveries==1 && completion_pending);
    assert(rearms==1 && retries==1); /* Uses pre-completion queue snapshot. */

    /* One glitched read is re-read, not latched. */
    reset(); store(tmq+TMQ_PENDING,2); frame(0,0,0,21); frame(0,1,1,22);
    pending_glitch=1;
    assert(zx_eth_poll(&ze.napi,8)==2 && !ze.rx_fault && faults==0);
    assert(resets==0 && ze.n_bad_pending==1 && delivered[0]==21 && delivered[1]==22);

    /* A return carried over from an earlier visit that retires at the top
     * of this one must not be followed by a refresh in the same visit. */
    reset(); auto_complete=false; store(tmq+TMQ_PENDING,1); frame(0,0,0,31);
    assert(zx_eth_poll(&ze.napi,8)==1 && ze.rxq[0].debt && ze.rxq[0].remaining==0);
    store(tmq+TMQ_PENDING,2); frame(0,1,1,32);   /* a second arrival */
    hardware_complete(); auto_complete=true;      /* count 2 -> 1, GO clear */
    assert(zx_eth_poll(&ze.napi,8)==0 && !ze.rxq[0].debt && ze.rxq[0].remaining==0);
    assert(zx_eth_poll(&ze.napi,8)==1 && delivered[1]==32 && ze.rxq[0].cursor==2);

    /* A return port that never retires: after ZX_RX_BLOCKED_POLLS empty
     * polls the completion stops rearming (no softirq spin) and backs off
     * on the retry work, 1, 2, 4, 8 jiffies, then HZ/10. */
    reset(); auto_complete=false; store(tmq+TMQ_PENDING,1); frame(0,0,0,41);
    assert(zx_eth_poll(&ze.napi,8)==1 && ze.rxq[0].debt);
    for(unsigned i=1;i<ZX_RX_BLOCKED_POLLS;i++) {
        unsigned r=rearms;
        assert(zx_eth_poll(&ze.napi,8)==0 && rearms==r+1 && last_delay==1);
    }
    {
        static const unsigned long want[]={1,2,4,8,10,10};
        for(unsigned i=0;i<6;i++) {
            unsigned r=rearms;
            assert(zx_eth_poll(&ze.napi,8)==0 && rearms==r && last_delay==want[i]);
        }
    }
    assert(ze.rxq[0].debt && submits==1 && frees==1);
    hardware_complete(); auto_complete=true;
    {
        unsigned r=rearms;
        assert(zx_eth_poll(&ze.napi,8)==0 && !ze.rxq[0].debt);
        assert(rearms==r+1 && ze.rx_blocked_polls==0);
    }
    return 0;
}
"""


class ReceiveTests(unittest.TestCase):
    def test_poll_and_release_state_machine(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        source = DRIVER.read_text()
        def section(start, end):
            offset = source.index(start)
            return source[offset:source.index(end, offset)]
        queue = section("struct zx_rx_queue {", "struct zx_eth {")
        free = section("static bool zx_bm_free(", "/* Descriptor field packing")
        release = section("static bool zx_rx_retire(", "/* irq_lock serializes")
        pending = section("static bool zx_rx_software_pending(", "/* Called only by NAPI.")
        poll = section("static void zx_rx_census(", "static void zx_eth_adjust_link(")
        with tempfile.TemporaryDirectory() as directory:
            cfile, binary = Path(directory) / "rx.c", Path(directory) / "rx"
            cfile.write_text(STUBS + queue + MODEL + pending + free + release + poll + CASES)
            result = subprocess.run([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                                     str(cfile), "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_no_scanner_or_unowned_reprime(self):
        source = DRIVER.read_text()
        for name in ("zx_rx_heal", "zx_reprime_write", "zx_fill_depth", "zx_bm_gate",
                     "zx_bm_thresh_post", "rx_window", "rx_timer", "rx_consumed",
                     "TMQ_RXPROD", "RX_FIRST_SLOT", "memset_io(ze->ring"):
            self.assertNotIn(name, source)
