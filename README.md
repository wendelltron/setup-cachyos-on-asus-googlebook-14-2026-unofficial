# CachyOS on the ASUS Googlebook (Lapis)

Run **CachyOS** (Arch-based, KDE Plasma) on the **ASUS Googlebook 14**
(CX9406CAA, board codename "Lapis") on **factory depthcharge firmware** with
an **unlocked bootloader**.

This is a fork of
[asus-googlebook-omarchy](https://github.com/jonathankleiman/asus-googlebook-omarchy)
(Jonathan Kleiman, MIT) that replaces the Omarchy payload with CachyOS while
keeping the hardware layer that makes Linux boot on this platform. The boot
science — the AVB-signed Android boot-set format, the checked Xe GPU
sequence, the audio quirks, the staged install with per-stage rollback —
is the upstream project's work. This fork changes the distribution, not
that. Unaffiliated with ASUS, Google, or CachyOS.

## Status

- **Live image verified on hardware (28 October 2026)**: the firmware
  accepted the external boot set, the checked Xe bring-up ran, and the stock
  CachyOS Plasma live desktop started with the internal disk untouched.
- **Native installation verified on hardware (28 October 2026)**: the full
  staged procedure (plan / backup / format / packages / configure / loader
  build / build / validate / commit) replaced a previous Omarchy
  installation on the same device in reinstall mode, and the installed
  system boots from internal storage with the USB removed — LUKS2 unlock,
  the checked Xe sequence, and plasmalogin autologin into Plasma on the
  pinned `linux-cachyos 7.2.7-1` kernel (its first hardware test).
- The upstream (Omarchy) live and installed paths were verified on one
  physical Lapis on 7 October 2026 (see `docs/support.md`).
- Still open: a from-scratch rerun of the exact current commit (the
  28 October run surfaced two package-list defects that are fixed in this
  repository), and the items marked untested in `docs/support.md`
  (suspend/resume, camera, Bluetooth audio, battery tuning, full-update
  path).

## How boot works here

Depthcharge on Lapis does not boot classic ChromeOS vboot (`CHROMEOS`
keyblock) images and cannot boot a plain ISO or EFI payload. It boots
**AVB-signed Android v4 boot images** (`boot_a`, `init_boot_a`,
`vendor_boot_a`, `vbmeta_a`) from the factory GPT, slot A. The builder:

1. Takes the checksum-pinned CachyOS desktop ISO (its payload is kept
   byte-for-byte as a partition, so the online installer and package set
   work unmodified).
2. Patches the live initramfs by **appending** an uncompressed cpio segment
   (a patched mkinitcpio `config` that adds the `lapis` late hook, the hook
   itself, and the install kit). The original xz archive is never
   recompressed — a recompressed stream is rejected by the kernel's XZ
   decoder and the board reboots instantly with no output. (This failure
   mode is covered by the QEMU regression check below.)
3. Wraps everything in a synthetic GPT (the CachyOS ISO is MBR/ISOLINUX):
   ISO partition, then the four boot images signed with a fresh local AVB
   key (trusted because the bootloader is unlocked), with `vbmeta_a` marked
   preferred.
4. Validates the final image through the real ChromiumOS
   `vb2api_load_kernel()` loader code before it is written anywhere.

## What is the same as upstream

`lapis/boot.py` (boot-set builder), `lapis/gpt.py`, `lapis/cpio.py`,
`tools/write_usb.py` (validated USB writer), `tools/build_loader.py` +
`tools/loader_harness.c` (host-side loader validation), `tools/native.py`
(staged install: plan/backup/format/build/validate/commit with dry-runs,
typed confirmations, read-back verification and rollback), and the checked
**Xe GPU sequence** in `assets/` — load xe with the hardware-verified
parameters, one checked unload/reload, audio ordered after graphics.

## What changed for CachyOS

| Piece | Upstream (Omarchy) | This fork |
|---|---|---|
| Live ISO | Omarchy 4.0.4 (GPT hybrid) | CachyOS desktop 260809 (MBR/ISOLINUX) |
| ISO integration | edit ISO's own GPT | synthetic GPT, ISO as one partition |
| Live kernel | `7.2.4-arch1-Watanare-T2-3-t2` | `7.1.6-1-cachyos` (pinned, sha256-checked) |
| Installed kernel | `linux-t2 7.2.4-3` | `linux-cachyos 7.2.7-1` (pinned packages) |
| Live desktop | custom Hyprland in RAM | stock CachyOS Plasma (plasmalogin autologin) behind the checked GPU sequence |
| Package stage | omarchy manifest + provisioner | pinned CachyOS package list, hand-rolled config, online install |
| Root mapper name | `omarchy_root` | `cachyos_root` |
| Kit path on target | `/opt/asus-googlebook-omarchy` | `/opt/cachyos-googlebook` |

Pins (all sha256-verified at build time):

| Artifact | SHA-256 |
|---|---|
| `cachyos-desktop-linux-260809.iso` | `959f6577f45e25ee9fd8c220fd221b08e4ea79412c7315c0f922dd6d86d5e33c` |
| live `vmlinuz-linux-cachyos` (7.1.6-1) | `1e9521170efcc2c26e34adc0e58051aa771726bb0b411f44296987051e180ba2` |
| `linux-cachyos-7.2.7-1` package | `cb164037efbdc8703580da9cca2a1f067e22a0ffc8a0fc1b7c03d4419e99fd37` |
| `linux-cachyos-headers-7.2.7-1` package | `14cdee3a743e7792200331c530bd71eb0b1b244b06c7244308afe3c67b869229` |

The ISO's archiso search UUID is pinned too: `2026-08-09-15-47-03-00`.

## Build the live USB

Requirements: Python 3.10+, git, openssl, zstd, bsdtar/libarchive, make, a C
compiler, ~20 GB free. Linux or macOS.

```sh
git clone <this repository> asus-googlebook-cachyos
cd asus-googlebook-cachyos
mkdir -p downloads build
curl --fail --location --output downloads/cachyos-desktop-linux-260809.iso \
  https://mirror.zyner.org/cachyos/ISO/desktop/260809/cachyos-desktop-linux-260809.iso
python3 tools/fetch_sources.py
python3 tools/build_loader.py
python3 tools/build_live.py --iso downloads/cachyos-desktop-linux-260809.iso --output build/lapis-cachyos-live.img
```

Validate through the firmware's Android loader:

```sh
cd build && ./load_android_test -b 1 lapis-cachyos-live.img && cd ..
```

Expect `vb2api_load_kernel() returned 0`. Then write a dedicated USB stick
(16 GB+, whole device, never a partition):

```sh
sudo python3 tools/write_usb.py --image build/lapis-cachyos-live.img --device /dev/sdX          # dry run
sudo python3 tools/write_usb.py --image build/lapis-cachyos-live.img --device /dev/sdX --apply  # erases the stick
```

### Optional but recommended: QEMU boot check

Boot the built kernel + initramfs pair under QEMU with a serial console.
The kernel must unpack the initramfs, run the archiso hooks, and reach the
media-search stage (the ISO is not attached, so "Device not found" there is
expected; a panic or "Initramfs unpacking failed" is not):

```sh
cd build/lapis-cachyos-live.build
qemu-system-x86_64 -enable-kvm -cpu host -m 8G -nodefaults -no-reboot \
  -kernel vmlinuz-linux-cachyos -initrd live-initramfs.img \
  -append "archisobasedir=arch console=ttyS0,115200 loglevel=7" \
  -serial stdio -display none
```

This catches initramfs-encoder regressions in seconds instead of after a
stick write and a hardware boot.

## Test on hardware

Unlock prerequisites and boot steps are identical to upstream: developer
mode, **Boot from external drive** on the dev screen. First boot copies the
ISO payload to RAM (`copytoram`) — the CachyOS logo can sit for a while; do
not remove the stick. Success checks at the root console (Ctrl+Alt+F1):

```sh
cat /sys/class/dmi/id/product_name   # Lapis
uname -r                             # 7.1.6-1-cachyos
systemctl status cachyos-live-prepare.service
```

The live desktop is stock Plasma with autologin (`liveuser`); Wi-Fi connects
from the network applet or `nmtui`/`iwctl` on the root console.

## Native install

Same staged procedure as upstream — see `docs/install.md`. It replaces
Googlebook OS and formats userdata: read the whole guide first, keep factory
recovery media and an external backup drive, stay on AC power, and never
relock the bootloader. Short version, from the live root console:

```sh
sudo -i
cd /opt/cachyos-googlebook
python3 tools/native.py plan --device /dev/nvme0n1
python3 tools/native.py backup --destination /run/media/backup/lapis-original
python3 tools/native.py format && python3 tools/native.py format --apply
python3 tools/configure_target.py packages --user <you> --name '<Name>' --timezone <Area/City>
python3 tools/configure_target.py configure
# Copy the kit into the target and build the loader harness there
# (the compiler lives in the target; the live session has none):
mkdir -p /mnt/opt/lapis-kit
cp -a /opt/cachyos-googlebook/. /mnt/opt/lapis-kit/
arch-chroot /mnt python3 /opt/lapis-kit/tools/build_loader.py
python3 tools/native.py build
python3 tools/native.py validate --loader /mnt/opt/lapis-kit/build/load_android_test
python3 tools/native.py commit --apply
```

The package stage is online — connect Wi-Fi first. Full details and
failure recovery: `docs/install.md`.

## Repository layout

```
lapis/            boot-set builder, cpio, GPT, shared helpers
tools/            build_live, build_loader, native, configure_target, write_usb, fetch_sources
assets/live/      initramfs late hook, live GPU-prepare service + script
assets/installed/ installed-side GPU sequence, mkinitcpio.conf
assets/lapis-512gb.json   factory partition profile (unchanged from upstream)
docs/             install, live-usb, recovery, maintenance, support, validation guides
tests/            safety tests (unittest)
```

## Maintenance notes

The installed kernel and headers are pinned and a pacman hook blocks kernel
replacement — on this platform a kernel update must be followed by a rebuild
and re-sign of the Android boot set. See `docs/maintenance.md`. Do not run
standard bootloader installers or factory reset tools on this machine.
