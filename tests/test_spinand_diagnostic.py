"""Fault-inject the actual patched SPI-NAND mutation callbacks and guard."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import function

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / 'files/target/linux/armsr/files-6.6/drivers/mtd/nand/spi/diagnostic.h'
PATCH = ROOT / 'files/target/linux/armsr/patches-6.6/998-spinand-diagnostic-mutation-guard.patch'

MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
typedef int64_t loff_t;
#define CONFIG_MTD_SPI_NAND_DIAGNOSTIC 1
#define module_param(...)
#define MODULE_PARM_DESC(...)
#define MTD_OPS_RAW 2
#define NAND_PAGE_WRITE 1
#define MTD_FAIL_ADDR_UNKNOWN UINT64_MAX
struct device { int ignored; };
struct spi_device { struct device dev; };
struct spi_mem { struct spi_device *spi; };
struct spinand_device {
 struct spi_mem *spimem;int lock;bool diagnostic_guard,diagnostic_failed;
 int diagnostic_errno;loff_t diagnostic_offset;
};
struct mtd_info { void *ooblayout; };
struct nand_device { int ignored; };
struct nand_pos { unsigned target;loff_t offset; };
struct request { struct nand_pos pos;unsigned mode,datalen,ooblen; };
struct nand_io_iter { unsigned page;struct request req; };
struct mtd_oob_ops { unsigned mode,retlen,oobretlen; };
struct erase_info { uint64_t addr,fail_addr; };
static struct spinand_device chip;
static struct spi_device spi;
static struct spi_mem mem={.spi=&spi};
static struct nand_device nand;
static unsigned selects,programs,erases,marks,logs,pages;
static int select_error,write_error,erase_error;
static unsigned fail_page;
static int last_error;
#define lockdep_assert_held(p) assert(*(p)==1)
static void mutex_lock(int *p) { assert(!*p);*p=1; }
static void mutex_unlock(int *p) {
 assert(*p);
 if(chip.diagnostic_guard && last_error)assert(chip.diagnostic_failed);
 *p=0;
}
static void info(struct device *dev,const char *fmt,...) { (void)dev;(void)fmt; }
static void error(struct device *dev,const char *fmt,...) { (void)dev;(void)fmt;logs++; }
#define dev_info info
#define dev_err error
static struct spinand_device *mtd_to_spinand(struct mtd_info *m) { (void)m;return &chip; }
static struct nand_device *mtd_to_nanddev(struct mtd_info *m) { (void)m;return &nand; }
static struct spinand_device *nand_to_spinand(struct nand_device *n) { assert(n==&nand);return &chip; }
static int iterator(struct nand_io_iter *i,loff_t start) {
 if(i->page>=pages)return 0;
 i->req.pos.target=0;i->req.pos.offset=start+i->page*2048;i->req.datalen=2048;i->req.ooblen=0;return 1;
}
#define nanddev_io_for_each_page(n,type,to,ops,it) \
 for((it)->page=0;iterator(it,to);(it)->page++)
static loff_t nanddev_pos_to_offs(struct nand_device *n,struct nand_pos *p) { assert(n==&nand);return p->offset; }
static void nanddev_offs_to_pos(struct nand_device *n,loff_t off,struct nand_pos *p) { assert(n==&nand);p->offset=off; }
static int spinand_select_target(struct spinand_device *s,unsigned target) {
 assert(s->lock && !target);selects++;if(select_error)last_error=select_error;return select_error;
}
static int spinand_write_page(struct spinand_device *s,struct request *r) {
 assert(s->lock);programs++;(void)r;
 if(write_error && programs==fail_page) { last_error=write_error;return write_error; }return 0;
}
static int nanddev_mtd_erase(struct mtd_info *m,struct erase_info *e) {
 (void)m;assert(chip.lock);erases++;
 if(erase_error) { e->fail_addr=e->addr+131072;last_error=erase_error; }return erase_error;
}
static int nanddev_markbad(struct nand_device *n,struct nand_pos *p) { (void)n;(void)p;assert(chip.lock);marks++;return 0; }
'''

CASES = r'''
static void reset(bool guard) {
 memset(&chip,0,sizeof(chip));chip.spimem=&mem;
 selects=programs=erases=marks=logs=0;pages=3;
 select_error=write_error=erase_error=last_error=0;fail_page=2;
 diagnostic_write_guard=guard;spinand_diag_init(&chip);
}
int main(void) {
 struct mtd_info m={.ooblayout=&nand};struct mtd_oob_ops ops={0};
 struct erase_info erase={.addr=0x5400000,.fail_addr=MTD_FAIL_ADDR_UNKNOWN};
 reset(true);assert(spinand_mtd_write(&m,0x5400000,&ops)==0 && programs==3 && !chip.diagnostic_failed);
 assert(spinand_mtd_erase(&m,&erase)==0 && erases==1);
 assert(spinand_mtd_block_markbad(&m,0x5400000)==-EROFS && !marks);
 int errors[]={-EIO,-ETIMEDOUT,-ENOMEM,-EROFS};
 for(unsigned i=0;i<4;i++) {
  reset(true);memset(&ops,0,sizeof(ops));write_error=errors[i];
  assert(spinand_mtd_write(&m,0x5400000,&ops)==-EROFS && programs==2 && ops.retlen==2048);
  assert(chip.diagnostic_errno==errors[i] && chip.diagnostic_offset==0x5400800 && logs==1);
  unsigned calls=selects+programs+erases+marks;
  for(unsigned retry=0;retry<4;retry++) {
   assert(spinand_mtd_write(&m,0x5400000,&ops)==-EROFS);
   assert(spinand_mtd_erase(&m,&erase)==-EROFS);
   assert(spinand_mtd_block_markbad(&m,0x5400000)==-EROFS);
  }
  assert(selects+programs+erases+marks==calls && logs==1);
  reset(true);erase_error=errors[i];erase.fail_addr=MTD_FAIL_ADDR_UNKNOWN;
  assert(spinand_mtd_erase(&m,&erase)==-EROFS && erases==1);
  assert(chip.diagnostic_offset==0x5420000 && chip.diagnostic_errno==errors[i]);
  assert(spinand_mtd_erase(&m,&erase)==-EROFS && erases==1);
 }
 reset(true);select_error=-EIO;assert(spinand_mtd_write(&m,0x5400000,&ops)==-EROFS && !programs && selects==1);
 reset(false);write_error=-EIO;assert(spinand_mtd_write(&m,0x5400000,&ops)==-EIO && !chip.diagnostic_failed);
 write_error=last_error=0;assert(spinand_mtd_write(&m,0x5400000,&ops)==0);
 erase_error=-ETIMEDOUT;assert(spinand_mtd_erase(&m,&erase)==-ETIMEDOUT && !chip.diagnostic_failed);
 erase_error=last_error=0;assert(spinand_mtd_block_markbad(&m,0x5400000)==0 && marks==1);
 return 0;
}
'''


class SpinandDiagnosticTests(unittest.TestCase):
    def test_actual_callbacks_stop_mutations_before_unlock_and_preserve_normal_errors(self):
        trees = list((ROOT / 'openwrt/build_dir').glob('target-*/linux-armsr_armv7/linux-6.6.151'))
        if len(trees) != 1:
            self.skipTest('requires the pinned prepared kernel; guard policy is also checked by kernel build')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ('drivers/mtd/nand/spi/core.c', 'drivers/mtd/nand/spi/Kconfig', 'include/linux/mtd/spinand.h')
            for name in names:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(trees[0] / name, target)
            if 'spinand_diag_enter' not in (root / names[0]).read_text():
                subprocess.run(['patch', '-p1', '--batch', '--input', str(PATCH)], cwd=root,
                               check=True, capture_output=True, text=True)
            source = (root / names[0]).read_text()
            self.assertIn('.suppress_bind_attrs = IS_ENABLED(CONFIG_MTD_SPI_NAND_DIAGNOSTIC)', source)
            code = MODEL + HEADER.read_text() + '\n'.join(function(source, name) for name in
                        ('spinand_mtd_write', 'spinand_mtd_block_markbad', 'spinand_mtd_erase')) + CASES
            cfile, executable = root / 'guard.c', root / 'guard'
            cfile.write_text(code)
            run = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', str(cfile), '-o', str(executable)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
