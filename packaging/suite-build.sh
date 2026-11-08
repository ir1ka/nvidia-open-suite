#!/bin/bash
set -euo pipefail
kernel=${1:?explicit kernel ABI required}
headers=${2:?prepared headers required}
compiler=${CC:-cc}
jobs=${NV_SUITE_JOBS:-8}
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo 'NV_SUITE_JOBS must be a positive integer' >&2; exit 2; }
[ -f "$headers/Makefile" ] || { echo 'Explicit prepared target headers required' >&2; exit 2; }
# Ask this explicit target's Kbuild, not the running host, for its common
# source headers. Debian keeps these separate from generated ABI headers.
sources=$(make -s --no-print-directory -C "$headers" M="$PWD/kernel-open" \
    --eval='nv-suite-srctree:;@printf "%s\n" "$(abs_srctree)"' nv-suite-srctree)
[ -f "$sources/include/linux/pci.h" ] || { echo 'Cannot resolve target source headers' >&2; exit 2; }
make -j"$jobs" modules CC="$compiler" KERNEL_UNAME="$kernel" SYSSRC="$sources" SYSOUT="$headers" IGNORE_PREEMPT_RT_PRESENCE=1 IGNORE_XEN_PRESENCE=1
bash check-modules.sh "$kernel"
