run_latehook() {
    mkdir -p /new_root/opt/cachyos-googlebook /new_root/etc/modprobe.d /new_root/etc/modules-load.d
    cp -a /lapis-kit/. /new_root/opt/cachyos-googlebook/ || return 1
    printf 'coreboot_table\nframebuffer_coreboot\ncorebootdrm\n' > /new_root/etc/modules-load.d/lapis-framebuffer.conf
    printf 'blacklist xe\nblacklist snd_sof_pci_intel_ptl\noptions xe gsc_firmware_path= enable_panel_replay=0 enable_psr=0 enable_fbc=0 enable_dsb=0 enable_sagv=0 enable_dc=0\n' > /new_root/etc/modprobe.d/lapis-live.conf
    mkdir -p /new_root/etc/systemd/system/multi-user.target.wants
    cp /lapis-kit/assets/live/prepare-live.service /new_root/etc/systemd/system/cachyos-live-prepare.service
    ln -sf ../cachyos-live-prepare.service /new_root/etc/systemd/system/multi-user.target.wants/cachyos-live-prepare.service
    # The stock login manager must not start before the checked GPU sequence.
    ln -sf /dev/null /new_root/etc/systemd/system/display-manager.service
    ln -sf /dev/null /new_root/etc/systemd/system/plasmalogin.service
    # The stock full-disk installer cannot handle the Googlebook factory layout.
    if [ -e /new_root/usr/bin/calamares ]; then
        printf '#!/bin/sh\necho "The stock installer cannot install to the Googlebook factory layout."\necho "Use /opt/cachyos-googlebook/tools/native.py from this live session instead."\nexit 1\n' > /new_root/usr/bin/calamares
        chmod 755 /new_root/usr/bin/calamares
    fi
    printf '\nCachyOS on ASUS Googlebook Lapis -- live test. The internal disk is untouched.\n'
    printf 'Desktop starts on tty2 after graphics preparation. Root console: Ctrl+Alt+F1.\n' > /new_root/etc/issue.d/lapis-live.issue
}
