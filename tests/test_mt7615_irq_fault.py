"""Reject inaccessible-device values before they become interrupts/reset states."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from mt76_fixture import sources, c_function

MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef uint32_t u32;
typedef int irqreturn_t;
#define BIT(n) (1U<<(n))
#define U32_MAX UINT32_MAX
#define MT76_DMA_ERROR 0
#define MT76_RESET 1
#define MT76_MCU_RESET 2
#define MT76_STATE_INITIALIZED 3
#define MT76_STATE_REGISTERED 4
#define READ_ONCE(x) (x)
#define smp_load_acquire(p) (*(p))
#define container_of(p,type,member) ((type *)((char *)(p)-offsetof(type,member)))
#define IRQ_NONE 0
#define IRQ_HANDLED 1
#define MT_INT_MASK_CSR 4
#define MT_INT_SOURCE_CSR 8
#define MT_MCU2HOST_INT_STATUS 12
#define MT_MCU_CMD 16
#define MT_INT_RX_DONE(q) BIT(q)
#define MT_INT_RX_DONE_ALL 3
#define MT_INT_MCU_CMD BIT(10)
#define MT7663_INT_MCU_CMD BIT(11)
#define MT7663_MCU_CMD_ERROR_MASK 15
#define MT_MCU_CMD_ERROR_MASK 15
enum mt76_rxq_id { RX0,RX1 };
struct device { int unused; };
struct tasklet_struct { int unused; };
struct napi_struct { int unused; };
struct work_struct { int unused; };
struct mt76_dev;
struct driver { void (*dma_error)(struct mt76_dev *); };
static struct driver driver;
struct mt76_dev {
 struct driver *drv;
 struct { unsigned long state; } phy;
 struct { u32 irqmask; } mmio;
 struct { int wait; } mcu;
 struct device *dev;void *wq;
 struct tasklet_struct irq_tasklet;
 struct napi_struct tx_napi,napi[2];
};
struct mt7615_dev {
 struct mt76_dev mt76;u32 reset_state;int reset_wait;
 struct work_struct reset_work,dma_error_work;bool dma_error_ready,removing;
};
#define mphy mt76.phy
static struct mt7615_dev device;
static bool chip7663;
static u32 raw_irq,raw_mcu;
static unsigned reads,writes,acks,mcu_acks,napi_calls,work_calls,tasklets,wakes,logs;
#define from_tasklet(p,t,field) (&device)
static bool test_bit(unsigned b,unsigned long *p) { return !!(*p&BIT(b)); }
static bool test_and_set_bit(unsigned b,unsigned long *p) { bool old=test_bit(b,p);*p|=BIT(b);return old; }
static void set_bit(unsigned b,unsigned long *p) { *p|=BIT(b); }
static void dev_err(struct device *d,const char *fmt,...) { (void)d;(void)fmt;logs++; }
static void wake_up(int *p) { (void)p;wakes++; }
static void mt76_set_irq_mask(struct mt76_dev *d,u32 reg,u32 clear,u32 set) {
 d->mmio.irqmask=(d->mmio.irqmask&~clear)|set;
 if(reg) { assert(reg==MT_INT_MASK_CSR);writes++; }
}
static u32 mt76_rr(struct mt7615_dev *d,u32 reg) {
 assert(d==&device);reads++;
 if(reg==MT_INT_SOURCE_CSR)return raw_irq;
 assert(reg==(chip7663?MT_MCU2HOST_INT_STATUS:MT_MCU_CMD));return raw_mcu;
}
static void mt76_wr(struct mt7615_dev *d,u32 reg,u32 value) {
 assert(d==&device);writes++;
 if(reg==MT_INT_MASK_CSR)assert(!value);
 else if(reg==MT_INT_SOURCE_CSR)acks++;
 else { assert(reg==MT_MCU2HOST_INT_STATUS);mcu_acks++; }
}
static bool is_mt7663(struct mt76_dev *d) { (void)d;return chip7663; }
static u32 mt7615_tx_mcu_int_mask(struct mt7615_dev *d) { (void)d;return BIT(2); }
static void trace_dev_irq(struct mt76_dev *d,u32 a,u32 b) { (void)d;(void)a;(void)b; }
static void napi_schedule(struct napi_struct *p) { (void)p;napi_calls++; }
static void queue_work(void *q,struct work_struct *w) { (void)q;(void)w;work_calls++; }
static void tasklet_schedule(struct tasklet_struct *p) { (void)p;tasklets++; }
'''

CASES = r'''
static void reset(void) {
 driver.dma_error=mt7615_dma_error;
 memset(&device,0,sizeof(device));device.mt76.drv=&driver;device.mt76.phy.state=BIT(MT76_STATE_INITIALIZED);
 device.mt76.mmio.irqmask=U32_MAX;device.reset_state=0x55;
 raw_irq=raw_mcu=reads=writes=acks=mcu_acks=napi_calls=work_calls=tasklets=wakes=logs=0;
}
int main(void) {
 for(unsigned chip=0;chip<2;chip++) {
  chip7663=chip;reset();raw_irq=U32_MAX;
  mt7615_irq_tasklet(&device.mt76.irq_tasklet);
  assert(mt76_dma_failed(&device.mt76) && !acks && !mcu_acks && !napi_calls && !work_calls);
  assert(device.reset_state==0x55 && !device.mt76.mmio.irqmask && logs==1);
  unsigned before=reads+writes;
  mt7615_rx_poll_complete(&device.mt76,RX0);
  mt7615_irq_tasklet(&device.mt76.irq_tasklet);
  assert(mt7615_irq_handler(95,&device)==IRQ_NONE);
  assert(reads+writes==before && !tasklets);
  reset();raw_irq=chip?MT7663_INT_MCU_CMD:MT_INT_MCU_CMD;raw_mcu=U32_MAX;
  mt7615_irq_tasklet(&device.mt76.irq_tasklet);
  assert(mt76_dma_failed(&device.mt76) && acks==1 && !mcu_acks && !work_calls && device.reset_state==0x55);
  reset();raw_irq=chip?MT7663_INT_MCU_CMD:MT_INT_MCU_CMD;raw_mcu=4;
  mt7615_irq_tasklet(&device.mt76.irq_tasklet);
  assert(!mt76_dma_failed(&device.mt76) && work_calls==1 && device.reset_state==4);
  reset();device.removing=true;
  raw_irq=chip?MT7663_INT_MCU_CMD:MT_INT_MCU_CMD;raw_mcu=4;
  mt7615_irq_tasklet(&device.mt76.irq_tasklet);
  assert(!work_calls && device.reset_state==0x55);
 }
 reset();raw_irq=MT_INT_RX_DONE(0)|BIT(2);
 mt7615_irq_tasklet(&device.mt76.irq_tasklet);
 assert(napi_calls==2 && !work_calls && !mt76_dma_failed(&device.mt76));
 mt7615_rx_poll_complete(&device.mt76,RX0);assert(tasklets==1);
 reset();device.dma_error_ready=true;device.mt76.phy.state|=BIT(MT76_STATE_REGISTERED);
 raw_irq=U32_MAX;mt7615_irq_tasklet(&device.mt76.irq_tasklet);
 assert(work_calls==1 && device.reset_state==0x55 && !device.mt76.mmio.irqmask);
 assert(!mt76_dma_set_failed(&device.mt76) && work_calls==1);
 reset();device.dma_error_ready=true;device.removing=true;
 device.mt76.phy.state|=BIT(MT76_STATE_REGISTERED);
 assert(mt76_dma_set_failed(&device.mt76) && !work_calls);
 return 0;
}
'''


class Mt7615IrqFaultTests(unittest.TestCase):
    def test_all_ones_cannot_generate_recovery_or_recurring_poll_work(self):
        source=sources()
        code='\n'.join([
            c_function(source['mt7615/pci_mac.c'],'mt7615_dma_error'),
            c_function(source['mt76.h'],'mt76_dma_failed'),
            c_function(source['mt76.h'],'mt76_dma_set_failed'),
            c_function(source['mt7615/mt7615.h'],'mt7615_dma_fail'),
            c_function(source['mt76_connac.h'],'mt76_connac_irq_enable'),
            *(c_function(source['mt7615/mmio.c'],name) for name in
              ('mt7615_rx_poll_complete','mt7615_irq_handler','mt7615_irq_tasklet')),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            src,exe=Path(tmp)/'irq.c',Path(tmp)/'irq'
            src.write_text(MODEL+'\n'+code+'\n'+CASES)
            run=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                                str(src),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
