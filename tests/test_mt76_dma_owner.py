"""Exercise the private DMA lifetime against device removal and allocation faults."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from mt76_fixture import sources, c_function

MODEL = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdio.h>
#include <errno.h>
typedef uintptr_t dma_addr_t;
struct list_head { struct list_head *next,*prev; };
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define LIST_HEAD(n) struct list_head n={&n,&n}
#define DEFINE_MUTEX(n) int n
#define list_for_each_entry(p,h,m) \
 for(p=container_of((h)->next,__typeof__(*p),m); &(p)->m!=(h); \
 p=container_of((p)->m.next,__typeof__(*p),m))
static void list_add(struct list_head *n,struct list_head *h) {
 n->next=h->next;n->prev=h;h->next->prev=n;h->next=n;
}
static void list_del(struct list_head *n) {n->prev->next=n->next;n->next->prev=n->prev;}
static void mutex_lock(int *p) {assert(!*p);*p=1;}
static void mutex_unlock(int *p) {assert(*p);*p=0;}
struct bus_type {const char *name;};
struct action {void (*fn)(void *);void *data;struct action *next;};
struct device {
 unsigned refs;struct bus_type *bus;const char *name;
 void (*release)(struct device *);struct action *actions;
};
struct mt76_dev {
 struct device *dev,*dma_dev,*dma_resources;bool dma_quarantined;
};
#define GFP_KERNEL 0
#define THIS_MODULE ((void *)1)
static unsigned module_refs,dma_live,dma_frees;
static int fail_alloc,alloc_calls;
static bool fail_module,fail_action,fail_dma;
static void *kzalloc(size_t bytes,int flags) {
 (void)flags;if(++alloc_calls==fail_alloc)return NULL;return calloc(1,bytes);
}
#define kfree free
static char *kasprintf(int flags,const char *fmt,...) {
 (void)flags;if(++alloc_calls==fail_alloc)return NULL;
 va_list ap;char *text;va_start(ap,fmt);int n=vasprintf(&text,fmt,ap);va_end(ap);
 return n<0?NULL:text;
}
static const char *dev_name(struct device *d) {return d->name;}
static bool try_module_get(void *m) {assert(m==THIS_MODULE);if(fail_module)return false;module_refs++;return true;}
static void module_put(void *m) {assert(m==THIS_MODULE && module_refs);module_refs--;}
static void device_initialize(struct device *d) {assert(!d->refs);d->refs=1;}
static struct device *get_device(struct device *d) {assert(d->refs);d->refs++;return d;}
static void release_resources(struct device *d) {
 while(d->actions) {
  struct action *a=d->actions;d->actions=a->next;a->fn(a->data);free(a);
 }
}
static void put_device(struct device *d) {
 assert(d->refs);if(--d->refs)return;
 release_resources(d);if(d->release)d->release(d);
}
static void *dma_alloc_coherent(struct device *d,size_t bytes,dma_addr_t *dma,int flags) {
 (void)flags;assert(d->refs);if(fail_dma)return NULL;
 void *p=calloc(1,bytes);assert(p);*dma=(uintptr_t)p;dma_live++;return p;
}
static void dma_free_coherent(struct device *d,size_t bytes,void *address,dma_addr_t dma) {
 assert(d->refs && bytes && address && dma==(uintptr_t)address && dma_live);
 free(address);dma_live--;dma_frees++;
}
static int devm_add_action_or_reset(struct device *d,void (*fn)(void *),void *data) {
 if(fail_action){fn(data);return -ENOMEM;}
 struct action *a=calloc(1,sizeof(*a));assert(a);a->fn=fn;a->data=data;
 a->next=d->actions;d->actions=a;return 0;
}
static void *dmam_alloc_coherent(struct device *d,size_t bytes,dma_addr_t *dma,int flags) {
 (void)d;(void)bytes;(void)dma;(void)flags;assert(!"unexpected fallback");return NULL;
}
'''

CASES = r'''
static struct bus_type pci={"pci"};
static struct device parent={.refs=1,.bus=&pci,.name="0000:01:00.0"};
static struct mt76_dev device={.dev=&parent,.dma_dev=&parent};
static void faults_off(void) {fail_alloc=alloc_calls=0;fail_module=fail_action=fail_dma=false;}
int main(void) {
 dma_addr_t dma;
 for(int fault=1;fault<=2;fault++) {
  faults_off();fail_alloc=fault;
  assert(mt76_dma_owner_init(&device)==-ENOMEM && !device.dma_resources);
  assert(!module_refs && parent.refs==1);
 }
 faults_off();fail_module=true;
 assert(mt76_dma_owner_init(&device)==-ENODEV && !module_refs);
 faults_off();assert(!mt76_dma_device_busy(&parent));
 assert(!mt76_dma_owner_init(&device) && module_refs==1 && parent.refs==2);
 assert(mt76_dma_device_busy(&parent));
 struct mt76_dev duplicate={.dev=&parent,.dma_dev=&parent};
 assert(mt76_dma_owner_init(&duplicate)==-EBUSY && !duplicate.dma_resources);
 fail_dma=true;assert(!mt76_dma_alloc_desc(&device,4096,&dma) && !dma_live);
 fail_dma=false;fail_action=true;
 assert(!mt76_dma_alloc_desc(&device,4096,&dma) && !dma_live && dma_frees==1);
 fail_action=false;
 assert(mt76_dma_alloc_desc(&device,4096,&dma) && dma_live==1);
 /* PCI devres release must not own or free the private allocation. */
 release_resources(&parent);assert(dma_live==1 && parent.refs==2);
 mt76_dma_owner_put(&device);
 assert(!device.dma_resources && !dma_live && dma_frees==2 && !module_refs && parent.refs==1);
 assert(!mt76_dma_device_busy(&parent));
 assert(!mt76_dma_owner_init(&device));
 assert(mt76_dma_alloc_desc(&device,4096,&dma));
 device.dma_quarantined=true;
 release_resources(&parent);mt76_dma_owner_put(&device);
 assert(device.dma_resources && dma_live==1 && module_refs==1 && parent.refs==2);
 /* A fresh struct device at the same BDF is also blocked after rescan. */
 struct device rescanned={.refs=1,.bus=&pci,.name="0000:01:00.0"};
 assert(mt76_dma_device_busy(&rescanned));
 duplicate.dev=duplicate.dma_dev=&rescanned;
 assert(mt76_dma_owner_init(&duplicate)==-EBUSY && !duplicate.dma_resources);
 rescanned.name="0001:01:00.0";assert(!mt76_dma_device_busy(&rescanned));
 /* Deliberately retained until process exit, like the reboot-only case. */
 return 0;
}
'''


class Mt76DmaOwnerTests(unittest.TestCase):
    def test_private_resources_survive_unbind_and_quarantine_blocks_reprobe(self):
        source = sources()['dma.c']
        definitions = '\n'.join(re.search(r'struct '+name+r' \{.*?^\};', source,
                                          re.M | re.S).group(0)
                                for name in ('mt76_dma_owner', 'mt76_dma_allocation'))
        code = '\n'.join(c_function(source, name) for name in (
            'mt76_dma_device_busy', 'mt76_dma_owner_release', 'mt76_dma_owner_init',
            'mt76_dma_owner_put', 'mt76_dma_free_allocation', 'mt76_dma_alloc_desc'))
        registry = 'static LIST_HEAD(mt76_dma_owners);\nstatic DEFINE_MUTEX(mt76_dma_owners_lock);'
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp)/'owner.c', Path(tmp)/'owner'
            src.write_text('\n'.join((MODEL, definitions, registry, code, CASES)))
            result = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                     str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
