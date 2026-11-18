"""Compile the exact pre-MMU BootPara validator and test fail-closed inputs."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import function

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'files/target/linux/armsr/files-6.6/arch/arm/boot/compressed/zx279128-boot.c'


class BootBankTest(unittest.TestCase):
    def test_valid_banks_single_slot_and_corrupt_bootpara(self):
        text = SOURCE.read_text()
        constants = '\n'.join(line for line in text.splitlines() if line.startswith('#define ZX_'))
        cases = r'''
#include <assert.h>
#include <string.h>
static void put(unsigned char *p, unsigned value) {
 p[0]=value;p[1]=value>>8;p[2]=value>>16;p[3]=value>>24;
}
static void sum(unsigned char *p) {
 unsigned n=0;
 for(unsigned i=0;i<ZX_BOOTPARA_SIZE;i++)
  if(i<ZX_BOOTPARA_CHECKSUM || i>=ZX_BOOTPARA_CHECKSUM+4)n+=p[i];
 put(p+ZX_BOOTPARA_CHECKSUM,n);
}
static void make(unsigned char *p,unsigned bank,unsigned count) {
 memset(p,0,ZX_BOOTPARA_SIZE);
 put(p,0xcccccccc);put(p+4,0x55555555);put(p+8,0xaaaaaaaa);put(p+12,0x11111111);
 put(p+0x34,count);put(p+0x38,count);put(p+0x3c,bank);
 put(p+0x130,0x700000);put(p+0x134,0xa00000);
 put(p+0x34c,0x2000000);put(p+0x350,0x2300000);
 sum(p);
}
int main(void) {
 unsigned char p[ZX_BOOTPARA_SIZE];
 make(p,0,2);assert(zx_boot_bank(p,sizeof(p))==0);
 make(p,1,2);assert(zx_boot_bank(p,sizeof(p))==1);
 make(p,1,1);assert(zx_boot_bank(p,sizeof(p))==1);
 /* Slot count is not the highest slot index: only slot B may exist. */
 put(p+0x130,0);put(p+0x134,0);sum(p);assert(zx_boot_bank(p,sizeof(p))==1);
 for(unsigned i=0;i<sizeof(p);i++) {
  unsigned char old=p[i];p[i]^=1;
  assert(zx_boot_bank(p,sizeof(p))<0);p[i]=old;
 }
 for(unsigned n=0;n<sizeof(p);n++)assert(zx_boot_bank(p,n)<0);
 assert(zx_boot_bank(p,sizeof(p)+1)<0);
 make(p,2,2);assert(zx_boot_bank(p,sizeof(p))<0);
 make(p,0,0);assert(zx_boot_bank(p,sizeof(p))<0);
 make(p,0,3);assert(zx_boot_bank(p,sizeof(p))<0);
 make(p,0,2);put(p+0x130,0x2000000);sum(p);assert(zx_boot_bank(p,sizeof(p))<0);
 make(p,1,2);put(p+0x350,0xa00000);sum(p);assert(zx_boot_bank(p,sizeof(p))<0);
 return 0;
}
'''
        code = constants + '\n' + function(text, 'zx_boot_le32') + '\n' + function(text, 'zx_boot_bank') + cases
        with tempfile.TemporaryDirectory() as tmp:
            source, binary = Path(tmp) / 'boot.c', Path(tmp) / 'boot'
            source.write_text(code)
            built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                    str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
