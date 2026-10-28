# Maintenance and troubleshooting

## Daily boot

Keep developer mode enabled. Choose internal boot on the startup screen, then enter the disk password. The tested firmware had internal boot as its default. Upstream Depthcharge normally uses a developer-screen timeout; that automatic timeout was not physically timed on the test unit, so this guide does not promise an unattended duration.

## Updates

The installed kernel and headers are pinned, and a Pacman pre-transaction hook blocks installing/removing/replacing files matching `usr/lib/modules/*/vmlinuz`. This prevents a new kernel's modules from replacing the kernel still inside the Android boot partitions. Do not disable that guard just to complete an update.

Ordinary user-space updates can still contain CachyOS migrations that assume Limine or an EFI system partition. **A full CachyOS update has not been validated.** Review the proposed packages and boot-related migrations before applying them, keep recovery media ready, and make a filesystem snapshot. A read-only dependency preview during original development found no kernel replacement; no updates were applied as part of that check.

The pin is temporary compatibility debt, including missed kernel fixes. A supported kernel upgrade needs all of: compatible modules and firmware, a small rebuilt initramfs, new Android v4 images, correct ramdisk alignment, AVB signing, a loader test, backup/read-back of exact changed regions, and physical restart/cold-boot checks. The fresh-install commands intentionally do not implement a repeatable upgrade path against an already-modified GPT.

Do not run standard Limine installation, CachyOS factory reset, or boot-menu snapshot restore. This firmware uses Android images. Snapper filesystem snapshots work; restoring one is a manual live-USB recovery operation. A root snapshot does not roll back the separate Android boot partitions or the independently mounted home/log/package-cache subvolumes.

## Black display

From a text console, inspect `journalctl -b -u cachyos-gpu-prepare.service` (installed) or `journalctl -b -u cachyos-live-prepare.service` (live). The service deliberately refuses forced driver removal or unloading while a client holds DRM nodes. It soft-blacklists Xe and SOF audio, loads Xe, releases framebuffer references, unloads it normally, reloads once, then permits audio binding and the display manager.

Do not run the reload routine inside an active desktop. A failed prerequisite should be investigated from the live USB, not bypassed. Kernel/firmware updates may eventually replace this workaround, but they require new hardware tests.

## Refresh rate

The installer defaults to 2880×1800 at 60 Hz, scale 2. The tested BOE NB140B91-M04 panel also ran steadily at 120 Hz with AirPlay disconnected. A brief blank or flash at the moment of switching occurred in the observed test; the image stayed steady between changes. Repeated flashing while the mode stays unchanged was not reproduced in that test.

To use the tested 120 Hz setting, This fork installs the CachyOS Plasma desktop, which follows the panel's preferred mode; no monitor-rule file is installed by the fork. To pin a specific rate, use the desktop's Display Configuration (or `kscreen-doctor -o` to inspect). The upstream 120 Hz observations were made under Hyprland with `hl.monitor({ output = "eDP-1", mode = "2880x1800@120", position = "0x0", scale = 2 })`; the same panel rules of thumb apply. No kernel change or Xe reload is needed for this setting. AirPlay, cold boot and suspend/resume at 120 Hz remain unverified.

## Audio

The tested audio subsystem is ASUS `1043:15e4`. For the ISO's SOF topology, `snd_soc_sof_sdw quirk=0x288000` and `snd_sof_intel_hda_generic dmic_num=0` avoid two nonexistent PCH microphone links shifting all later backend IDs. The real CS42L43 SoundWire microphone path remains described, but microphone capture is untested.

Inspect `cat /proc/asound/cards`, `wpctl status` and relevant SOF journal lines. Speaker playback was confirmed and persisted over reboot. An unused Bluetooth-offload PCM may still log probe warnings; disabling that unused PipeWire node is not a test of ordinary Bluetooth audio. Do not raise volume aggressively to compensate for missing amplifiers or tuning firmware.

## Networking and SSH

Connect Wi-Fi with the installed desktop menu or `nmtui`; the installer does not reuse live credentials. NetworkManager owns wireless on the installed system and uses the wpa_supplicant backend (its default, and the configuration hardware-validated on this board). iwd is intentionally not installed in the target; do not enable `iwd.service` alongside NetworkManager. The live ISO ships iwd for `iwctl` use before the desktop is up, which is unrelated to the installed system. Automatic EFI discovery is disabled so the factory ESP cannot derail startup services.

SSH starts masked. If you deliberately want remote access, configure your own account/public key, firewall policy and key-only SSH settings before unmasking/enabling it. No shared maintenance key is provided.
