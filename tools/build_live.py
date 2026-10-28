#!/usr/bin/env python3
"""Build a CachyOS live image bootable by the ASUS Googlebook Lapis firmware.

Takes the checksum-pinned CachyOS desktop ISO, patches its live initramfs
with a Lapis hardware-preparation hook, and wraps the result in a synthetic
GPT carrying Android v4 boot images (boot/init_boot/vendor_boot/vbmeta)
signed with a fresh local AVB key. The ISO payload is preserved byte-for-byte
as a partition so its online installer and package set work unmodified.
"""
import argparse
import lzma
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lapis.common import ROOT, ISO_SHA256, ISO_KERNEL_PATH, ISO_INITRD_PATH, KERNEL_SHA256, XE_PARAMETERS, new_regular_output, require, run, save_json, sha256
from lapis.boot import build_set
from lapis.cpio import archive, members
from lapis.gpt import ENTRY, tables

ISO_VOLUME_UUID = '2026-08-09-15-47-03-00'
SECTOR = 512


def payload(vendor):
    files = {}

    def add(name, data, mode=0o100644):
        pieces = name.split('/')
        for i in range(1, len(pieces)):
            files.setdefault('/'.join(pieces[:i]), (0o040755, b''))
        files[name] = (mode, data)

    # Deliberate allowlist. Never sweep a workspace or copy a live system.
    for folder in ('lapis', 'tools', 'assets', 'docs'):
        for path in sorted((ROOT / folder).rglob('*')):
            if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts:
                require(path.suffix not in ('.pem', '.psk', '.img', '.bin'), 'Unexpected private/build file in sources')
                add('lapis-kit/' + str(path.relative_to(ROOT)), path.read_bytes(), 0o100755 if path.suffix in ('.py', '.sh') else 0o100644)
    for name in ('LICENSE', 'NOTICE.md', 'README.md'):
        add('lapis-kit/' + name, (ROOT / name).read_bytes())
    for name, (_, revision) in SOURCES.items():
        src = vendor / name
        got = subprocess.check_output(['git', '-C', str(src), 'rev-parse', 'HEAD'], text=True).strip()
        require(got == revision, f'Unexpected {name} revision')
        dirty = subprocess.check_output(['git', '-C', str(src), 'status', '--porcelain', '--untracked-files=no'], text=True)
        require(not dirty, f'Modified {name} source')
        tracked = subprocess.check_output(['git', '-C', str(src), 'ls-files', '-z']).decode().split('\0')
        for rel in filter(None, tracked):
            path = src / rel
            if path.suffix in ('.pem', '.key', '.p12', '.pfx'):
                continue  # Upstream test signing keys are not needed in the live kit.
            if ('test' in path.parts or 'tests' in path.parts or 'testdata' in path.parts) and path.name != 'Makefile.inc':
                continue
            if path.is_symlink():
                # These build tools do not need symlinked test fixtures.
                continue
            if path.is_file():
                add(f'lapis-kit/vendor/{name}/{rel}', path.read_bytes(), 0o100755 if os.access(path, os.X_OK) else 0o100644)
        add(f'lapis-kit/vendor/{name}/.source-revision', (revision + '\n').encode())
    return files


def patch_initramfs(initrd, extra_files):
    """Append an extra cpio segment carrying the Lapis hook and config override.

    The CachyOS initramfs is: uncompressed early cpio + xz-compressed main
    cpio (mkinitcpio config/init/hooks). Recompressing the xz segment with
    Python lzma produces a stream the kernel's XZ decoder rejects ("settings
    that are not supported"), which panics before /init with no console
    output. Instead the original bytes stay untouched and a trailing
    uncompressed cpio is concatenated: the kernel unpacks archives in order
    and later members overwrite earlier ones, so the appended `config`
    (LATEHOOKS including `lapis`) and `hooks/lapis` take effect.
    """
    require(initrd.find(b'TRAILER!!!') > 0, 'Initramfs has no cpio trailer')
    require(initrd.find(b'\xfd7zXZ\x00') > 0, 'Initramfs main archive is not xz after the early cpio')
    # Read the original config (read-only decompress; never recompressed).
    import lzma
    main_files, _ = members(lzma.decompress(initrd[initrd.find(b'\xfd7zXZ\x00'):]))
    require('config' in main_files and 'init' in main_files, 'Missing mkinitcpio members')
    config = main_files['config'][1].decode()
    require('LATEHOOKS="' in config, 'Unexpected initramfs config layout')
    config = config.replace('LATEHOOKS="', 'LATEHOOKS="lapis ')
    extra_files = dict(extra_files)
    extra_files['config'] = (0o100644, config.encode())
    pad = bytes((-len(initrd)) % 4)
    return initrd + pad + archive(extra_files)


def protective_mbr(last_lba):
    mbr = bytearray(SECTOR)
    mbr[450] = 0xee
    struct.pack_into('<II', mbr, 454, 1, min(last_lba, 0xffffffff))
    mbr[510:512] = b'\x55\xaa'
    return bytes(mbr)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--iso', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--vendor', type=Path, default=ROOT / 'vendor')
    args = p.parse_args()
    iso = args.iso.resolve()
    require(iso.is_file(), 'Missing ISO')
    require(sha256(iso) == ISO_SHA256, 'Wrong ISO checksum; no unverified newer ISO fallback')
    image = new_regular_output(args.output).resolve()
    work = image.with_suffix('.build')
    require(not work.exists(), 'Build directory already exists')
    work.mkdir(mode=0o700)
    for name, member in (('vmlinuz-linux-cachyos', ISO_KERNEL_PATH), ('initramfs-linux-cachyos.img', ISO_INITRD_PATH)):
        with (work / name).open('wb') as f:
            run(['bsdtar', '-xOf', iso, member], stdout=f)
    require(sha256(work / 'vmlinuz-linux-cachyos') == KERNEL_SHA256, 'ISO kernel differs from the hardware-tested version')
    cmdline = (f'archisobasedir=arch archisosearchuuid={ISO_VOLUME_UUID} '
               'cow_spacesize=10G copytoram=auto module_blacklist=pcspkr nvme_load=yes '
               'modprobe.blacklist=xe asus.live_desktop=1 console=tty0 loglevel=4 '
               'log_buf_len=4M printk.time=1 panic=30 ' +
               ' '.join('xe.' + k + '=' + v for k, v in XE_PARAMETERS.items()))
    files = payload(args.vendor.resolve())
    files['hooks/lapis'] = (0o100755, (ROOT / 'assets/live/latehook.sh').read_bytes())
    initrd = patch_initramfs((work / 'initramfs-linux-cachyos.img').read_bytes(), files)
    combined = work / 'live-initramfs.img'
    combined.write_bytes(initrd)
    boot = work / 'boot'
    manifest = build_set(work / 'vmlinuz-linux-cachyos', combined, cmdline, boot, args.vendor.resolve())
    # Synthetic GPT: the CachyOS ISO is an MBR/hybrid image with no GPT, so the
    # whole ISO becomes one basic-data partition and the boot set follows it.
    iso_size = iso.stat().st_size
    require(iso_size % SECTOR == 0, 'ISO is not sector aligned')
    entries = bytearray(128 * 128)
    iso_part = uuid.uuid4()
    cursor = 34 * SECTOR + iso_size
    cursor = ((cursor + 1048575) // 1048576) * 1048576
    layout = []
    items = [(x['name'], boot / (x['name'] + '.img'), x['size']) for x in manifest['images']]
    misc = work / 'misc.img'
    misc.write_bytes(bytes(1048576))
    items.append(('misc', misc, 1048576))
    with image.open('wb') as f:
        f.write(protective_mbr(0))  # placeholder; rewritten with the real last LBA below
        f.write(b'\0' * SECTOR)     # GPT header placeholder
        f.write(entries)            # GPT entries placeholder
        f.seek(34 * SECTOR)
        with iso.open('rb') as src:
            shutil.copyfileobj(src, f, 1024 * 1024)
        for index, (name, source, size) in enumerate(items, 2):
            typ = '88434509-d9d1-487d-b82c-15ef964cbd4b' if name == 'vbmeta_a' else '0fc63daf-8483-4772-8e79-3d69d8477de4'
            attrs = (15 << 48) | (1 << 56) if name == 'vbmeta_a' else 0
            entry = ENTRY.pack(uuid.UUID(typ).bytes_le, uuid.uuid4().bytes_le, cursor // SECTOR,
                               (cursor + size) // SECTOR - 1, attrs, name.encode('utf-16-le'))
            entries[index * 128:(index + 1) * 128] = entry
            f.seek(cursor)
            with source.open('rb') as src:
                shutil.copyfileobj(src, f, 1024 * 1024)
            layout.append(dict(name=name, offset=cursor, size=size))
            cursor += size
        # ISO partition is entry index 1, written last so its GUID is final.
        entry = ENTRY.pack(uuid.UUID('ebd0a0a2-b9e5-4433-87c0-68b6b72699c7').bytes_le, iso_part.bytes_le,
                           34, 34 + iso_size // SECTOR - 1, 0, 'ISO9660'.encode('utf-16-le'))
        entries[128:256] = entry
        h = [b'EFI PART', 0x10000, 92, 0, 0, 1, 0, 34, 0,
             uuid.uuid4().bytes_le, 2, 128, 128, 0]
        h[6] = cursor // SECTOR + 32
        h[8] = cursor // SECTOR - 1
        primary, secondary = tables(h, entries, protective_mbr(h[6]))
        f.truncate((h[6] + 1) * SECTOR)
        f.seek(0)
        f.write(primary)
        f.seek(cursor)
        f.write(secondary)
        f.flush()
        os.fsync(f.fileno())
    with image.open('rb') as f:
        from lapis.gpt import read_gpt
        read_gpt(f, image.stat().st_size)
    report = dict(image=image.name, sha256=sha256(image), size=image.stat().st_size,
                  iso_sha256=ISO_SHA256, iso_volume_uuid=ISO_VOLUME_UUID, cmdline=cmdline,
                  android_partitions=layout, included_credentials=False,
                  internal_disk_writes=False,
                  status='Built and structurally checked; test this image on hardware before installing')
    save_json(image.with_suffix('.manifest.json'), report, 0o644)
    image.with_suffix('.sha256').write_text(report['sha256'] + '  ' + image.name + '\n')
    print('Created', image, '\nSHA256', report['sha256'])


if __name__ == '__main__':
    from tools.fetch_sources import SOURCES
    main()
