# Validation record

## Physical evidence: original procedure

On 7 October 2026, one 512 GB ASUS CX9406CAA / Google Lapis completed the original (Omarchy) staged installation. The full Omarchy desktop booted from the internal encrypted drive with USB removed. The owner confirmed the desktop and audible speaker playback. A subsequent internal boot retained the display, Wi-Fi and audio fixes and had no failed systemd units. A graphics shader/pixel-readback test, Snapper snapshot creation and snapshot cleanup passed.

The working live USB also passed a restart and cold-start graphics test. Before internal installation, the Android loader accepted the native candidate, a disposable encrypted-root QEMU fixture reached its init program, and each committed disk region passed read-back. Original logs and disk backups remain private; they are not included here.

A subsequent display test on the BOE NB140B91-M04 panel verified 2880×1800 at 120 Hz in both the Hyprland desktop and the kernel's active display state (upstream). With AirPlay disconnected, the owner confirmed a steady image between the brief flashes at the beginning and end of an approximately 18-second test. The before/during/after kernel captures contained no new messages. The desktop setting was then saved at 120 Hz, scale 2; configuration checks passed and the owner confirmed steady scrolling and window movement. A 60 Hz configuration backup was retained. The existing Xe/Aquamarine workarounds were unchanged; VRR remained disabled. This was a session test, not a 120 Hz reboot, suspend or AirPlay test.

## Fork physical evidence: CachyOS live image (28 October 2026)

The CachyOS live image built by this repository (pinned ISO 260809, live kernel `7.1.6-1-cachyos`, stock Plasma live session) was written to a USB stick with `tools/write_usb.py` and booted on the same physical Lapis from the developer-mode external-boot entry. The firmware accepted the Android boot set, the checked Xe bring-up service ran, and the Plasma live desktop started with the internal disk untouched. This validates the fork live-boot path on hardware.

## Fork physical evidence: native installation (28 October 2026)

The complete staged procedure — plan, backup, format, packages, configure, loader-harness build in the target chroot, build, validate, commit --apply — was executed on the same physical Lapis on 28 October 2026, replacing a previous Omarchy installation. Reinstall mode was detected and handled: the earlier install's `factory_pvmfw_a/b` label renames were tolerated, and its boot partitions were preserved in the backup as the rollback target. `commit --apply` passed read-back verification for all four slot-A images, both GPT label regions and the misc sector. The installed system then booted from internal storage with the USB removed: LUKS2 unlock at the text prompt, the checked Xe GPU sequence, and plasmalogin autologin into the CachyOS Plasma desktop on the installed `linux-cachyos 7.2.7-1` kernel — the first hardware test of that kernel.

Two package-set defects were found and fixed during this run (a package name that does not exist in any repository, aborting target resolution before any write; and a service-disable list entry for a unit not present in the fork's target package set). Both fixes are part of this repository. Because those fixes were applied mid-run, the exact current commit has not itself completed a from-scratch rerun; the procedure, ordering and safety machinery were what ran.

In development, a first live image version failed with an instant silent restart: the initramfs patch recompressed the xz main cpio and the kernel XZ decoder rejected the result, so `/init` never ran. This was reproduced in QEMU direct-kernel boots and fixed by appending an uncompressed cpio segment instead of recompressing (see `tools/build_live.py`). The QEMU boot check in the README exists to catch that class of regression.

## Public repository checks

The generalized source toolkit is tested separately from that original installation:

- Python safety tests cover corrupted GPT headers/entries, overlapping/out-of-bounds partitions, duplicate labels, minimal label renaming, USB capacity relocation, refusal of device/existing/symlink outputs, CPIO overrides/path rejection, unsupported layouts and short writes.
- An injected partial boot-write failure checks restoration of **every attempted region**, including the partly written region.
- The tests pass both normally and under `python3 -O`, confirming safety checks do not depend on assertions.
- The ChromiumOS loader harness builds from pinned upstream source on macOS, including from the exact filtered source payload embedded in the live image.
- A complete live image was built from the checksum-pinned ISO. AVB signature/hash verification passed for all boot components, both GPTs validated, and `vb2api_load_kernel() returned 0` on the final disk image.
- QEMU booted the loader-assembled live ramdisk and read-only USB image through to the live serial login in 39 seconds, with no initramfs unpacking error and no network attached. The hardware-specific desktop service is expected to reject a VM's non-Lapis identity; this validates the boot/archive/live-root path only.
- Tracked-file checks reject common secret material, private local paths, oversized files and disk/key artifacts. A manual review complements those checks; pattern scans are not a guarantee against every possible secret.

GitHub Actions runs the safety suite and loader build on Linux and macOS. See the Actions tab for actual results of the current commit. The multi-gigabyte ISO and physical boot are not part of CI.

## Not established by these checks

The generalized public installer has **not** completed a second fresh physical installation. The public USB writer has not been used to overwrite the already-working test drive. No generalized-script test authorizes writes to a different board, firmware or capacity. The original laptop was not reinstalled merely to publish this repository.

This release does not claim suspend/resume, camera, microphone capture, external displays, Bluetooth/headphone playback, battery-life tuning, a complete future update path or a tested factory restore. See [support.md](support.md) for the full matrix.
