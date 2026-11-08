# NVIDIA Open Suite User Manual

**English** | [Chinese](README.zh-CN.md)

**Distribution validation:** Tested only on Debian 13. Other distributions, including Ubuntu, have not been validated.

CMP unlocking and PCIe P2P integration for NVIDIA open driver **610.43.02**. The `nvidia-610.43.02` branch maintains this driver baseline; other NVIDIA versions require separate `nvidia-<version>` branches and adaptation. DKMS rebuilds for kernel updates do not imply compatibility with other NVIDIA driver versions.

For Debian/Ubuntu amd64 systems using a package-managed NVIDIA open DKMS driver. PF BAR Recover and PCI ACS Scope are independent projects and are not dependencies.

## Get the source

```sh
git clone --branch nvidia-610.43.02 --recurse-submodules https://github.com/ir1ka/nvidia-open-suite.git
cd nvidia-open-suite
```

For an existing checkout, run `git submodule update --init --recursive`. GitHub's automatically generated ZIP archives omit submodules; the complete release source archive includes the pinned dependencies.

## Quick start

Run from this repository. Prepare a DKMS package, then install it through APT to replace the original driver provider. The work directory must not already exist.

```sh
# Detect the installed open DKMS driver and distribution package versions.
./bin/nvidia-open-suite prepare --work /var/tmp/nvidia-suite-build-01
sudo apt install /var/tmp/nvidia-suite-build-01/packages/nvidia-open-suite-dkms_*.deb
```

On a build host without the driver, specify the supported version explicitly:

```sh
./bin/nvidia-open-suite prepare --driver-version 610.43.02 \
  --provide-version nvidia-kernel-open-dkms=610.43.02-1 \
  --work /var/tmp/nvidia-suite-build-02
```

Replace the example distribution package version with the target system's version. Repeat `--provide-version` for other supported provider package names if necessary. Use `--firmware-package PACKAGE=VERSION` for the target's exact GSP firmware dependency; the default is Debian's `firmware-nvidia-gsp`, and non-Debian targets must specify it explicitly.

### Driver source acquisition

The Suite Git repository and release source archive contain integration code, patches, and the pinned cmpunlocker dependency, **not a bundled NVIDIA open driver source tree**. During `prepare`, the build downloads NVIDIA's official GitHub release-tag source archive for the selected supported version and verifies the pinned SHA256 in `components/nvidia-bar1-p2p/vendor.json` before extraction and patching. A complete installed `/usr/src/nvidia-*` tree is no longer implicitly reused. Installed-driver detection selects the version and provider metadata, not the source contents.

For offline builds, pass `--archive /path/to/nvidia-610.43.02-upstream.tar.gz`; the same pinned SHA256 is mandatory. The explicit development override `--source /path/to/source` accepts a complete, matching, unpatched local tree and is mutually exclusive with `--archive`. It bypasses archive provenance verification and is not the default release build path.

The generated **DKMS deb necessarily includes the downloaded and patched driver source** so DKMS can compile at installation and after kernel updates without downloading source again. The optional tools package contains preparation tools and patches, not the downloaded driver tree. This distinction applies to project source distribution versus the installable DKMS driver package.


## Preparation, installation, and kernel updates

| Stage | Action | Original DKMS registration |
| --- | --- | --- |
| prepare | Select and validate source, apply patches, validate, and build deb packages | Unchanged |
| apt install | Replace conflicting provider packages and register/build Suite through DKMS | Removed by the original package's removal scripts |
| Optional tools package | Provide preparation, installation, status, and test tools | Installing tools alone changes nothing |

**The DKMS package activates automatically on installation; no enable command is needed.** Standard `dh_dkms` maintainer scripts use the distribution's DKMS installation process to register, select kernels, and build/install all five modules. `AUTOINSTALL=yes` requests rebuilds after kernel updates. Kernel selection, missing headers, build failures, and signing follow the target system's DKMS behavior; a successful package installation is not proof that every kernel has built successfully.

The main package has no enable/disable, boot, or p2p management commands and no custom initramfs hook. `/etc/modprobe.d/nvidia-open-suite.conf` contains the default P2P policy and is a dpkg conffile, preserving administrator changes on upgrades. Installation does not hot-reload the running driver. Module loading and inclusion in initramfs follow the distribution's existing mechanisms. After configuration changes, update initramfs as appropriate with `sudo update-initramfs -u -k all` and load the new driver during a maintenance window.

Versioned `Provides: nvidia-kernel-open-dkms (= 610.43.02-1)` can satisfy exact distribution-version dependencies; upstream version `610.43.02` alone is not equivalent. `Conflicts` prevents simultaneous provider installation, and `Replaces` declares file replacement. APT performs the transaction. These declarations do not remove manually registered DKMS trees. Ownership checks reject unmanaged conflicting files or source trees; administrators must review such installations before migration.

An optional installation entry point combines preparation and APT installation:

```sh
sudo ./bin/nvidia-open-suite install --work /var/tmp/nvidia-suite-install-01
```

It verifies the installed package-managed open DKMS provider and does not remove manual registrations or implement a separate source rollback. `install --driver-version` does not bypass host checks. `--kernel` selects the installed original DKMS ABI to inspect; it does not constrain the generated DKMS package to a runtime kernel and is not accepted by explicit-version preparation.

Suite does not reboot or hot-reload NVIDIA during installation. Original provider maintainer scripts still perform their own package operations. CMP changes take effect during subsequent initialization of matching GPUs. Normal loading is handled by udev/the operating system; Suite does not wrap udev or preload NVIDIA.

## Included features

| Feature | Scope |
| --- | --- |
| cmpunlocker | Pinned upstream scripts, constants, and all 14 patches; select 64GB/40GB profiles for CMP `10de:20c2` / `10de:2082`, independently of build-host inventory |
| Full BAR1 PCIe P2P | Both endpoints opt in, BAR1 covers the complete framebuffer address space, static mapping succeeds, and eligibility checks pass; native NVLink retains priority |

P2P configuration does not manufacture hardware compatibility. Unsupported small-BAR devices and VF/MIG configurations remain protected. CMP patches modify firmware boot, registers, and memory geometry, but do not flash GPU firmware. **ECC reporting patches synthesize or override reported state: enabled/scrubComplete or infoROM version output does not establish actual ECC correctness or hardware health.**

Preparation directly runs a prepare-only working copy of upstream `driver/build.sh`, not upstream `install.sh`. The package enables the Gen2 boot retrain service by default but does not start it in the current session. It does not configure GRUB, IOMMU, ACS, VFIO, PCI reset, passthrough, or driver hot-reloading. The upstream in-driver CMP Gen2 retrain patch also remains part of the pinned patch set and runs during applicable device initialization.

## Global and per-device full BAR1 policy

`RMFullBar1P2P` is the new numeric registry key: `1` permits the added full BAR1 path and `0` disables it. It does not accept a device list. Both endpoints must enable it and pass eligibility checks. Disabling it does not disable NVIDIA's native P2P or NVLink.

`NVreg_RegistryDwords` and `NVreg_RegistryDwordsPerDevice` are existing NVIDIA parameters for global defaults and per-GPU overrides. Use those interfaces directly; Suite does not add a device-list management mechanism.

For example, edit `/etc/modprobe.d/nvidia-open-suite.conf` to disable globally and enable two devices:

```conf
options nvidia NVreg_RegistryDwords="RMFullBar1P2P=0;RmForceEnableGen2=1;RMPcieLinkSpeed=0x1;" NVreg_RegistryDwordsPerDevice="pci=0000:16:00.0;RMFullBar1P2P=1;pci=0000:17:00.0;RMFullBar1P2P=1;RmForceEnableGen2=1;RMPcieLinkSpeed=0x1;"
```

Or enable globally and disable one device:

```conf
options nvidia NVreg_RegistryDwords="RMFullBar1P2P=1;RmForceEnableGen2=1;RMPcieLinkSpeed=0x1;" NVreg_RegistryDwordsPerDevice="pci=0000:16:00.0;RMFullBar1P2P=0;RmForceEnableGen2=1;RMPcieLinkSpeed=0x1;"
```

Each `pci=` begins a device section, lasting until the next `pci=`. Use the complete domain:bus:slot.function address and update it if bus numbering changes. Merge existing registry keys before editing; repeated string parameters in multiple files are not merged by their internal keys. Configuration is read on subsequent module loads, not applied to the running driver. Update initramfs as required. Adding these keys to an unpatched NVIDIA driver does not add Suite functionality.

## Packages

- `nvidia-open-suite-dkms`: complete patched source, DKMS configuration, necessary build/validation scripts, default modprobe conffile, Gen2 service, licenses, and manuals. No preparation commands or test tools.
- `nvidia-open-suite-tools`: prepare/install/status commands, patches, packaging helpers, and tests. It optionally suggests the main package; installing tools alone does not register DKMS or change P2P policy. A build host does not need the driver package or GSP firmware installed.

```sh
sudo apt install ./nvidia-open-suite-dkms_*.deb
# Optional preparation and test tools:
sudo apt install ./nvidia-open-suite-tools_*.deb
```

Packaging uses debhelper compatibility level 13, `dh_dkms`, and standard DKMS maintainer scripts. It depends on matching GSP firmware and g++; `dh_dkms` generates the minimum DKMS dependency. It also provides `nvidia-kernel-610.43.02`. The default firmware package version follows `--provide-version nvidia-kernel-open-dkms=VERSION`, falling back to `610.43.02-1`. Specify distribution-specific revisions explicitly. Kernel selection and signing use the system DKMS implementation.

## Dynamic small BAR1 P2P (optional; RTX 30/40 preview)

The full BAR1 path is enabled by default but requires complete mappings at both endpoints. When BAR1 is smaller than VRAM, add the following to the existing NVIDIA modprobe configuration to opt into dynamic mappings:

```conf
options nvidia NVreg_RMDynamicBar1P2P=1
```

The dynamic path is disabled by default and admits Ampere, Ada, and TU102, retaining guards for incompatible devices, VF/MIG, confidential computing, and other unsupported configurations. It maps shared allocations into a limited BAR1 window rather than mapping all VRAM simultaneously. Exhausting the window returns allocation failure; applications must release mappings or reduce concurrently shared memory. Remote atomics are unsupported, and this feature adds no direct managed-memory P2P path. Mixed full/dynamic and cross-model combinations are not guaranteed; CUDA peer access between A100 and RTX 2080 Ti is currently unavailable.

### Hardware and validation scope

| Device | Dynamic small BAR1 P2P status |
| --- | --- |
| A100 PCIe 40GB (GA100) | Hardware-tested with a same-model two-card pair and BAR1 temporarily reduced to 256MiB: correctness, bandwidth/latency, window exhaustion, normal/abnormal process-exit cleanup |
| RTX 2080 Ti (TU102) | Hardware-tested with a same-model two-card pair and 256MiB BAR1; modified 22GB VRAM cards, with NVLink disabled for PCIe testing |
| GeForce RTX 30 series (GA10x), including RTX 3090 | **Preview**; already admitted by the Ampere gate, with additional static coverage; no hardware validation |
| GeForce RTX 40 series (AD10x) | **Preview**; Ada admission added; no hardware validation |
| RTX 4090 48GB (AD102, modified VRAM) | **Expected support, preview only**; no test hardware or hardware validation. The driver must correctly recognize VRAM and all dynamic small BAR1 eligibility checks must pass |

A100/RTX 2080 Ti results are from earlier versions. The RTX 30/40 extension received static analysis and compilation checks only, with no new GPU runtime tests. These checks do not establish CUDA/GSP acceptance, performance, or stability on untested cards. Every device remains subject to window budgeting and eligibility checks, including rejection of unsupported static-small-BAR, VF/MIG, confidential-computing, and architecture configurations. Cross-model or cross-architecture interoperability must not be inferred from the table. The existing full BAR1 path and its guards are unchanged.

Changes take effect on a later module load. Update initramfs according to the distribution and schedule the driver transition during a maintenance window. Unpatched drivers do not gain this functionality from configuration alone.

## Removal and restoring the original provider

During a maintenance window, remove Suite through APT and reinstall the distribution's original open DKMS provider of the matching version. Match kernel headers, user-space libraries, and GSP firmware. Do not install both providers simultaneously. Suite does not automatically unload modules in use or reboot.

## Build and checks

Preparation requires Python 3, Bash, Git, patch, make, C/C++ compilers, debhelper, and dh-sequence-dkms. DKMS compilation also requires target kernel headers. User-space and GSP versions must match 610.43.02. GPU test programs require the CUDA toolkit; ordinary `make check` does not load drivers or change devices.

```sh
make check
make check-source SOURCE=/path/to/prepared/source
```

DKMS attempts automatic rebuilds after kernel updates. Missing headers, incompatible interfaces, or untrusted signatures can still prevent use. Secure Boot signing follows the target system's DKMS/key configuration. Packages contain no private signing keys or proprietary NVIDIA user-space/GSP firmware.

## Dependencies and attribution

- Required upstream: [amoghmunikote/cmpunlocker](https://github.com/amoghmunikote/cmpunlocker), pinned commit `2c7e2ecd7944e791fec040d2680036beb4a9327b`, GPL v2, in `vendor/cmpunlocker`. Suite uses its preparation script, all 14 patches, constants, and Gen2 behavior, adding prepare-only adaptation in a working copy before Suite patches. Its installer, GRUB modifications, and passthrough deployment are not run. No separate cmpunlocker deb is required. Original LICENSE and CREDITS files are preserved.
- Driver source: [NVIDIA/open-gpu-kernel-modules](https://github.com/NVIDIA/open-gpu-kernel-modules), 610.43.02. The exact archive URL/SHA256 is recorded in `components/nvidia-bar1-p2p/vendor.json`; licensing is preserved in `licenses/NVIDIA-COPYING` and individual source files.
- Dynamic mapping reference: [Duanyll/open-gpu-kernel-modules](https://github.com/Duanyll/open-gpu-kernel-modules/tree/8edb5f6c36f39a45cb6df0b8ac19bd42ece80235). Suite references its allocation-relative encoder/call-site approach, with rewritten window management and guards; it is not a runtime dependency. Upstream COPYING retains NVIDIA's MIT/GPLv2 terms.

This is not an official NVIDIA or cmpunlocker distribution. Suite integration code is GPL v2; upstream files retain their original licenses and attribution. Bundled upstream material is retained for verification and reproducibility, not as this project's development history.

## Contact and maintenance

Maintainer: IriKa Qiu ([ir1ka](https://github.com/ir1ka)). Use [Issues](https://github.com/ir1ka/nvidia-open-suite/issues) for reports and discussion, and [Pull Requests](https://github.com/ir1ka/nvidia-open-suite/pulls) for improvements. Request a private channel before sharing security-sensitive details; do not post exploit details or keys in public issues.
