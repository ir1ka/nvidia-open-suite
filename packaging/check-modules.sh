#!/bin/bash
# Verify outputs before DKMS can install them. This never loads a module.
set -euo pipefail
kernel=${1:?explicit kernel ABI required}
for name in nvidia nvidia-modeset nvidia-drm nvidia-uvm nvidia-peermem;do
 file=kernel-open/$name.ko
 [ "$(modinfo -F version "$file")" = @DRIVER_VERSION@ ] || { echo "Wrong NVIDIA version: $file" >&2;exit 1; }
 [ "$(modinfo -F vermagic "$file" | cut -d ' ' -f1)" = "$kernel" ] || { echo "Wrong kernel ABI: $file" >&2;exit 1; }
done
[ "$(modinfo -F nvidia_open_suite kernel-open/nvidia.ko)" = 2.1.0 ] || { echo 'Suite marker missing' >&2;exit 1; }
[ "$(modinfo -F full_bar1_p2p kernel-open/nvidia.ko)" = 1.0.0-explicit-opt-in ] || { echo 'P2P marker missing' >&2;exit 1; }
[ -z "$(modinfo -F pf_bar_in_nvidia kernel-open/nvidia.ko)" ] || { echo 'Unexpected embedded PF recovery' >&2;exit 1; }
[ -z "$(modinfo -F pf_bar_scope kernel-open/nvidia.ko)" ] || { echo 'Unexpected NVIDIA PF scope' >&2;exit 1; }
echo "Verified all five CMP/P2P NVIDIA modules, without embedded PF recovery, for $kernel"
