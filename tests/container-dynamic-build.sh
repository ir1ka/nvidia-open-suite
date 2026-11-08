#!/bin/bash
# Disposable build container, no GPU access and no installation/driver loading.
# /source: checkout (read-only); /out: writable empty work area; target headers
# and their kbuild dependencies must be available inside the container.
set -euo pipefail
: "${TARGET_KERNEL:?explicit target ABI required}"
: "${TARGET_HEADERS:?explicit target headers required}"
: "${SOURCE_ARCHIVE:?NVIDIA source archive required}"
: "${PROVIDE_VERSION:?target NVIDIA DKMS package=version required}"
: "${FIRMWARE_PACKAGE:?target GSP package=version required}"
export PYTHONDONTWRITEBYTECODE=1
cd /source
driver_version=${DRIVER_VERSION:-$(python3 -c 'import sys;sys.path.insert(0,"tools");import driver_registry;print(driver_registry.profile()["driver_version"])')}
./bin/nvidia-open-suite prepare --driver-version "$driver_version" \
    --archive "$SOURCE_ARCHIVE" --provide-version "$PROVIDE_VERSION" \
    --firmware-package "$FIRMWARE_PACKAGE" --work /out/prepared > /out/prepare.log 2>&1
prepared=$(python3 -c 'import json; print(json.load(open("/out/prepared/result.json"))["prepared_source"])')
make check-source SOURCE="$prepared" > /out/source-tests.log 2>&1
cd "$prepared"
bash suite-build.sh "$TARGET_KERNEL" "$TARGET_HEADERS" > /out/build.log 2>&1
mkdir /out/modules
cp kernel-open/*.ko /out/modules/
modinfo /out/modules/nvidia.ko > /out/modinfo.txt
printf '%s\n' 'PASS: source preparation, unit/actual-function tests and five module builds; no hardware acceptance or installation' > /out/result.txt
