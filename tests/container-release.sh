#!/bin/bash
# Disposable container only: /source and target headers read-only, no host GPU,
# /boot, /etc or writable host /lib/modules mounted. Firmware is a test fixture.
set -euo pipefail
trap 'rc=$?; log=/var/lib/dkms/nvidia-open-suite/2.1.0+nvidia.610.43.02/build/make.log; [ ! -f "$log" ] || cp "$log" /out/driver-build.log; exit "$rc"' EXIT
: "${TARGET_KERNEL:?explicit target ABI required}"
export PYTHONDONTWRITEBYTECODE=1
cd /source
make check > /out/unit.log 2>&1
./bin/nvidia-open-suite prepare --driver-version 610.43.02 --archive /archive/nvidia-610.43.02-upstream.tar.gz --provide-version nvidia-kernel-open-dkms=610.43.02-1 --firmware-package firmware-nvidia-gsp=610.43.02-1 --work /work/prepared > /out/prepare.log 2>&1
source=$(python3 -c 'import json;print(json.load(open("/work/prepared/result.json"))["prepared_source"])')
make check-source SOURCE="$source" > /out/check-source.log 2>&1
# Ensure debhelper cleanup did not invalidate the shipped source manifest.
mkdir -p /work/source-check
dpkg-deb -x /work/prepared/packages/*dkms*.deb /work/source-check
python3 - <<'PY_SOURCE'
import sys,json
from pathlib import Path
sys.path.insert(0,'/source/tools')
import source
p=next(Path('/work/source-check/usr/src').iterdir())
assert source.tree_files(p)==json.loads((p/'nvidia-suite-source.json').read_text())['prepared_files']
PY_SOURCE
mkdir -p /out/packages
cp /work/prepared/packages/*.deb /out/packages/
python3 - "$source" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,'/source/tools')
import package
package.build(Path(sys.argv[1]),Path('/work/repeat'),{'nvidia-kernel-open-dkms':'610.43.02-1'},'firmware-nvidia-gsp=610.43.02-1')
PY
for f in /out/packages/*.deb; do cmp "$f" "/work/repeat/$(basename "$f")";done
# Run real tests from the tools deb's installed layout, without repository siblings.
mkdir -p /work/extracted
for f in /out/packages/*tools*.deb;do dpkg-deb -x "$f" /work/extracted;done
python3 -B -m unittest discover -s /work/extracted/usr/share/nvidia-open-suite/toolkit/nvidia-open-suite/tests -p 'test_*.py' > /out/installed-tests.log 2>&1
# Only dependency/lifecycle fixture, not usable firmware or GPU acceptance.
mkdir -p /work/firmware/DEBIAN
printf 'Package: firmware-nvidia-gsp\nVersion: 610.43.02-1\nArchitecture: all\nMaintainer: Test <test@example.invalid>\nDescription: EMPTY CONTAINER TEST FIXTURE ONLY\n' > /work/firmware/DEBIAN/control
dpkg-deb --build /work/firmware /work/firmware.deb
dpkg -i /work/firmware.deb
export NV_SUITE_JOBS=4
dpkg -i /out/packages/*dkms*.deb > /out/dkms-install.log 2>&1
cp /var/lib/dkms/nvidia-open-suite/2.1.0+nvidia.610.43.02/*/x86_64/log/make.log /out/driver-build.log
dkms status > /out/dkms-status.txt
find "/lib/modules/$TARGET_KERNEL" -maxdepth 4 -type f > /out/installed-module-files.txt
# An image-less container lacks the normal distro depmod trigger context.
depmod -a "$TARGET_KERNEL" > /out/depmod.log 2>&1
modinfo -k "$TARGET_KERNEL" nvidia > /out/modinfo.txt
# Reinstall uses generated dh_dkms scripts; preserve user conffile.
printf '\n# container user setting\n' >> /etc/modprobe.d/nvidia-open-suite.conf
dpkg -i /out/packages/*dkms*.deb > /out/reinstall.log 2>&1
grep -q 'container user setting' /etc/modprobe.d/nvidia-open-suite.conf
dpkg -i /out/packages/*tools*.deb > /out/tools-install.log 2>&1
/usr/sbin/nvidia-open-suite --help > /out/tools-help.txt
dpkg --remove nvidia-open-suite-tools nvidia-open-suite-dkms > /out/remove.log 2>&1
! dkms status | grep -q '^nvidia-open-suite/'
[ -f /etc/modprobe.d/nvidia-open-suite.conf ]
dpkg --purge nvidia-open-suite-tools nvidia-open-suite-dkms > /out/purge.log 2>&1
[ ! -e /etc/modprobe.d/nvidia-open-suite.conf ]
printf '%s\n' 'PASS: reproducible deb pair, installed-layout tests, real DKMS build/install/reinstall/remove/purge; empty firmware fixture, no GPU acceptance' > /out/result.txt
