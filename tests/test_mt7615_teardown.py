"""Inject recovery requeue at IRQ teardown and enforce DMA ownership ordering."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from mt76_fixture import sources, c_function

MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#define WRITE_ONCE(x,v) ((x)=(v))
#define MT76_DMA_ERROR 0
#define MT76_STATE_MCU_RUNNING 1
#define MT76_STATE_REGISTERED 2
#define MT_INT_MASK_CSR 8
struct work_struct {bool queued;unsigned cancels;};
struct delayed_work {struct work_struct work;};
struct mt76_dev {
 struct {unsigned long state;} phy;
 bool dma_quarantined,dma_quiesced;int irq_tasklet;
 struct delayed_work scan_work;struct {int res_q;} mcu;
 void *dev;
};
struct mt7615_phy {bool registered,freed;};
struct bus_ops {void (*wr)(struct mt76_dev *,unsigned,unsigned);};
struct mt7615_dev {
 struct mt76_dev mt76;bool removing,irq_requested;int irq;
 struct work_struct reset_work,dma_error_work,mcu_work;
 struct mt7615_phy phy,ext;
 struct {struct delayed_work ps_work;struct work_struct wake_work;} pm;
 struct {struct delayed_work work;int msg_list;} coredump;
 struct bus_ops *bus_ops;
};
#define mphy mt76.phy
static struct mt7615_dev device;
static bool inject_requeue,stop_fails,tasklet_dead,napi_stopped,unregistered,freed;
static unsigned mcu_exits,token_frees,dma_frees;
static bool tx_stopped;
static void mt7615_stop_data_tx(struct mt7615_dev *d) {
 assert(d->removing && !d->reset_work.queued);tx_stopped=true;
}
static void raw_write(struct mt76_dev *d,unsigned reg,unsigned value) {
 assert(d==&device.mt76 && reg==MT_INT_MASK_CSR && !value);
}
static struct bus_ops bus={raw_write};
static bool test_bit(unsigned b,unsigned long *p) {return !!(*p&(1UL<<b));}
static void set_bit(unsigned b,unsigned long *p) {*p|=1UL<<b;}
static bool mt76_dma_failed(struct mt76_dev *d) {return test_bit(MT76_DMA_ERROR,&d->phy.state);}
static void cancel_work_sync(struct work_struct *w) {w->queued=false;w->cancels++;}
static void cancel_delayed_work_sync(struct delayed_work *w) {cancel_work_sync(&w->work);}
static struct mt7615_phy *mt7615_ext_phy(struct mt7615_dev *d) {return &d->ext;}
static void mt7615_cancel_phy_work(struct mt7615_phy *p) {(void)p;}
static void mt7615_mcu_exit(struct mt7615_dev *d) {
 assert(tx_stopped && !mt76_dma_failed(&d->mt76) && !d->mcu_work.queued);mcu_exits++;
}
static void mt7615_dma_error(struct mt76_dev *d) {
 assert(mt76_dma_failed(d) && device.removing);
}
static void devm_free_irq(void *p,int irq,struct mt7615_dev *d) {
 (void)p;(void)irq;assert(d->irq_requested);
 /* A tasklet already past its admission check can still publish here. */
 if(inject_requeue) {
  d->reset_work.queued=true;d->dma_error_work.queued=true;
  d->pm.wake_work.queued=true;
 }
}
static void tasklet_kill(int *p) {(void)p;tasklet_dead=true;}
static void mt76_dma_stop_napi(struct mt76_dev *d) {
 (void)d;assert(tasklet_dead && !device.irq_requested);
 assert(!device.reset_work.queued && !device.dma_error_work.queued && !device.pm.wake_work.queued);
 napi_stopped=true;
 /* A NAPI error notification already in flight finishes before return. */
 device.dma_error_work.queued=true;
}
static int mt7615_dma_stop_checked(struct mt7615_dev *d) {
 assert(napi_stopped && !d->dma_error_work.queued);
 d->mt76.dma_quiesced=!stop_fails;return stop_fails?-EIO:0;
}
static void mt76_dma_quarantine(struct mt76_dev *d) {assert(napi_stopped);d->dma_quarantined=true;}
static void mt7615_unregister_ext_phy(struct mt7615_dev *d) {
 assert(mt76_dma_failed(&d->mt76));d->ext.registered=false;
 d->ext.freed=!d->mt76.dma_quarantined;
}
static void mt76_unregister_device(struct mt76_dev *d) {
 assert(napi_stopped && tasklet_dead && mt76_dma_failed(d));
 assert(d->dma_quiesced || d->dma_quarantined);
 device.phy.registered=false;unregistered=true;
 device.pm.ps_work.work.queued=true;device.pm.wake_work.queued=true;
 device.coredump.work.work.queued=true;d->scan_work.work.queued=true;
}
static void skb_queue_purge(int *q) {(void)q;}
#define mt76_connac_free_pending_tx_skbs(p,w) ((void)(p),(void)(w))
static void mt7615_tx_token_put(struct mt7615_dev *d) {
 assert(unregistered && d->mt76.dma_quiesced && !d->mt76.dma_quarantined);token_frees++;
}
static void mt7615_dma_cleanup(struct mt7615_dev *d) {
 assert(d->mt76.dma_quiesced && !d->mt76.dma_quarantined && token_frees);dma_frees++;
}
static void mt76_free_device(struct mt76_dev *d) {
 assert(unregistered && !device.pm.ps_work.work.queued && !device.pm.wake_work.queued);
 assert(!device.coredump.work.work.queued && !d->scan_work.work.queued);
 assert(!device.reset_work.queued && !device.dma_error_work.queued);
 freed=!d->dma_quarantined;
 assert(freed ? dma_frees==1 : !dma_frees);
}
'''

CASES = r'''
static void reset(bool fault,bool requested) {
 memset(&device,0,sizeof(device));tasklet_dead=napi_stopped=unregistered=freed=false;
 device.bus_ops=&bus;
 mcu_exits=token_frees=dma_frees=0;tx_stopped=false;device.irq_requested=requested;
 device.phy.registered=device.ext.registered=true;
 device.mt76.phy.state=(1UL<<MT76_STATE_MCU_RUNNING)|(fault?1:0);
 device.reset_work.queued=device.dma_error_work.queued=device.mcu_work.queued=true;
}
int main(void) {
 for(unsigned failed=0;failed<2;failed++) {
  for(unsigned request=0;request<2;request++) {
   reset(failed,request);stop_fails=failed;inject_requeue=true;
   mt7615_unregister_device(&device);
   assert(unregistered && freed==!failed && mcu_exits==!failed);
   assert(device.ext.freed==!failed && token_frees==!failed && dma_frees==!failed);
   assert(device.reset_work.cancels==2 && device.dma_error_work.cancels==3);
  }
 }
 /* Early probe unwind: constructors ran, no MCU or registered wiphy. */
 reset(false,false);device.mt76.phy.state=0;stop_fails=false;
 mt7615_unregister_device(&device);assert(!mcu_exits && freed);
 return 0;
}
'''


class Mt7615TeardownTests(unittest.TestCase):
    def test_producers_are_drained_before_napi_and_ownership_is_retained_on_failure(self):
        code = c_function(sources()['mt7615/pci_init.c'], 'mt7615_unregister_device')
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp)/'teardown.c', Path(tmp)/'teardown'
            src.write_text('\n'.join((MODEL, code, CASES)))
            result = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                     str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
