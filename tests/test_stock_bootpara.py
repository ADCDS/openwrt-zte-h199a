import importlib.util
from pathlib import Path
import struct
import unittest


spec = importlib.util.spec_from_file_location(
    "stock_bootpara", Path(__file__).resolve().parents[1] / "tools/stock-bootpara.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixtures():
    physical = bytearray(0x554)
    struct.pack_into("<4I", physical, 0, *module.MAGIC)
    struct.pack_into("<4I", physical, 0x30, 3, 2, 2, 0)
    struct.pack_into("<I", physical, 0xA0, sum(physical))
    runtime = physical[:]
    runtime[0x10:0x18] = b"V1.0.0\0\0"
    return bytes(physical), bytes(runtime)


class BootParaTests(unittest.TestCase):
    def test_preserves_metadata_and_updates_selection_and_sum(self):
        physical, runtime = fixtures()
        output = module.select_bank_b(physical, runtime)
        self.assertEqual(struct.unpack_from("<I", output, 0x3C)[0], 1)
        for i, (old, new) in enumerate(zip(runtime, output)):
            if not (0x3C <= i < 0x40 or 0xA0 <= i < 0xA4):
                self.assertEqual(old, new, f"changed byte {i:x}")
        check = bytearray(output)
        expected = struct.unpack_from("<I", check, 0xA0)[0]
        check[0xA0:0xA4] = bytes(4)
        self.assertEqual(sum(check), expected)

    def test_rejects_bad_physical_checksum(self):
        physical, runtime = fixtures()
        physical = bytearray(physical)
        physical[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            module.select_bank_b(bytes(physical), runtime)

    def test_rejects_unexplained_runtime_change(self):
        physical, runtime = fixtures()
        runtime = bytearray(runtime)
        runtime[0x200] = 1
        with self.assertRaisesRegex(ValueError, "known version field"):
            module.select_bank_b(physical, bytes(runtime))

    def test_parses_words_and_rejects_missing_line(self):
        physical, _ = fixtures()
        lines = []
        for off in range(0, len(physical), 16):
            words = [f"{struct.unpack_from('<I', physical, i)[0]:08x}"
                     for i in range(off, min(off + 16, len(physical)), 4)]
            lines.append(f"{0x40007000 + off:08x}: {' '.join(words)}    ....")
        self.assertEqual(module.parse_dump("\n".join(lines)), physical)
        with self.assertRaisesRegex(ValueError, "non-contiguous"):
            module.parse_dump("\n".join(lines[:1] + lines[2:]))


if __name__ == "__main__":
    unittest.main()
