"""Apply the recipe patch to its exact public, pinned mt76 source archive."""
from functools import lru_cache
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import function

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/'openwrt/dl/mt76-2025.11.06~eb567bc7.tar.zst'
PATCH = ROOT/'files/package/kernel/mt76/patches/990-dma-invalid-index-fail-stop.patch'


def c_function(source, name):
    body = function(source, name)
    if re.match(re.escape(name) + r'\s*\(', body):
        offset = source.index(body)
        declaration = source[:offset].rstrip('\n').splitlines()[-1]
        assert re.match(r'(static\b|void\b|int\b|bool\b|u[0-9]+\b)', declaration)
        assert not any(c in declaration for c in ';{}')
        body = declaration + '\n' + body
    return body


@lru_cache(maxsize=1)
def sources():
    if not ARCHIVE.is_file():
        raise unittest.SkipTest('requires the pinned public mt76 archive downloaded by the OpenWrt build')
    names = re.findall(r'^--- a/(.+)$', PATCH.read_text(), re.M)
    assert len(names) == len(set(names)) and all('..' not in PurePosixPath(n).parts for n in names)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for name in names:
            data = subprocess.check_output(['tar','--zstd','-xOf',str(ARCHIVE),
                                            'mt76-2025.11.06~eb567bc7/'+name])
            path = folder/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        subprocess.run(['patch','-p1','--batch','--input',str(PATCH)],cwd=folder,
                       capture_output=True,check=True)
        return {name: (folder/name).read_text() for name in names}
