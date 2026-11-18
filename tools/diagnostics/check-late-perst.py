#!/usr/bin/env python3
"""Apply the diagnostic patches in a temporary tree and test actual C reset logic.

No device access, source-tree mutation, or firmware build occurs.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
REL = Path('drivers/pci/controller/dwc/pcie-zx279128.c')
PREFIX = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <errno.h>
typedef uint32_t u32;
#define ZX_GLUE_CTRL 0
#define ZX_GLUE_LTSSM_EN (1u<<5)
struct zx_pcie { int id; void *glue; };
static u32 ctr[2];
static unsigned stuck, assert_fail, release_fail, assertions[2], releases[2], trains, low_waits, high_waits;
static bool asserted[2];
static u32 readl(void *p){return *(u32*)p;}
static void writel(u32 v,void *p){unsigned i=p==&ctr[1];if(stuck&(1u<<i))v|=ZX_GLUE_LTSSM_EN;*(u32*)p=v;}
static int zx_perst_set(struct zx_pcie *p,bool low){
 unsigned i=p->id;
 if(low){assert(!(ctr[0]&ZX_GLUE_LTSSM_EN)&&!(ctr[1]&ZX_GLUE_LTSSM_EN));assertions[i]++;asserted[i]=true;return (assert_fail&(1u<<i))?-ETIMEDOUT:0;}
 releases[i]++;if(release_fail&(1u<<i))return -EREMOTEIO;asserted[i]=false;return 0;
}
static void mdelay(unsigned t){
 if(t==100){assert(asserted[0]&&asserted[1]);low_waits++;}
 else if(t==200){assert(!asserted[0]&&!asserted[1]);assert(releases[0]&&releases[1]);high_waits++;}
 else abort();
}
static void zx_pcie_train(struct zx_pcie *p){assert(!asserted[0]&&!asserted[1]);assert(high_waits==1);assert(!(ctr[p->id]&ZX_GLUE_LTSSM_EN));ctr[p->id]|=ZX_GLUE_LTSSM_EN;trains++;}
"""
SUFFIX = r"""
static void clear(unsigned stuck_mask,unsigned af,unsigned rf){
 stuck=stuck_mask;assert_fail=af;release_fail=rf;trains=low_waits=high_waits=0;
 for(int i=0;i<2;i++){ctr[i]=0x28;assertions[i]=releases[i]=0;asserted[i]=false;}
}
int main(void){
 struct zx_pcie p[2]={{0,&ctr[0]},{1,&ctr[1]}};unsigned cases=0;
 clear(0,0,0);assert(zx_pcie_retry_after_clocks(p)==0);assert(trains==2&&low_waits==1&&high_waits==1);cases++;
 for(unsigned i=1;i<4;i++){
  clear(i,0,0);assert(zx_pcie_retry_after_clocks(p)==-EIO);assert(!assertions[0]&&!assertions[1]);assert(releases[0]==1&&releases[1]==1&&!trains);cases++;
  clear(0,i,0);assert(zx_pcie_retry_after_clocks(p)==-ETIMEDOUT);assert(releases[0]==1&&releases[1]==1&&!trains);assert(!asserted[0]&&!asserted[1]);cases++;
  clear(0,0,i);assert(zx_pcie_retry_after_clocks(p)==-EREMOTEIO);assert(releases[0]==1&&releases[1]==1&&!trains);cases++;
  clear(0,i,3);assert(zx_pcie_retry_after_clocks(p)==-ETIMEDOUT);assert(releases[0]==1&&releases[1]==1&&!trains);cases++;
 }
 printf("PASS: %u actual-C late-reset success/fault cases; both releases always attempted, first error retained, train only after verified releases/delay\n",cases);
 return 0;
}
"""


def main():
    with tempfile.TemporaryDirectory(prefix='h199a-late-perst-check-') as temporary:
        tree = Path(temporary)
        driver = tree / REL
        driver.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / 'files/target/linux/armsr/files-6.6' / REL, driver)
        for name in ('pcie-config-trace.patch', 'pcie-late-perst-experiment.patch'):
            patch = Path(__file__).resolve().parent / name
            subprocess.run(['git', 'apply', '--check', str(patch)], cwd=tree, check=True)
            subprocess.run(['git', 'apply', str(patch)], cwd=tree, check=True)
        source = driver.read_text()
        start = source.index('static int zx_pcie_retry_after_clocks(')
        opening = source.index('{', start)
        depth = 1
        end = opening + 1
        while depth:
            depth += (source[end] == '{') - (source[end] == '}')
            end += 1
        test = tree / 'test.c'
        test.write_text(PREFIX + source[start:end] + '\n' + SUFFIX)
        compiler = shutil.which('cc')
        if not compiler:
            raise SystemExit('host C compiler required')
        binary = tree / 'test'
        subprocess.run([compiler, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(test), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
