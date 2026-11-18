"""Exercise the actual TM startup command sequence and timeout handling."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_eth_rx import DRIVER

STUBS = r"""
#include <assert.h>
#include <stdint.h>
#include <errno.h>
typedef uint32_t u32;
struct zx_eth { void *dev; void *tmc; };
static unsigned char regs[0x200];
static unsigned writes, polls, waited, fail_poll, errors;
#define dev_err(dev, ...) ((void)(dev), errors++)
static void writel(u32 value, void *addr) {
    assert(!waited && !polls);
    assert((unsigned char *)addr == regs + (writes ? 0x130 : 0x128));
    assert(value == (writes ? 0x1fffffu : 0x1fffu));
    assert(writes < 2);
    writes++;
}
static void usleep_range(unsigned min, unsigned max) {
    assert(writes == 2 && !waited && !polls);
    assert(min == 1000 && max >= min);
    waited = 1;
}
static u32 poll_value(void *addr, unsigned delay, unsigned timeout) {
    assert(writes == 2 && waited && polls < 2);
    assert((unsigned char *)addr == regs + (polls ? 0x130 : 0x128));
    assert(delay && timeout >= 10000 && timeout <= 100000);
    polls++;
    return polls == fail_poll ? 1u : 0x80000000u;
}
#define readl_poll_timeout(addr, value, condition, delay, timeout) \
    ((value) = poll_value(addr, delay, timeout), (condition) ? 0 : -ETIMEDOUT)
"""

CASES = r"""
int main(void) {
    struct zx_eth ze = { .tmc = regs };
    for (unsigned fail = 0; fail <= 2; fail++) {
        writes = polls = waited = errors = 0;
        fail_poll = fail;
        assert(zx_tm_queue_state_init(&ze) == (fail ? -ETIMEDOUT : 0));
        assert(writes == 2 && waited);
        assert(polls == (fail == 1 ? 1u : 2u));
        assert(errors == (fail ? 1u : 0u));
    }
    return 0;
}
"""


class TmInitTests(unittest.TestCase):
    def test_command_order_and_timeouts(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        source = DRIVER.read_text()
        start = source.index("static int zx_tm_queue_state_init(")
        end = source.index("static int zx_pp_seed_vlans(", start)
        with tempfile.TemporaryDirectory() as directory:
            cfile, binary = Path(directory) / "tm.c", Path(directory) / "tm"
            cfile.write_text(STUBS + source[start:end] + CASES)
            result = subprocess.run([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                                     str(cfile), "-o", str(binary)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, timeout=10)
