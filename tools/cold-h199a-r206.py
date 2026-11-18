#!/usr/bin/env python3
"""PARENT ONLY: fresh non-network UART/R204 CRC-gated boot + Ethernet test.
Own the SAME UART FD through U-Boot, Linux setup and traffic validation. No old
UART helpers, flash, environment changes, default promotion or live handoff.
Finally power OFF, verify, release, restore the normal logger while OFF.
"""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import time
from h199a_uart_fd import Lease, UARTError
from h199a_cold_r206 import (ColdConsole, PARAM, SOURCE_SHA, require_r204,
                              verify_enabled, validate_probe, tcp_roundtrip,
                              classify_uart_bytes, normalize_trace_text, parse_image,
                              ascii_console_text, require_cmdline, expected_parameters)
from xmodem_h199a import TransferPlan, SenderOptions, TransferError

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('r205_pilot_base',ROOT/'tools/pilot-h199a-xmodem-r205.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def network_suite(c,out,data,result,checkpoint,expect_force=True):
    def board(cmd,timeout=10):
        text=c.linux(cmd,timeout)
        with (out/'linux-commands.log').open('a') as log:log.write(text)
        return text
    for cmd in ['mount -t proc proc /proc','mount -t sysfs sysfs /sys',
                'mount -t tmpfs tmpfs /tmp','mount -t tmpfs tmpfs /dev',
                'mknod /dev/null c 1 3','mknod /dev/urandom c 1 9','mknod /dev/console c 5 1',
                'ifconfig lo 127.0.0.1 up']:
        board(cmd)
    mounts=board('cat /proc/mounts')
    if not re.search(r'\S+ / squashfs ro(?:,|\s)',mounts):raise UARTError('root is not readonly squashfs')
    cmdline=board('cat /proc/cmdline')
    result['cmdline']=cmdline
    require_cmdline(cmdline,expect_force=expect_force)
    expected=expected_parameters(expect_force)
    result['runtime_parameters']={}
    for key,value in expected.items():
        text=board('cat '+PARAM+key)
        # The command wrapper prints a newline before its independently split marker.
        if not re.search(r'(?:^|\r?\n)'+re.escape(value)+r'\r?\n',text):
            raise UARTError('runtime parameter mismatch: '+key)
        result['runtime_parameters'][key]=value
    board('echo 0 > '+PARAM+'tx_dbg_max');board('echo Y > '+PARAM+'regs_path_only')
    def open_interface():
        # A reopen may emit asynchronous PHY/link printk before the shell
        # footer/prompt; allow the command's 20-second UART bound to cover that
        # transition without treating delayed console output as driver failure.
        board('ifconfig eth2 192.168.1.1 netmask 255.255.255.0 up',20)
        for i in range(12):
            carrier=board('cat /sys/class/net/eth2/carrier')
            if re.search(r'(?:^|\r?\n)1\r?\n',carrier):break
            time.sleep(1)
        else:raise UARTError('carrier did not become1')
        state=board('ifconfig eth2')
        if 'UP BROADCAST RUNNING' not in state or '06:20:84:2F:87:B5' not in state:
            raise UARTError('unexpected interface state/MAC')
    open_interface()
    result['probes']=[]
    def probe(name,count,identifier,trace):
        checkpoint('probe-'+name)
        if trace:board(f'echo {identifier} > '+PARAM+'packet_trace_id')
        prefix=out/name
        argv=['sudo','-n','python3',str(ROOT/'tools/packet-probe-r200.py'),
              '--iface','enx00e04c125990','--source','192.168.1.100','--target','192.168.1.1',
              '--target-mac','06:20:84:2f:87:b5','--identifier',str(identifier),
              '--count',str(count),'--interval','0.005' if count==1000 else '0.02',
              '--sizes','56,57,512,1400','--size-seed',str(identifier),
              '--grace','3','--output-prefix',str(prefix)]
        raw=base.command_run(argv,40);Path(str(prefix)+'-run.log').write_bytes(raw)
        if trace:board('echo -1 > '+PARAM+'packet_trace_id')
        d=json.loads(Path(str(prefix)+'.json').read_text())
        evidence=validate_probe(d,Path(str(prefix)+'.pcap').read_bytes());evidence['name']=name
        if trace:
            tracepath=Path(str(prefix)+'.trace')
            trace_raw=board('cat /proc/zx_eth_packets',12)
            tracepath.write_text(trace_raw)
            trace_clean=Path(str(prefix)+'.trace-clean')
            trace_clean.write_text(normalize_trace_text(trace_raw))
            corr=Path(str(prefix)+'-correlation.json')
            raw=base.command_run(['python3',str(ROOT/'tools/correlate-packet-trace-r201.py'),
                 '--capture-prefix',str(prefix),'--trace',str(trace_clean),'--output',str(corr)],15)
            Path(str(prefix)+'-correlation.log').write_bytes(raw)
            cc=json.loads(corr.read_text())
            if (cc['matched_rx_request_records']!=count or cc['matched_host_reply_records']!=count or
                not cc['clock_model']['feasible'] or cc['trace_header']['dropped']!='0'):
                raise UARTError('trace/current-identity correlation failed')
            evidence['matched_trace_records']=2*count
        result['probes'].append(evidence);checkpoint('passed-'+name)
    probe('mixed',24,45632,True)
    for i in range(4):probe(f'wrap-{i+1}',1000,45633+i,False)
    for name in ('before-reopen','after-reopen'):
        if name=='after-reopen':
            board('ifconfig eth2 down');open_interface()
            probe('reopen-mixed',32,45637,True)
        checkpoint('tcp-'+name)
        tcp=tcp_roundtrip(data,board)
        (out/('tcp-'+name+'.json')).write_text(json.dumps(tcp,indent=2)+'\n')
    (out/'final-interface.log').write_text(board('ifconfig eth2'))
    (out/'final-kernel.log').write_text(board('dmesg',12))
    result['icmp_exact_total']=sum(x['exact_replies'] for x in result['probes'])
    result['tcp_aggregate_bytes']=4*len(data)
    result['linux_commands']=c.command_log


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-cold-r204',action='store_true',required=True)
    parser.add_argument('--image-mode',choices=('forced','default'),default='forced')
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--tcp-payload',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    image_data=args.image.read_bytes()
    if args.image_mode=='forced':
        image=require_r204(image_data);expect_force=True
    else:
        image=parse_image(image_data,expected_name='h199a-r206-default')
        if len(image_data)!=3*1024*1024:parser.error('default image must be padded to 3MiB')
        expect_force=False
    plan=TransferPlan(image.data)
    data=args.tcp_payload.read_bytes()
    if len(data)!=4*1024*1024:parser.error('fresh4MiB TCP payload required')
    backup=(base.RIG/'h199a-firmware/mtd0-bootloader.bin').read_bytes()
    if hashlib.sha256(backup).hexdigest()!=base.BACKUP_SHA:parser.error('unverified own-H backup')
    sources=[ROOT/'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c',
             ROOT/'openwrt/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c',
             ROOT/'openwrt/build_dir/target-arm_cortex-a9_musl_eabi/linux-armsr_armv7/linux-6.6.151/drivers/net/ethernet/zte/zx279128-eth.c']
    if any(hashlib.sha256(x.read_bytes()).hexdigest()!=SOURCE_SHA for x in sources):parser.error('R204 source drift')
    if os.geteuid()==0:parser.error('run as bench user; sudo only for audits/raw packet probe')
    out=args.output_dir.resolve();out.mkdir()  # fresh dedicated directory, no overwrites
    result=dict(phase='preflight',success=False,image_sha256=hashlib.sha256(image.data).hexdigest(),
                source_sha256=SOURCE_SHA,tcp_payload_sha256=hashlib.sha256(data).hexdigest(),
                audits=[],events=[],flash_writes=False,uboot_network_commands=False)
    lease=None;stopped=False;touched=False;off=False
    def checkpoint(phase):
        result['phase']=phase
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        if lease is not None:
            raw=bytes(lease.transport.received)
            (out/'uart.rx.bin').write_bytes(raw);(out/'uart.rx.txt').write_text(raw.decode('utf-8','replace'))
        print(phase,flush=True)
    def audit(path):
        d=json.loads(base.command_run(['sudo','-n','python3',str(ROOT/'tools/h199a_uart_fd.py'),
                                      '--audit-device',str(path)],15))
        result['audits'].append(d);return d
    def relay_state(expected):
        d=json.loads(base.command_run(['tomada','json']))
        if d.get('1') is not expected:raise UARTError('relay state not confirmed')
        result['events'].append(dict(relay_confirmed=expected,monotonic=time.monotonic()))
    def power_off():
        nonlocal touched,off
        touched=True;off=False;base.command_run(['tomada','off']);relay_state(False);off=True
    try:
        before=base.service_properties();result['service_before']=before
        if (before.get('ActiveState')!='active' or before.get('SubState')!='running' or
            before.get('KillMode')!='control-group' or before.get('Restart')!='always' or
            before.get('DropInPaths')!='' or not before.get('ControlGroup') or
            before.get('FragmentPath')!=str(Path.home()/'.config/systemd/user'/base.UNIT)):
            raise UARTError('unexpected logger supervision')
        first=audit(base.PORT)
        if first.get('complete') is not True or first.get('errors')!=[]:raise UARTError('initial audit incomplete')
        checkpoint('power-off-before-ownership');power_off();time.sleep(7)
        base.command_run(['systemctl','--user','stop',base.UNIT]);stopped=True
        after=base.service_properties();result['service_stopped']=after
        if after.get('ActiveState')!='inactive' or after.get('SubState')!='dead' or after.get('MainPID')!='0':
            raise UARTError('logger not stopped')
        cg=Path('/sys/fs/cgroup'+before['ControlGroup'])/'cgroup.events'
        if cg.exists() and not re.search(r'^populated 0$',cg.read_text(),re.M):raise UARTError('logger cgroup populated')
        lease=Lease.acquire(base.PORT,base.LOCK,powered_off=off,audit=audit)
        result['lease']=dict(device=lease.expected,lock=lease.lock_identity,pid=os.getpid(),fd=lease.fd)
        end=time.monotonic()+2
        while lease.transport.read(4096,.1):
            if time.monotonic()>=end:raise UARTError('not quiet while OFF')
        c=ColdConsole(lease.transport)
        result['uboot_commands']=c.uboot_log  # live reference; serialized at checkpoint
        checkpoint('fresh-nonnetwork-entry');off=False
        result['power_on_rx_start']=len(lease.transport.received)
        entry=dict(stages=[]);result['entry']=entry
        entry_start=time.monotonic()
        def entry_stage(name,action):
            before=len(lease.transport.received)
            try:
                value=action()
            except BaseException:
                entry['failed_stage']=name
                entry['failed_stage_rx_bytes']=len(lease.transport.received)-before
                entry['elapsed_seconds']=round(time.monotonic()-entry_start,3)
                entry['rx_after_power_on_hex']=bytes(
                    lease.transport.received[result['power_on_rx_start']:
                                             result['power_on_rx_start']+256]).hex()
                raise
            entry['stages'].append(dict(name=name,rx_bytes=len(lease.transport.received)-before))
            return value
        base.command_run(['tomada','on'])
        time.sleep(.7)
        entry_stage('press-1',lambda:(c.boot_token(b'1'),relay_state(True)))
        entry_stage('password-prompt',lambda:c.until(b'input bootmode password',12))
        entry_stage('bootmode-password',lambda:c.boot_token(b'Boot4128s!\r'))
        entry_stage('autoboot-prompt',lambda:c.until(b'Hit any key to stop autoboot',12))
        entry_stage('stop-autoboot',lambda:c.boot_token(b'\r'))
        entry_stage('u-boot-prompt',c.confirm_uboot)
        entry['elapsed_seconds']=round(time.monotonic()-entry_start,3)
        info=base.validate_info(ascii_console_text(c.command('bdinfo')));result['bdinfo']=info
        offset=info['reloc_off'];result['code_checks']=[]
        windows=[('xmodem_handler',0x47f2d814),('xmodem_receiver',0x47f2d5b8),
                 ('bootm_start_dispatch',0x47f03f04),('bootm_start',0x47f03ab8),
                 ('header_crc',0x47f0d6a8),('data_crc',0x47f0d6f4),('verify_getter',0x47f0b43c)]
        for name,linked in windows:
            actual=c.memory(linked+offset,8);pos=linked-base.LINK_BASE
            result['code_checks'].append(dict(name=name,address=hex(linked+offset),actual=actual.hex(),expected=backup[pos:pos+32].hex()))
            if actual!=backup[pos:pos+32]:raise UARTError('live code mismatch: '+name)
        def software_state():
            return dict(rx_table_hex=c.memory(0x47f5a648+offset,16).hex(),
                        tx_cursor_base_hex=c.memory(0x47f5a694+offset,2).hex())
        result['software_before']=software_state()
        if result['software_before']!={'rx_table_hex':'00'*64,'tx_cursor_base_hex':'00'*8}:
            raise UARTError('nonzero cold software state; do not substitute a warm seed')
        result['verify_before']=verify_enabled(c.fixed_uboot('printenv verify'))
        lease.recheck();checkpoint('uart-transfer-3072-blocks')
        result['transfer_rx_start']=len(lease.transport.received)
        try:
            sent=c.transfer(plan,options=SenderOptions(total_timeout=600))
        except TransferError as error:
            # Preserve the sender's terminal outcome instead of only its repr.
            result['transfer_failure']=dict(type=type(error).__name__,phase=error.phase,
                block=error.block,sequence=error.sequence,
                acknowledged_blocks=error.acknowledged_blocks,
                cancel_bytes_sent=error.cancel_bytes_sent,cleanup_error=error.cleanup_error,
                receiver_state_unknown=error.receiver_state_unknown,
                prompt_verified=error.prompt_verified)
            raise
        result['protocol']=asdict(sent)
        result['prompt_after_transfer']=c.state=='console'
        result['software_after']=software_state()
        if result['software_after']!=result['software_before']:raise UARTError('software handoff changed during serial load')
        lease.recheck();checkpoint('crc-gate')
        result['crc_gate'],crc_text=(c.crc_gate(image) if expect_force else
            c.crc_gate(image,expected_name=image.name));(out/'crc-stage.log').write_bytes(crc_text)
        checkpoint('crc-verified-booting-readonly-r204')
        boot,result['origin']=(c.boot() if expect_force else c.boot(expect_force=False));(out/'boot.log').write_bytes(boot)
        checkpoint('linux-setup')
        network_suite(c,out,data,result,checkpoint,expect_force)
        result['success']=True;checkpoint('cold-validation-passed')
    except BaseException as error:
        result['error']=repr(error)
        if lease is not None:
            raw=bytes(lease.transport.received)
            # Bounded raw tail: at an XMODEM failure the last received byte is
            # the offending response, so this is the primary serial-path evidence.
            result['rx_tail_hex']=raw[-96:].hex()
            result['transport_rx_bytes_at_failure']=len(raw)
            start=result.get('power_on_rx_start')
            if isinstance(start,int):
                result['power_on_rx_classification']=classify_uart_bytes(raw[start:])
        print('STOP:',result['phase'],repr(error),flush=True)
    finally:
        if touched:
            while True:
                try:
                    power_off();time.sleep(4)
                    if lease is not None and lease.fd is not None:
                        result['transport_rx_bytes']=len(lease.transport.received)
                        result['transport_tx_accepted']=lease.transport.tx_accepted
                        lease.release(powered_off=off)
                    if stopped:
                        clean=audit(base.PORT)
                        if clean.get('complete') is not True or clean.get('errors')!=[] or clean.get('holders')!=[]:
                            raise UARTError('remaining UART holder; logger not restored')
                        base.command_run(['systemctl','--user','start',base.UNIT])
                        restored=base.service_properties();result['service_restored']=restored
                        if restored.get('ActiveState')!='active' or restored.get('SubState')!='running':raise UARTError('logger not running')
                    result['left_powered_off']=True;break
                except Exception as error:
                    result['recovery_error']=repr(error);result['success']=False;checkpoint(result['phase'])
                    if lease is None or lease.fd is None:break
                    print('QUARANTINE: retaining UART; retry only external power-off in30s',flush=True);time.sleep(30)
        checkpoint(result['phase'])
    print(json.dumps(result,indent=2),flush=True)
    if not result['success']:raise SystemExit(1)


if __name__=='__main__':main()
