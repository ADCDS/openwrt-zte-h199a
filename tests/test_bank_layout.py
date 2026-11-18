"""Run the real early OF mapping with a host model and allocation failures."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'files/target/linux/armsr/files-6.6/arch/arm/mach-zx279128/boot-bank.c'

MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <setjmp.h>
typedef uint32_t u32;
#define __init
#define __ro_after_init
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define GFP_KERNEL 0
#define pr_info(...) ((void)0)
struct property { char *name; void *value; int length; struct property *next; };
struct device_node { const char *name; struct property *properties; unsigned refs; };
static struct device_node nodes[9];
static unsigned allocations,fail_allocation;
static bool board=true;
static jmp_buf panic_env;
static void __attribute__((noreturn)) panic(const char *fmt,...) {
 (void)fmt;longjmp(panic_env,1);
}
static void *allocate(size_t n) {
 if(++allocations==fail_allocation)return NULL;
 return calloc(1,n?n:1);
}
static void *kzalloc(size_t n,int flags) {(void)flags;return allocate(n);}
static char *kstrdup(const char *s,int flags) {
 (void)flags;char *p=allocate(strlen(s)+1);if(p)strcpy(p,s);return p;
}
static void *kmemdup(const void *s,size_t n,int flags) {
 (void)flags;void *p=allocate(n);if(p && n)memcpy(p,s,n);return p;
}
#define kfree free
static bool of_machine_is_compatible(const char *s) {
 return board && !strcmp(s,"zte,zxhn-h199a");
}
static struct property *of_find_property(struct device_node *n,const char *name,int *length) {
 if(!n)return NULL;
 for(struct property *p=n->properties;p;p=p->next)if(!strcmp(p->name,name)) {
  if(length)*length=p->length;return p;
 }
 return NULL;
}
static int of_property_count_u32_elems(struct device_node *n,const char *name) {
 struct property *p=of_find_property(n,name,NULL);return p && !(p->length%4)?p->length/4:-EINVAL;
}
static int of_property_read_u32_array(struct device_node *n,const char *name,u32 *v,unsigned count) {
 struct property *p=of_find_property(n,name,NULL);
 if(!p || p->length<(int)(4*count))return -EINVAL;
 memcpy(v,p->value,4*count);return 0;
}
static int of_property_read_u32(struct device_node *n,const char *name,u32 *v) {
 return of_property_read_u32_array(n,name,v,1);
}
static bool of_property_read_bool(struct device_node *n,const char *name) {
 return of_find_property(n,name,NULL)!=NULL;
}
static const void *of_get_property(struct device_node *n,const char *name,int *len) {
 struct property *p=of_find_property(n,name,len);return p?p->value:NULL;
}
static struct device_node *get(struct device_node *n) {if(n)n->refs++;return n;}
static void of_node_put(struct device_node *n) {if(n){assert(n->refs);n->refs--;}}
static struct device_node *of_find_node_by_path(const char *s) {
 if(!strcmp(s,"/chosen"))return get(&nodes[0]);
 if(!strcmp(s,"/soc/spi@94406000/flash@0"))return get(&nodes[1]);
 for(unsigned i=3;i<9;i++)if(nodes[i].name) {
  char path[128];snprintf(path,sizeof(path),"/soc/spi@94406000/flash@0/partitions/%s",nodes[i].name);
  if(!strcmp(path,s))return get(&nodes[i]);
 }
 return NULL;
}
static struct device_node *of_get_child_by_name(struct device_node *n,const char *name) {
 if(n==&nodes[1] && !strcmp(name,"partitions"))return get(&nodes[2]);
 if(n==&nodes[2])for(unsigned i=3;i<9;i++) {
  size_t length=strcspn(nodes[i].name,"@");
  if(strlen(name)==length && !strncmp(nodes[i].name,name,length))return get(&nodes[i]);
 }
 return NULL;
}
static int of_remove_property(struct device_node *n,struct property *p) {
 struct property **link=&n->properties;
 while(*link && *link!=p)link=&(*link)->next;
 if(!*link)return -EINVAL;
 *link=p->next;free(p->name);free(p->value);free(p);return 0;
}
static int of_update_property(struct device_node *n,struct property *p) {
 struct property *old=of_find_property(n,p->name,NULL);
 if(old)of_remove_property(n,old);
 p->next=n->properties;n->properties=p;return 0;
}
'''

CASES = r'''
static const unsigned offsets[]={0x700000,0xa00000,0x1720000,0x2000000,0x2300000,0x3020000};
static const unsigned sizes[]={0x300000,0xd20000,0x20000,0x300000,0xd20000,0x20000};
static const char *names[]={"partition@700000","partition@a00000","partition@1720000",
 "partition@2000000","partition@2300000","partition@3020000"};
static void fixture_property(struct device_node *n,const char *name,const void *v,unsigned len) {
 struct property *p=calloc(1,sizeof(*p));p->name=strdup(name);p->length=len;
 p->value=malloc(len?len:1);if(len)memcpy(p->value,v,len);of_update_property(n,p);
}
static void reset(u32 bank,bool malformed) {
 for(unsigned i=0;i<9;i++)while(nodes[i].properties)of_remove_property(&nodes[i],nodes[i].properties);
 memset(nodes,0,sizeof(nodes));active_bank=-1;board=true;allocations=0;fail_allocation=0;
 u32 cell[2]={bank,0};fixture_property(&nodes[0],"zte,boot-bank",cell,malformed?8:4);
 fixture_property(&nodes[1],"zte,bank-aware",NULL,0);
 for(unsigned i=0;i<6;i++) {
  nodes[i+3].name=names[i];u32 reg[2]={offsets[i],sizes[i]};
  fixture_property(&nodes[i+3],"reg",reg,sizeof(reg));
  const char *label=i<3?(i==0?"kernel1":i==1?"rootfs":"header"):
                      (i==3?"kernel2":i==4?"rootfs2":"header2");
  fixture_property(&nodes[i+3],"label",label,strlen(label)+1);
  if(i>=3)fixture_property(&nodes[i+3],"read-only",NULL,0);
  if(i==1)fixture_property(&nodes[i+3],"linux,rootfs",NULL,0);
 }
}
static void check(unsigned bank) {
 assert(zx279128_active_bank()==(int)bank);
 for(unsigned i=0;i<6;i++) {
  bool selected=(i/3)==bank;unsigned kind=i%3;
  const char *expected=selected?(kind==0?"kernel1":kind==1?"rootfs":"header"):
                                 (kind==0?"kernel2":kind==1?"rootfs2":"header2");
  assert(!strcmp(of_find_property(&nodes[i+3],"label",NULL)->value,expected));
  assert(of_property_read_bool(&nodes[i+3],"read-only")==!selected);
  /* fixed-partitions uses of_get_property(), not only read_bool(). */
  assert((of_get_property(&nodes[i+3],"read-only",NULL)!=NULL)==!selected);
  assert(of_property_read_bool(&nodes[i+3],"linux,rootfs")== (selected && kind==1));
  assert((of_get_property(&nodes[i+3],"linux,rootfs",NULL)!=NULL)== (selected && kind==1));
  u32 reg[2];assert(!of_property_read_u32_array(&nodes[i+3],"reg",reg,2));
  assert(reg[0]==offsets[i] && reg[1]==sizes[i]);
 }
 for(unsigned i=0;i<9;i++)assert(!nodes[i].refs);
}
int main(void) {
 reset(0,false);assert(of_get_child_by_name(&nodes[2],"partition@700000")==NULL);
 for(unsigned bank=0;bank<2;bank++) {
  reset(bank,false);assert(!setjmp(panic_env));zx279128_init_boot_bank();check(bank);
 }
 unsigned allocation_count=allocations;
 for(unsigned failure=1;failure<=allocation_count;failure++) {
  reset(1,false);fail_allocation=failure;
  if(!setjmp(panic_env)){zx279128_init_boot_bank();assert(!"allocation failure must stop boot");}
  assert(zx279128_active_bank()<0);
 }
 reset(0,true);
 if(!setjmp(panic_env)){zx279128_init_boot_bank();assert(!"oversized marker must fail");}
 assert(zx279128_active_bank()<0);
 reset(0xffffffff,false);
 if(!setjmp(panic_env)){zx279128_init_boot_bank();assert(!"unknown marker must fail");}
 assert(zx279128_active_bank()<0);
 reset(1,false);u32 wrong[2]={0x2000000,0x100000};fixture_property(&nodes[6],"reg",wrong,8);
 if(!setjmp(panic_env)){zx279128_init_boot_bank();assert(!"wrong geometry must fail");}
 assert(zx279128_active_bank()<0);
 reset(0,false);board=false;zx279128_init_boot_bank();assert(zx279128_active_bank()<0);
 reset(0xffffffff,false);of_remove_property(&nodes[1],of_find_property(&nodes[1],"zte,bank-aware",NULL));
 assert(!setjmp(panic_env));zx279128_init_boot_bank();assert(zx279128_active_bank()<0);
 return 0;
}
'''


class BankLayoutTest(unittest.TestCase):
    def test_both_banks_permissions_geometry_and_fail_closed_mapping(self):
        source = '\n'.join(line for line in SOURCE.read_text().splitlines()
                           if not line.startswith('#include'))
        with tempfile.TemporaryDirectory() as tmp:
            c, binary = Path(tmp) / 'layout.c', Path(tmp) / 'layout'
            c.write_text(MODEL + source + CASES)
            built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                    '-Wno-misleading-indentation', str(c), '-o', str(binary)],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
