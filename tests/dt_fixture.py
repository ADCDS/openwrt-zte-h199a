"""Shared helpers for the device-tree resource tests.

* Compile the H199A DTS exactly as test_production_dts.py does (cpp + dtc),
  preferring the kernel tree's own scripts/dtc/dtc, and read properties back
  with fdtget.
* Build the C prelude that gives host models the Ethernet driver's actual
  register-block enum and fallback table.
* Cross-compile one driver source against the pinned, already-prepared
  linux-6.6.151 tree with the compile command kbuild recorded for it. Nothing
  is written into the shared tree: the object goes to a temporary directory.
"""
from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess

from test_tx_origin_r204 import exact_define, exact_enum

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / 'files/target/linux/armsr/files-6.6'
DTS_DIR = FILES / 'arch/arm/boot/dts/zte'
INCLUDE_DIR = FILES / 'include'
ETH_SOURCE = FILES / 'drivers/net/ethernet/zte/zx279128-eth.c'
PCIE_SOURCE = FILES / 'drivers/pci/controller/dwc/pcie-zx279128.c'
GPIO_SOURCE = FILES / 'drivers/gpio/gpio-zx279128.c'
KTREES = sorted((ROOT / 'openwrt/build_dir').glob('target-*/linux-armsr_armv7/linux-6.6.151'))
TOOLCHAINS = sorted((ROOT / 'openwrt/staging_dir').glob('toolchain-arm_cortex-a9_gcc-*_musl_eabi'))
BASE_DTS = 'zx279128s-zte-h199a'
DTS_NAMES = (BASE_DTS, BASE_DTS + '-production', BASE_DTS + '-production-qualify')


def kernel_tree():
    return KTREES[0].resolve() if len(KTREES) == 1 else None


def dtc_binary():
    tree = kernel_tree()
    if tree and (tree / 'scripts/dtc/dtc').is_file():
        return str(tree / 'scripts/dtc/dtc')
    return shutil.which('dtc')


def dts_tools_available():
    return bool(kernel_tree() and dtc_binary() and shutil.which('fdtget') and shutil.which('cpp'))


def compile_dts(name, out):
    """Build DTS `name` into directory `out`; return (DTB path, dtc stderr)."""
    tree = kernel_tree()
    pre, dtb = Path(out) / (name + '.pre'), Path(out) / (name + '.dtb')
    cpp = subprocess.run([
        'cpp', '-nostdinc', '-x', 'assembler-with-cpp',
        '-I', str(DTS_DIR), '-I', str(INCLUDE_DIR), '-I', str(tree / 'include'),
        '-I', str(tree / 'scripts/dtc/include-prefixes'),
        '-undef', '-D__DTS__', '-o', str(pre), str(DTS_DIR / (name + '.dts'))],
        capture_output=True, text=True)
    if cpp.returncode:
        raise AssertionError(cpp.stderr)
    dtc = subprocess.run([dtc_binary(), '-I', 'dts', '-O', 'dtb', '-i', str(DTS_DIR),
                          '-o', str(dtb), str(pre)], capture_output=True, text=True)
    if dtc.returncode:
        raise AssertionError(dtc.stderr)
    return dtb, dtc.stderr


def fdtget(dtb, node, prop, kind='x'):
    """Property as a list: integers for kind 'x'/'u', strings for kind 's'.

    None if the property is absent.
    """
    run = subprocess.run(['fdtget', '-t', kind, str(dtb), node, prop],
                         capture_output=True, text=True)
    if run.returncode:
        return None
    words = run.stdout.split()
    if kind == 's':
        return words
    return [int(w, 16 if kind == 'x' else 10) for w in words]


def reg_pairs(dtb, node):
    """reg of a node under a 1/1-cell bus, as [(base, size), ...]."""
    cells = fdtget(dtb, node, 'reg')
    if len(cells) % 2:
        raise AssertionError(f'{node}: odd reg cell count')
    return list(zip(cells[0::2], cells[1::2]))


def exact_table(text, name):
    found = list(re.finditer(r'^static const struct ' + re.escape(name) + r' \{.*?^\};',
                             text, re.M | re.S))
    if len(found) != 1:
        raise AssertionError(f'Missing unique actual table {name}')
    return found[0].group()


ETH_TABLE_DEFINES = ('BM_BASE', 'TMD_BASE', 'TMC_BASE', 'TMQ_BASE', 'ZX_MAC_BASE',
                     'ZX_MAC_STRIDE', 'ZX_NPP_SPA', 'ZX_NPP_ATTACH')


def eth_reg_prelude(text):
    """The driver's enum zx_eth_reg and zx_eth_reg_desc, verbatim, for a host model.

    Adds zx_test_fallback_phys(), which fills a phys[] array from the table's
    fallbacks, i.e. what the driver resolves with a device tree that names no
    register block.
    """
    return '\n'.join([
        '#include <stdint.h>',
        '#ifndef SZ_4K', '#define SZ_4K 4096', '#endif',
        '#ifndef SZ_128K', '#define SZ_128K 131072', '#endif',
        'typedef uint32_t phys_addr_t;', 'typedef uint32_t resource_size_t;',
        *(exact_define(text, name) for name in ETH_TABLE_DEFINES),
        exact_enum(text, 'zx_eth_reg'),
        exact_table(text, 'zx_eth_reg_desc'),
        'static void zx_test_fallback_phys(phys_addr_t *phys)',
        '{ for (int i = 0; i < ZX_NREGS; i++) phys[i] = zx_eth_reg_desc[i].fallback; }',
        '',
    ])


def cross_tools():
    tree = kernel_tree()
    if not tree or len(TOOLCHAINS) != 1:
        return None
    return tree, TOOLCHAINS[0].resolve()


def recorded_command(tree, record):
    """The kbuild command for one object, with relative paths made absolute."""
    path = tree / record
    if not path.exists():
        return None
    directory, name = record.rsplit('/', 1)  # drivers/.../.foo.o.cmd
    target = directory + '/' + name[1:-len('.cmd')]
    line = next(l for l in path.read_text().splitlines()
                if l.startswith(f'savedcmd_{target} := '))
    command = line.split(' := ', 1)[1].split(' -c -o ', 1)[0]
    command = re.sub(r'-Wp,-MMD,\S+ ', '', command)
    command = re.sub(r'(^|\s)(-I|-include\s+)?\./',
                     lambda m: m.group(1) + (m.group(2) or '') + str(tree) + '/', command)
    return shlex.split(command)


def release_autoconf(tree, out):
    """A generated/autoconf.h with the bring-up Ethernet options switched off.

    The shared tree is configured with the debug and PP options on; the
    shipping config-6.6 has them off. Returns the include directory to put
    first on the command line.
    """
    text = (tree / 'include/generated/autoconf.h').read_text()
    drop = ('CONFIG_ZX279128_ETH_DEBUG', 'CONFIG_ZX279128_PP_TABLES',
            'CONFIG_ZX279128_PP_FLOW_TEST', 'CONFIG_ZX279128_PP_OFFLOAD')
    lines = [l for l in text.splitlines()
             if not any(re.match(r'#define ' + name + r'(_MODULE)? ', l) for name in drop)]
    inc = Path(out) / 'release-include'
    (inc / 'generated').mkdir(parents=True, exist_ok=True)
    (inc / 'generated/autoconf.h').write_text('\n'.join(lines) + '\n')
    return inc


def cross_compile(source, record, out, extra=(), first_include=None):
    tools = cross_tools()
    tree, toolchain = tools
    words = recorded_command(tree, record)
    compiler = toolchain / 'bin' / words[0]
    head = [str(compiler)]
    if first_include:
        head += ['-I', str(first_include)]
    environment = dict(os.environ, STAGING_DIR=str(toolchain.parent))
    return subprocess.run(head + words[1:] + list(extra) +
                          ['-c', '-o', str(Path(out) / 'out.o'), str(source)],
                          capture_output=True, text=True, cwd=str(out), env=environment,
                          timeout=300)
