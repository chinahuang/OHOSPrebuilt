# OHOS Prebuilt SDK Tools

将 OpenHarmony device/vendor 源码编译替换为预编译分发模式，供合作伙伴无源码编译产品。

## 目录结构

```
scripts/
  transform_sdk.py              # 核心转换脚本：供应商 out/ → 合作伙伴 tar.gz
  merge_sdk.py                  # 多产品 tar.gz 合并脚本（730+735 → combined）
  apply_patches_sdk.sh          # 供应商侧 apply 脚本
  apply_patches_sdk_partner.sh  # 合作伙伴侧 apply 脚本（由 transform 生成）

run_scripts/
  run_vendor_730.sh             # 供应商编译 730
  run_vendor_735.sh             # 供应商编译 735
  run_partner_730.sh            # 合作伙伴编译 730
  run_partner_735.sh            # 合作伙伴编译 735

patches/
  custom-ohos-patch/            # 持久化的自定义 patch（build/device/developtools）

docs/
  memory/                       # 项目记忆文件（流程/checklist/bug历史）
```

## 目录规划（参考）

| 目录 | 角色 | 产品 |
|------|------|------|
| `<build_root>/OHOS3/ohos5` | 供应商编译 | mp_hi3781v730 |
| `<build_root>/OHOS4/ohos5` | 供应商编译 | mp_hi3781v735 |
| `<build_root>/OHOS2/ohos5` | 合作伙伴编译 | mp_hi3781v730 |
| `<build_root>/OHOS5/ohos5` | 合作伙伴编译 | mp_hi3781v735 |

## 标准流程

### 供应商侧（以 730 为例）
```bash
cd <ohos_root>/common_patch && bash apply_patches_sdk.sh
./build.sh --product-name mp_hi3781v730 --patch
./build.sh --product-name mp_hi3781v730 --cache
python3 transform_sdk.py --product mp_hi3781v730 --ohos-root <ohos_root>
```

### 多产品合并
```bash
python3 merge_sdk.py \
    --base  <730_tar.gz> \
    --merge <735_tar.gz> \
    --output R200X_combined_730_735.tar.gz
```

### 合作伙伴侧
```bash
cd <ohos_root>/common_patch && bash apply_patches_sdk_partner.sh
# 重建 node_modules symlink（apply 中 git clean -df 会删掉）
ln -sfn <node_modules_cache>/ace_ets2bundle/node_modules \
    <ohos_root>/developtools/ace_ets2bundle/compiler/node_modules
ln -sfn <node_modules_cache>/ace_js2bundle/node_modules \
    <ohos_root>/developtools/ace_js2bundle/ace-loader/node_modules
./build.sh --product-name mp_hi3781v730 --patch
./build.sh --product-name mp_hi3781v730 --cache
```

## 编译前检查清单

见 `docs/memory/project_prebuild_checklist.md`

## 共享缓存（独立于 OHOS 目录）

| 路径 | 内容 |
|------|------|
| `<build_root>/prebuilts_cache/` | 编译工具链（~4GB） |
| `<build_root>/node_modules_cache/` | node_modules（~309MB） |

## 版本记录

| 版本 | tar.gz 大小 | 说明 |
|------|-------------|------|
| v1 | ~1.2GB | 初始版本 |
| v2 | ~943MB | 过滤不必要源码（u-boot/liteos/frameworks/av 等），修复 Phase 7 board 动态解析 |
