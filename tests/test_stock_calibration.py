"""Portable corruption gates for stock calibration recovery; no private dumps."""
import gzip
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

SOURCE = Path(__file__).resolve().parents[1] / "tools/extract-stock-calibration.py"
spec = importlib.util.spec_from_file_location("stock_calibration", SOURCE)
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)


def wrapped(raw):
    payload = bytes(cal.GZIP_OFFSET - 96) + gzip.compress(raw, mtime=0)
    header = bytearray(struct.pack(">7I4B32s", 0x27051956, 0, 0, len(payload),
        0x40008000, 0x40008000, zlib.crc32(payload), 5, 2, 2, 0, b"test"))
    struct.pack_into(">I", header, 4, zlib.crc32(header))
    return (bytes(32) + header + payload).ljust(3 * 1024 * 1024, b"\0")


def dirent(parent, name, inode, dtype=4):
    name = name.encode()
    head = struct.pack("<HHI", 0x1985, 0xe001, 40 + len(name))
    node = head + struct.pack("<I", cal.crc(head))
    node += struct.pack("<IIIIBBH", parent, 1, inode, 0, len(name), dtype, 0)
    return node + struct.pack("<II", cal.crc(node), cal.crc(name)) + name


def inode(ino, version, size, offset, data, compressed=False, declared=None):
    packed = zlib.compress(data) if compressed else data
    head = struct.pack("<HHI", 0x1985, 0xe002, 68 + len(packed))
    node = bytearray(head + struct.pack("<I", cal.crc(head)) + bytes(56))
    struct.pack_into("<III", node, 12, ino, version, 0o100644)
    struct.pack_into("<I", node, 28, size)
    struct.pack_into("<III", node, 44, offset, len(packed),
                     len(data) if declared is None else declared)
    node[56] = 6 if compressed else 0
    struct.pack_into("<I", node, 60, cal.crc(packed))
    struct.pack_into("<I", node, 64, cal.crc(node[:60]))
    return node + packed


def filesystem(problem=None):
    nodes = [dirent(*args) for args in (
        (1, "etc", 2), (2, "Wireless", 3), (3, "MT7603e", 4),
        (3, "MT7613E", 5), (1, "lib", 6), (6, "modules", 7),
        (4, "MT7603E_EEPROM.bin", 8, 8), (5, "MT7613E_EEPROM.bin", 9, 8),
        (7, "mt7603eap.ko", 10, 8))]
    expected = {"MT7603E_EEPROM.bin": bytes(range(256)) * 2,
                "MT7613E_EEPROM.bin": b"five-ghz-fixture" * 30,
                "mt7603eap.ko": b"synthetic-driver" + bytes(range(256)) * 6}
    for index, name in ((8, "MT7603E_EEPROM.bin"), (9, "MT7613E_EEPROM.bin")):
        data = expected[name]
        nodes.append(inode(index, 1, len(data), 0, data))
    data = expected["mt7603eap.ko"]
    nodes.append(inode(10, 1, len(data), 0, data[:200]))
    nodes.append(inode(10, 2, len(data), 201 if problem == "gap" else 200,
                       data[200:], compressed=True,
                       declared=10 if problem == "expansion" else None))
    if problem == "data_crc":
        nodes[-1][60] ^= 1
    if problem == "name_crc":
        nodes[0] = bytearray(nodes[0])
        nodes[0][36] ^= 1
    return b"".join(bytes(n).ljust((len(n) + 3) & ~3, b"\xff") for n in nodes), expected


class StockCalibrationTests(unittest.TestCase):
    def test_reconstructs_all_targets_including_compressed_split_file(self):
        image, expected = filesystem()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            result = cal.extract(image, out)
            self.assertEqual(len(result["files"]), 3)
            for name, data in expected.items():
                self.assertEqual((out / name).read_bytes(), data)
                self.assertEqual((out / name).stat().st_mode & 0o777, 0o600)
            self.assertEqual(out.stat().st_mode & 0o777, 0o700)

    def test_name_and_data_crcs_rejected_without_partial_output(self):
        for problem in ("name_crc", "data_crc"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "output"
                with self.assertRaisesRegex(ValueError, "CRC mismatch"):
                    cal.extract(filesystem(problem)[0], out)
                self.assertFalse(out.exists())

    def test_coverage_gap_leaves_no_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            with self.assertRaisesRegex(ValueError, "incomplete file coverage"):
                cal.extract(filesystem("gap")[0], out)
            self.assertFalse(out.exists())

    def test_fragment_expansion_leaves_no_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            with self.assertRaisesRegex(ValueError, "oversized compressed fragment"):
                cal.extract(filesystem("expansion")[0], out)
            self.assertFalse(out.exists())

    def test_raw_and_wrapped_inputs_need_the_supported_digest(self):
        raw = b"synthetic kernel for portable CRC testing"
        with patch.object(cal, "RAW_SIZE", len(raw)), patch.object(
                cal, "KERNEL_SHA", hashlib.sha256(raw).hexdigest()):
            self.assertEqual(cal.load_kernel(raw), raw)
            self.assertEqual(cal.load_kernel(wrapped(raw)), raw)
            with self.assertRaisesRegex(ValueError, "unsupported kernel"):
                cal.load_kernel(raw[:-1] + b"X")

    def test_wrapper_crc_failures_are_not_bypassed(self):
        raw = b"synthetic kernel"
        data = bytearray(wrapped(raw))
        data[40] ^= 1
        with self.assertRaisesRegex(ValueError, "header CRC"):
            cal.load_kernel(data)
        data = bytearray(wrapped(raw))
        data[cal.GZIP_OFFSET + 15] ^= 1
        with self.assertRaisesRegex(ValueError, "payload CRC"):
            cal.load_kernel(data)

    def test_gzip_expansion_is_bounded(self):
        with patch.object(cal, "RAW_SIZE", 32):
            with self.assertRaisesRegex(ValueError, "oversized kernel gzip"):
                cal.load_kernel(wrapped(b"A" * 65536))

    def test_bad_jffs2_header_rejected_before_output_creation(self):
        image = struct.pack("<HHII", 0x1985, 0xe001, 40, 0) + bytes(28)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            with self.assertRaisesRegex(ValueError, "header CRC"):
                cal.extract(image, out)
            self.assertFalse(out.exists())

    def test_short_jffs2_node_rejected_before_output_creation(self):
        head = struct.pack("<HHI", 0x1985, 0xe002, 12)
        image = head + struct.pack("<I", cal.crc(head))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            with self.assertRaisesRegex(ValueError, "short inode"):
                cal.extract(image, out)
            self.assertFalse(out.exists())

    def test_existing_output_is_never_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            out.mkdir()
            sentinel = out / "keep"
            sentinel.write_bytes(b"existing evidence")
            with patch("sys.argv", [str(SOURCE), "missing-kernel", "missing-rootfs", str(out)]):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    cal.main()
            self.assertEqual(sentinel.read_bytes(), b"existing evidence")


if __name__ == "__main__":
    unittest.main()
