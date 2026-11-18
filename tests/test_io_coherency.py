"""The vendor setup must finish before coherent PCI DMA can be published."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import function

SOURCE = Path(__file__).resolve().parents[1] / "files/target/linux/armsr/files-6.6/arch/arm/mach-zx279128/platform.c"

PRELUDE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <setjmp.h>
#include <stdarg.h>
#include <string.h>
typedef uint32_t u32;
#define __init
#define __iomem
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
struct device_node { int unused; };
struct resource { unsigned int size; };
static struct device_node node;
static u32 registers[1024];
static int scenario, puts_count, maps, unmaps, writes, reads;
static jmp_buf stopped;
/* Bank mapping has its own fault-injection tests. */
static void zx279128_init_boot_bank(void) {}
/* Independent contract recovered from the verified stock init_machine. */
static const unsigned int offsets[]={0x80,0x84,0x88,0x78,0};
static const u32 values[]={0x40000001,0xbfffffff,0x1f0f1f0f,0x1f0f1f0f,0x0d000000};
static struct device_node *of_find_compatible_node(void *a,void *b,const char *compat) {
    assert(!a&&!b&&!strcmp(compat,"zte,zx279128s-iocc"));
    return scenario==1?NULL:&node;
}
static int of_address_to_resource(struct device_node *n,int index,struct resource *r) {
    assert(n==&node&&!index);r->size=scenario==3?0x88:4096;return scenario==2?-1:0;
}
static unsigned int resource_size(struct resource *r) { return r->size; }
static void *of_iomap(struct device_node *n,int index) {
    assert(n==&node&&!index);maps++;return scenario==4?NULL:registers;
}
static void of_node_put(struct device_node *n) { assert(n==&node);puts_count++; }
static void iounmap(void *p) { assert(p==registers);unmaps++; }
static void writel(u32 value,void *p) {
    unsigned long offset=(unsigned char *)p-(unsigned char *)registers;
    assert(writes<5&&offset==offsets[writes]&&value==values[writes]);
    /* The final control write must follow all four configuration writes. */
    if(!offset)assert(writes==4);
    registers[offset/4]=value;writes++;
}
static u32 readl(void *p) {
    unsigned long offset=(unsigned char *)p-(unsigned char *)registers;
    assert(writes==5&&reads<5&&offset==offsets[reads]);
    u32 value=registers[offset/4];
    if(scenario>=5&&reads==scenario-5)value^=1;
    reads++;return value;
}
static void pr_info(const char *fmt,...) { (void)fmt; }
static void __attribute__((noreturn)) panic(const char *fmt,...) {
    (void)fmt;longjmp(stopped,1);
}
'''

CASES = r'''
int main(void) {
    for(scenario=0;scenario<10;scenario++) {
        puts_count=maps=unmaps=writes=reads=0;memset(registers,0,sizeof(registers));
        if(!setjmp(stopped)) {
            zx279128_init_machine();
            assert(scenario==0);
        } else assert(scenario!=0);
        assert(puts_count==(scenario==1?0:1));
        if(scenario>=1&&scenario<=4)assert(!writes&&!reads&&!unmaps);
        else assert(writes==5&&reads==5&&unmaps==1);
        if(scenario>=1&&scenario<=3)assert(!maps);
        else assert(maps==1);
    }
    return 0;
}
'''


class IoCoherencyTests(unittest.TestCase):
    def test_complete_sequence_and_fail_closed_paths(self):
        source = PRELUDE + function(SOURCE.read_text(), "zx279128_init_machine") + CASES
        with tempfile.TemporaryDirectory() as tmp:
            c, exe = Path(tmp) / "coherency.c", Path(tmp) / "coherency"
            c.write_text(source)
            result = subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                                     str(c), "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
