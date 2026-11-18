"""Debug controls disappear from release preprocessing and compiled ELF checks."""
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c'
spec = importlib.util.spec_from_file_location('eth_debug_verify', ROOT / 'tools/verify-eth-debug.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class EthernetDebugGateTests(unittest.TestCase):
    def test_all_actual_parameter_registrations_follow_debug_configuration(self):
        source = re.sub(r'^#include[^\n]*', '', SOURCE.read_text(), flags=re.M)
        for enabled in (0, 1):
            run = subprocess.run(['cc', '-E', '-P', '-x', 'c', '-',
                                  '-DIS_ENABLED(x)=(x)', f'-DCONFIG_ZX279128_ETH_DEBUG={enabled}'],
                                 input=source, capture_output=True, text=True, check=True)
            params = re.findall(r'^module_param_(?:named|cb)\(', run.stdout, re.M)
            # 27 diagnostic knobs, plus rx_recover, rx_stall_ms and tx_drain_us
            # from the datapath-recovery merge.
            self.assertEqual(len(params), 30 if enabled else 0)
            if not enabled:
                self.assertNotIn('MODULE_PARM_DESC(', run.stdout)
                self.assertNotIn('static int zx_packet_trace_set(', run.stdout)
                self.assertNotIn('static int zx_rx_q0_seed_set(', run.stdout)

    def test_config_and_real_elf_parameter_presence_must_agree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, source, obj = root / '.config', root / 'driver.c', root / 'driver.o'
            for enabled in (False, True):
                text = 'const char license[] __attribute__((section(".modinfo"),used))="license=GPL";\n'
                if enabled:
                    text += 'const int knob __attribute__((section("__param"),used))=1;\n'
                    text += 'const char parm[] __attribute__((section(".modinfo"),used))="parm=knob:debug";\n'
                source.write_text(text)
                subprocess.run(['cc', '-c', str(source), '-o', str(obj)], check=True, capture_output=True)
                config.write_text('CONFIG_ZX279128_ETH_DEBUG=y\n' if enabled else '# CONFIG_ZX279128_ETH_DEBUG is not set\n')
                self.assertEqual(verify.verify(config, obj, enabled)['parameter_table_present'], enabled)
                with self.assertRaises(ValueError):
                    verify.verify(config, obj, not enabled)
                config.write_text('# CONFIG_ZX279128_ETH_DEBUG is not set\n' if enabled else 'CONFIG_ZX279128_ETH_DEBUG=y\n')
                with self.assertRaises(ValueError):
                    verify.verify(config, obj, not enabled)
            config.write_text('# CONFIG_ZX279128_ETH_DEBUG is not set\n')
            source.write_text('const char parm[] __attribute__((section(".modinfo"),used))="parm=leaked:debug";\n')
            subprocess.run(['cc', '-c', str(source), '-o', str(obj)], check=True, capture_output=True)
            with self.assertRaises(ValueError):
                verify.verify(config, obj, False)
