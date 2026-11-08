# NVIDIA Open Suite 用户手册

[English](README.md) | **简体中文**

**发行版验证范围：目前仅在 Debian 13 上测试过。其他发行版（包括 Ubuntu）尚未验证。

集成 NVIDIA open 驱动的 CMP 解锁与 PCIe P2P。项目统一在 `main` 维护，使用 Suite 自有版本号（当前 **2.1.0**），未来发行标签采用 `v<Suite版本>`。历史驱动基线分支及标签保留为归档，不再作为并行开发分支。

## 支持的 NVIDIA open 版本

机器可读白名单为 [`supported-drivers.json`](supported-drivers.json)。仅允许列表中存在、且具有匹配的已审阅补丁和源码配置的版本准备源码和构建 deb；自动检测及显式 `--driver-version` 均执行检查，本地源码或离线归档也不能绕过。

| NVIDIA open 版本 | Suite 版本 | 状态 | 发行版验证 |
| --- | --- | --- | --- |
| 610.43.02 | 2.1.0 | 支持；RTX 30/40 动态小 BAR1 仍为预览 | 仅 Debian 13 |

`supported-drivers.json` 是驱动配置的唯一来源，统一维护版本键、默认选择、源码时间戳和默认发行版修订号。准备阶段据此生成 DKMS 配置及模块检查脚本，CMP 适配器和打包器共享相同元数据。`manifest.json` 仅保留 Suite 与补丁完整性信息，不再重复定义 NVIDIA 版本；第三方上游文件保持原样。

其他版本直接拒绝。新增版本需要适配并验证源码及补丁配置，不能仅添加版本号。DKMS 对内核更新的自动构建不代表支持新的 NVIDIA 驱动版本。

Suite 与 NVIDIA 分别编号。DKMS 版本为 `2.1.0+nvidia.610.43.02`，deb 版本以 `1:2.1.0+nvidia.610.43.02` 开头。Debian epoch `1:` 用于保证从旧的 NVIDIA 版本优先编号方式正常升级，不属于 Suite 版本或归档文件名。原驱动提供者的版本依赖仍使用 NVIDIA 发行版包版本。

面向 Debian/Ubuntu amd64 和由包管理器/DKMS 管理的 NVIDIA open 驱动；PF BAR Recover、PCI ACS Scope 均不是安装依赖。

## 获取源码

```sh
git clone --branch main --recurse-submodules https://github.com/ir1ka/nvidia-open-suite.git
cd nvidia-open-suite
```

已有检出执行 `git submodule update --init --recursive`。普通自动生成的 GitHub ZIP 不含 submodule；完整发行源码归档包含固定上游依赖。

## 快速使用

在本仓库目录执行。先生成 DKMS deb，再由 APT 安装并替换原驱动包；工作目录必须尚不存在。

```bash
# 默认读取本机已安装的 open DKMS 驱动版本和发行版包版本
./bin/nvidia-open-suite prepare --work /var/tmp/nvidia-suite-build-01
sudo apt install /var/tmp/nvidia-suite-build-01/packages/nvidia-open-suite-dkms_*.deb
```

构建机没有 NVIDIA 驱动时，显式指定版本；当前只接受已适配的 610.43.02：

```bash
./bin/nvidia-open-suite prepare --driver-version 610.43.02 \
  --provide-version nvidia-kernel-open-dkms=610.43.02-1 \
  --work /var/tmp/nvidia-suite-build-02
```

`--firmware-package PACKAGE=VERSION` 指定目标系统的精确 GSP 固件依赖；默认是 Debian 的 `firmware-nvidia-gsp`，非 Debian 目标必须显式指定。

`--provide-version` 请使用目标发行版的原包版本，可重复指定不同的已知 NVIDIA 内核包名。

### 驱动源码获取

Suite Git 仓库和发行源码归档仅包含集成代码、补丁和固定版本的 cmpunlocker 依赖，**不内置 NVIDIA open 驱动源码树**。构建的 `prepare` 阶段从 NVIDIA 官方 GitHub 下载对应受支持版本的 release tag 源码归档，随后解压和打补丁，不再要求固定的源码归档 SHA256。不再自动复用 `/usr/src/nvidia-*`；已安装驱动的检测仅用于选择版本和包元数据。

离线或外部修改过的源码归档可通过 `--archive /path/to/source.tar.gz` 提供，不要求与原始归档 SHA256 相同。归档顶层目录仍须为 `open-gpu-kernel-modules-<版本>`。也可使用 `--source /path/to/source` 提供完整且版本受支持的本地源码；两种选项互斥。

不再把 NVIDIA 原文件或执行 CMP 补丁后的文件与固定 SHA256 比较；已移除旧的上游文件哈希清单遍历和原始源码校验代码，不保留备用开关。仍保留版本白名单、安全解压、补丁应用和源码功能检查。已有补丁若冲突或重复应用，会明确报错，不再根据文件哈希自动跳过。Suite 补丁完整性及构建快照检查保留：哈希用于标识用户提供的源码，并检测准备过程中或验证后的变动，不要求源码等同于原始上游文件。

不再维护必需源码文件清单。确认版本受支持后，准备阶段直接尝试打补丁；失败时提示源码结构或版本不匹配、补丁冲突或可能含预编译 RM，并保留补丁工具输出。这是可能原因提示，不会把所有失败都判定为预编译二进制；补丁成功也不代表后续编译必然成功。

生成的 **DKMS deb 必须包含下载后打好补丁的驱动源码**，供目标系统安装和内核更新时离线编译；这些阶段无需再次下载。可选 tools 包仅包含准备工具和补丁，不包含下载的驱动源码树。项目源码分发与可安装的 DKMS 驱动包属于不同层次。


## 三个阶段与包替换语义

| 阶段 | 执行内容 | 原 DKMS 注册 |
| --- | --- | --- |
| prepare | 检查/选择版本，复制完整源码、打补丁、校验并生成 deb | 不修改 |
| apt install | 根据 Provides/Conflicts/Replaces 替换原包；新包注册并编译 Suite DKMS | 原包管理的注册由其卸载脚本清理 |
| 可选 tools 包 | 提供 prepare/install/status 和测试，不自动配置驱动 | 不因安装工具包而改变 |

**DKMS 在安装成功时已经自动接管，不需要执行 enable 才激活。** 标准 `dh_dkms` 生成的 postinst 调用 DKMS 公共安装流程，注册、选择内核并构建安装五个模块；`AUTOINSTALL=yes` 负责后续内核更新时的自动构建。内核选择、缺少 headers 时的跳过和构建失败处理遵循目标系统 DKMS，安装成功不代替逐内核构建状态检查。

主包不再提供 enable/disable、boot 或 p2p 子命令，不提供自有 initramfs hook。默认 P2P 开关位于 `/etc/modprobe.d/nvidia-open-suite.conf`，作为 dpkg conffile 管理；升级保留用户修改。当前已加载模块不被主动切换。驱动进入 initramfs 与模块加载遵循发行版现有机制；更改 modprobe 配置后，按需执行 `update-initramfs -u -k all`。

`Provides: nvidia-kernel-open-dkms (= 610.43.02-1)` 可以满足依赖该精确版本的元包；仅声明上游 `610.43.02` 不等同于发行版 `610.43.02-1`。`Conflicts` 表示不能与原包共存，`Replaces` 声明包替换关系；APT 负责事务，不由套件启用命令卸载原驱动。

这些声明只作用于包管理，**不会清理手工 dkms add 注册**。安装前归属检查拒绝未受管的同名文件和 DKMS 源码；手工注册或残留需由管理员审阅迁移。可选安装入口同样只处理包管理的提供者：

```bash
sudo ./bin/nvidia-open-suite install --work /var/tmp/nvidia-suite-install-01
```

它包含 prepare 和 APT 安装，核验受包管理的原 open DKMS 提供者；只由 APT 移除声明冲突的受管包，不清理手工注册或自行回滚源码。`install --driver-version` 仍不绕过当前主机检查。`--kernel` 仅选择检查哪个已安装原 DKMS ABI，不用于指定 DKMS deb 的运行内核；显式版本 prepare 不接受它。

APT 安装不会由 Suite 热重载 NVIDIA 或重启。磁盘模块与当前已加载模块可以暂时不同，切换在维护窗口安排。原第三方包自身的维护脚本属于其包行为；本机原包的 prerm 执行 dkms remove，主包不额外实现一套接管脚本。

CMP 补丁随新模块在匹配设备后续初始化时生效；P2P 默认允许符合资格的设备使用扩展路径。正常加载由 udev/系统负责，套件不提前 modprobe、不包装 udev。


## 功能范围

| 功能 | 范围 |
| --- | --- |
| cmpunlocker | 固定上游 commit 的原样脚本、constants.yaml 与 14 项原样补丁；按 CMP `10de:20c2` / `10de:2082` 选择 64GB/40GB profile，不按当前机器库存固化 |
| PCIe P2P | 不按 A100 型号限定；公共静态 BAR1 路径两端均开启、BAR1 ≥ 完整 FB 地址空间、静态映射成功、非 MIG/VF，并保留原生 NVLink 优先级 |

P2P 启用不会伪造硬件兼容性；小 BAR1、MIG/VF 等不合格设备保持受保护。CMP 补丁含固件引导、寄存器与显存几何修改，不修改 GPU Flash。**其中 ECC reporting 会合成/覆盖状态，显示 enabled/scrubComplete 或 infoROM 版本不能证明真实 ECC 正确性或健康状态。**

prepare 直接执行上游 driver/build.sh 的 prepare-only 工作副本；不执行上游 install.sh。安装默认启用 Gen2 开机 retrain 服务，但不在当前会话启动；不配置 IOMMU、ACS、VFIO、PCI reset、直通或驱动热重载。驱动内 CMP Gen2 retrain 仍属于固定补丁集，会在相应设备初始化时执行。


## P2P 全局与逐设备配置

`RMFullBar1P2P` 是本补丁新增的数值开关，`1` 允许使用新增 BAR1 P2P 路径，`0` 关闭该路径；不接受设备列表。两端均需开启并通过 BAR1 覆盖完整显存、非 MIG/VF 等检查。关闭此开关不等于关闭 NVIDIA 原生 P2P 或 NVLink。

`NVreg_RegistryDwords` 和 `NVreg_RegistryDwordsPerDevice` 都是 NVIDIA 原有参数，分别用于全局默认值和逐 GPU 覆盖。逐设备选择直接使用原接口，不作为本工具的设备列表功能。

例如，修改主包的 `/etc/modprobe.d/nvidia-open-suite.conf`，全局关闭，仅为两张卡开启：

```conf
options nvidia NVreg_RegistryDwords="RMFullBar1P2P=0;RmForceEnableGen2=1;RMPcieLinkSpeed=0x1;" NVreg_RegistryDwordsPerDevice="pci=0000:16:00.0;RMFullBar1P2P=1;pci=0000:17:00.0;RMFullBar1P2P=1;RmForceEnableGen2=1;RMPcieLinkSpeed=0x1;"
```

或者全局开启，仅为一张卡关闭：

```conf
options nvidia NVreg_RegistryDwords="RMFullBar1P2P=1;RmForceEnableGen2=1;RMPcieLinkSpeed=0x1;" NVreg_RegistryDwordsPerDevice="pci=0000:16:00.0;RMFullBar1P2P=0;RmForceEnableGen2=1;RMPcieLinkSpeed=0x1;"
```

每个 `pci=` 开始一个设备配置段，后续键值对作用于该 GPU，直到下一个 `pci=`；这里使用完整 domain:bus:slot.function 地址。PCI 总线编号变化后须同步修改。配置只在后续模块加载时读取，不改变已加载模块。

配置前合并已有 NVIDIA registry 键，避免丢失其他参数。不要在多个文件中重复设置同一个字符串参数：它们不会自动按内部键合并。写好后执行 `sudo update-initramfs -u -k all`，在维护窗口下次正常加载驱动时生效；无需重新编译。`RMFullBar1P2P` 需配合本补丁模块，给原版 NVIDIA 驱动添加该键不会获得此功能。


## 主包与可选工具包

- `nvidia-open-suite-dkms`：完整已打补丁源码、dkms.conf、必要构建/校验脚本、默认 modprobe conffile、许可证和手册。包含默认 Gen2 服务；没有测试、管理命令或补丁准备工具。
- `nvidia-open-suite-tools`：prepare/install/status 命令、补丁、准备/打包工具及测试。通过 Suggests 可选关联主包；构建机不需要安装主包或 GSP 固件。安装此包本身不注册 DKMS、不改变 P2P 配置。

```bash
# 目标主机：只安装驱动主包
sudo apt install ./nvidia-open-suite-dkms_*.deb
# 可选：安装准备、打包与测试工具
sudo apt install ./nvidia-open-suite-tools_*.deb
```

主包使用 debhelper compat 13、`dh_dkms` 与标准 DKMS 公共维护脚本。依赖匹配版本的 firmware-nvidia-gsp 和 g++；dkms 最低版本由 dh_dkms 的 misc:Depends 自动生成，并提供 `nvidia-kernel-610.43.02` 能力名。默认固件包版本取 `--provide-version nvidia-kernel-open-dkms=VERSION`，未指定时为 610.43.02-1；不同仓库的修订号必须按目标发行版指定。不再自行循环所有 headers 目录，具体内核选择、失败和签名行为遵循目标系统 DKMS；归属不明的原提供者拒绝自动接管。


## 动态 BAR1 P2P（可选；RTX 30/40 系列为预览功能）

full BAR1 路径默认开启，但要求两端完整映射和设备准入条件满足。BAR1 小于显存时，可在已有 NVIDIA modprobe 配置中增加：

```conf
options nvidia NVreg_RMDynamicBar1P2P=1
```

动态路径默认关闭，目前准入 Ampere、Ada 和 TU102，保留非兼容设备、VF/MIG、机密计算等保护。它为共享分配建立有限 BAR1 窗口，不是把全部显存同时映射进小 BAR。窗口不足会返回分配失败；应用应释放窗口或减少同时共享的显存。远端原子操作不支持；managed 内存不新增直接 P2P 路径。混合 full/dynamic 和跨型号组合不能保证可用；A100 与 2080 Ti 的 CUDA 跨型号访问当前不可用。RTX 30/40 系列没有测试硬件，仅做静态分析与编译检查，不能据此承诺 CUDA/GSP 接受、性能或稳定性。

### 设备与验证范围

| 设备 | 动态 small BAR1 P2P 状态 |
| --- | --- |
| A100 PCIe 40GB（GA100） | 已在两张卡的同型号配对上实机测试，BAR1 临时缩至 256MiB；覆盖正确性、带宽/延迟、窗口耗尽及正常/异常退出清理 |
| RTX 2080 Ti（TU102） | 已在两张卡的同型号配对上实机测试，256MiB BAR1；测试卡为改装 22GB 显存型号，测试时禁用 NVLink，走 PCIe |
| GeForce RTX 30 系列（GA10x，包括 RTX 3090） | **预览支持**；原 Ampere 准入已包含该系列，补充静态覆盖；没有实机验证 |
| GeForce RTX 40 系列（AD10x） | **预览支持**；新增 Ada 动态准入；没有实机验证 |
| RTX 4090 48GB（AD102，改装显存） | **预期支持，预览功能**；无此型号测试环境、未经实机验证；要求驱动正确识别显存，且满足动态小 BAR1 的全部准入条件 |

上述 A100/2080 Ti 是此前版本的实机结果，本次 30/40 系列扩展未做 GPU 运行测试。所有设备仍须满足窗口预算、非静态小 BAR1、非 VF/MIG/机密计算等限制；不支持的架构继续拒绝。不同型号或跨架构配对不在已验证范围，不能从表中推断互通；full BAR1 路径与准入条件不变。

配置在后续加载模块时读取，不会在线修改已加载驱动。按发行版要求更新 initramfs，并在维护窗口切换模块。原版 NVIDIA 驱动不会因增加这些参数而获得补丁功能。

## 卸载与恢复原包

在维护窗口通过 APT 移除 Suite，并安装目标发行版同版本的原 open DKMS 包；确认 headers、用户态和 GSP 版本匹配。不要同时安装两种驱动提供者。Suite 不自动热卸载正在使用的模块、不自动重启。

## 构建与测试

prepare 需要 Python 3、Bash、Git、patch、make、C/C++ 编译器、debhelper、dh-sequence-dkms。DKMS 构建另需目标内核 headers；用户态和 GSP 必须匹配 610.43.02。GPU 测试程序需要 CUDA toolkit；普通 `make check` 不加载驱动或更改设备。

```sh
make check
make check-source SOURCE=/path/to/prepared/source
```

DKMS 更新内核后自动尝试重编译；缺少 headers、接口不兼容或签名不被信任仍可能失败。Secure Boot 的签名由目标系统 DKMS/密钥配置负责。安装包不包含私钥或专有 NVIDIA 用户态/GSP 固件。

## 第三方依赖与署名

- 必需上游：[amoghmunikote/cmpunlocker](https://github.com/amoghmunikote/cmpunlocker)，固定提交 `2c7e2ecd7944e791fec040d2680036beb4a9327b`，GPL v2，位于 `vendor/cmpunlocker`。使用上游准备脚本、14 项补丁、常量和 Gen2 行为；仅在工作副本加入 prepare-only 适配，再叠加 Suite 补丁。不执行其安装器、GRUB 或 passthrough 部署。不需要另装 cmpunlocker deb。原始 LICENSE 和 CREDITS 保留。
- 驱动源码：[NVIDIA/open-gpu-kernel-modules](https://github.com/NVIDIA/open-gpu-kernel-modules)，610.43.02。发行版本在 `supported-drivers.json`，官方 GitHub URL 根据版本号生成；许可证在 `licenses/NVIDIA-COPYING`，保留各文件原始署名。
- 动态映射参考：[Duanyll/open-gpu-kernel-modules](https://github.com/Duanyll/open-gpu-kernel-modules/tree/8edb5f6c36f39a45cb6df0b8ac19bd42ece80235)，参考 allocation-relative encoder/call-site 方法，窗口管理及守卫由 Suite 重写；不是运行依赖。上游 COPYING 保留 NVIDIA MIT/GPLv2 说明。

本项目并非 NVIDIA 或 cmpunlocker 官方发行。Suite 自有集成代码采用 GPL v2；上游代码保留其原始许可证。上游依赖自身附带的文件保留原样，供校验和重现，不代表本项目的开发历史。

## 交流与维护

维护者：IriKa Qiu（[ir1ka](https://github.com/ir1ka)）。通过 [Issues](https://github.com/ir1ka/nvidia-open-suite/issues) 报告问题与讨论，通过 [Pull Requests](https://github.com/ir1ka/nvidia-open-suite/pulls) 提交改进。安全问题请先请求私密渠道，不要在公开 issue 中附上漏洞细节或密钥。

本项目采用 GPL v2；保留所有第三方原始许可证和署名。
