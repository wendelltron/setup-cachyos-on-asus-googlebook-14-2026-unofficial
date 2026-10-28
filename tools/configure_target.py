#!/usr/bin/env python3
"""Install CachyOS packages and configure the mounted Lapis encrypted root."""
import argparse
import datetime
import getpass
import os
from pathlib import Path
import re
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lapis.common import (ROOT, KERNEL_PACKAGES, KERNEL_RELEASE, INSTALLED_KERNEL_RELEASE, INSTALLED_KERNEL_SHA256,
                          KERNEL_REPO_URL, output, read_json, require, run, save_json, sha256)
from tools.native import STATE, TARGET, current, mounted, checked_backup

MASKED_HOOKS = ['60-mkinitcpio-remove.hook', '90-mkinitcpio-install.hook']

# Pinned CachyOS desktop package set. The kernel pair is NOT in this list:
# it comes from the checksum-pinned repository packages, never from the
# online repositories, so the tested kernel cannot drift.
PACKAGES = [
    'archlinux-keyring', 'base', 'base-devel', 'btrfs-progs', 'cryptsetup',
    'mkinitcpio', 'intel-ucode', 'linux-firmware', 'sof-firmware', 'sudo',
    'python', 'git', 'mesa', 'vulkan-intel', 'vulkan-icd-loader',
    'xorg-xwayland', 'pipewire', 'wireplumber', 'pipewire-alsa', 'pipewire-pulse',
    'networkmanager', 'wpa_supplicant', 'plasma-desktop', 'plasma-workspace',
    'plasma-login-manager', 'plasma-nm', 'plasma-pa', 'konsole', 'dolphin',
    'xdg-desktop-portal-kde', 'firefox', 'nano', 'vim', 'man-db', 'less',
    'xdg-user-dirs', 'cachyos-settings', 'cachyos-keyring',
]


def put(name, content, mode=0o644):
    path = TARGET / name.lstrip('/')
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.is_symlink(), 'Refuse writing through target symlink: ' + name)
    path.write_text(content)
    path.chmod(mode)


def mask(name):
    path = TARGET / name.lstrip('/')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        require(path.is_symlink() and os.readlink(path) == '/dev/null', 'Unexpected file at ' + name)
    else:
        path.symlink_to('/dev/null')


def chroot(*argv, **kw):
    return run(['arch-chroot', TARGET, *argv], **kw)


def fetch_kernel_packages(dest):
    dest.mkdir(parents=True, exist_ok=True)
    for file, expected in KERNEL_PACKAGES.items():
        target = dest / file
        if not target.exists():
            run(['curl', '--fail', '--location', '--output', target, KERNEL_REPO_URL + file])
        require(sha256(target) == expected, 'Wrong kernel package hash: ' + file)


def packages(args):
    current(); mounted()
    require(sys.stdin.isatty(), 'Package setup needs a local terminal for the private account-password prompt')
    require(not (STATE / 'packages-started').exists(), 'Packages already attempted; inspect failure before manual resumption')
    require(re.fullmatch('[a-z][a-z0-9_-]{0,30}', args.user) and args.user not in ('root', 'liveuser'), 'Invalid username')
    require('\n' not in args.name and '\r' not in args.name and ':' not in args.name, 'Invalid full name')
    require((Path('/usr/share/zoneinfo') / args.timezone).is_file() and '..' not in args.timezone.split('/'), 'Invalid timezone')
    require(re.fullmatch('[a-zA-Z0-9_-]+', args.keymap), 'Invalid console keymap')
    require((STATE / 'network-checked').exists() or output(['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', '20', 'https://cdn77.cachyos.org/repo/x86_64/cachyos/cachyos.db']) == '200',
            'No repository access; connect Wi-Fi in the live desktop first')
    account = dict(user=args.user, name=args.name, timezone=args.timezone, keymap=args.keymap)
    save_json(STATE / 'account.json', account)
    (STATE / 'packages-started').touch(mode=0o600)
    for name in MASKED_HOOKS:
        mask('/etc/cachyos-boot/pacman-hooks/' + name)
    # Pacstrap resolves repo Include= lines inside the target; provide the
    # live session's CachyOS mirrorlists there first.
    for name in ('mirrorlist', 'cachyos-mirrorlist'):
        src = Path('/etc/pacman.d') / name
        require(src.is_file(), 'Live mirrorlist missing: ' + name)
        put('/etc/pacman.d/' + name, src.read_text())
    conf = STATE / 'cachyos-pacman.conf'
    conf.write_text('[options]\nArchitecture = auto\nHookDir = /etc/cachyos-boot/pacman-hooks\n'
                    'SigLevel = Required DatabaseOptional\nLocalFileSigLevel = Required\n'
                    'CacheDir = /var/cache/pacman/pkg\n'
                    '[core]\nInclude = /etc/pacman.d/mirrorlist\n'
                    '[extra]\nInclude = /etc/pacman.d/mirrorlist\n'
                    '[cachyos]\nInclude = /etc/pacman.d/cachyos-mirrorlist\n')
    run(['systemctl', 'start', 'pacman-init.service'])
    run(['pacstrap', '-C', conf, '-M', '-c', TARGET, *PACKAGES])
    kernel_cache = STATE / 'kernel-pkgs'
    fetch_kernel_packages(kernel_cache)
    local_conf = STATE / 'kernel-local.conf'
    local_conf.write_text(conf.read_text().replace('LocalFileSigLevel = Required', 'LocalFileSigLevel = Optional'))
    run(['pacstrap', '-U', '-C', local_conf, '-M', '-c', TARGET, *(kernel_cache / x for x in KERNEL_PACKAGES)])
    chroot('useradd', '-m', '-s', '/bin/bash', '-G', 'wheel', '-c', args.name, args.user)
    password = getpass.getpass('New login/sudo password (may differ from disk password): ')
    require(len(password) >= 12 and '\n' not in password and '\0' not in password, 'Use at least 12 characters')
    require(password == getpass.getpass('Repeat login password: '), 'Passwords differ')
    chroot('chpasswd', input=(args.user + ':' + password + '\n').encode())
    del password
    chroot('passwd', '-l', 'root')
    put('/etc/pacman.conf', conf.read_text())
    require(sha256(TARGET / 'boot/vmlinuz-linux-cachyos') == INSTALLED_KERNEL_SHA256, 'Installed kernel differs from the pinned version')
    save_json(STATE / 'packages.json', dict(status='CachyOS package installation complete'))


def configure(args):
    p, device, _ = current(); mounted(); backup = checked_backup(device)
    require((STATE / 'packages.json').is_file(), 'Install packages first')
    require(not (STATE / 'configure-started').exists(), 'Configuration already attempted; inspect before resuming')
    require(Path('/sys/bus/pci/devices/0000:00:1f.3/subsystem_device').read_text().strip() == '0x15e4', 'Audio subsystem differs')
    account = read_json(STATE / 'account.json')
    user = account['user']
    (STATE / 'configure-started').touch(mode=0o600)
    fs = read_json(STATE / 'format.json')['btrfs_uuid']
    put('/etc/fstab', ''.join(f'UUID={fs} {mount} btrfs noatime,compress=zstd:3,subvol={sub} 0 0\n' for mount, sub in [('/', '@'), ('/home', '@home'), ('/var/log', '@log'), ('/var/cache/pacman/pkg', '@pkg')]))
    put('/etc/hostname', 'cachyos\n')
    put('/etc/hosts', '127.0.0.1 localhost\n::1 localhost\n127.0.1.1 cachyos.localdomain cachyos\n')
    put('/etc/locale.gen', 'en_US.UTF-8 UTF-8\n')
    put('/etc/locale.conf', 'LANG=en_US.UTF-8\n')
    put('/etc/vconsole.conf', 'KEYMAP=' + account['keymap'] + '\n')
    localtime = TARGET / 'etc/localtime'
    localtime.unlink(missing_ok=True)
    localtime.symlink_to('../usr/share/zoneinfo/' + account['timezone'])
    put('/etc/adjtime', '0.0 0 0.0\n0\nUTC\n')
    put('/etc/sudoers.d/10-wheel', '%wheel ALL=(ALL:ALL) ALL\n', 0o440)
    chroot('locale-gen'); chroot('systemd-machine-id-setup')
    # Display manager: plasmalogin (CachyOS Plasma). Graphics must be prepared
    # with the checked Xe sequence before any graphical client starts.
    chroot('systemctl', 'enable', 'plasmalogin.service')
    require((TARGET / 'etc/systemd/system/display-manager.service').is_symlink(),
            'display-manager alias missing after enabling plasmalogin')
    put('/usr/local/libexec/cachyos-gpu-prepare', (ROOT / 'assets/installed/gpu-prepare.py').read_text(), 0o755)
    put('/etc/systemd/system/cachyos-gpu-prepare.service', (ROOT / 'assets/installed/gpu-prepare.service').read_text())
    put('/etc/systemd/system/display-manager.service.d/20-lapis-gpu.conf',
        '[Unit]\nRequires=cachyos-gpu-prepare.service\nAfter=cachyos-gpu-prepare.service\n')
    put('/etc/plasmalogin.conf.d/20-lapis-hidpi.conf', '[Wayland]\nEnableHiDPI=true\n')
    put('/etc/plasmalogin.conf.d/99-lapis-autologin.conf',
        '[Autologin]\nUser=' + user + '\nSession=plasma.desktop\nRelogin=false\n')
    put('/etc/modprobe.d/lapis-xe.conf', 'blacklist xe\noptions xe gsc_firmware_path= enable_panel_replay=0 enable_psr=0 enable_fbc=0 enable_dsb=0 enable_sagv=0 enable_dc=0\n')
    # Wireless backend: NetworkManager is the only network owner on the
    # installed system, and wpa_supplicant is its default, most-tested
    # backend -- and the one hardware-validated on this board by the
    # upstream installation. iwd is deliberately NOT installed: enabling
    # two wireless daemons invites them fighting over the interface, and
    # iwd's advantages apply to standalone (no-NM) setups this fork does
    # not use. The live session keeps the ISO's iwd for pre-desktop
    # iwctl use; nothing here should enable iwd.service in the target.
    put('/etc/modprobe.d/lapis-audio.conf', 'blacklist snd_sof_pci_intel_ptl\noptions snd_soc_sof_sdw quirk=0x288000\noptions snd_sof_intel_hda_generic dmic_num=0\n')
    put('/etc/wireplumber/wireplumber.conf.d/52-lapis-unused-bt-offload.conf',
        'monitor.alsa.rules = [ { matches = [ { api.alsa.pcm.id = "Bluetooth" } ] actions = { update-props = { node.disabled = true } } } ]\n')
    mask('/etc/systemd/system-generators/systemd-gpt-auto-generator')
    put('/etc/NetworkManager/conf.d/90-lapis.conf', '[device]\nwifi.backend=wpa_supplicant\n')
    resolv = TARGET / 'etc/resolv.conf'; resolv.unlink(missing_ok=True); resolv.symlink_to('../run/systemd/resolve/stub-resolv.conf')
    chroot('visudo', '-c')
    chroot('systemctl', 'enable', 'cachyos-gpu-prepare.service', 'NetworkManager.service', 'systemd-resolved.service', 'systemd-timesyncd.service')
    chroot('systemctl', 'disable', 'systemd-networkd.service')
    chroot('systemctl', 'mask', 'sshd.service')
    chroot('systemctl', 'set-default', 'graphical.target')
    conf = TARGET / 'etc/pacman.conf'
    body = conf.read_text()
    body = body.replace('[options]', '[options]\nHookDir = /etc/cachyos-boot/pacman-hooks\nIgnorePkg = linux-cachyos linux-cachyos-headers', 1)
    require('[cachyos]' in body, 'Target pacman.conf lacks the cachyos repository; inspect before boot')
    put('/etc/pacman.conf', body)
    put('/usr/local/libexec/cachyos-boot-update-guard',
        '#!/bin/sh\necho "Lapis kernel update blocked: rebuild and validate Android boot images first. See the repository update guide." >&2\nexit 1\n', 0o755)
    put('/etc/pacman.d/hooks/00-lapis-kernel-guard.hook',
        '[Trigger]\nOperation = Upgrade\nOperation = Install\nOperation = Remove\nType = Path\nTarget = usr/lib/modules/*/vmlinuz\n[Action]\nDescription = Protect Lapis kernel and Android boot pair\nWhen = PreTransaction\nExec = /usr/local/libexec/cachyos-boot-update-guard\nAbortOnFail\n')
    for name in ('/etc/mkinitcpio.conf',):
        put(name, (ROOT / 'assets/installed/mkinitcpio.conf').read_text())
    save_json(TARGET / 'etc/cachyos-boot/install.json', p)
    shutil.copy2(backup / 'luks-header.bin', TARGET / 'etc/cachyos-boot/luks-header.bin')
    chroot('/usr/bin/mkinitcpio', '-c', '/etc/mkinitcpio.conf', '-k', INSTALLED_KERNEL_RELEASE, '-g', '/boot/initramfs-linux-cachyos.img')
    listing = output(['arch-chroot', TARGET, 'lsinitcpio', '/boot/initramfs-linux-cachyos.img'])
    require(all(x not in listing for x in ('avb-private', 'luks-header', '.nmconnection', 'authorized_keys')), 'Private file in initramfs')
    require((TARGET / 'boot/initramfs-linux-cachyos.img').stat().st_size < 29 * 1024**2, 'Initramfs exceeds partition budget')
    save_json(STATE / 'configured.json', dict(status='Configured; boot partitions not yet committed'))
    print('Configuration complete. Wi-Fi credentials are not copied: connect through the desktop after first boot.')


def main():
    os.umask(0o022)
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(required=True)
    q = subs.add_parser('packages'); q.add_argument('--user', required=True); q.add_argument('--name', required=True)
    q.add_argument('--timezone', required=True); q.add_argument('--keymap', default='us'); q.set_defaults(fn=packages)
    q = subs.add_parser('configure'); q.set_defaults(fn=configure)
    a = p.parse_args(); a.fn(a)


if __name__ == '__main__':
    main()
