#!/usr/bin/env python3
"""Ladder step 3 verification (host side, read-only): compare a post-install
full corrected NAND dump with the pre-install (step 2) dump.

  * every byte (data AND OOB) outside bank A [0x700000, 0x1740000) identical;
  * bank A DATA (de-interleaved) == kernel @0x700000, rootfs @0xa00000,
    header @0x1720000 exactly (the parts that were installed);
  * the dump tool's COMPLETE line reports read-errors=0 (every bank-A page has
    valid on-die parity, i.e. it reads back under the same ECC the bootloader
    and the production kernel use);
  * ECC events per region are reported.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

PAGE, OOB = 2048, 128
STRIDE = PAGE + OOB
TOTAL = 0x8000000 // PAGE * STRIDE
BANK_A = (0x700000, 0x1740000)
PARTS = (('kernel', 0x700000, 0x300000), ('rootfs', 0xa00000, 0xd20000), ('header', 0x1720000, 0x20000))
S = lambda x: x // PAGE * STRIDE


def data_of(dump, start, length):
    out = bytearray()
    for page in range(start // PAGE, (start + length) // PAGE):
        out += dump[page * STRIDE:page * STRIDE + PAGE]
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('post'); ap.add_argument('pre'); ap.add_argument('parts_dir')
    ap.add_argument('--ecc-log', required=True); ap.add_argument('--json', required=True)
    ap.add_argument('--allow-ubi-window', action='store_true',
                    help='the overlay was legitimately written (e.g. sysupgrade saved config): exclude '
                         'the UBI window [0x5400000,0x6400000) from the identity check')
    a = ap.parse_args()
    post, pre = Path(a.post).read_bytes(), Path(a.pre).read_bytes()
    h = lambda b: hashlib.sha256(b).hexdigest()
    res = {'lengths_ok': len(post) == len(pre) == TOTAL}
    if not res['lengths_ok']:
        sys.exit('length mismatch')
    outside = ([(0, BANK_A[0]), (BANK_A[1], 0x5400000), (0x6400000, 0x8000000)] if a.allow_ubi_window
               else [(0, BANK_A[0]), (BANK_A[1], 0x8000000)])
    res['identity_regions'] = [[hex(s), hex(e)] for s, e in outside]
    res['ubi_window_changed'] = post[S(0x5400000):S(0x6400000)] != pre[S(0x5400000):S(0x6400000)]
    res['outside_bank_a_identical'] = all(post[S(s):S(e)] == pre[S(s):S(e)] for s, e in outside)
    if not res['outside_bank_a_identical']:
        diffs = []
        for s, e in outside:
            for page in range(s // PAGE, e // PAGE):
                if post[page * STRIDE:(page + 1) * STRIDE] != pre[page * STRIDE:(page + 1) * STRIDE]:
                    diffs.append(hex(page * PAGE))
                    if len(diffs) >= 32:
                        break
        res['outside_diff_pages_first32'] = diffs
    res['parts'] = {}
    for name, off, n in PARTS:
        want = (Path(a.parts_dir) / name).read_bytes()
        got = data_of(post, off, n)
        res['parts'][name] = {'offset': hex(off), 'bytes': n, 'want_sha256': h(want),
                              'nand_sha256': h(got), 'equal': got == want}
    res['bank_a_prior_sha256'] = h(pre[S(BANK_A[0]):S(BANK_A[1])])
    res['bank_a_post_sha256'] = h(post[S(BANK_A[0]):S(BANK_A[1])])
    log = Path(a.ecc_log).read_text(errors='replace')
    done = re.findall(r'COMPLETE bytes=(\d+) pages=(\d+) read-errors=(\d+) corrected-bound=(\d+) max-bitflips=(\d+)', log)
    res['complete'] = done[-1] if done else None
    res['read_errors_zero'] = bool(done) and done[-1][2] == '0'
    ev = [int(x, 16) for x in re.findall(r'ECC_CORRECTED offset=0x([0-9a-f]+)', log)]
    res['ecc_events_bank_a'] = sorted(hex(o) for o in ev if BANK_A[0] <= o < BANK_A[1])
    res['ecc_events_total'] = len(ev)
    res['full_sha256'] = h(post)
    res['pass'] = (res['outside_bank_a_identical'] and res['read_errors_zero'] and
                   all(p['equal'] for p in res['parts'].values()))
    Path(a.json).write_text(json.dumps(res, indent=2) + '\n')
    print(json.dumps(res, indent=2))
    sys.exit(0 if res['pass'] else 1)


if __name__ == '__main__':
    main()
