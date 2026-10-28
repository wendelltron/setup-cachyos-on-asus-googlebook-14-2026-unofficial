#!/usr/bin/env python3
"""Checked Xe GPU bring-up for the ASUS Lapis live session (CachyOS port).

Runs before the display manager: loads xe with the hardware-verified
parameters, performs the one checked unload/reload that the board needs,
then hands control back to plasmalogin (stock CachyOS autologin desktop).
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(argv, timeout=60):
    print('RUN', json.dumps(argv), flush=True)
    subprocess.run(argv, check=True, timeout=timeout)


def output(argv):
    return subprocess.check_output(argv, text=True).strip()


params = {
    'gsc_firmware_path': '',
    'enable_panel_replay': '0',
    'enable_psr': '0',
    'enable_fbc': '0',
    'enable_dsb': '0',
    'enable_sagv': '0',
    'enable_dc': '0',
}

require(os.geteuid() == 0, 'Live hardware/environment prerequisite failed')
require(Path('/sys/class/dmi/id/product_name').read_text().strip() == 'Lapis', 'Live hardware/environment prerequisite failed')
require(Path('/sys/bus/pci/devices/0000:00:02.0/device').read_text().strip() == '0xb090', 'Live hardware/environment prerequisite failed')
require(output(['findmnt', '-no', 'FSTYPE', '/']) == 'overlay', 'Live hardware/environment prerequisite failed')
require(not any(('/dev/nvme' in line for line in Path('/proc/mounts').read_text().splitlines())), 'Internal disk must not be mounted in the live session')

if not Path('/sys/module/xe').exists():
    run(['modprobe', 'xe'] + [f'{k}={v}' for k, v in params.items()], timeout=40)
    # The first firmware-to-Xe display handoff failed in two physical boots.
    # Two physical sessions recovered after a normal unload and identical reload.
    # Do this once before any graphical client starts; never force an unload.
    time.sleep(2)
    drm_nodes = [str(p) for p in Path('/dev/dri').glob('*') if p.is_char_device()]
    require(drm_nodes, 'First Xe load did not create DRM devices')
    users = subprocess.run(['fuser'] + drm_nodes, capture_output=True, text=True)
    require(users.returncode == 1 and (not users.stdout.strip()), 'DRM devices are in use')
    for vt in Path('/sys/class/vtconsole').glob('vtcon*'):
        if 'frame buffer' in (vt / 'name').read_text() and (vt / 'bind').read_text().strip() == '1':
            (vt / 'bind').write_text('0\n')
    run(['modprobe', '-r', 'xe'], timeout=30)
    require(not Path('/sys/module/xe').exists(), 'Xe remained loaded')
    time.sleep(1)
    run(['modprobe', 'xe'] + [f'{k}={v}' for k, v in params.items()], timeout=40)
    Path('/run/cachyos-xe-reinitialized').write_text(Path('/proc/uptime').read_text())
    print('CACHYOS_XE_REINITIALIZED: one checked unload/reload before desktop startup', flush=True)

for name, value in params.items():
    actual = (Path('/sys/module/xe/parameters') / name).read_text().strip()
    require(actual == value or (value == '0' and actual == 'N'), (name, actual, value))

# Hand off to the stock CachyOS login manager. The initramfs latehook masked
# display-manager/plasmalogin so no graphical client could start before the
# checked Xe sequence; unmask, restore the display-manager alias, start it.
run(['systemctl', 'unmask', 'display-manager.service', 'plasmalogin.service'], timeout=30)
alias = Path('/etc/systemd/system/display-manager.service')
alias.unlink(missing_ok=True)
alias.symlink_to('plasmalogin.service')
run(['systemctl', 'daemon-reload'], timeout=30)
run(['systemctl', 'start', 'display-manager.service'], timeout=120)
print('LAPIS_LIVE_DESKTOP_STARTED: plasmalogin autologin after checked GPU preparation', flush=True)
