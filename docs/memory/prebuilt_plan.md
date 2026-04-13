---
name: prebuilt改造完整方案说明
description: 四个核心问题的归档：完整方案概述、供应商编译流程、合作伙伴编译流程、残留源码分析
type: project
---

# Prebuilt 改造完整方案

## 一、背景与目标

**问题：** SoC 厂商（供应商）要将 OpenHarmony SDK 分发给合作伙伴，但 `device/` 和 `vendor/` 下有大量 C/C++ 源码涉及开源合规，不可对外直接分发。

**目标：** 将所有源码编译目标改为预编译二进制分发，合作伙伴侧无需源码也能编译出与供应商 md5 一致的镜像。

---

## 二、环境规划

| 目录 | 用途 | 产品 |
|------|------|------|
| `OHOS3/ohos5` | 供应商编译 | 730（mp_hi3781v730）|
| `OHOS4/ohos5` | 供应商编译 | 735（mp_hi3781v735）|
| `OHOS2/ohos5` | 合作伙伴验证 | 730 |
| `OHOS5/ohos5` | 合作伙伴验证 | 735 |

---

## 三、核心工具：transform_sdk.py（9 个 Phase）

**Phase 1 — 读取产品配置**
从 `vendor/hisilicon/<product>/config.json` 动态读取 board 名（730→`<board_730>`，735→`<board_735>`）。无硬编码。

**Phase 2 — 扫描发现所有源码编译目标**
自动扫描以下扫描根下所有 BUILD.gn，找出 `ohos_shared_library`、`ohos_executable`、`ohos_static_library` 目标；已是 `ohos_prebuilt_*` 的自动跳过：
- `device/soc/hisilicon/huanglong/vendor/huanglong`（symlink → outer vendor）
- `device/soc/hisilicon/common`
- `vendor/hisilicon/<product>`

**Phase 3 — 定位 out/ 产物**
在 `out/<board>/` 下定位对应 .so / 可执行文件。产物不存在 = feature 未开启 = 自动跳过，无需维护白名单。

**Phase 4 — 拷贝预编译产物**
将产物拷贝到 `device/soc/hisilicon/huanglong/vendor/huanglong/binary/platform/<part>/ohos3.2/`（通过 symlink 落地到 outer vendor）。

**Phase 5 — 改写 BUILD.gn**
`ohos_shared_library` → `ohos_prebuilt_shared_library` 等，删除 sources/cflags/deps/include_dirs，保留 install_images/part_name/public_configs，新增 `source = "..."` 指向预编译产物。特殊处理：`libteec_vendor`、`secure_c`、`pdmtool`。

**Phase 6 — 源码删除**
- `delete_source_files()` 删除扫描根下已转换目标的 .c/.cpp
- 保留 `KEEP_SOURCE_WHITELIST`（vendor_capture.c、vendor_render.c）
- 保留 `EXCLUDE_WITHIN_SCAN_ROOT`（ohos/ohos5_ext）
- `pack_tarball` 的 `_SOURCE_EXCLUDE_PREFIXES` 过滤 outer vendor 中的大块源码（u-boot/liteos/av/opus/fdk-aac/alsa/mbedtls/libteec/secure_c 等）
- GPU driver 目录只删 .c/.cpp，保留 .h

**Phase 7 — Kernel & Bootloader 预编译化**
将 `build_kernel.sh` 和 `build_bootloader.sh` 改为从 `device/<board>/kernel/` 拷贝预编译产物。board 名称动态解析（`BOARD=$(basename "$2")`），避免 730/735 互相覆盖。

**Phase 8 — 预应用 device/ 自定义 patch**
`custom-ohos-patch/device/soc/hisilicon/` 下所有 .patch 在打包前预应用到源码树（如 `0001-Add-driverbase-and-sepolicy.patch`、`0012` dep 修复、`0022` display 修复），结果直接打入 tar.gz，合作伙伴不需要再应用这些 patch。

**Phase 9 — 打包 tar.gz**
打包三部分：
- `./vendor/`（outer vendor，已去源码）
- `./ohos5/device/`（改造后的 device 目录）
- `./ohos5/vendor/hisilicon/<product>/`（产品 BUILD.gn，含预编译路径）

同时内嵌 3 个 bundled patch（`0002`/`0003`/`0001-fix-cstring-include`）。

**生成合作伙伴 apply 脚本（`apply_patches_sdk_partner.sh`）**
从供应商原脚本自动改造：
- 移除 `apply_custom_sdk_vendor_patches()`
- `apply_custom_ohos_patches()` 跳过 `device/` 子目录
- `apply_other_patches()` 注释 `vendor_hisilicon/mp_*` 的 cp
- 顶部注入 `PRODUCT="${1:-mp_hi3781v730}"` 支持双产品参数化
- 插入 `fix_depsgard_hdi_whitelist()` 修复 HDI 白名单

---

## 四、供应商原始编译流程

### 步骤一：`bash apply_patches_sdk.sh`

**1. `clean_workspace()`**
- `git clean -q -dfx`（含 .gitignore 目录）
- 删除 prebuilts/，重新运行 `build/prebuilts_download.sh`（~4GB 工具链，已优化为本地缓存跳过下载）

**2. `upgrade_sdk()`**
- 将 `<SDK_PKG>.tar.gz`（原始硬件 SDK 包）解压到 `device/` 和 `vendor/`（含芯片 SDK：驱动头文件、预编译 .so、board 配置、BUILD.gn）

**3. `apply_sdk_base_patches()`**
- 对开源社区仓库（base/build/drivers/foundation/kernel/third_party）打供应商定制 patch

**4. `apply_custom_ohos_patches()`**
- 打 custom-ohos-patch/ 下自定义补丁，包括：
  - `device/soc/hisilicon/0001-Add-driverbase-and-sepolicy.patch`（注入 driverbase 源码 + sepolicy）
  - `0012-Fix-huanglong-uapi-extra-deps.patch`（修 BUILD.gn dep）
  - `0022-fix-display-composer-deps.patch`
  - build/、developtools/ 下的构建系统修复 patch

**5. `apply_other_patches()`**
- 从 PATCH_OTHER_DIR/ 将 `vendor/hisilicon/<product>/` BUILD.gn 拷贝到工作区
- 拷贝 common_patch/ 中供 `build.sh --patch` 使用的 patch 文件

### 步骤二：`./build.sh --product-name <product> --patch`
- 注入 `drivers/interface/tvservice/`（IDL 接口定义）
- 注入 `drivers/peripheral/tvservice/`（驱动实现骨架）
- GN 初始化，生成 `out/<board>/build_configs/`

### 步骤三：`./build.sh --product-name <product> --cache`

| 产物类型 | 数量 | 代表 |
|---|---|---|
| `libuapi_*.so` | ~43 个 | 芯片 UAPI 接口库 |
| 驱动 HAL .so | ~20 个 | display/audio/tvservice/TEE |
| 可执行文件 | ~70 个 | pdmtool + sample_* 系列 |
| Kernel 镜像 | boot_d.img / dtbo_d.img | 内核+设备树 |
| Bootloader | fastboot_d.bin / sbl_d.bin / slaveboot_d.bin | 引导链 |
| 分区镜像 | vendor.img / system.img 等 | 最终烧录产物 |

---

## 五、合作伙伴完整编译流程

### 前提条件
- 干净 ohos5 源码树（从 `ohos5_2026_03_14.tar.gz` 解压，55GB，无 device/vendor/out）
- `common_patch/` 目录中放入：partner SDK tar.gz（943MB）和 `apply_patches_sdk_partner.sh`

### 步骤一：`bash apply_patches_sdk_partner.sh [product]`

**`clean_workspace()`**

| 操作 | 供应商脚本 | 合作伙伴脚本 | 原因 |
|------|-----------|------------|------|
| git clean | `-dfx` | `-df`（保留 .gitignore 目录）| 保留 node_modules symlink |
| 删除 prebuilts/ | 每次删除重下 | 不删，条件检查 | 避免时序问题 |
| prebuilts_download | 每次都跑 | `build-tools` 不存在才跑 | 已安装则跳过 |
| lfs pull | 执行 | 注释掉 | 源码来自本地 tar.gz |

**`upgrade_sdk()`**：从 partner tar.gz 解压 vendor/、device/、vendor/hisilicon/$PRODUCT/ 和 3 个 bundled patch，覆盖到工作区。

**`apply_sdk_base_patches()`**：与供应商完全相同（开源仓 patch）。

**`apply_custom_ohos_patches()`**：跳过 device/ 子目录（已预应用），仍应用 build/、developtools/ patch。

**`apply_other_patches()`**：注释 vendor_hisilicon/mp_* 的 cp（BUILD.gn 已在 tar.gz，是 prebuilt 版本，不能被覆盖）；保留 common_patch/ 的 cp。

**`fix_depsgard_hdi_whitelist()`**：追加 `libdisplay_hwgraphics_driver_1.0.z.so` 到白名单，防止增量编译误报。

### 步骤二：`./build.sh --product-name $PRODUCT --patch`
与供应商相同（注入 drivers/interface/tvservice、drivers/peripheral/tvservice）。

### 步骤三：`./build.sh --product-name $PRODUCT --cache`

| 目标 | 供应商 | 合作伙伴 |
|------|--------|---------|
| `libuapi_*.so` × 43 | 源码编译 | prebuilt install |
| `libteec_vendor.so + teecd` | 源码编译 | prebuilt install |
| `libuapi_securec.so` | 源码编译 | prebuilt install |
| `libtvhal_soc.z.so` 等 | 源码编译 | prebuilt install |
| `pdmtool` | 源码编译 | prebuilt install |
| `boot_d.img / dtbo_d.img` | kernel 源码编译 | 从 device/<board>/kernel/ 拷贝 |
| `fastboot_d.bin` 等 | bootloader 编译 | 从 device/<board>/bootloader/ 拷贝 |
| sample_* 系列 | 源码编译 | 源码编译（保留） |
| OHOS 框架层 .so | 源码编译 | 源码编译（不变） |

**结果**：所有关键镜像与供应商 md5 完全一致 ✅

### node_modules 注意事项
`git clean -df` 会删除 symlink。每次 apply 后需检查并重建：
```bash
ln -s /data/<user>/node_modules_cache/ace_ets2bundle/node_modules \
      ohos5/developtools/ace_ets2bundle/compiler/node_modules
ln -s /data/<user>/node_modules_cache/ace_js2bundle/node_modules \
      ohos5/developtools/ace_js2bundle/ace-loader/node_modules
```

---

## 六、双产品合并：merge_sdk.py

730 和 735 各自 transform 生成独立 tar.gz，再通过 `merge_sdk.py` 合并为单一包（943MB），支持两产品共用一份 SDK。合并时自动检测 `vendor/hisilicon/` 下的产品目录。

---

## 七、版本记录

| 版本 | SDK 大小 | 主要变化 |
|------|----------|---------|
| v1 | 1.2GB | 初始版（含 Phase7 board 硬编码 bug）|
| v2 | 943MB | Phase7 动态 board + 大块源码过滤（u-boot/liteos/av/opus 等）|
| v3 | 944MB | 追加 alsa/display 测试过滤 |
| v4 | 943MB | Phase 5.11：libteec_vendor/secure_c/pdmtool 改为预编译 |
| v5 | 942MB | 追加 13 个过滤条目 + apply 脚本双产品参数化 |

---

## 八、残留源码分析（v5，共 64 个 .c/.cpp）

### 类型一：`ohos5_ext/` 平台扩展源码（~35 个）

**路径：** `vendor/huanglong/ohos/ohos5_ext/**/*.c/.cpp`

**保留原因：** `EXCLUDE_WITHIN_SCAN_ROOT = {'ohos/ohos5_ext'}` 保护，不被 `delete_source_files()` 删除。

**不能删原因：** `build.sh --patch` 给 foundation/ 打 patch 后，OHOS 开源框架（graphic_2d、tvservice 等）会直接 `#include` 或在 GN `sources` 中引用这些文件。它们是被 OHOS 框架内联编译的芯片适配层，必须以源码形式分发，否则 foundation 层编译报 missing file。

### 类型二：`vendor_capture.c` + `vendor_render.c`（2 个）

**路径：** `device/board/hisilicon/<board_730>/audio_alsa/`

**保留原因：** 在 `KEEP_SOURCE_WHITELIST` 中显式保留。

**不能删原因：** OHOS 社区 `drivers/peripheral/audio/` 在编译 `libaudio_primary_impl_vendor.z.so` 时，通过 `sources` 直接引用这两个文件。它们不是独立的 BUILD.gn 目标，而是被社区侧 BUILD.gn 包含进去一起编译，改为 prebuilt 需要修改社区代码，不可行。

### 类型三：`uapi/pvr/` + `uapi/teletext/` 静态库（~15 个）

**路径：** `vendor/huanglong/uapi/pvr/`、`vendor/huanglong/uapi/teletext/`

**保留原因：** 静态库产物（.a）被链接进其他 .so，不独立安装到分区。

**不能删原因：** 静态库在编译时被静态链接进 .so，每个引用它的 .so 的 BUILD.gn 都需要调整，关系复杂。pvr/teletext 涉及 GPU 和图文电视驱动，ABI 依赖头文件，改造工作量大、风险高。

### 类型四：feature 未开启的未转换目标（~5~10 个）

**保留原因：** `delete_source_files()` 中：同目录 BUILD.gn 不含 `ohos_prebuilt_` 则保留源文件。

**不能删原因：** 当前产品 feature 未开启，但其他产品（如 730/735 差异）或合作伙伴可能开启，保留是安全兜底。

### 汇总

| 类型 | 估计数量 | 是否可删 | 原因 |
|------|---------|---------|------|
| `ohos5_ext/` 平台扩展 | ~35 | ❌ 不可删 | OHOS 开源框架直接引用，必须源码 |
| `vendor_capture/render.c` | 2 | ❌ 不可删 | 社区 ALSA HAL 内联编译 |
| `uapi/pvr` + `uapi/teletext` 静态库 | ~15 | ⚠️ 可改造但复杂 | 静态链接关系复杂，ABI 依赖 |
| feature 未开启的目标 | ~5~10 | ✅ 可分析后删 | 确认 730/735 均不用则可删 |

**实际上 64 个里真正涉及芯片 IP 的只有 `uapi/pvr`、`uapi/teletext` 两组静态库，其余的要么是必须的 OHOS 框架适配源码，要么已经是安全的示例代码。**

---

## 九、待完成工作

| 优先级 | 内容 |
|--------|------|
| P0 | 确认 OHOS3(730)/OHOS4(735) driverbase 补齐后编译通过 |
| P1 | 重跑 transform v5，验证合作伙伴侧编译 |
| P2 | 烧录验证（730/735 硬件启动）|
| P3 | `libteec_system/source/`（14 个 .c）改为预编译（已加入 `_SOURCE_EXCLUDE_PREFIXES`，待验证）|
| P4 | `uapi/pvr` + `uapi/teletext` 静态库改造（复杂，低优先级）|
