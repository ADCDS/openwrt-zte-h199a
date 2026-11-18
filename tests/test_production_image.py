"""Factory image generation: header byte-exactness, CRC fields, size limits.

Two layers are checked:
  * flash-prep.py's pure header math, proven byte-exact against this unit's own
    header-template.bin (the design doc's verification) and against the CRC
    fields it must rewrite;
  * verify-production-image.py, the build-time factory-image validator, over a
    synthesised sysupgrade tar and every way it should be rejected.
No hardware and no NAND contents are read.
"""
import importlib.util
import io
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT.parent
TEMPLATE = BENCH / 'h199a-firmware' / 'header-template.bin'


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fp = load('flash_prep', 'flash-prep.py')
vpi = load('verify_production_image', 'verify-production-image.py')

# Bank A's own kernel/fs CRCs, from the design doc's header decode. Patching the
# device template with these must reproduce the device header byte-for-byte.
BANK_A_KERNEL_CRC = 0xdc16de6e
BANK_A_FS_CRC = 0x3d20317e


def fake_template():
    """A self-consistent 128 KiB header when the real one is unavailable.

    It carries a distinct identity region so a validator that silently accepts
    a template mismatch would be caught.
    """
    hdr = bytearray(b'\x00' * fp.HEADER_BLK)
    struct.pack_into('<I', hdr, 0x08, 0x266)       # upgrade key1
    struct.pack_into('<I', hdr, 0x0c, 7)           # upgrade key2
    hdr[0x10:0x1e] = b'V9.9.9_TESTUNIT'[:0x0e]
    struct.pack_into('<I', hdr, 0x34, fp.CRC_LEN)  # kernel length
    struct.pack_into('<I', hdr, 0x40, fp.FS_LEN)   # fs_size (load-bearing)
    struct.pack_into('<I', hdr, 0x44, 0x300214)    # fs offset
    hdr[0xf4:0x104] = bytes.fromhex('33333333666666669999999 9cccccccc'.replace(' ', ''))
    struct.pack_into('<I', hdr, 0x1f0, 0x700000)   # bank start
    struct.pack_into('<I', hdr, 0x1f4, 5)          # version serial
    struct.pack_into('<I', hdr, 0x1fc, zlib.crc32(bytes(hdr[:0x1fc])) & 0xffffffff)
    return bytes(hdr)


def uimage(payload=b'kernel-body', load=0x40008000, entry=0x40008000):
    # Minimal 64-byte uImage header: magic, then load/entry at offsets 16/20,
    # which land at container offsets 48/52 after the 32-byte ZTE magic.
    hdr = bytearray(64)
    hdr[0:4] = bytes.fromhex('27051956')
    struct.pack_into('>II', hdr, 16, load, entry)
    return bytes(hdr) + payload


def kernel_container(payload=b'kernel-body'):
    return fp.build_kernel_container(uimage(payload))


def squashfs(size=4096):
    body = b'hsqs' + bytes(size - 4)
    return body


def make_tar(kernel, rootfs, header, prefix='h199a'):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w') as tf:
        for name, data in (('kernel', kernel), ('rootfs', rootfs), ('header', header)):
            ti = tarfile.TarInfo(f'{prefix}/{name}')
            ti.size = len(data)
            ti.mode = 0o644
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def build_parts(template, kraw=b'kernel-body', fsraw=None):
    fsraw = squashfs() if fsraw is None else fsraw
    kernel = kernel_container(kraw)
    fs = fp.fs_image(fsraw)
    header = fp.patch_header(fp.header_template(template), fp.kernel_crc(kernel), fp.fs_crc(fs))
    return kernel, fs, header


class HeaderMathTests(unittest.TestCase):
    def test_patch_header_only_touches_the_three_crc_fields(self):
        tpl = fake_template()
        out = fp.patch_header(tpl, 0x11223344, 0x55667788)
        changed = [i for i in range(len(tpl)) if tpl[i] != out[i]]
        self.assertEqual(set(changed),
                         set(range(0x3c, 0x40)) | set(range(0x48, 0x4c)) | set(range(0xa4, 0xa8)))
        self.assertEqual(struct.unpack_from('<I', out, 0x3c)[0], 0x11223344)
        self.assertEqual(struct.unpack_from('<I', out, 0x48)[0], 0x55667788)
        self.assertEqual(struct.unpack_from('<I', out, 0xa4)[0],
                         zlib.crc32(out[:0xa4]) & 0xffffffff)

    def test_self_crc_depends_on_the_kernel_and_fs_crc_fields(self):
        tpl = fake_template()
        a = fp.patch_header(tpl, 1, 2)
        b = fp.patch_header(tpl, 1, 3)
        self.assertNotEqual(a[0xa4:0xa8], b[0xa4:0xa8])

    @unittest.skipUnless(TEMPLATE.is_file(), 'device header-template.bin not present')
    def test_regenerates_this_units_header_byte_exact(self):
        template = TEMPLATE.read_bytes()
        out = fp.patch_header(fp.header_template(template),
                              BANK_A_KERNEL_CRC, BANK_A_FS_CRC)
        self.assertEqual(out, template,
                         'patching the template with the stock bank-A CRCs must '
                         'reproduce the device header byte-for-byte')

    def test_fs_image_pads_and_refuses_oversize(self):
        self.assertEqual(len(fp.fs_image(b'hsqs')), fp.FS_LEN)
        with self.assertRaises(SystemExit):
            fp.fs_image(b'x' * (fp.FS_LEN + 1))

    def test_kernel_container_is_fixed_size_and_refuses_oversize(self):
        self.assertEqual(len(kernel_container()), fp.KERNEL_LEN)
        with self.assertRaises(SystemExit):
            fp.build_kernel_container(bytes.fromhex('27051956') + b'x' * fp.KERNEL_LEN)


class ProductionImageValidatorTests(unittest.TestCase):
    def setUp(self):
        self.tpl = fake_template()
        self.kernel, self.fs, self.header = build_parts(self.tpl)

    def check(self, tar_bytes, template=None):
        with tempfile.NamedTemporaryFile(suffix='.tar') as f:
            f.write(tar_bytes)
            f.flush()
            return vpi.verify(f.name, self.tpl if template is None else template)

    def test_valid_image_passes_and_reports_crcs(self):
        report = self.check(make_tar(self.kernel, self.fs, self.header))
        self.assertEqual(report['kernel_bytes'], fp.KERNEL_LEN)
        self.assertEqual(report['rootfs_bytes'], fp.FS_LEN)
        self.assertEqual(report['fs_size'], f'{fp.FS_LEN:08x}')
        self.assertEqual(report['identity_bytes_changed'], 12)

    def test_extract_writes_three_parts(self):
        with tempfile.TemporaryDirectory() as d, tempfile.NamedTemporaryFile(suffix='.tar') as f:
            f.write(make_tar(self.kernel, self.fs, self.header))
            f.flush()
            vpi.verify(f.name, self.tpl, extract_dir=d)
            for name, data in (('kernel', self.kernel), ('rootfs', self.fs), ('header', self.header)):
                self.assertEqual((Path(d) / name).read_bytes(), data)

    def test_rejects_wrong_kernel_crc(self):
        bad = bytearray(self.header)
        struct.pack_into('<I', bad, 0x3c, 0xdeadbeef)
        struct.pack_into('<I', bad, 0xa4, zlib.crc32(bytes(bad[:0xa4])) & 0xffffffff)
        with self.assertRaisesRegex(ValueError, 'kernel CRC'):
            self.check(make_tar(self.kernel, self.fs, bytes(bad)))

    def test_rejects_wrong_fs_crc(self):
        bad = bytearray(self.header)
        struct.pack_into('<I', bad, 0x48, 0xdeadbeef)
        struct.pack_into('<I', bad, 0xa4, zlib.crc32(bytes(bad[:0xa4])) & 0xffffffff)
        with self.assertRaisesRegex(ValueError, 'fs CRC'):
            self.check(make_tar(self.kernel, self.fs, bytes(bad)))

    def test_rejects_bad_self_crc(self):
        bad = bytearray(self.header)
        struct.pack_into('<I', bad, 0xa4, 0x00000000)
        with self.assertRaisesRegex(ValueError, 'self-CRC'):
            self.check(make_tar(self.kernel, self.fs, bytes(bad)))

    def test_rejects_identity_tampering(self):
        # A header whose CRCs are internally consistent but whose identity
        # bytes differ from the template must be refused.
        tampered = bytearray(self.tpl)
        tampered[0x10] ^= 0xff
        kernel, fs, header = build_parts(bytes(tampered))
        with self.assertRaisesRegex(ValueError, 'template|identity'):
            self.check(make_tar(kernel, fs, header))

    def test_rejects_shrunk_fs_size_field(self):
        bad = bytearray(self.header)
        struct.pack_into('<I', bad, 0x40, fp.FS_LEN - 0x20000)
        struct.pack_into('<I', bad, 0xa4, zlib.crc32(bytes(bad[:0xa4])) & 0xffffffff)
        with self.assertRaises(ValueError):
            self.check(make_tar(self.kernel, self.fs, bytes(bad)))

    def test_rejects_unpadded_rootfs(self):
        with self.assertRaisesRegex(ValueError, 'rootfs'):
            self.check(make_tar(self.kernel, squashfs(), self.header))

    def test_rejects_oversize_kernel_container(self):
        with self.assertRaisesRegex(ValueError, 'kernel'):
            self.check(make_tar(self.kernel + b'\x00', self.fs, self.header))

    def test_rejects_wrong_board_dir_and_extra_members(self):
        with self.assertRaises(ValueError):
            self.check(make_tar(self.kernel, self.fs, self.header, prefix='other'))

    def test_rejects_missing_member(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w') as tf:
            for name, data in (('kernel', self.kernel), ('rootfs', self.fs)):
                ti = tarfile.TarInfo(f'h199a/{name}')
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))
        with self.assertRaisesRegex(ValueError, 'header'):
            self.check(buf.getvalue())

    def test_rejects_wrong_uimage_load_address(self):
        kernel = fp.build_kernel_container(uimage(load=0x40000000, entry=0x40000000))
        header = fp.patch_header(fp.header_template(self.tpl), fp.kernel_crc(kernel), fp.fs_crc(self.fs))
        with self.assertRaisesRegex(ValueError, 'load/entry'):
            self.check(make_tar(kernel, self.fs, header))


if __name__ == '__main__':
    unittest.main()
