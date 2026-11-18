"""Exercise the actual restart callback and resource/registration error paths."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import function

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'files/target/linux/armsr/files-6.6/drivers/power/reset/zx279128-reboot.c'

MODEL = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#define __iomem
#define NOTIFY_DONE 0
#define SYS_OFF_MODE_RESTART 3
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
struct device { unsigned value; };
struct platform_device { struct device dev; };
struct sys_off_data { void *cb_data; };
static uint32_t reset;
static unsigned maps,registrations,writes,delays;
static int map_error,registration_error;
static struct platform_device device;
static int (*callback)(struct sys_off_data *);
static void *callback_data;
static void *devm_platform_ioremap_resource(struct platform_device *p,unsigned index) {
 assert(p==&device && index==0);maps++;
 return map_error?(void *)(intptr_t)map_error:&reset;
}
static int devm_register_sys_off_handler(struct device *d,unsigned mode,int priority,
                                       int (*cb)(struct sys_off_data *),void *data) {
 assert(d==&device.dev && mode==SYS_OFF_MODE_RESTART && priority==128 && data==&reset);
 assert(maps==1 && !writes && !delays);registrations++;
 if(registration_error)return registration_error;
 callback=cb;callback_data=data;return 0;
}
static void writel(uint32_t value,void *address) {
 assert(address==&reset && value==1 && !writes && !delays);reset=value;writes++;
}
static void mdelay(unsigned ms) { assert(writes==1 && !delays && ms==1000);delays++; }
'''

CASES = r'''
int main(void) {
 map_error=-EBUSY;
 assert(zx279128_reboot_probe(&device)==-EBUSY && maps==1 && !registrations && !writes);
 maps=0;map_error=0;registration_error=-ENOMEM;
 assert(zx279128_reboot_probe(&device)==-ENOMEM && registrations==1 && !writes);
 maps=registrations=0;registration_error=0;
 assert(zx279128_reboot_probe(&device)==0 && registrations==1 && callback && !writes);
 struct sys_off_data data={.cb_data=callback_data};
 reset=1; /* Even if an idle read would return 1, issue the trigger write. */
 assert(callback(&data)==NOTIFY_DONE && writes==1 && delays==1 && reset==1);
 return 0;
}
'''


class RebootTests(unittest.TestCase):
    def test_unconditional_trigger_and_probe_errors(self):
        source = SOURCE.read_text()
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp) / 'reboot.c', Path(tmp) / 'reboot'
            src.write_text(MODEL + function(source, 'zx279128_restart') +
                           function(source, 'zx279128_reboot_probe') + CASES)
            run = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                  str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
