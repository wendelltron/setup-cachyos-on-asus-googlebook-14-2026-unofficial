"""Small, explicit helpers shared by the image builder and target tools."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
# Live kernel: exactly the one inside the pinned CachyOS ISO.
KERNEL_RELEASE = '7.1.6-1-cachyos'
LIVE_KERNEL_RELEASE = KERNEL_RELEASE
ISO_SHA256 = '959f6577f45e25ee9fd8c220fd221b08e4ea79412c7315c0f922dd6d86d5e33c'
ISO_URL = 'https://mirror.zyner.org/cachyos/ISO/desktop/260809/cachyos-desktop-linux-260809.iso'
ISO_KERNEL_PATH = 'arch/boot/x86_64/vmlinuz-linux-cachyos'
ISO_INITRD_PATH = 'arch/boot/x86_64/initramfs-linux-cachyos.img'
KERNEL_SHA256 = '1e9521170efcc2c26e34adc0e58051aa771726bb0b411f44296987051e180ba2'
# Installed kernel: pinned packages from the CachyOS repository (cachyos repo db).
INSTALLED_KERNEL_RELEASE = '7.2.7-1-cachyos'
INSTALLED_KERNEL_SHA256 = 'a468545294aefa4cb52a589894521a52b80effeef4eca8545f8b754abd765c57'
KERNEL_PACKAGES = {
    'linux-cachyos-7.2.7-1-x86_64.pkg.tar.zst': 'cb164037efbdc8703580da9cca2a1f067e22a0ffc8a0fc1b7c03d4419e99fd37',
    'linux-cachyos-headers-7.2.7-1-x86_64.pkg.tar.zst': '14cdee3a743e7792200331c530bd71eb0b1b244b06c7244308afe3c67b869229',
}
KERNEL_REPO_URL = 'https://cdn77.cachyos.org/repo/x86_64/cachyos/'
XE_PARAMETERS = {
    'gsc_firmware_path': '', 'enable_panel_replay': '0', 'enable_psr': '0',
    'enable_fbc': '0', 'enable_dsb': '0', 'enable_sagv': '0', 'enable_dc': '0',
}


def require(condition, message):
    # Never use assert for a guard: Python -O must not disable it.
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(argv, **kwargs):
    # Passwords are passed on stdin, never in argv or this log.
    print('+', ' '.join(map(str, argv)), flush=True)
    return subprocess.run(list(map(str, argv)), check=True, **kwargs)


def output(argv):
    return subprocess.check_output(list(map(str, argv)), text=True).strip()


def save_json(path, value, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.new')
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def new_regular_output(path):
    path = Path(path)
    require(not path.exists() and not path.is_symlink(), f'Output already exists: {path}')
    require(not str(path.resolve()).startswith('/dev/'), 'Image tools never write device nodes')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def require_regular(path):
    path = Path(path)
    require(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), f'Not a regular file: {path}')


def read_json(path):
    return json.loads(Path(path).read_text())
