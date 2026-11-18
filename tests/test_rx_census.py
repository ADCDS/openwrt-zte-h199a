"""Compile the real census against guard-page-backed short Ethernet frames."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import function

SOURCE = Path(__file__).resolve().parents[1] / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c'
MODEL = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
typedef uint8_t u8;
typedef uint16_t u16;
#define ETH_HLEN 14
#define IS_ENABLED(option) (option)
struct zx_eth { unsigned c_tcp_bare,c_icmp,c_icmp_req,c_icmp_rep,c_udp,c_tcp_data,c_report; };
'''
CASES = r'''
static unsigned char packet[64],*memory;
static long page_size;
static struct zx_eth run(unsigned len) {
 struct zx_eth ze={0};unsigned char *at=memory+page_size-len;
 assert(len<=sizeof(packet));memcpy(at,packet,len);zx_rx_census(&ze,at,len);return ze;
}
static unsigned count(struct zx_eth z) {
 return z.c_tcp_bare+z.c_icmp+z.c_icmp_req+z.c_icmp_rep+z.c_udp+z.c_tcp_data+z.c_report;
}
static void base(void) {
 memset(packet,0,sizeof(packet));packet[12]=8;packet[14]=0x45;packet[17]=28;
 packet[23]=1;packet[34]=8;
}
int main(void) {
 page_size=sysconf(_SC_PAGESIZE);assert(page_size>64);
 memory=mmap(NULL,2*page_size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 assert(memory!=MAP_FAILED && !mprotect(memory+page_size,page_size,PROT_NONE));base();
 for(unsigned len=0;len<42;len++)assert(!count(run(len)));
 struct zx_eth z=run(42);
 if(!CONFIG_ZX279128_ETH_DEBUG) { assert(!count(z));return 0; }
 assert(z.c_icmp==1 && z.c_icmp_req==1 && !z.c_icmp_rep);
 z=run(60);assert(z.c_icmp_req==1); /* Ethernet padding is not IP length. */
 packet[14]=0x46;packet[17]=32;packet[34]=8;packet[38]=0;
 z=run(46);assert(z.c_icmp==1 && z.c_icmp_rep==1 && !z.c_icmp_req);
 for(unsigned flag=0;flag<2;flag++) {
  base();packet[20]=flag?0:0x20;packet[21]=flag?1:0;
  z=run(42);assert(z.c_icmp==1 && !z.c_icmp_req && !z.c_icmp_rep);
 }
 base();packet[20]=0x40;assert(run(42).c_icmp_req==1); /* DF is not fragmentation. */
 unsigned versions[]={0x44,0x65,0x4f};
 for(unsigned i=0;i<3;i++) { base();packet[14]=versions[i];assert(!count(run(42))); }
 base();packet[17]=19;assert(!count(run(42)));packet[17]=29;assert(!count(run(42)));
 base();packet[17]=20;z=run(34);assert(z.c_icmp==1 && !z.c_icmp_req);
 packet[23]=17;assert(run(34).c_udp==1);packet[23]=6;assert(run(34).c_tcp_data==1);
 packet[23]=2;assert(run(34).c_report==1);
 packet[12]=0x81;packet[13]=0;assert(run(14).c_tcp_bare==1);
 assert(!munmap(memory,2*page_size));return 0;
}
'''


class RxCensusTests(unittest.TestCase):
    def test_truncation_options_fragments_and_disabled_instrumentation(self):
        source = SOURCE.read_text()
        gate = next(line for line in source.splitlines() if line.startswith('#define ZX_HAVE_DEBUG_IFACES '))
        code = MODEL + '\n' + gate + '\n' + function(source, 'zx_rx_census') + CASES
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp) / 'census.c', Path(tmp) / 'census'
            src.write_text(code)
            for debug in (0, 1):
                with self.subTest(debug=debug):
                    run = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                          f'-DCONFIG_ZX279128_ETH_DEBUG={debug}', str(src), '-o', str(exe)],
                                         capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
