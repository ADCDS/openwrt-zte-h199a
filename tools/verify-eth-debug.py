#!/usr/bin/env python3
"""Check the merged kernel config and compiled Ethernet parameter exposure."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def verify(config, driver, expected):
    enabled = 'CONFIG_ZX279128_ETH_DEBUG=y' in config.read_text().splitlines()
    if enabled != expected:
        raise ValueError('merged Ethernet debug configuration differs from requested profile')
    sections = subprocess.run(['readelf', '-SW', str(driver)], check=True, capture_output=True, text=True).stdout
    params = bool(re.search(r'\s__param\s', sections))
    if params != expected:
        raise ValueError('compiled Ethernet parameter table differs from requested profile')
    info = subprocess.run(['readelf', '-p', '.modinfo', str(driver)], check=True, capture_output=True, text=True).stdout
    if not expected and re.search(r'\bparm(?:type)?=', info):
        raise ValueError('release Ethernet object still advertises experimental parameters')
    return {'ethernet_debug': enabled, 'parameter_table_present': params,
            'kernel_config_sha256': hashlib.sha256(config.read_bytes()).hexdigest(),
            'driver_object_sha256': hashlib.sha256(driver.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('driver', type=Path)
    parser.add_argument('--expect-debug', choices=('yes', 'no'), required=True)
    args = parser.parse_args()
    try:
        result = verify(args.config, args.driver, args.expect_debug == 'yes')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, 'Ethernet build-profile verification failed: ' + str(error) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
