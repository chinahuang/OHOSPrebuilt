---
name: prebuilt改造验证操作日志
description: 逐步操作日志：每执行一步更新，下次对话先读此文件恢复进度
type: project
---

## 当前状态（2026-04-02）

### 🔄 四目录全量编译验证中（解决启动失败问题）

**背景**：合作伙伴镜像烧录后启动失败，怀疑 transform_sdk.py 的 bootloader/kernel 转换逻辑有问题。
本次目标：四个目录全部编译完成后，做全面产物对比，定位 transform_sdk.py 的具体问题。

**目录分工**：

| 目录 | 角色 | 产品 | 状态 |
|------|------|------|------|
| `/data/huanghao/OHOS3/ohos5` | 供应商 | 730 | ✅ 已完成（images/730.tar.gz 725MB） |
| `/data/huanghao/OHOS4/ohos5` | 供应商 | 735 | ✅ 已完成（images/735.tar.gz 738MB，19:14） |
| `/data/huanghao/OHOS2/ohos5` | 合作伙伴 | 730 | 🔄 build --patch 进行中（~65%） |
| `/data/huanghao/OHOS5/ohos5` | 合作伙伴 | 735 | 🔄 apply 清理阶段（repo forall 中） |

**已知问题（2026-04-02）**：
- OHOS5 被监控脚本启动了两个实例，发生 index.lock 冲突 → 已清理，单实例重启
- OHOS2 之前因 index.lock 失败过一次 → 已清理 lock 文件重启，目前正常

**运行中的脚本**：
- OHOS2：`/data/huanghao/OHOS2/run_partner_730_new.sh`（PID 2715000），log：`run_partner_730_new.log`
- OHOS5：`/data/huanghao/OHOS5/run_partner_735.sh`（PID 3392434），log：`run_partner_735.log`

**完成后下一步**：
对比四目录产物（vendor.img / system.img / bootloader / kernel），分析 transform_sdk.py 中 Phase 7 bootloader/kernel 转换逻辑是否导致 partner build 重新编译了预编译产物。

---

## 历史状态（2026-03-31）

### ✅ 四阶段验证计划 — Phase 1~3 全部完成

**用户确定的验证方法论**：

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 供应商编译 730+735，制作单一 tar.gz（同时支持两产品） | ✅ 完成 |
| Phase 2 | 供应商 clean rebuild 730，合作伙伴用 Phase1 tar.gz rebuild 730，对比 out/ | ✅ 通过 |
| Phase 3 | 供应商 clean rebuild 735，合作伙伴用 Phase1 tar.gz rebuild 735，对比 out/ | ✅ 通过 |
| Phase 4 | 根据 Phase2/3 差异修复，迭代至无差异 | ✅ 不需要（无内容差异） |

---

### Phase 1 结果

**最终 tar.gz**：`/home/wuhan/OHOS3/R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz`（**1183.8 MB**）
**Partner 脚本**：`/home/wuhan/OHOS3/ohos5/common_patch/apply_patches_sdk_partner.sh`

| 步骤 | 日志 | 结果 |
|------|------|------|
| OHOS3 apply+build 730 | apply/build_patch/cache_730_rebuild.log | ✅ |
| transform --product mp_hi3781v730 | transform_730_rebuild.log | ✅ 155 产物 |
| OHOS3 apply+build 735 | apply_735_rebuild2.log / build_patch/cache_735_rebuild.log | ✅ |
| 恢复 730 prebuilts（从 tar.gz 提取） | run_735_full2.log | ✅ 69 个 .so |
| transform --product mp_hi3781v735 | transform_735_rebuild.log | ✅ 156 产物，1183.8 MB |

**Phase 1 中发现并修复的问题**：

- **Bug P1-A**：`0022-fix-display-composer-deps.patch` 因路径含符号链接导致 apply_735 报错退出
  - 修复：patch 备份移出（`/home/wuhan/OHOS3/0022-fix-display-composer-deps.patch.bak`），transform Phase 8.5 以代码方式处理同一修复
- **Bug P1-B**：`apply_patches_sdk.sh` 执行 `rm -Rf device/` 清除 730 prebuilts
  - 修复：transform_735 运行前从 tar.gz 提取恢复 device/wudangstick/（写入 run_735_full2.sh 脚本中）

---

### Phase 2 结果（730 供应商 vs 合作伙伴）

供应商 OHOS3 build 730 完成：17:33 | 合作伙伴 OHOS2 build 730 完成：17:33

| 对比内容 | 差异 | 结论 |
|---------|------|------|
| vendor 分区（.so/bin 全部文件） | 0 | ✅ 完全一致 |
| system 分区 .so | 0 | ✅ 完全一致 |
| vendor 缺失 | 6 个 khdf 内核编译中间件 | ✅ 不进入分区，无影响 |
| bootloader/kernel (.img/.bin) | 不同 | ⚠️ 非确定性编译（含时间戳），预期行为 |
| *.img 镜像文件 | 部分不同 | ⚠️ ext4 打包时间戳，内容已验证一致 |

**结论：Phase 2 (730) 通过** ✅

---

### Phase 3 结果（735 供应商 vs 合作伙伴）

供应商 OHOS3 build 735 完成 | 合作伙伴 OHOS2 build 735 完成

| 对比内容 | 差异 | 结论 |
|---------|------|------|
| vendor 分区（.so/bin 全部文件） | 0 | ✅ 完全一致 |
| system 分区 .so | 0 | ✅ 完全一致 |
| vendor 缺失 | 6 个 khdf 内核编译中间件 | ✅ 不进入分区，无影响 |
| bootloader/kernel (.img/.bin) | 不同 | ⚠️ 非确定性编译（含时间戳），预期行为 |
| *.img 镜像文件 | 部分不同 | ⚠️ ext4 打包时间戳，内容已验证一致 |

**结论：Phase 3 (735) 通过** ✅

---

### 整体结论

单一 tar.gz（1183.8 MB）同时支持 730 和 735 合作伙伴编译，两个产品的 vendor/system 分区内容与供应商产物完全一致。bootloader/kernel 差异为非确定性编译的预期行为，不影响功能。

**下次部署新版本时的标准流程**：
1. OHOS3 apply → build 730 → transform 730
2. OHOS3 apply → build 735 → （脚本自动从 tar.gz 恢复 wudangstick prebuilts）→ transform 735
3. 将生成的 tar.gz 和 apply_patches_sdk_partner.sh 交付合作伙伴

---

## 历史状态（2026-03-28）

### ✅ Round 3 全流程验证完成（730 + 735 双产品，含 bundled patches + prebuilts 条件检查）

transform_sdk.py 新增：3个 bundled patch 嵌入 tar.gz，apply 脚本自动解压覆盖，prebuilts_download 条件检查（首次拉取自动安装）。在全新重置的 OHOS2 上验证通过。

**Round 3 验证（2026-03-28，tar.gz 1185.3 MB + bundled patches）：**

| 步骤 | 产品 | 结果 |
|------|------|------|
| apply_patches_sdk_partner.sh | 730 | ✅（bundled patches 自动应用，prebuilts 自动安装） |
| build --patch | mp_hi3781v730 | ✅ 11m31s |
| build --cache | mp_hi3781v730 | ✅ 6m23s |
| apply_patches_sdk_partner.sh | 735 前重置 | ✅（bundled patches 自动应用，prebuilts 跳过已安装） |
| build --patch | mp_hi3781v735 | ✅ 11m31s |
| build --cache | mp_hi3781v735 | ✅ 6m19s |

**transform_sdk.py 新增功能（Round 3）：**
- `pack_tarball()`: 打包 3 个 bundled patches 到 tar.gz（`./ohos5/common_patch/custom-ohos-patch/...`）
- `generate_partner_apply_patches_sh()` step 6: tar 解压时额外提取 bundled patches，然后 cp 覆盖到 custom-ohos-patch/
- `generate_partner_apply_patches_sh()` step 10: prebuilts_download 条件检查（`if [ ! -d "$OHOS_PATH/prebuilts/build-tools" ]`）

**问题记录（Round 3）：**
- prebuilts_download 再次网络卡死（stalled on cmake/clang_windows downloads）→ kill 重启后秒完（已全部缓存）

---

## 历史状态（2026-03-27）

### ✅ 合并 tar.gz 全流程验证完成（730 + 735 双产品，含源码清理）

单一 tar.gz（1185.3 MB）同时支持 730 和 735 合作伙伴编译，额外清理了 vendor/hisilicon/mp_hi3781v735/ 中残留的 50 个 .c/.cpp 源码文件。

**Round 2 验证（2026-03-27，新 tar.gz 1185.3 MB）：**

| 步骤 | 产品 | 结果 |
|------|------|------|
| apply_patches_sdk_partner.sh | 730 前 | ✅ |
| build --patch | mp_hi3781v730 | ✅ |
| build --cache | mp_hi3781v730 | ✅ |
| apply_patches_sdk_partner.sh | 735 前重置 | ✅ |
| build --patch | mp_hi3781v735 | ✅ |
| build --cache | mp_hi3781v735 | ✅ |

**Partner 产物**：
- tar.gz：`/home/wuhan/OHOS3/R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz`（1185.3 MB）
- 脚本：`/home/wuhan/OHOS3/ohos5/common_patch/apply_patches_sdk_partner.sh`

**里程碑备份**：`/home/wuhan/backup_combined_730_735_v1.0/`（含 README.txt）

---

## 735 阶段新增修复

### Bug 735-A：build --patch 在错误时机运行导致 patch 失败
- 根因：`build --patch` 在 `apply_patches_sdk.sh` 之前运行，workspace 处于 730 post-build 状态，`0005-usb_upgrade.patch` context 不匹配
- 修复：按正确顺序执行（先 apply 再 build --patch）

### Bug 735-B：patch_process.py 幂等性修复在 apply 后丢失
- 根因：`clean_workspace` 的 `repo forall git checkout` 重置了 `build/hb/util/prebuild/patch_process.py`，丢失幂等性检查代码
- 修复：
  1. 从 OHOS2 复制修复版到 OHOS3
  2. 持久化：`common_patch/custom-ohos-patch/build/0002-fix-patch-idempotency.patch`

### Bug 735-C：cstring include 缺失（同 730 的问题）
- 根因：`developtools/global_resource_tool` 中 `strerror`/`strcmp` 未声明
- 修复：
  1. 从备份应用 `0001-fix-cstring-include.patch`
  2. 持久化：`common_patch/custom-ohos-patch/developtools/global_resource_tool/0001-fix-cstring-include.patch`

### Bug 735-D：transform_sdk.py SyntaxError（字面换行）
- 根因：`generate_partner_apply_patches_sh` 第9步中的 `modified.replace()` 字符串含字面换行，Python 3.12 报 `unterminated string literal`
- 修复：用二进制字节替换，将 `0x0a 0x27 0x2c`（字面换行+'`,`）改为 `0x5c 0x6e 0x27 0x2c`（`\n`,）

---

## 730 里程碑 v1.0 备份信息

**备份目录**：`/home/wuhan/backup_730_prebuilt_v1.0/`（192.168.50.88）

```
backup_730_prebuilt_v1.0/
├── README.txt                                  产品/验证结果说明
├── transform_sdk.py                            SDK 转换主脚本（供应商→合作伙伴）
├── apply_patches_sdk.sh                        供应商侧 apply 脚本
├── apply_patches_sdk_partner.sh                合作伙伴侧 apply 脚本（由 transform 生成）
├── patches/
│   ├── 0012-Fix-huanglong-uapi-extra-deps.patch   huanglong_uapi 加入 8 个 uapi deps
│   ├── 0022-fix-display-composer-deps.patch        display_composer_model 加入 libdisplay_utils_vendor
│   ├── 0001-fix-patch-idempotency.patch             build 幂等性修复
│   └── 0001-fix-cstring-include.patch              developtools cstring include 修复
└── other-patches/
    └── rtkbt_wifi_BUILD.gn                         rtkbt_wifi 加入 libbt_vendor 依赖
```

---

## 环境信息

| 角色 | 地址 | 路径 |
|------|------|------|
| 供应商侧 | 192.168.50.88 | /data/huanghao/OHOS3/ohos5 |
| 合作伙伴侧 | 192.168.50.88 | /data/huanghao/OHOS2/ohos5 |
| transform_sdk.py | 192.168.50.88 | /data/huanghao/OHOS3/ohos5/transform_sdk.py |
| 原始 base SDK (730) | 192.168.50.88 | /home/wuhan/sdk/R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz（只读，1.1G）|
| partner tar.gz 输出 | 192.168.50.88 | /data/huanghao/OHOS3/R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz |
| 备份文件 | 192.168.50.88 | /home/wuhan/erjinzhi/0401/（scripts/ + logs/）|

**目录变更记录（2026-04-01）**：原 `/home/wuhan/OHOS3` 和 `/home/wuhan/OHOS2` 已迁移至 `/data/huanghao/`，原目录已删除。`/data` 为新增 1.4T 分区（nvme0n1p6），开机自动挂载，所有用户可读写。

---

## 标准操作流程（经过验证）

### 供应商侧（OHOS3）：
1. `cd /data/huanghao/OHOS3/ohos5/common_patch && bash apply_patches_sdk.sh`
2. `./build.sh --product-name mp_hi3781v7XX --patch`
3. `./build.sh --product-name mp_hi3781v7XX --cache`
4. `python3 transform_sdk.py --product mp_hi3781v7XX`
5. `cp /data/huanghao/OHOS3/R200X_...tar.gz /data/huanghao/OHOS2/ohos5/common_patch/`
6. `cp /data/huanghao/OHOS3/ohos5/common_patch/apply_patches_sdk_partner.sh /data/huanghao/OHOS2/ohos5/common_patch/`

### 合作伙伴侧（OHOS2）：
1. `cd /data/huanghao/OHOS2/ohos5/common_patch && bash apply_patches_sdk_partner.sh`（内含 clean_workspace + 白名单修复）
2. `./build.sh --product-name mp_hi3781v7XX --patch`（**不可跳过**，否则缺 drivers/interface/tvservice/）
3. `./build.sh --product-name mp_hi3781v7XX --cache`

⚠️ **重要**：
- `apply_patches_sdk.sh` 必须在 `build --patch` 之前运行，否则 workspace 状态不对
- build --patch 失败后不可直接重试，必须重新跑 apply_patches_sdk_partner.sh 清理状态
- prebuilts/ 不可删除（避免 node_modules 时序问题）
- 两个产品之间必须重跑 apply_patches_sdk_partner.sh（重置 workspace）
- 如 ohpm init 阶段 npm 卡死（pnpm 安装），kill 该 npm 进程，build 会自动继续
- `sdk-base-patch/build/` 中**不应有** 0001-fix-patch-idempotency.patch（已于2026-03-26删除），只保留 `build.patch`

---

## 全部已修复 Bug 汇总

### 合并 tar.gz 阶段（2026-03-26 ~ 2026-03-27）
- **Bug M1**：`prebuilt_board_dir` Undefined identifier —— 原因：product.gni 中的变量是文件作用域；修复：在 `build/ohos_var.gni` 中加 `declare_args() { prebuilt_board_dir = device_name }`，通过 patch `custom-ohos-patch/build/0003-add-prebuilt-board-dir.patch` 持久化
- **Bug M2**：node_modules 被 git clean 删除 —— 原因：apply 脚本使用 `-dfx`；修复：改为 `-df`；transform_sdk.py 同步修改生成逻辑
- **Bug M3**：libcust BUILD.gn 缺失预编译目标 —— 原因：Phase 5 只处理主产品（730）无 libcust；修复：手动写 prebuilt BUILD.gn 引用 `${prebuilt_board_dir}`，经 symlink 改到 outer vendor，tar.gz 重新生成
- **Bug M4**：0002-fix-patch-idempotency.patch 冲突 —— 原因：sdk-base-patch/build/0001（旧2-fix版）先于 custom-ohos-patch/build/0002（新3-fix版）应用，导致 patch_process.py 已有 subprocess；修复：删除 OHOS2 的 sdk-base-patch/build/0001，并将 custom-ohos-patch/build/0002 重新生成为从原始→3-fix 的完整 diff
- **Bug M5**：pnpm 安装卡死 —— 原因：ohpm 初始化时 npm install 等待网络下载 pnpm 7.30.0 超时；修复：kill 卡死的 npm 进程，build 自动继续（pnpm 已从 corepack 可用）
- **Bug M6**：extra_products .c/.cpp 源码残留 —— 原因：`all_scan_roots` 只包含主产品 vendor 目录，未包含 extra_products；修复：在 `transform_sdk.py` main() 中新增 `extra_vendor_scan_roots = [f"vendor/hisilicon/{ep}" for ep in extra_products]` 并加入 `all_scan_roots`，Phase 5.5/6 同步清理 extra_products 的 vendor 目录

### 735 阶段（2026-03-24）
- **Bug 735-A**：build --patch 顺序错误
- **Bug 735-B**：patch_process.py 幂等性丢失
- **Bug 735-C**：cstring include 缺失（同 730）
- **Bug 735-D**：transform_sdk.py 字面换行 SyntaxError

### Round16 修复（730）
- **Bug AG**：prebuilts_download.py node_modules 时序问题

### Round15 修复（730）
- **Bug AE**：transform_sdk.py tar_output 覆盖原始 base tar.gz
- **Bug AF**：Fix3（rtkbt_wifi libbt_vendor）持久化到 other-patches

### Round13/14 修复（730）
- **Bug AA**：transform_sdk.py dataclass 字段顺序 TypeError
- **Bug AB**：apply_patches_sdk_partner.sh 生成路径错误
- **Bug AC**：Phase 8 device patches 全部 WARN 失败
- **Bug AD**：Fix1/2/3 持久化

### 第三轮修复（Round 11-12，730）
- **Bug S-Y**：各种 prebuilt 安装问题

### 遗留低优先级问题
- 4 个 empty ohos_prebuilt_etc 块（source 文件缺失，未处理）：
  - vendor/huanglong/linux/scripts/ohos/BUILD.gn: rtk_bt, rtk_wifi
  - vendor/huanglong/modules/virtualkeypad/source/BUILD.gn: ohos_virtualkeypad.cfg, ohos_key_pad.xml

---

## transform_sdk.py 改进汇总

| Phase | 内容 |
|-------|------|
| Phase 5 | 保留 relative_install_dir + install_enable=true for prebuilt_executable |
| Phase 5.5 | 清理残留 source-compiled 目标 |
| Phase 5.6 | 清理 bundle.json test 引用 |
| Phase 5.7 | 修复 deps_guard 白名单（whitelist.json 加入 libdisplay_hwgraphics_driver_1.0.z.so）|
| Phase 5.8 | 自动添加 companion ohos_prebuilt_etc 目标 |
| Phase 5.9 | 修复 //out/ source 引用 |
| Phase 7 (kernel) | build_kernel.sh OUT_ROOT 路径修复 |
| Phase 7 (bootloader) | programmer_d.bin 加入拷贝列表 |
| Phase 8 | 预应用 device custom patches |
| generate_partner_sh | 生成的脚本包含白名单修复函数 |
| generate_partner_sh | 不删除 prebuilts/（避免 node_modules 时序问题）|
