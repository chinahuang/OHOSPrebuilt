---
name: prebuilt改造验证操作日志
description: 逐步操作日志：每执行一步更新，下次对话先读此文件恢复进度
type: project
---

## 当前状态（2026-04-03）

### ✅ v3 阶段完成 — 追加 alsa/display 测试源码过滤，验证通过

**本阶段（v2→v3）新增内容：**
- `_SOURCE_EXCLUDE_PREFIXES` 追加 alsa-lib/modules、alsalisp、aserver（无 BUILD.gn，不参与编译）
- 追加 display/source/test/（ohos_moduletest，不进设备镜像）
- `sample/audio/` 保留（cast/ai/aenc 子目录使用 ohos_executable 源码编译，不可删）

**累计完成（v2+v3）：**
1. **修复 bootloader/kernel 启动失败**（Phase 7 动态 board 解析）
2. **merge_sdk.py 新增 vendor 产品目录合并**
3. **transform_sdk.py 新增源码过滤**（tar.gz 1.2GB → 944MB，剩余 151 个 .c/.cpp 均编译必需）
4. **v3 合作伙伴验证编译全部通过**，关键镜像 md5 与供应商一致

---

### v3 验证结果（2026-04-03）

| 步骤 | 730 | 735 |
|------|-----|-----|
| transform v3 | ✅ 925MB | ✅ 901MB |
| merge v3 | ✅ 944MB | — |
| 分发到合作伙伴目录 | ✅ | ✅ |
| apply | ✅ exit=0 | ✅ exit=0 |
| build --patch | ✅ exit=0 | ✅ exit=0 |
| build --cache | ✅ exit=0 | ✅ exit=0 |

**关键镜像对比（合作伙伴 vs 供应商 md5）**：

| 镜像 | 730 | 735 |
|------|-----|-----|
| boot_d.img | ✅ 一致 | ✅ 一致 |
| dtbo_d.img | ✅ 一致 | ✅ 一致 |
| sbl_d.bin | ✅ 一致 | ✅ 一致 |
| slaveboot_d.bin | ✅ 一致 | ✅ 一致 |
| fastboot_d.bin | ✅ 一致 | ✅ 一致 |
| programmer_d.bin | ✅ 一致 | ✅ 一致 |

---

### v2 归档位置

服务器 `/home/<user>/erjinzhi/0403/archive_v2/`：

| 文件 | 大小 | 说明 |
|------|------|------|
| `R200X_combined_730_735_v2.tar.gz` | 943MB | 合作伙伴 SDK 包（730+735 合并，源码过滤后）|
| `images/730_partner_v2_0403.tar.gz` | 725MB | 730 编译产物，待烧录验证 |
| `images/735_partner_v2_0403.tar.gz` | 737MB | 735 编译产物，待烧录验证 |
| `scripts/transform_sdk.py` | 74K | v2 转换脚本 |
| `scripts/merge_sdk.py` | 7.6K | 合并脚本 |

---

### 修复内容汇总（2026-04-03）

**Bug Boot-1：bootloader/kernel 镜像不匹配导致启动失败**
- 根因：transform_sdk.py Phase 7 生成脚本中 board 名称**硬编码**，730 transform 先跑写 wudangstick，735 transform 后跑覆盖为 shaolingun，partner 730 build 指向错误 board 目录 → 源码重编 → 镜像不一致
- 修复：`build_kernel.sh` 改为 `BOARD=$(basename "$2")`，`build_bootloader.sh` 改为 `BOARD=$(basename "$PRODUCT_OUT")`，运行时动态解析

**merge_sdk.py 新增 vendor 产品目录自动合并**
- 原来只合并 `ohos5/device/<board>/`，遗漏了 `ohos5/vendor/hisilicon/<product>/`
- 新增 `detect_vendor_paths()` 函数，主流程自动检测并合并新 vendor product 目录

**transform_sdk.py 新增源码过滤（_tar_filter 增强）**
- 新增 `_SOURCE_EXCLUDE_PREFIXES` 列表，打包时排除：
  - `vendor/open_source/u-boot/`（bootloader 已预编译）
  - `vendor/platform/liteos/liteos-207.0.0-release/`
  - `vendor/open_source/frameworks/av/`
  - `vendor/open_source/opus/`、`fdk-aac/`
  - `vendor/open_source/alsa-lib/src/`、`test/`
  - `vendor/open_source/mbedtls/library/`、`tests/`、`programs/`、`3rdparty/`
- GPU driver 目录只排除 `.c/.cpp`，保留 `.h`
- 效果：67,060 文件 / 658MB（未压缩），tar.gz 减少 257MB

---

### 下阶段待完成工作

**P1（待烧录验证）**：
- 用户烧录 `730_partner_v2_0403.tar.gz` 和 `735_partner_v2_0403.tar.gz` 验证硬件启动

**P2（已分析，待实现）— 剩余 162 个 .c/.cpp 源码清理**：

C 类（可直接删除，测试/示例代码）：
- `vendor/huanglong/ohos/hardware/graphics/.../test/` 4 个 .cpp（ohos_moduletest，不进镜像）
- `vendor/huanglong/sample/audio/` 10 个 .c（示例程序，BUILD.gn 用预编译二进制）
- `vendor/open_source/alsa-lib/modules/` + `alsalisp/` + `aserver/` 7 个（alsa 工具）
- 操作：在 `_tar_filter()` 中追加这 3 个路径前缀

A 类（可改造为 prebuilt，有价值但工作量较大）：
- `vendor/platform/libteec_vendor/source/`（24 .c）— `prebuilt_part.gni` 已存在，改 product.gni 一行
- `vendor/platform/libteec_system/source/`（14 .c）— 同上
- `vendor/platform/secure_c/source/`（39 .c）— 需新建 prebuilt BUILD.gn
- `vendor/tools/board/huanglong/pdmtool.c`（1）— 改为 `ohos_prebuilt_executable`

B/D 类（不建议动）：
- `uapi/pvr/` `uapi/teletext/` `ohos5_ext/graphic/` 等（静态库或 graphic 扩展，改造复杂）

**P3（generate_partner_apply_patches_sh 维护）**：
- 确认生成的 apply 脚本每次 transform 后仍包含定向 lfs pull（av_codec + player_framework）
- 当前状态：脚本内容已验证正确，但 transform 重新生成后需再次验证

---

## 历史状态（2026-04-03 v1）

### ✅ Phase 1~3 四阶段验证 — 启动失败修复前

**v1 数据**：
- transform 730 tar.gz：1172.6 MB
- transform 735 tar.gz：1148.8 MB
- merged v1：`R200X_combined_730_735.tar.gz` 1196.3 MB（已备份到 `erjinzhi/0403/backup_v1/`）

**Phase 2/3 对比结论**（含时间戳差异说明）：
- vendor/system 分区 .so：完全一致 ✅
- boot/dtbo/sbl：不一致 ⚠️（Phase 7 board 硬编码 bug，已在 v2 修复）
- vendor.img/system.img：md5 不同（ext4 打包时间戳，内容一致）✅

---

## 历史状态（2026-03-31）

### ✅ 四阶段验证计划 — Phase 1~3 全部完成

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 供应商编译 730+735，制作单一 tar.gz（同时支持两产品）| ✅ 完成 |
| Phase 2 | 供应商 clean rebuild 730，合作伙伴用 Phase1 tar.gz rebuild 730，对比 out/ | ✅ 通过 |
| Phase 3 | 供应商 clean rebuild 735，合作伙伴用 Phase1 tar.gz rebuild 735，对比 out/ | ✅ 通过 |
| Phase 4 | 根据 Phase2/3 差异修复，迭代至无差异 | ✅ 不需要（无内容差异）|

**最终 tar.gz**：`R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz`（**1183.8 MB**）

**Phase 1 中发现并修复的问题**：
- **Bug P1-A**：`0022-fix-display-composer-deps.patch` 符号链接路径问题 → 移出，transform Phase 8.5 代码处理
- **Bug P1-B**：`apply_patches_sdk.sh` 执行 `rm -Rf device/` 清除 730 prebuilts → transform 735 前从 tar.gz 恢复

---

## 历史状态（2026-03-28）

### ✅ Round 3 全流程验证完成（730 + 735 双产品，含 bundled patches + prebuilts 条件检查）

transform_sdk.py 新增：3个 bundled patch 嵌入 tar.gz，apply 脚本自动解压覆盖，prebuilts_download 条件检查。

---

## 历史状态（2026-03-27）

### ✅ 合并 tar.gz 全流程验证完成（730 + 735 双产品，含源码清理）

单一 tar.gz（1185.3 MB）同时支持 730 和 735 合作伙伴编译。里程碑备份于 `backup_combined_730_735_v1.0/`。

---

## 全部已修复 Bug 汇总

### v2 阶段（2026-04-03）
- **Bug Boot-1**：Phase 7 board 硬编码 → 动态解析

### 合并 tar.gz 阶段（2026-03-26 ~ 2026-03-27）
- **Bug M1**：`prebuilt_board_dir` Undefined
- **Bug M2**：node_modules 被 git clean 删除
- **Bug M3**：libcust BUILD.gn 缺失预编译目标
- **Bug M4**：0002-fix-patch-idempotency.patch 冲突
- **Bug M5**：pnpm 安装卡死
- **Bug M6**：extra_products .c/.cpp 源码残留

### 735 阶段（2026-03-24）
- **Bug 735-A~D**：顺序/幂等性/cstring/SyntaxError

---

## transform_sdk.py 改进汇总

| Phase | 内容 |
|-------|------|
| Phase 5 | 保留 relative_install_dir + install_enable=true for prebuilt_executable |
| Phase 5.5 | 清理残留 source-compiled 目标 |
| Phase 5.6 | 清理 bundle.json test 引用 |
| Phase 5.7 | 修复 deps_guard 白名单 |
| Phase 5.8 | 自动添加 companion ohos_prebuilt_etc 目标 |
| Phase 5.9 | 修复 //out/ source 引用 |
| Phase 7 (kernel) | build_kernel.sh 动态解析 board（BOARD=$(basename "$2")）|
| Phase 7 (bootloader) | build_bootloader.sh 动态解析 board + programmer_d.bin 拷贝 |
| Phase 8 | 预应用 device custom patches |
| pack_tarball | _tar_filter 过滤不必要源码目录（v2 新增）|
| generate_partner_sh | 包含白名单修复函数、定向 lfs pull（av_codec + player_framework）|
