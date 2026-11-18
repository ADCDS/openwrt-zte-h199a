"""Fault-inject the complete preflight without opening any real MTD device."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/nand-ubi-preflight.c'

MOCK = r'''
#define _FILE_OFFSET_BITS 64
#include <assert.h>
#include <dirent.h>
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
static int fake_open(const char *,int,...),fake_fstat(int,struct stat *);
static int fake_stat(const char *,struct stat *),fake_lstat(const char *,struct stat *);
static int fake_ioctl(int,unsigned long,...),fake_close(int);
static DIR *fake_opendir(const char *);
static struct dirent *fake_readdir(DIR *);
static int fake_closedir(DIR *);
static void fake_exit(int);
#define fopen fake_fopen
#define open fake_open
#define fstat fake_fstat
#define stat fake_stat
#define lstat fake_lstat
#define ioctl fake_ioctl
#define close fake_close
#define opendir fake_opendir
#define readdir fake_readdir
#define closedir fake_closedir
#define exit fake_exit
#define main test_main
'''
# Function-like macros avoid replacing 'struct stat'.
MOCK = MOCK.replace('#define stat fake_stat', '#define stat(p,s) fake_stat(p,s)')

HARNESS = r'''
#undef fopen
#undef open
#undef fstat
#undef stat
#undef lstat
#undef ioctl
#undef close
#undef opendir
#undef readdir
#undef closedir
#undef exit
#undef main
static unsigned scenario,reads,badchecks,opens,dirs;
static jmp_buf escape;
static int result;
static FILE *fake_fopen(const char *path,const char *mode) {
 char text[80];const char *value=NULL;unsigned n;
 assert(!strcmp(mode,"r"));
 if(!strcmp(path,"/sys/class/mtd/mtd13/name"))value="ubi-test\n";
 else if(!strcmp(path,"/sys/class/mtd/mtd13/offset"))value=scenario==1?"83886080\n":"88080384\n";
 else if(!strcmp(path,"/sys/class/mtd/mtd13/size"))value="16777216\n";
 else if(!strcmp(path,"/sys/class/mtd/mtd0/size"))value="134217728\n";
 else if(!strcmp(path,"/sys/module/spi_zx279128/parameters/ubi_test"))value=scenario==2?"N\n":"Y\n";
 else if(!strcmp(path,"/sys/module/spi_zx279128/parameters/write_test"))value=scenario==3?"Y\n":"N\n";
 else if(!strcmp(path,"/sys/module/spinand/parameters/diagnostic_write_guard"))value=scenario==4?"N\n":"Y\n";
 else {
  assert(sscanf(path,"/sys/class/mtd/mtd%u/flags",&n)==1 && n<=13);
  snprintf(text,sizeof(text),"0x%x\n",(n==0 || n==13 || (scenario==5 && n==9))?0x400:0);value=text;
 }
 FILE *f=tmpfile();assert(f);assert(fputs(value,f)>=0);rewind(f);return f;
}
static int fake_open(const char *path,int flags,...) {
 assert(!strcmp(path,"/dev/mtd13") && (flags&O_NOFOLLOW));
 assert((flags&O_ACCMODE)==O_RDONLY);opens++;return 61;
}
static int fake_fstat(int fd,struct stat *st) {
 assert(fd==61);memset(st,0,sizeof(*st));st->st_mode=S_IFCHR;
 st->st_rdev=makedev(90,scenario==10?24:26);return 0;
}
static int fake_stat(const char *path,struct stat *st) {
 assert(strstr(path,"/drivers/"));memset(st,0,sizeof(*st));st->st_mode=S_IFDIR;
 if(scenario==7) { errno=ENOENT;return -1; }return 0;
}
static int fake_lstat(const char *path,struct stat *st) {
 (void)st;
 if((scenario==6 && strstr(path,"mtd14")) || (scenario==8 && strstr(path,"unbind")))return 0;
 errno=ENOENT;return -1;
}
static DIR *fake_opendir(const char *path) { assert(!strcmp(path,"/sys/class/ubi"));dirs++;return (DIR *)1; }
static struct dirent *fake_readdir(DIR *d) {
 static struct dirent entry;assert(d==(DIR *)1);
 if(scenario==9) { strcpy(entry.d_name,"ubi1");return &entry; }
 errno=0;return NULL;
}
static int fake_closedir(DIR *d) { assert(d==(DIR *)1);return 0; }
static int fake_ioctl(int fd,unsigned long request,...) {
 va_list ap;void *arg;assert(fd==61);va_start(ap,request);arg=va_arg(ap,void *);va_end(ap);
 if(request==MEMGETINFO) {
  struct mtd_info_user *m=arg;memset(m,0,sizeof(*m));m->type=MTD_NANDFLASH;
  m->flags=MTD_WRITEABLE;m->size=16777216;m->erasesize=131072;m->writesize=2048;
  m->oobsize=scenario==11?64:128;return 0;
 }
 if(request==MEMGETBADBLOCK) {
  assert(*(int64_t *)arg==badchecks*131072);badchecks++;
  if(scenario==12 && badchecks==128)return 1;
  return 0;
 }
 if(request==MEMREAD) {
  struct mtd_read_req *r=arg;assert(r->start==(reads/2)*2048 && r->start<16777216);
  assert(r->len==2048 && r->ooblen==128 && r->usr_data && r->usr_oob);
  assert(r->mode==(reads%2?MTD_OPS_RAW:MTD_OPS_PLACE_OOB));reads++;
  uint8_t *data=(void *)(uintptr_t)r->usr_data,*oob=(void *)(uintptr_t)r->usr_oob;
  memset(data,0xff,2048);memset(oob,0xff,128);
  r->start+=2048; /* The pinned mtdchar implementation advances this field. */
  if(reads==16384) {
   if(scenario==13) { errno=EIO;return -1; }
   if(scenario==14)data[2047]=0;
   if(scenario==15)oob[127]=0;
   if(scenario==16)r->ecc_stats.corrected_bitflips=1;
  }
  return 0;
 }
 assert(!"unexpected ioctl: preflight must never mutate flash");return -1;
}
static int fake_close(int fd) { assert(fd==61);return 0; }
static void fake_exit(int code) { result=code;longjmp(escape,1); }
int main(int argc,char **argv) {
 assert(argc==2);scenario=atoi(argv[1]);
 char *args[]={"nand-ubi-preflight","--check-blank",NULL};
 if(!setjmp(escape))result=test_main(2,args);
 if(scenario==0)assert(result==0 && reads==16384 && badchecks==128 && dirs==2);
 else {
  assert(result==1);
  if(scenario<=9)assert(!opens && !reads);
  if(scenario>=13)assert(reads==16384);
 }
 return 0;
}
'''


class UbiPreflightTests(unittest.TestCase):
    def test_guards_geometry_full_window_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp) / 'preflight.c', Path(tmp) / 'preflight'
            src.write_text(MOCK + '\n' + SOURCE.read_text() + '\n' + HARNESS)
            run = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                  str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            for scenario in range(17):
                with self.subTest(scenario=scenario):
                    run = subprocess.run([str(exe), str(scenario)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    if scenario == 16:
                        self.assertIn('physical=0x63ff800', run.stderr)
