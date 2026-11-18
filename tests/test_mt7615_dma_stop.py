"""Execute the driver's stop/reset code with injected register and queue faults."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from mt76_fixture import sources, c_function

MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
typedef uint32_t u32;
#define U32_MAX UINT32_MAX
#define MT_WPDMA_GLO_CFG 4
#define MT_INT_MASK_CSR 8
#define MT_WPDMA_GLO_CFG_RX_DMA_EN 1
#define MT_WPDMA_GLO_CFG_TX_DMA_EN 2
#define MT_WPDMA_GLO_CFG_TX_WRITEBACK_DONE 4
#define MT_WPDMA_GLO_CFG_RX_DMA_BUSY 8
#define MT_WPDMA_GLO_CFG_TX_DMA_BUSY 16
#define __MT_TXQ_MAX 4
#define __MT_MCUQ_MAX 2
struct mt76_queue { int id; };
struct mt76_dev {
 bool dma_quiesced,failed;
 struct { struct mt76_queue *q_tx[4]; } phy;
 struct mt76_queue *q_mcu[2];
};
struct bus_ops { u32 (*rr)(struct mt76_dev *,u32);void (*wr)(struct mt76_dev *,u32,u32); };
struct mt7615_dev { struct mt76_dev mt76;struct bus_ops *bus_ops; const u32 *reg_map; };
#define mphy mt76.phy
#define mt76_for_each_q_rx(d,i) for(i=0;i<2;i++)
static unsigned reads,writes,sleeps,failures,cleanups,resets,starts,status;
static unsigned fail_cleanup,fail_reset;
static u32 values[3],written;
static unsigned value_count;
static u32 rr(struct mt76_dev *d,u32 reg) {
 (void)d;assert(reg==MT_WPDMA_GLO_CFG);
 unsigned i=reads++;return values[i<value_count?i:value_count-1];
}
static void wr(struct mt76_dev *d,u32 reg,u32 value) {
 (void)d;writes++;
 if(reg==MT_INT_MASK_CSR)assert(value==0);
 else {assert(reg==MT_WPDMA_GLO_CFG);written=value;}
}
static void usleep_range(unsigned a,unsigned b) { assert(a==1000 && b==2000);sleeps++; }
static bool mt76_dma_failed(struct mt76_dev *d) {return d->failed;}
static void mt7615_dma_fail(struct mt7615_dev *d,const char *why,u32 value) {
 (void)why;(void)value;d->mt76.failed=true;failures++;
}
static void mt76_queue_tx_cleanup(struct mt7615_dev *d,struct mt76_queue *q,bool flush) {
 (void)q;assert(flush);cleanups++;if(cleanups==fail_cleanup)d->mt76.failed=true;
}
static void mt76_queue_rx_reset(struct mt7615_dev *d,int i) {
 assert((unsigned)i==resets);resets++;if(resets==fail_reset)d->mt76.failed=true;
}
static void mt76_tx_status_check(struct mt76_dev *d,bool flush) {(void)d;assert(flush);status++;}
static void mt7615_dma_start(struct mt7615_dev *d) {
 assert(!d->mt76.failed);starts++;d->mt76.dma_quiesced=false;
}
static struct bus_ops bus={rr,wr};
static struct mt7615_dev device;
'''

CASES = r'''
static void reset(void) {
 memset(&device,0,sizeof(device));device.bus_ops=&bus;device.reg_map=values;
 reads=writes=sleeps=failures=cleanups=resets=starts=status=0;
 fail_cleanup=fail_reset=0;values[0]=31;values[1]=0;value_count=2;written=UINT32_MAX;
}
int main(void) {
 reset();assert(!mt7615_dma_stop_checked(&device));
 assert(device.mt76.dma_quiesced && written==24 && sleeps==1 && writes==1);
 reset();device.mt76.failed=true;
 assert(!mt7615_dma_stop_checked(&device) && device.mt76.dma_quiesced);
 reset();values[0]=U32_MAX;
 assert(mt7615_dma_stop_checked(&device)==-EIO && !device.mt76.dma_quiesced);
 assert(!writes && !sleeps);
 reset();values[1]=U32_MAX;
 assert(mt7615_dma_stop_checked(&device)==-EIO && !device.mt76.dma_quiesced);
 reset();values[1]=8;
 assert(mt7615_dma_stop_checked(&device)==-EIO && sleeps==1000 && !device.mt76.dma_quiesced);
 reset();assert(!mt7615_dma_reset(&device));
 assert(cleanups==6 && resets==2 && starts==1 && status==1 && !device.mt76.dma_quiesced);
 reset();values[0]=U32_MAX;
 assert(mt7615_dma_reset(&device)==-EIO && !cleanups && !resets && !starts && !status);
 for(unsigned fail=1;fail<=6;fail++) {
  reset();fail_cleanup=fail;
  assert(mt7615_dma_reset(&device)==-EIO && cleanups==fail && !resets && !starts && !status);
 }
 for(unsigned fail=1;fail<=2;fail++) {
  reset();fail_reset=fail;
  assert(mt7615_dma_reset(&device)==-EIO && cleanups==6 && resets==fail && !starts && !status);
 }
 return 0;
}
'''


class Mt7615DmaStopTests(unittest.TestCase):
    def test_stop_proof_is_independent_of_fault_latch_and_reset_requires_it(self):
        source = sources()['mt7615/pci_mac.c']
        code = '\n'.join(c_function(source, name) for name in
                         ('mt7615_dma_stop_checked', 'mt7615_dma_reset'))
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp)/'stop.c', Path(tmp)/'stop'
            src.write_text(MODEL+'\n'+code+'\n'+CASES)
            result = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                     str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
