"""Every patch's hunk headers must match its body.

GNU patch tolerates a hunk whose declared line counts are wrong, because it
searches for the context anyway. That tolerance is a trap: the counts can drift
for a long time and then a small edit - adding one line to a hunk - turns a
tolerated mistake into a patch that fails to apply, several minutes into a
kernel build with no message that names the patch.

Three of this port's patches had counts off by one before this test existed.
They applied anyway, which is exactly why nothing noticed.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / 'files/target/linux/armsr/patches-6.6'

HUNK = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')


def hunks(text):
    """Yield (header_line_no, declared_old, declared_new, old, new) per hunk."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = HUNK.match(lines[i])
        if not m:
            i += 1
            continue
        start = i
        i += 1
        body = []
        while i < len(lines) and not HUNK.match(lines[i]) and not lines[i].startswith('--- '):
            if lines[i].startswith('diff ') or lines[i].startswith('index '):
                break
            body.append(lines[i])
            i += 1
        old = sum(1 for line in body if line[:1] in (' ', '-'))
        new = sum(1 for line in body if line[:1] in (' ', '+'))
        # a header may omit the count when it is exactly 1
        yield (start + 1, int(m.group(2) if m.group(2) is not None else 1),
               int(m.group(4) if m.group(4) is not None else 1), old, new)


class PatchHunkCountTests(unittest.TestCase):
    def test_every_hunk_declares_the_lines_it_carries(self):
        patches = sorted(PATCHES.glob('*.patch'))
        self.assertTrue(patches, 'no patches found')
        for patch in patches:
            with self.subTest(patch=patch.name):
                for line_no, d_old, d_new, old, new in hunks(patch.read_text()):
                    self.assertEqual(
                        (d_old, d_new), (old, new),
                        f'{patch.name}:{line_no}: header declares -{d_old}/+{d_new} '
                        f'but the body carries -{old}/+{new}')

    def test_the_check_itself_rejects_a_wrong_count(self):
        """A test that cannot fail is worse than no test."""
        bad = '@@ -1,5 +1,5 @@\n a\n b\n'
        counts = list(hunks(bad))
        self.assertEqual(counts[0][1:3], (5, 5))
        self.assertEqual(counts[0][3:5], (2, 2))


if __name__ == '__main__':
    unittest.main()
