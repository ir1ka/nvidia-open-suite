#!/bin/bash
# Disposable container only. Real APT/dpkg; fixture DKMS, no actual module build/load.
# /boot and /lib/modules must be container tmpfs, never host mounts.
set -euo pipefail
: "${DEB_PATH:?}"; : "${TOOLS_PATH:?}"; : "${OUT:=/out}"
mkdir -p "$OUT" /work /lib/modules/fixture-kernel/build/include
printf 'fixture headers; no kernel build\n' > /lib/modules/fixture-kernel/build/Makefile
# Only DKMS/initramfs side effects are fixtures; package solving/removal is real.
cat > /usr/sbin/dkms <<'PY'
#!/usr/bin/python3
import json,sys,shutil
from pathlib import Path
p=Path('/work/dkms-state.json');state=json.loads(p.read_text())if p.exists()else{}
a=sys.argv[1:];action=a[0]
with Path('/work/dkms-calls').open('a')as f:f.write(' '.join(a)+'\n')
def value(flag,default=None):return a[a.index(flag)+1]if flag in a else default
m,v=value('-m'),value('-v');key=m+'/'+v if m and v else None
if action=='status':
 for k,s in state.items():
  if key and key!=k:continue
  print(k+': added'if s=='added'else k+', fixture-kernel, x86_64: '+s)
elif action in ('add','build','install'):
 assert key;state[key]={'add':'added','build':'built','install':'installed'}[action]
 if action=='add':
  d=Path('/var/lib/dkms')/m/v;d.mkdir(parents=True,exist_ok=True)
  link=d/'source'
  if not link.exists():link.symlink_to('/usr/src/'+m+'-'+v)
elif action=='remove':
 state.pop(key,None)
 if m and v:shutil.rmtree(Path('/var/lib/dkms')/m/v,ignore_errors=True)
else:raise SystemExit('Unexpected DKMS fixture command')
p.write_text(json.dumps(state))
PY
chmod 755 /usr/sbin/dkms
cat > /usr/sbin/update-initramfs <<'EOF2'
#!/bin/sh
printf '%s\n' "$*" >> /work/initramfs-calls
EOF2
chmod 755 /usr/sbin/update-initramfs
for name in rmmod reboot;do
 rm -f /usr/sbin/"$name"
 printf '#!/bin/sh\necho "Unexpected live module/reboot action" >&2\nexit 97\n' > /usr/sbin/"$name"
 chmod 755 /usr/sbin/"$name"
done
rm -f /usr/sbin/modprobe
cat > /usr/sbin/modprobe <<'EOF2'
#!/bin/sh
if [ "${1:-}" = --showconfig ];then
 for f in /etc/modprobe.d/*.conf;do [ ! -f "$f" ] || cat "$f";done
 exit 0
fi
echo 'Unexpected module load' >&2;exit 97
EOF2
chmod 755 /usr/sbin/modprobe
fixture() {
 local name=$1 version=$2 extra=$3 dir=/work/package-$1
 mkdir -p "$dir/DEBIAN"
 {
  printf 'Package: %s\nVersion: %s\nArchitecture: amd64\nMaintainer: Test <root@localhost>\n' "$name" "$version"
  [ -z "$extra" ] || printf '%s\n' "$extra"
  printf 'Description: isolated APT relationship fixture\n'
 } > "$dir/DEBIAN/control"
}
# Tools must install without the driver or firmware.
apt-get --yes install "$TOOLS_PATH" > "$OUT/tools-install.log" 2>&1
! dpkg-query -W -f='${Status}' nvidia-open-suite-dkms 2>/dev/null | grep -q 'install ok installed'
nvidia-open-suite --help > "$OUT/tools-help.log"
fixture firmware-nvidia-gsp 610.43.02-1 ''
dpkg-deb --build /work/package-firmware-nvidia-gsp /work/firmware.deb >/dev/null
dpkg -i /work/firmware.deb >/dev/null
fixture nvidia-kernel-open-dkms 610.43.02-1 'Depends: dkms'
cat > /work/package-nvidia-kernel-open-dkms/DEBIAN/postinst <<'EOF2'
#!/bin/sh
set -e
dkms add -m nvidia -v 610.43.02
EOF2
cat > /work/package-nvidia-kernel-open-dkms/DEBIAN/prerm <<'EOF2'
#!/bin/sh
set -e
dkms remove -m nvidia -v 610.43.02 --all
EOF2
chmod 755 /work/package-nvidia-kernel-open-dkms/DEBIAN/{postinst,prerm}
fixture test-nvidia-meta 1 'Depends: nvidia-kernel-open-dkms (= 610.43.02-1)'
fixture nvidia-open 610.43.02-1 $'Depends: test-nvidia-meta, nvidia-kernel-open-dkms (>= 610.43.02)\nConflicts: nvidia-kernel-dkms'
fixture unrelated-service-fixture 1 ''
for name in nvidia-kernel-open-dkms test-nvidia-meta nvidia-open unrelated-service-fixture;do
 dpkg-deb --build /work/package-"$name" /work/"$name".deb >/dev/null
done
dpkg -i /work/nvidia-kernel-open-dkms.deb /work/test-nvidia-meta.deb /work/nvidia-open.deb /work/unrelated-service-fixture.deb > "$OUT/fixture-install.log"
# Show why upstream-only versioned Provides is insufficient for exact distro dependencies.
fixture wrong-provides-fixture 1 $'Provides: nvidia-kernel-open-dkms (= 610.43.02)\nConflicts: nvidia-kernel-open-dkms'
dpkg-deb --build /work/package-wrong-provides-fixture /work/wrong-provides.deb >/dev/null
apt-get -s install /work/wrong-provides.deb > "$OUT/wrong-version-simulation.log"
grep -q '^Remv test-nvidia-meta ' "$OUT/wrong-version-simulation.log"
apt-get -s install "$DEB_PATH" > "$OUT/apt-simulation.log"
! grep -q '^Remv test-nvidia-meta ' "$OUT/apt-simulation.log"
apt-get --yes install "$DEB_PATH" > "$OUT/apt-install.log" 2>&1
[ "$(dpkg-query -W -f='${Status}' test-nvidia-meta)" = 'install ok installed' ]
[ "$(dpkg-query -W -f='${Status}' nvidia-open)" = 'install ok installed' ]
[ "$(dpkg-query -W -f='${Status}' unrelated-service-fixture)" = 'install ok installed' ]
[ "$(dpkg-query -W -f='${Status}' nvidia-open-suite-dkms)" = 'install ok installed' ]
! dpkg-query -W -f='${Status}' nvidia-kernel-open-dkms 2>/dev/null | grep -q 'install ok installed'
[ -z "$(dkms status -m nvidia -v 610.43.02)" ]
[ -n "$(dkms status -m nvidia-open-suite -v 2.1.0+nvidia.610.43.02)" ]
[ ! -e /etc/nvidia-open-suite/p2p.json ]
[ ! -e /etc/initramfs-tools/conf.d/nvidia-open-suite ]
[ ! -e /usr/share/initramfs-tools/hooks/nvidia-open-suite ]
[ -f /etc/modprobe.d/nvidia-open-suite.conf ]
grep -q 'common.postinst' /var/lib/dpkg/info/nvidia-open-suite-dkms.postinst
# Local configuration survives reinstall and remove; purge deletes it.
printf '# administrator override\noptions nvidia NVreg_RegistryDwords="RMFullBar1P2P=0;"\n' > /etc/modprobe.d/nvidia-open-suite.conf
apt-get --yes --reinstall install "$DEB_PATH" > "$OUT/reinstall.log" 2>&1
grep -q 'administrator override' /etc/modprobe.d/nvidia-open-suite.conf
if [ -n "${OLD_DEB_PATH:-}" ];then
 apt-get --yes remove nvidia-open-suite-tools > "$OUT/tools-remove-before-legacy.log" 2>&1
 apt-get --yes --allow-downgrades install "$OLD_DEB_PATH" > "$OUT/legacy-install.log" 2>&1
 [ -f /usr/share/initramfs-tools/hooks/nvidia-open-suite ]
 apt-get --yes install "$DEB_PATH" "$TOOLS_PATH" > "$OUT/legacy-upgrade.log" 2>&1
 [ ! -e /usr/share/initramfs-tools/hooks/nvidia-open-suite ]
 nvidia-open-suite --help | grep -q '{prepare,install,status}'
fi
apt-get --yes remove nvidia-open-suite-tools > "$OUT/tools-remove.log" 2>&1
[ "$(dpkg-query -W -f='${Status}' nvidia-open-suite-dkms)" = 'install ok installed' ]
[ ! -e /usr/sbin/nvidia-open-suite ]
apt-get --yes remove nvidia-open-suite-dkms > "$OUT/remove.log" 2>&1
[ -f /etc/modprobe.d/nvidia-open-suite.conf ]
[ -z "$(dkms status -m nvidia-open-suite -v 2.1.0+nvidia.610.43.02)" ]
apt-get --yes purge nvidia-open-suite-dkms > "$OUT/purge.log" 2>&1
[ ! -e /etc/modprobe.d/nvidia-open-suite.conf ]
cp /work/dkms-calls "$OUT/dkms-calls.log"
printf '%s\n' 'PASS: standard dh_dkms/common.postinst, APT replacement and exact-version metapackage retention.' 'PASS: optional tools install alone and remove independently; conffile survives reinstall/remove and is removed by purge; no suite hook.' 'DKMS commands are fixtures; common.postinst, APT and dpkg are real. No kernel build/load or GPU test claimed.' > "$OUT/result.txt"
