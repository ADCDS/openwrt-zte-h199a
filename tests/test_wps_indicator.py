"""Exercise the actual bounded observer without hardware or enrollment calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

BOARD = Path(__file__).resolve().parents[1]/'files/target/linux/armsr/base-files'


class WpsIndicatorTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which('flock') or not shutil.which('timeout'):
            self.skipTest('requires host flock/timeout for process lifetime tests')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for folder in ('led', 'run', 'bin'):
            (self.root/folder).mkdir()
        for name, value in (('trigger', 'none'), ('brightness', '0'), ('delay_on', '0'), ('delay_off', '0')):
            (self.root/'led'/name).write_text(value+'\n')
        (self.root/'uptime').write_text('100.00 0.00\n')
        (self.root/'status').write_text('Active')
        source = (BOARD/'usr/libexec/h199a-wps-led').read_text()
        source = source.replace('/sys/class/leds/green:wps', str(self.root/'led'))
        source = source.replace('/var/run/h199a-wps-led', str(self.root/'run/h199a-wps-led'))
        source = source.replace('/proc/uptime', str(self.root/'uptime'))
        source = source.replace('/usr/bin/util-linux-flock', shutil.which('flock'))
        source = source.replace('/usr/libexec/timeout-coreutils', shutil.which('timeout'))
        self.script = self.root/'observer'
        self.script.write_text(source)
        self.script.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.root/'bin')+os.pathsep+os.environ['PATH'],
                        WPS_TEST_ROOT=str(self.root), WPS_TEST_MODE='terminal', WPS_TEST_END='Disabled')
        self.command('ubus', '''
import json,os,sys,time
from pathlib import Path
r=Path(os.environ['WPS_TEST_ROOT'])
if 'list' in sys.argv:
 if (r/'status').read_text()=='HANG': time.sleep(30)
 print('hostapd.phy0-ap0')
else:
 assert sys.argv[-1]=='wps_status', 'observer must never enroll or cancel'
 state=(r/'status').read_text()
 if state=='HANG': time.sleep(30)
 if os.environ['WPS_TEST_MODE']=='inactive-refresh' and (r/'scan-next').exists() and not (r/'scan-waiting').exists():
  (r/'scan-waiting').touch();end=time.monotonic()+4.7
  while not (r/'scan-release').exists():
   assert time.monotonic()<end
   time.sleep(.005)
  state='Disabled'
 print(json.dumps({'pbc_status':state,
                   'last_wps_result':'Success','peer_address':'PRIVATE_PEER_MUST_NOT_BE_LOGGED'}))
''')
        self.command('jsonfilter', '''
import json,sys
print(json.load(sys.stdin)['pbc_status'])
''')
        self.command('sleep', r'''
import json,os,time
from pathlib import Path
r=Path(os.environ['WPS_TEST_ROOT']);mode=os.environ['WPS_TEST_MODE']
trace=r/'trace';records=json.loads(trace.read_text()) if trace.exists() else []
records.append({name:(r/'led'/name).read_text().strip() for name in ['trigger','delay_on','delay_off']})
trace.write_text(json.dumps(records))
if mode=='repeat' and len(records)==1:
 (r/'waiting').touch();end=time.monotonic()+4
 while not (r/'release').exists():
  assert time.monotonic()<end, 'test failed to release first observer'
  time.sleep(.005)
elif mode=='repeat' and len(records)==2:
 (r/'uptime').write_text('260.00 0.00\n')
elif mode=='deadline':
 (r/'uptime').write_text('230.00 0.00\n')
elif mode=='hang':
 (r/'status').write_text('HANG')
elif mode=='inactive-refresh' and len(records)==1:
 (r/'scan-next').touch()
else:
 (r/'status').write_text(os.environ['WPS_TEST_END'])
''')

    def command(self, name, body):
        path = self.root/'bin'/name
        path.write_text('#!/usr/bin/env python3\n'+body)
        path.chmod(0o755)

    def run_observer(self):
        return subprocess.run(['sh', str(self.script)], env=self.env,
                              capture_output=True, timeout=8)

    def assert_clean(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout+result.stderr, b'')
        self.assertEqual((self.root/'led/trigger').read_text().strip(), 'none')
        self.assertEqual((self.root/'led/brightness').read_text().strip(), '0')

    def wait_for(self, predicate):
        deadline = time.monotonic()+3
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail('observer coordination deadline expired')
            time.sleep(.005)

    def test_active_indication_ends_on_each_terminal_state(self):
        for state in ('Disabled', 'Timed-out', 'Overlap'):
            with self.subTest(state=state):
                (self.root/'status').write_text('Active')
                self.env['WPS_TEST_END'] = state
                self.assert_clean(self.run_observer())
        trace = json.loads((self.root/'trace').read_text())
        self.assertEqual(trace, [{'trigger':'timer', 'delay_on':'200', 'delay_off':'100'}]*3)

    def test_active_forever_still_has_a_monotonic_deadline(self):
        self.env['WPS_TEST_MODE'] = 'deadline'
        self.assert_clean(self.run_observer())
        self.assertEqual(len(json.loads((self.root/'trace').read_text())), 1)
        self.assertEqual((self.root/'status').read_text(), 'Active')

    def test_stalled_bus_lookup_cannot_hold_led_or_lock_indefinitely(self):
        self.env['WPS_TEST_MODE'] = 'hang'
        self.assert_clean(self.run_observer())
        subprocess.run(['flock', '-n', str(self.root/'run/h199a-wps-led.lock'), 'true'],
                       check=True, timeout=2)

    def test_refresh_during_inactive_scan_survives_the_followers_lock_timeout(self):
        self.env['WPS_TEST_MODE'] = 'inactive-refresh'
        first = subprocess.Popen(['sh', str(self.script)], env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        second = None
        try:
            self.wait_for(lambda: (self.root/'scan-waiting').exists())
            (self.root/'uptime').write_text('200.00 0.00\n')
            second = subprocess.Popen(['sh', str(self.script)], env=self.env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            request = self.root/'run/h199a-wps-led.request'
            self.wait_for(lambda: request.read_text().split()[0] == '200')
            out, err = second.communicate(timeout=4)
            self.assertEqual((second.returncode, out, err), (0, b'', b''))
            self.assertEqual((self.root/'led/trigger').read_text().strip(), 'timer')
            (self.root/'scan-release').touch()
            out, err = first.communicate(timeout=4)
            self.assert_clean(subprocess.CompletedProcess(first.args, first.returncode, out, err))
            self.assertEqual(len(json.loads((self.root/'trace').read_text())), 2)
        finally:
            for process in (first, second):
                if process and process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_repeated_press_extends_one_observer_without_competing_writers(self):
        self.env['WPS_TEST_MODE'] = 'repeat'
        first = subprocess.Popen(['sh', str(self.script)], env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        second = None
        try:
            self.wait_for(lambda: (self.root/'waiting').exists())
            (self.root/'uptime').write_text('200.00 0.00\n')
            second = subprocess.Popen(['sh', str(self.script)], env=self.env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            request = self.root/'run/h199a-wps-led.request'
            self.wait_for(lambda: request.read_text().split()[0] == '200')
            (self.root/'release').touch()
            for process in (first, second):
                out, err = process.communicate(timeout=8)
                self.assert_clean(subprocess.CompletedProcess(process.args, process.returncode, out, err))
            # One leader survived beyond its original deadline230, observing
            # the refreshed deadline330. The follower never drove the LED.
            self.assertEqual(len(json.loads((self.root/'trace').read_text())), 3)
        finally:
            for process in (first, second):
                if process and process.poll() is None:
                    process.kill()
                    process.communicate()
