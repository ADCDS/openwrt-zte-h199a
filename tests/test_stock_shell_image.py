import contextlib
import gzip
import importlib.util
import io
from pathlib import Path
import struct
import unittest
import zlib


spec = importlib.util.spec_from_file_location(
    "stock_shell_image", Path(__file__).resolve().parents[1] / "tools/stock-shell-image.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(image):
    packed = gzip.compress(image, mtime=0)
    packed = packed[:3] + b"\x10" + packed[4:10] + b"padding" * 100 + b"\0" + packed[10:]
    payload = b"zImage-prefix" * 16 + packed + b"appended-DTB-sentinel"
    header = bytearray(struct.pack(
        ">7I4B32s", 0x27051956, 0, 0, len(payload), 0x40008000,
        0x40008000, zlib.crc32(payload), 5, 2, 2, 0, b"original"
    ))
    struct.pack_into(">I", header, 4, zlib.crc32(header))
    return b"P" * 32 + header + payload + b"\xff" * 128


class StockShellImageTests(unittest.TestCase):
    def prepare(self, source):
        with contextlib.redirect_stdout(io.StringIO()):
            return module.prepare(source)

    def test_changes_only_init_and_keeps_linked_offsets(self):
        image = bytes(range(256)) * 32 + b"/sbin/init\0/etc/init\0/bin/init\0/bin/sh\0"
        source = fixture(image)
        output = self.prepare(source)
        expected = image.replace(b"/sbin/init\0", b"/bin/sh\0\0\0\0")
        expected = expected.replace(b"/etc/init\0", b"/bin/sh\0\0\0")
        expected = expected.replace(b"/bin/init\0", b"/bin/sh\0\0\0")
        self.assertEqual(len(output), len(source))
        start = source.index(b"\x1f\x8b\x08")
        end = source.index(b"appended-DTB-sentinel")
        self.assertEqual(output[:32], source[:32])
        self.assertEqual(output[96:start], source[96:start])
        self.assertEqual(output[end:], source[end:])
        flags = output[start + 3]
        self.assertEqual(flags & ~0x08, 0)
        deflate = start + 10
        if flags & 0x08:
            deflate = output.index(b"\0", deflate) + 1
        self.assertEqual(
            zlib.decompress(output[deflate:end - 8], -15),
            gzip.decompress(output[start:end]),
        )
        self.assertEqual(
            gzip.decompress(output[start:end]),
            expected,
        )
        header = bytearray(output[32:96])
        expected_crc = struct.unpack_from(">I", header, 4)[0]
        header[4:8] = bytes(4)
        self.assertEqual(zlib.crc32(header), expected_crc)
        size = struct.unpack_from(">I", header, 12)[0]
        self.assertEqual(zlib.crc32(output[96:96 + size]), struct.unpack_from(">I", header, 24)[0])

    def test_refuses_bad_input_crc(self):
        source = bytearray(fixture(b"/sbin/init\0"))
        source[100] ^= 1
        with self.assertRaisesRegex(ValueError, "data checksum"):
            self.prepare(bytes(source))

    def test_refuses_ambiguous_init_path(self):
        with self.assertRaisesRegex(ValueError, "one gzip kernel"):
            self.prepare(fixture(b"/sbin/init\0/sbin/init\0"))


if __name__ == "__main__":
    unittest.main()
