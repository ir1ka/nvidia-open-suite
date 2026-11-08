#!/bin/bash
# Disposable containers only. /lib/modules and /boot must be tmpfs, no GPU.
set -euo pipefail
: "${TARGET_KERNEL:?}" "${DEB_PATH:?}"
mkdir -p /out/validation /out/modules/$TARGET_KERNEL
trap 'find /var/lib/dkms/nvidia-open-suite -name make.log -type f -exec cp "{}" /out/validation/build-$TARGET_KERNEL.log \; 2>/dev/null || :' EXIT
if [ "$TARGET_KERNEL" = 7.0.0-30-generic ];then
 dpkg --force-unsafe-io -i /opt/kernel-debs/*.deb
 ln -sfn /usr/src/linux-headers-$TARGET_KERNEL /lib/modules/$TARGET_KERNEL/build
else
 apt-get update -qq
 DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gcc-14 > /out/validation/gcc-14-install.log
 export CC=gcc-14
 # Noble's pahole predates Debian's BTF feature flags. This is a container
 # cross-build-only debug-info choice, not a delivered DKMS build policy.
 export MAKEFLAGS='CONFIG_DEBUG_INFO_BTF_MODULES='
 printf '%s\n' 'Container cross-build: gcc-14; optional module BTF disabled for Noble pahole compatibility' > /out/validation/build-$TARGET_KERNEL.flags
 mkdir -p /lib/modules/$TARGET_KERNEL
 ln -s /usr/src/linux-headers-$TARGET_KERNEL /lib/modules/$TARGET_KERNEL/build
 ln -s /usr/src/linux-headers-6.12.113+deb13-common /lib/modules/$TARGET_KERNEL/source
fi
# Matching firmware-nvidia-gsp dependency must already be installed in this container.
dpkg --force-unsafe-io -i "$DEB_PATH"
[ ! -f /etc/initramfs-tools/conf.d/nvidia-open-suite ]
[ ! -f /etc/nvidia-open-suite/p2p.json ]
[ "$(modinfo -k "$TARGET_KERNEL" -F nvidia_open_suite nvidia)" = 2.0.0 ]
[ -z "$(modinfo -k "$TARGET_KERNEL" -F pf_bar_in_nvidia nvidia)" ]
for name in nvidia nvidia-modeset nvidia-drm nvidia-uvm nvidia-peermem;do
 file=$(modinfo -k "$TARGET_KERNEL" -n "$name")
 modinfo "$file" > /out/modules/$TARGET_KERNEL/$name.modinfo
 case "$file" in *.zst)zstd -dc "$file" > /out/modules/$TARGET_KERNEL/$name.ko;;*.xz)xz -dc "$file" > /out/modules/$TARGET_KERNEL/$name.ko;;*)cp "$file" /out/modules/$TARGET_KERNEL/$name.ko;;esac
done
find /var/lib/dkms/nvidia-open-suite -name make.log -type f -exec cp '{}' /out/validation/build-$TARGET_KERNEL.log \;
[ -f /etc/modprobe.d/nvidia-open-suite.conf ]
[ ! -e /usr/share/initramfs-tools/hooks/nvidia-open-suite ]
[ ! -e /usr/sbin/nvidia-open-suite ]
# Same autoinstall path used by future kernel/header updates.
dkms remove -m nvidia-open-suite -v 610.43.02+suite.2.0.0 -k "$TARGET_KERNEL"
dkms autoinstall -k "$TARGET_KERNEL"
[ "$(modinfo -k "$TARGET_KERNEL" -F nvidia_open_suite nvidia)" = 2.0.0 ]
dpkg --force-unsafe-io --remove nvidia-open-suite-dkms
[ -f /etc/modprobe.d/nvidia-open-suite.conf ]
if dkms status -m nvidia-open-suite | grep -q .;then exit 1;fi
dpkg --purge nvidia-open-suite-dkms
[ ! -e /etc/modprobe.d/nvidia-open-suite.conf ]
printf '%s\n' 'PASS: five actual modules compiled/installed and autoinstalled; no suite hook or tools; standard remove/purge; no module load' > /out/validation/build-$TARGET_KERNEL.result
