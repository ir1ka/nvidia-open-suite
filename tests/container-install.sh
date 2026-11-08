#!/bin/bash
# Isolated source/apt takeovers. No host module tree, /boot or GPU passthrough.
set -euo pipefail
: "${MODE:=manual}"
kernel=7.0.0-30-generic
mkdir -p /work /out/validation
trap 'find /var/lib/dkms/nvidia-open-suite -name make.log -type f -exec cp "{}" /out/validation/'"$MODE"'-install-make.log \; 2>/dev/null || :' EXIT
dpkg --force-unsafe-io -i /opt/kernel-debs/*.deb
ln -sfn /usr/src/linux-headers-$kernel /lib/modules/$kernel/build
if [ "$MODE" = managed ];then
 mkdir -p /work/original/DEBIAN /work/original/usr/src
 cp -a /original /work/original/usr/src/nvidia-610.43.02
 chmod -R u+w /work/original/usr/src/nvidia-610.43.02
 cat > /work/original/DEBIAN/control <<'EOF'
Package: nvidia-kernel-dkms
Version: 610.43.02
Architecture: amd64
Maintainer: Test <root@localhost>
Description: Isolated original NVIDIA provider fixture
EOF
 cat > /work/original/DEBIAN/postinst <<'EOF'
#!/bin/sh
set -eu
dkms add -m nvidia -v 610.43.02
dkms build -m nvidia -v 610.43.02 -k 7.0.0-30-generic -j 8
dkms install -m nvidia -v 610.43.02 -k 7.0.0-30-generic
EOF
 cat > /work/original/DEBIAN/prerm <<'EOF'
#!/bin/sh
set -eu
if dkms status -m nvidia -v 610.43.02 | grep -q .;then dkms remove -m nvidia -v 610.43.02 --all;fi
EOF
 chmod 755 /work/original/DEBIAN/{postinst,prerm}
 dpkg-deb --build /work/original /work/original.deb
 dpkg --force-unsafe-io -i /work/original.deb
 mkdir -p /work/meta/DEBIAN
 cat > /work/meta/DEBIAN/control <<'EOF'
Package: test-nvidia-userland-meta
Version: 1
Architecture: all
Maintainer: Test <root@localhost>
Depends: nvidia-kernel-dkms (= 610.43.02)
Description: Keep userland dependency during provider replacement
EOF
 dpkg-deb --build /work/meta /work/meta.deb
 dpkg --force-unsafe-io -i /work/meta.deb
 # Model an installed interface-only source after a valid original install.
 # No attempt to patch or execute its precompiled RM bytes is permitted.
 rm -rf /usr/src/nvidia-610.43.02/src
 printf 'precompiled-RM-fixture\n' > /usr/src/nvidia-610.43.02/kernel-open/nvidia/nv-kernel.o_binary
else
 cp -a /original /usr/src/nvidia-610.43.02
 chmod -R u+w /usr/src/nvidia-610.43.02
 dkms add -m nvidia -v 610.43.02
 dkms build -m nvidia -v 610.43.02 -k "$kernel" -j 8
 dkms install -m nvidia -v 610.43.02 -k "$kernel"
fi
if [ "$MODE" != managed ]; then
 if python3 /suite/nvidia-open-suite/bin/nvidia-open-suite install --kernel "$kernel" --archive /archive.tar.gz --work /work/new > /out/validation/manual-refusal.log 2>&1; then exit 1;fi
 dkms status -m nvidia -v 610.43.02 | grep -q installed
 [ -f /usr/src/nvidia-610.43.02/dkms.conf ]
 echo 'PASS: unmanaged provider preserved and refused' > /out/validation/manual-install.result
 exit 0
fi
python3 /suite/nvidia-open-suite/bin/nvidia-open-suite install --kernel "$kernel" --archive /archive.tar.gz --work /work/new
[ "$(modinfo -k "$kernel" -F nvidia_open_suite nvidia)" = 2.1.0 ]
[ -z "$(modinfo -k "$kernel" -F pf_bar_in_nvidia nvidia)" ]
[ ! -f /etc/initramfs-tools/conf.d/nvidia-open-suite ]
[ ! -f /etc/nvidia-open-suite/p2p.json ]
if dkms status -m nvidia -v 610.43.02 | grep -q .;then exit 1;fi
if [ "$MODE" = managed ];then
 dpkg-query -W -f='${db:Status-Status}' test-nvidia-userland-meta | grep -q installed
 grep -q '"source_origin": "official-fallback"' /work/new/patched-source/nvidia-suite-source.json
else
 grep -q '"source_origin": "installed-full-source"' /work/new/patched-source/nvidia-suite-source.json
fi
cp /work/new/result.json /out/validation/$MODE-install-result.json
printf '%s\n' "PASS: $MODE original DKMS provider verified, all-patch source prepared, five modules installed by unified command; no reload and early-boot/P2P opt-in off" > /out/validation/$MODE-install.result
