"""Execute patched DMA index/cleanup code without device or DMA access."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from mt76_fixture import sources, c_function as function

MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#define MT76_DMA_ERROR 0
#define MT_QFLAG_WED_RRO_EN 1
#define MT_DMA_RRO_EN 8192
#define MT_DRV_TXWI_NO_FREE 1
#define MT_DMA_CTL_DMA_DONE (1U<<31)
#define cpu_to_le16(x) (x)
#define cpu_to_le32(x) (x)
#define wmb() ((void)0)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define mt76_for_each_q_rx(d,i) for(i=0;i<2;i++)
typedef uint32_t u32;
struct device { int unused; };
struct mt76_queue_regs { u32 desc_base,ring_size,cpu_idx,dma_idx; };
struct mt76_desc { u32 ctrl; };
struct mt76_queue_entry { void *txwi; };
struct mt76_queue {
 struct mt76_queue_regs *regs;struct mt76_desc *desc;struct mt76_queue_entry *entry;
 uint16_t head,tail,flags,*emi_cpu_idx;int ndesc,queued;
 unsigned cleanup_lock,lock;u32 desc_dma;
 void *page_pool;
};
struct mt76_dev;
struct driver { unsigned drv_flags; void (*dma_error)(struct mt76_dev *); };
enum mt76_rxq_id { RX0, RX1 };
struct mt76_phy {unsigned long state;struct mt76_queue *q_tx[2];};
struct napi {void *dev;};
struct mt76_dev {
 struct mt76_phy phy,*phys[2];struct device *dev;struct driver *drv;
 int tx_wait;bool dma_cleanup_only;struct mt76_queue q_rx[2],*q_mcu[2];
 struct {int wed,wed_hif2;} mmio;
 void *dma_resources,*napi_dev,*tx_napi_dev;int tx_worker;
 struct napi tx_napi,napi[2];
 bool dma_quiesced,dma_quarantined,dma_napi_stopped,dma_napi_disabled;
};
static struct driver driver;
static struct mt76_dev device={.drv=&driver};
static struct mt76_queue_regs registers;
static struct mt76_desc descriptors[512];
static unsigned reads,writes,kicks,unmaps,completes,wakes,logs;
static unsigned rx_cleanups,rx_fills;static bool wed_setup_failed;
static unsigned pool_frees,netdev_frees,pending_frees;
static u32 indices[8];static unsigned nindices;
static bool test_bit(unsigned bit,unsigned long *p) { return !!(*p&(1UL<<bit)); }
static bool test_and_set_bit(unsigned bit,unsigned long *p) {
 bool old=test_bit(bit,p);*p|=1UL<<bit;return old;
}
static void dev_err(struct device *d,const char *fmt,...) { (void)d;(void)fmt;logs++; }
static bool mt76_npu_device_active(struct mt76_dev *d) { (void)d;return false; }
static bool mt76_queue_is_npu_tx(struct mt76_queue *q) { (void)q;return false; }
static bool mt76_queue_is_emi(struct mt76_queue *q) { (void)q;return false; }
static bool mt76_queue_is_wed_rro_ind(struct mt76_queue *q) { (void)q;return false; }
static bool mt76_queue_is_wed_rro_rxdmad_c(struct mt76_queue *q) { (void)q;return false; }
static bool mt76_queue_is_npu(struct mt76_queue *q) { (void)q;return false; }
static void mt76_dma_queue_magic_cnt_init(struct mt76_dev *d,struct mt76_queue *q) { (void)d;(void)q; }
static u32 queue_read(struct mt76_queue *q) {
 assert(q->regs==&registers && reads<nindices);return indices[reads++];
}
static void writel(u32 value,u32 *p) { writes++;*p=value;if(p==&registers.cpu_idx)kicks++; }
#define Q_READ(q,field) queue_read(q)
#define Q_WRITE(q,field,value) writel(value,&(q)->regs->field)
static void spin_lock_bh(unsigned *p) { assert(!*p);*p=1; }
static void spin_unlock_bh(unsigned *p) { assert(*p);*p=0; }
static void mt76_dma_tx_cleanup_idx(struct mt76_dev *d,struct mt76_queue *q,int idx,struct mt76_queue_entry *e) {
 (void)d;assert(q->cleanup_lock && idx>=0 && idx<q->ndesc);unmaps++;e->txwi=0;
}
static void mt76_npu_txdesc_cleanup(struct mt76_queue *q,int idx) { assert(idx==q->tail); }
static void mt76_queue_tx_complete(struct mt76_dev *d,struct mt76_queue *q,struct mt76_queue_entry *e) {
 (void)d;(void)e;completes++;q->tail=(q->tail+1)%q->ndesc;q->queued--;
}
static void mt76_put_txwi(struct mt76_dev *d,void *p) { (void)d;(void)p;assert(!"unexpected TXWI"); }
static void wake_up(int *p) { (void)p;wakes++; }
static bool mt76_queue_is_wed_tx_free(struct mt76_queue *q) {(void)q;return false;}
static bool mt76_queue_is_wed_rro(struct mt76_queue *q) {(void)q;return false;}
static bool mtk_wed_device_active(int *wed) {(void)wed;return false;}
static int mt76_wed_dma_setup(struct mt76_dev *d,struct mt76_queue *q,bool reset) {
 (void)d;(void)q;assert(reset);return wed_setup_failed?-1:0;
}
static void mt76_dma_rx_cleanup(struct mt76_dev *d,struct mt76_queue *q) {
 (void)d;rx_cleanups++;q->queued=0;
}
static void mt76_npu_fill_rx_queue(struct mt76_dev *d,struct mt76_queue *q) {
 (void)d;(void)q;assert(!"unexpected NPU");
}
static void mt76_dma_rx_fill(struct mt76_dev *d,struct mt76_queue *q,bool direct) {
 (void)d;assert(!direct && q->head<q->ndesc && q->tail<q->ndesc);rx_fills++;
}
static void mt76_worker_disable(int *w) {(void)w;}
static void napi_disable(struct napi *n) {(void)n;}
static void netif_napi_del(struct napi *n) {(void)n;}
static void page_pool_destroy(void *p) {(void)p;pool_frees++;}
static void mtk_wed_device_detach(int *wed) {(void)wed;assert(!"unexpected WED");}
static void mt76_free_pending_txwi(struct mt76_dev *d) {(void)d;pending_frees++;}
static void mt76_free_pending_rxwi(struct mt76_dev *d) {(void)d;pending_frees++;}
static void free_netdev(void *p) {assert(p);netdev_frees++;}
'''

CASES = r'''
static struct mt76_queue queue;
static void reset(void) {
 memset(&queue,0,sizeof(queue));memset(&registers,0,sizeof(registers));
 memset(&device,0,sizeof(device));device.drv=&driver;
 device.phy.state=0;device.dma_cleanup_only=false;reads=writes=kicks=unmaps=completes=wakes=logs=0;nindices=1;
 indices[0]=0;queue.regs=&registers;queue.desc=descriptors;queue.ndesc=512;
 queue.desc_dma=0x45000000;queue.head=5;queue.tail=1;queue.queued=4;
 rx_cleanups=rx_fills=0;wed_setup_failed=false;
 device.q_rx[0]=queue;device.q_rx[1]=queue;
 pool_frees=netdev_frees=pending_frees=0;
}
int main(void) {
 unsigned valid[]={0,511};
 for(unsigned i=0;i<2;i++) {
  reset();indices[0]=valid[i];assert(mt76_dma_sync_idx(&device,&queue));
  assert(queue.head==valid[i] && queue.tail==valid[i] && !logs);
 }
 u32 bad[]={512,65535,65536,0xffff0001,UINT32_MAX};
 for(unsigned i=0;i<5;i++) {
  reset();indices[0]=bad[i];assert(!mt76_dma_sync_idx(&device,&queue));
  assert(queue.head==5 && queue.tail==1 && mt76_dma_failed(&device) && logs==1);
  unsigned before=reads+writes;
  assert(!mt76_dma_sync_idx(&device,&queue));mt76_dma_kick_queue(&device,&queue);
  assert(reads+writes==before && !kicks);
  mt76_dma_tx_cleanup(&device,&queue,true);assert(!unmaps && !completes);
 }
 reset();indices[0]=UINT32_MAX;mt76_dma_tx_cleanup(&device,&queue,false);
 assert(!unmaps && !completes && queue.tail==1 && queue.queued==4);
 reset();indices[0]=3;indices[1]=UINT32_MAX;nindices=2;
 mt76_dma_tx_cleanup(&device,&queue,false);
 assert(unmaps==2 && completes==2 && queue.tail==3 && queue.queued==2 && logs==1);
 reset();indices[0]=5;indices[1]=5;nindices=2;
 mt76_dma_tx_cleanup(&device,&queue,false);
 assert(unmaps==4 && completes==4 && !queue.queued && !logs);
 reset();indices[0]=UINT32_MAX;mt76_dma_tx_cleanup(&device,&queue,true);
 assert(unmaps==4 && completes==4 && !queue.queued && logs==1 && !kicks);
 reset();queue.tail=65535;mt76_dma_tx_cleanup(&device,&queue,false);
 assert(!reads && !unmaps && !completes && logs==1);
 reset();queue.head=65535;mt76_dma_queue_reset(&device,&queue,true);
 assert(!reads && !writes && logs==1);
 reset();device.phy.state=1;device.dma_cleanup_only=true;
 mt76_dma_tx_cleanup(&device,&queue,true);
 assert(unmaps==4 && !queue.queued && !reads && !writes);
 reset();queue.entry=(void *)1;
 assert(mt76_dma_queue_cleanup_valid(&queue));
 queue.queued=-1;assert(!mt76_dma_queue_cleanup_valid(&queue));
 queue.queued=513;assert(!mt76_dma_queue_cleanup_valid(&queue));
 queue.queued=4;queue.tail=65535;assert(!mt76_dma_queue_cleanup_valid(&queue));
 queue.tail=1;queue.head=65535;assert(!mt76_dma_queue_cleanup_valid(&queue));
 queue.entry=NULL;assert(!mt76_dma_queue_cleanup_valid(&queue));
 queue.queued=0;assert(mt76_dma_queue_cleanup_valid(&queue));
 reset();indices[0]=511;mt76_dma_rx_reset(&device,RX0);
 assert(rx_cleanups==1 && rx_fills==1 && device.q_rx[0].head==511);
 for(unsigned i=0;i<5;i++) {
  reset();indices[0]=bad[i];mt76_dma_rx_reset(&device,RX0);
  assert(rx_cleanups==1 && !rx_fills && logs==1 && device.q_rx[0].head==5);
  mt76_dma_rx_reset(&device,RX0);assert(rx_cleanups==1 && !rx_fills);
 }
 reset();device.q_rx[0].tail=65535;mt76_dma_rx_reset(&device,RX0);
 assert(!rx_cleanups && !rx_fills && !reads && !writes);
 reset();wed_setup_failed=true;mt76_dma_rx_reset(&device,RX0);
 assert(rx_cleanups==1 && !rx_fills && !reads && mt76_dma_failed(&device));
 for(unsigned owner=0;owner<2;owner++) {
  reset();device.phy.state=1;device.phy.q_tx[0]=&queue;device.phys[0]=&device.phy;
  queue.entry=(void *)1;device.q_rx[0].entry=device.q_rx[1].entry=(void *)1;
  device.dma_resources=owner?(void *)1:NULL;device.dma_quiesced=true;
  device.napi_dev=(void *)1;device.tx_napi_dev=(void *)2;
  mt76_dma_cleanup(&device);
  assert(!queue.queued && !device.q_rx[0].queued && !device.q_rx[1].queued);
  assert(!reads && !writes && !rx_fills && !device.dma_quarantined);
  assert(unmaps==4 && rx_cleanups==2 && pending_frees==2 && netdev_frees==2);
  assert(pool_frees==(owner?0:2));
 }
 for(unsigned bad=0;bad<2;bad++) {
  reset();device.phy.state=1;device.phy.q_tx[0]=&queue;device.phys[0]=&device.phy;
  queue.entry=(void *)1;device.dma_resources=(void *)1;device.dma_quiesced=bad;
  if(bad)queue.tail=65535;
  mt76_dma_cleanup(&device);
  assert(device.dma_quarantined && queue.queued==4 && !unmaps && !rx_cleanups);
  assert(!pending_frees && !pool_frees && !netdev_frees && !reads && !writes);
 }
 return 0;
}
'''


class Mt76DmaGuardTests(unittest.TestCase):
    def test_full_width_indices_and_exact_completion_ownership(self):
        source = sources()
        helpers = '\n'.join(function(source['mt76.h'], name) for name in
                            ('mt76_dma_failed','mt76_dma_set_failed'))
        code = '\n'.join(function(source['dma.c'], name) for name in
                         ('mt76_dma_index_valid','mt76_dma_cursors_valid','mt76_dma_sync_idx',
                          'mt76_dma_queue_reset','mt76_dma_kick_queue','mt76_dma_tx_cleanup'))
        code += '\n' + function(source['dma.c'], 'mt76_dma_queue_cleanup_valid')
        code += '\n' + function(source['dma.c'], 'mt76_dma_rx_reset')
        code += '\n' + '\n'.join(function(source['dma.c'], name) for name in
                                  ('mt76_dma_stop_napi', 'mt76_dma_quarantine',
                                   'mt76_dma_cleanup_valid', 'mt76_dma_cleanup'))
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp)/'dma.c', Path(tmp)/'dma'
            src.write_text(MODEL+'\n'+helpers+'\n'+code+'\n'+CASES)
            run = subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-sign-compare',str(src),'-o',str(exe)],
                                 capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            run = subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
