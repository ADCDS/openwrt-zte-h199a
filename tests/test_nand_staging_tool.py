"""Run the actual bounded NAND test against fake syscalls, never a real MTD."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/nand-staging-test.c'

MOCK = r'''
#define _FILE_OFFSET_BITS 64
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <mtd/mtd-user.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <setjmp.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>
static FILE *fake_fopen(const char *,const char *);
static int fake_open(const char *,int,...);
static int fake_fstat(int,struct stat *);
static int fake_ioctl(int,unsigned long,...);
static int fake_close(int);
static void fake_exit(int);
#define fopen fake_fopen
#define open fake_open
#define fstat fake_fstat
#define ioctl fake_ioctl
#define close fake_close
#define exit fake_exit
#define main test_main
'''

HARNESS = r'''
#undef fopen
#undef open
#undef fstat
#undef ioctl
#undef close
#undef exit
#undef main
static unsigned scenario,reads,erases,programs,opens;
static uint8_t flash[64][2176];
static jmp_buf escape;
static int result;
static FILE *fake_fopen(const char *path,const char *mode) {
 char text[80];const char *value=NULL;unsigned n;
 assert(!strcmp(mode,"r"));
 if(!strcmp(path,"/sys/class/mtd/mtd13/name"))value="write-test\n";
 else if(!strcmp(path,"/sys/class/mtd/mtd13/offset"))value=scenario==1?"104595456\n":"104726528\n";
 else if(!strcmp(path,"/sys/class/mtd/mtd13/size"))value="131072\n";
 else if(!strcmp(path,"/sys/class/mtd/mtd0/size"))value="134217728\n";
 else if(!strcmp(path,"/sys/module/spi_zx279128/parameters/write_test"))value=scenario==2?"N\n":"Y\n";
 else {
  assert(sscanf(path,"/sys/class/mtd/mtd%u/flags",&n)==1 && n<=13);
  snprintf(text,sizeof(text),"0x%x\n",(n==0 || n==13 || (scenario==3 && n==9))?0x400:0);
  value=text;
 }
 FILE *f=tmpfile();assert(f);assert(fputs(value,f)>=0);rewind(f);return f;
}
static int fake_open(const char *path,int flags,...) {
 assert(!strcmp(path,"/dev/mtd13") && (flags&O_NOFOLLOW));opens++;return 61;
}
static int fake_fstat(int fd,struct stat *st) {
 assert(fd==61);memset(st,0,sizeof(*st));st->st_mode=S_IFCHR;
 st->st_rdev=makedev(90,scenario==4?24:26);return 0;
}
static int fake_ioctl(int fd,unsigned long request,...) {
 va_list ap;void *arg;assert(fd==61);va_start(ap,request);arg=va_arg(ap,void *);va_end(ap);
 if(request==MEMGETINFO) {
  struct mtd_info_user *m=arg;memset(m,0,sizeof(*m));m->type=MTD_NANDFLASH;
  m->flags=MTD_WRITEABLE;m->size=m->erasesize=131072;m->writesize=2048;
  m->oobsize=scenario==5?64:128;return 0;
 }
 if(request==MEMGETBADBLOCK) { assert(*(int64_t *)arg==0);return scenario==6?1:0; }
 if(request==MEMREAD) {
  struct mtd_read_req *r=arg;assert(r->start%2048==0 && r->start<131072);
  assert(r->len==2048 && r->ooblen==128 && r->usr_data && r->usr_oob);
  assert(r->mode==MTD_OPS_RAW || r->mode==MTD_OPS_PLACE_OOB);reads++;
  if(scenario==7) { errno=EIO;return -1; }
  memcpy((void *)(uintptr_t)r->usr_data,flash[r->start/2048],2048);
  memcpy((void *)(uintptr_t)r->usr_oob,flash[r->start/2048]+2048,128);
  if(scenario==10 && programs==64 && r->start==2048)r->ecc_stats.corrected_bitflips=1;
  return 0;
 }
 if(request==MEMERASE64) {
  struct erase_info_user64 *e=arg;assert(e->start==0 && e->length==131072);
  assert((erases==0 && reads==128 && !programs) || (erases==1 && reads==384 && programs==64));
  erases++;assert(erases<=2);memset(flash,0xff,sizeof(flash));return 0;
 }
 if(request==MEMWRITE) {
  struct mtd_write_req *w=arg;assert(erases==1 && reads==256 && programs<64);
  assert(w->start==programs*2048 && w->len==2048 && w->usr_data && !w->usr_oob && !w->ooblen);
  assert(w->mode==MTD_OPS_PLACE_OOB);programs++;
  if(scenario==9 && programs==8) { errno=EIO;return -1; }
  memcpy(flash[w->start/2048],(void *)(uintptr_t)w->usr_data,2048);
  memset(flash[w->start/2048]+2112,0xa5,64);
  if(scenario==12)flash[w->start/2048][2050]=0;
  return 0;
 }
 assert(!"unexpected NAND ioctl");return -1;
}
static int fake_close(int fd) { assert(fd==61);return 0; }
static void fake_exit(int code) { result=code;longjmp(escape,1); }
int main(int argc,char **argv) {
 assert(argc==2);scenario=atoi(argv[1]);memset(flash,0xff,sizeof(flash));
 if(scenario==8)flash[63][2175]=0;
 char *args[]={"nand-staging-test",scenario==11?"--check":"--execute-staging-block799",NULL};
 if(!setjmp(escape))result=test_main(2,args);
 if(scenario==0)assert(result==0 && erases==2 && programs==64 && reads==512);
 else if(scenario==11)assert(result==0 && !erases && !programs && reads==128);
 else {
  assert(result==1);
  if(scenario<=3)assert(!opens);
  if(scenario<=8)assert(!erases && !programs);
  if(scenario==9)assert(erases==1 && programs==8);
  if(scenario==10 || scenario==12)assert(erases==1 && programs==64);
 }
 return 0;
}
'''


class StagingToolTests(unittest.TestCase):
    def test_exact_window_preflight_sequence_and_failure_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp) / 'staging.c', Path(tmp) / 'staging'
            src.write_text(MOCK + '\n' + SOURCE.read_text() + '\n' + HARNESS)
            run = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                  str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            for scenario in range(13):
                with self.subTest(scenario=scenario):
                    run = subprocess.run([str(exe), str(scenario)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
