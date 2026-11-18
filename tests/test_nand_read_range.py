"""A recovery dump must not hide uncorrectable data behind a successful read."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "tools/nand-read-range.c"


class NandReadRangeTests(unittest.TestCase):
    def test_ecc_errors_lengths_and_mode(self):
        program = r'''
#define ioctl fake_ioctl
#define main range_main
#include "SOURCE_PATH"
#undef ioctl
#undef main
#include <assert.h>
#include <stdarg.h>
static int scenario;
int fake_ioctl(int fd, unsigned long request, ...) {
    va_list ap;
    va_start(ap,request);
    struct mtd_read_req *r=va_arg(ap,struct mtd_read_req *);
    va_end(ap);
    assert(fd==7 && request==MEMREAD);
    assert(r->start==0x2000000 && r->len==2048);
    assert(r->mode==MTD_OPS_PLACE_OOB && !r->ooblen && !r->usr_oob);
    memset((void *)(uintptr_t)r->usr_data,0x5a,r->len);
    if(scenario==1) {
        r->ecc_stats.corrected_bitflips=3;r->ecc_stats.max_bitflips=3;
        errno=EUCLEAN;return -1;
    }
    if(scenario==2) { errno=EBADMSG;return -1; }
    if(scenario==3) { r->ecc_stats.uncorrectable_errors=1;return 0; }
    if(scenario==4) { r->len=1024;return 0; }
    if(scenario==5) { errno=ETIMEDOUT;return -1; }
    if(scenario==6) { r->ecc_stats.uncorrectable_errors=1;errno=EUCLEAN;return -1; }
    return 0;
}
int main(void) {
    unsigned char buf[2048];struct totals stats={0};
    assert(read_corrected(7,0x2000000,buf,sizeof(buf),&stats)==0 && buf[0]==0x5a);
    scenario=1;
    assert(read_corrected(7,0x2000000,buf,sizeof(buf),&stats)==0);
    assert(stats.corrected==3 && stats.max_bitflips==3);
    for(scenario=2;scenario<=6;scenario++) {
        assert(read_corrected(7,0x2000000,buf,sizeof(buf),&stats)==-1);
        assert(stats.corrected==3 && stats.max_bitflips==3);
    }
    assert(ram_path("/tmp/kernel-ecc.bin"));
    assert(!ram_path("/tmp/../dev/mtd0") && !ram_path("/dev/mtd0"));
    return 0;
}
'''.replace("SOURCE_PATH", str(SOURCE))
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp) / "read.c", Path(tmp) / "read"
            src.write_text(program)
            compiled = subprocess.run(
                ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe)],
                capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            ran = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == "__main__":
    unittest.main()
