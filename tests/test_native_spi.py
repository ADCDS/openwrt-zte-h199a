"""Execute native SPI transport C against wire/FIFO and failure contracts."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import function

SOURCE = Path(__file__).resolve().parents[1] / 'files/target/linux/armsr/files-6.6/drivers/spi/spi-zx279128.c'

MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint32_t __le32;
#define BIT(n) (1U<<(n))
#define BIT_ULL(n) (1ULL<<(n))
#define GENMASK(h,l) ((~0U<<(l))&(~0U>>(31-(h))))
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define NSEC_PER_MSEC 1000000ULL
#define cpu_relax() ((void)0)
#define cpu_to_le32(x) (x)
#define le32_to_cpu(x) (x)
#define U32_MAX UINT32_MAX
#define SPI_RX_DUAL BIT(10)
enum spi_mem_data_dir { SPI_MEM_NO_DATA, SPI_MEM_DATA_IN, SPI_MEM_DATA_OUT };
struct spi_mem_op {
 struct { unsigned nbytes,buswidth,dtr,opcode; } cmd;
 struct { unsigned nbytes,buswidth,dtr; u64 val; } addr;
 struct { unsigned nbytes,buswidth,dtr; } dummy;
 struct { unsigned buswidth,dtr,ecc,swap16,nbytes; enum spi_mem_data_dir dir;
          union { void *in; const void *out; } buf; } data;
 unsigned max_freq;
};
struct device { int dummy; };
struct zx_spifc { void *base; struct device *dev; unsigned long rate; bool failed,write_test,ubi_test; u64 attempted_pages; };
struct zx_wire_op { u32 cfg,cfg2,address; };
struct spi_controller { struct zx_spifc *data; };
struct spi_device { struct spi_controller *controller; unsigned cs,mode; };
struct spi_mem { struct spi_device *spi; };
static void *spi_controller_get_devdata(struct spi_controller *c) { return c->data; }
static unsigned spi_get_chipselect(struct spi_device *s,unsigned index) { assert(!index);return s->cs; }
static bool spi_mem_default_supports_op(struct spi_mem *m,const struct spi_mem_op *o) {
 return o->data.buswidth!=2 || (m->spi->mode&SPI_RX_DUAL);
}
static unsigned char mmio[128], payload[2200];
static unsigned reads,writes,triggers,prepared,configured,position,tx_bytes,logs;
static unsigned expected_cfg,expected_cfg2;
static unsigned prefill_words;
static bool short_done,stall_fifo,format_error;
static u64 now,step;
static struct spi_mem_op current;
static struct zx_spifc sp;
static struct spi_controller ctlr={.data=&sp};
static struct spi_device spi={.controller=&ctlr};
static struct spi_mem mem={.spi=&spi};
static u64 ktime_get_ns(void) { now+=step;return now; }
static u32 load(unsigned reg) { u32 v;memcpy(&v,mmio+reg,4);return v; }
static bool short_input(void) { return current.cmd.opcode==0x9f || current.cmd.opcode==0xf; }
static u32 readl(void *addr) {
 unsigned reg=(unsigned char *)addr-mmio;reads++;
 if(reg==ZX_STATUS) {
  if(!triggers)return 1; /* Old completion must not be mistaken for this op. */
  if(current.data.dir==SPI_MEM_DATA_IN && !short_input() && position<current.data.nbytes)return 0;
  if(current.data.dir==SPI_MEM_DATA_OUT && tx_bytes<current.data.nbytes)return 0;
  short_done=true;return ZX_DONE|(format_error?ZX_FORMAT_ERROR:0);
 }
 if(reg==ZX_FIFO_STATUS) {
  if(stall_fifo)return 0;
  if(!triggers && tx_bytes>=prefill_words*4)return ZX_RX_AVAILABLE;
  return ZX_RX_AVAILABLE|ZX_TX_AVAILABLE;
 }
 if(reg==ZX_FIFO) {
  assert(triggers==1 && (!short_input() || short_done));
  u32 value=0;
  for(unsigned i=0;i<4;i++)value|=(((position+i)*17+3)&255U)<<(8*i);
  position+=min_t(unsigned,4,current.data.nbytes-position);return value;
 }
 return load(reg);
}
static void writel(u32 value,void *addr) {
 unsigned reg=(unsigned char *)addr-mmio;writes++;
 if(reg==ZX_CFG2) { assert(value==expected_cfg2);configured|=1; }
 if(reg==ZX_COUNT) { assert(value==(current.data.nbytes?current.data.nbytes-1:0));configured|=2; }
 if(reg==ZX_ADDRESS)configured|=4;
 if(reg==ZX_OPCODE) { assert(value==current.cmd.opcode);configured|=8; }
 if(reg==ZX_CFG) { assert(value==expected_cfg);configured|=16; }
 if(reg==ZX_INIT) { assert(configured==31 && value==0x0201c460);prepared=1; }
 if(reg==ZX_INT_CLEAR) { assert(prepared==1 && value==0x3f);prepared=2; }
 if(reg==ZX_TRIG) { assert(prepared==2 && !triggers && value==1);triggers++; }
 if(reg==ZX_FIFO) {
  if(current.cmd.opcode==0x1f) { assert(triggers==1 && value==0x18);tx_bytes++; }
  else {
   assert(prepared==2 && (current.cmd.opcode==2 || current.cmd.opcode==0x84));
   if(!triggers)assert(tx_bytes<64 && tx_bytes<prefill_words*4);
   unsigned n=min_t(unsigned,4,current.data.nbytes-tx_bytes);
   for(unsigned i=0;i<4;i++)assert(((value>>(8*i))&255)==(i<n?payload[1+tx_bytes+i]:255));
   tx_bytes+=n;
  }
 }
 memcpy(mmio+reg,&value,4);
}
static void diagnostic(void *dev,const char *fmt,...) { (void)dev;(void)fmt;logs++; }
#define dev_err diagnostic
static struct spi_mem_op op(unsigned cmd,unsigned addr,u64 val,unsigned dummy,
                            enum spi_mem_data_dir dir,unsigned width,unsigned size) {
 struct spi_mem_op o={0};o.cmd.opcode=cmd;o.cmd.nbytes=o.cmd.buswidth=1;
 o.addr.nbytes=addr;o.addr.buswidth=addr?1:0;o.addr.val=val;
 o.dummy.nbytes=dummy;o.dummy.buswidth=dummy?1:0;
 o.data.dir=dir;o.data.buswidth=width;o.data.nbytes=size;o.data.buf.in=payload+1;return o;
}
static void reset(struct spi_mem_op o,unsigned cfg,unsigned cfg2) {
 memset(mmio,0,sizeof(mmio));memset(payload,0xa5,sizeof(payload));
 u32 init=0x02000020;memcpy(mmio+ZX_INIT,&init,4);
 memset(&sp,0,sizeof(sp));sp.base=mmio;sp.rate=50000000;
 spi.cs=0;spi.mode=SPI_RX_DUAL;current=o;expected_cfg=cfg;expected_cfg2=cfg2;
 reads=writes=triggers=prepared=configured=position=tx_bytes=logs=0;
 short_done=stall_fifo=format_error=false;now=0;step=1000;
 prefill_words=16;
}
'''

CASES = r'''
static void input(struct spi_mem_op o,unsigned cfg,unsigned cfg2) {
 reset(o,cfg,cfg2);assert(zx_supports_op(&mem,&o));assert(zx_exec_op(&mem,&o)==0);
 assert(triggers==1 && position==o.data.nbytes && !sp.failed && !logs);
 for(unsigned i=0;i<o.data.nbytes;i++)assert(payload[i+1]==((i*17+3)&255));
 assert(payload[0]==0xa5 && payload[o.data.nbytes+1]==0xa5);
}
int main(void) {
 input(op(0x9f,0,0,0,SPI_MEM_DATA_IN,1,4),0x02,0x40);
 input(op(0x9f,1,0,0,SPI_MEM_DATA_IN,1,4),0x12,0);
 input(op(0x9f,0,0,1,SPI_MEM_DATA_IN,1,4),0x12,0);
 input(op(0x0f,1,0xc0,0,SPI_MEM_DATA_IN,1,1),0x12,0);
 input(op(0x3b,2,0,1,SPI_MEM_DATA_IN,2,2176),0x16,0x1024);
 input(op(0x3b,2,0x800,1,SPI_MEM_DATA_IN,2,128),0x16,0x1024);
 input(op(0x3b,2,3,1,SPI_MEM_DATA_IN,2,2173),0x16,0x1024);
 assert(load(ZX_ADDRESS)==3);
 struct spi_mem_op o=op(0x1f,1,0xb0,0,SPI_MEM_DATA_OUT,1,1);
 reset(o,0x11,0);payload[1]=0x18;assert(zx_exec_op(&mem,&o)==0 && tx_bytes==1 && triggers==1);
 unsigned cmds[]={0x06,0x02,0x84,0x10,0xd8};
 for(unsigned i=0;i<5;i++) {
  unsigned cmd=cmds[i];bool cache=cmd==2 || cmd==0x84;
  o=op(cmd,cache?2:cmd==6?0:3,0,0,cache?SPI_MEM_DATA_OUT:SPI_MEM_NO_DATA,cache?1:0,0);
  reset(o,0,0);assert(zx_supports_op(&mem,&o));assert(zx_exec_op(&mem,&o)==-EROFS);
  assert(!reads && !writes && !triggers);
 }
 o=op(0x3b,2,0,1,SPI_MEM_DATA_IN,2,0);reset(o,0,0);
 assert(zx_supports_op(&mem,&o));assert(zx_exec_op(&mem,&o)==-EINVAL && !writes);
 o.data.nbytes=2177;assert(!zx_supports_op(&mem,&o));
 assert(zx_adjust_op_size(&mem,&o)==0 && o.data.nbytes==2176 && zx_supports_op(&mem,&o));
 spi.mode=0;assert(!zx_supports_op(&mem,&o));spi.mode=SPI_RX_DUAL;
 o.max_freq=25000000;assert(!zx_supports_op(&mem,&o));o.max_freq=0;
 o.addr.val=0x10000;assert(!zx_supports_op(&mem,&o));o.addr.val=0;
 o.cmd.dtr=1;assert(!zx_supports_op(&mem,&o));o.cmd.dtr=0;
 o=op(0x3b,2,0,1,SPI_MEM_DATA_IN,2,128);reset(o,0x16,0x1024);
 stall_fifo=true;step=1000000;assert(zx_exec_op(&mem,&o)==-ETIMEDOUT && sp.failed && logs==1);
 unsigned old=reads+writes;assert(zx_exec_op(&mem,&o)==-EIO && reads+writes==old);
 reset(o,0x16,0x1024);step=ZX_TIMEOUT_NS;
 assert(zx_exec_op(&mem,&o)==-ETIMEDOUT && !position && sp.failed);
 o=op(0xf,1,0xc0,0,SPI_MEM_DATA_IN,1,1);reset(o,0x12,0);format_error=true;
 assert(zx_exec_op(&mem,&o)==-EIO && !position && logs==1 && sp.failed);

 unsigned sizes[]={1,3,4,63,64,65,2176};
 for(unsigned cmd=2;cmd<=0x84;cmd+=0x82)
  for(unsigned n=0;n<sizeof(sizes)/sizeof(sizes[0]);n++)
   for(unsigned capacity=0;capacity<=16;capacity+=8) {
    o=op(cmd,2,0,0,SPI_MEM_DATA_OUT,1,sizes[n]);reset(o,0x11,0x20);
    sp.write_test=true;prefill_words=capacity;
    for(unsigned i=0;i<o.data.nbytes;i++)payload[i+1]=(i*31+7)&255;
    assert(zx_exec_op(&mem,&o)==0 && triggers==1 && tx_bytes==o.data.nbytes);
    assert(!sp.attempted_pages && !sp.failed);
   }
 o=op(0x84,2,2175,0,SPI_MEM_DATA_OUT,1,2);reset(o,0x11,0x20);sp.write_test=true;
 assert(!zx_supports_op(&mem,&o) && zx_exec_op(&mem,&o)==-EINVAL && !writes);
 assert(zx_adjust_op_size(&mem,&o)==0 && o.data.nbytes==1);
 for(unsigned cmd=0x10;cmd<=0xd8;cmd+=0xc8) {
  u64 invalid[]={ZX_TEST_FIRST_ROW-1,ZX_TEST_FIRST_ROW+ZX_TEST_PAGES,0x1c7c0,0x100c7c0};
  for(unsigned n=0;n<4;n++) {
   o=op(cmd,3,invalid[n],0,SPI_MEM_NO_DATA,0,0);reset(o,0x10,0x40);sp.write_test=true;
   assert(zx_exec_op(&mem,&o)<0 && !writes && !reads && !sp.attempted_pages);
  }
 }
 o=op(0x10,3,ZX_TEST_FIRST_ROW,0,SPI_MEM_NO_DATA,0,0);reset(o,0x10,0x40);sp.write_test=true;
 assert(zx_exec_op(&mem,&o)==0 && sp.attempted_pages==1);
 old=reads+writes;assert(zx_exec_op(&mem,&o)==-EALREADY && reads+writes==old);
 o=op(0xd8,3,ZX_TEST_FIRST_ROW,0,SPI_MEM_NO_DATA,0,0);reset(o,0x10,0x40);sp.write_test=true;sp.attempted_pages=1;
 assert(zx_exec_op(&mem,&o)==0 && sp.attempted_pages==1);
 o.addr.val++;assert(zx_allow_array_op(&sp,&o)==-EROFS);
 o=op(0x10,3,ZX_TEST_FIRST_ROW+63,0,SPI_MEM_NO_DATA,0,0);reset(o,0x10,0x40);sp.write_test=true;format_error=true;
 assert(zx_exec_op(&mem,&o)==-EIO && sp.attempted_pages==BIT_ULL(63));
 assert(zx_allow_array_op(&sp,&o)==-EALREADY);
 /* UBI may reuse a page after erasure, but its address and erase alignment
  * must remain within the separate 16MiB qualification window. */
 for(unsigned cmd=0x10;cmd<=0xd8;cmd+=0xc8) {
  u64 invalid[]={ZX_UBI_FIRST_ROW-1,ZX_UBI_END_ROW,0x1a800,0x100a800};
  for(unsigned i=0;i<4;i++) {
   o=op(cmd,3,invalid[i],0,SPI_MEM_NO_DATA,0,0);reset(o,0x10,0x40);sp.ubi_test=true;
   assert(zx_exec_op(&mem,&o)<0 && !writes && !reads);
  }
 }
 o=op(0x10,3,ZX_UBI_FIRST_ROW,0,SPI_MEM_NO_DATA,0,0);reset(o,0x10,0x40);sp.ubi_test=true;
 assert(zx_allow_array_op(&sp,&o)==0 && zx_allow_array_op(&sp,&o)==0 && !sp.attempted_pages);
 o.addr.val=ZX_UBI_END_ROW-1;assert(zx_allow_array_op(&sp,&o)==0);
 o.cmd.opcode=0xd8;assert(zx_allow_array_op(&sp,&o)==-EROFS);
 o.addr.val=ZX_UBI_END_ROW-64;reset(o,0x10,0x40);sp.ubi_test=true;
 assert(zx_exec_op(&mem,&o)==0);
 sp.write_test=true;assert(zx_allow_array_op(&sp,&o)==-EINVAL);
 return 0;
}
'''


class NativeSpiTests(unittest.TestCase):
    def test_wire_fifo_deadline_and_write_denial(self):
        text = SOURCE.read_text()
        constants = '\n'.join(line for line in text.splitlines() if line.startswith('#define ZX_'))
        names = ('zx_decode_op', 'zx_supports_op', 'zx_adjust_op_size', 'zx_wait',
                 'zx_wait_done', 'zx_array_write', 'zx_allow_array_op', 'zx_tx_word', 'zx_exec_op')
        code = constants + '\n' + MODEL + '\n'.join(function(text, n) for n in names) + CASES
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp)/'spi.c', Path(tmp)/'spi'
            src.write_text(code)
            r = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                '-Wno-unused-parameter', str(src), '-o', str(exe)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
