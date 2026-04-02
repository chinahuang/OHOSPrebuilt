# OHOS Prebuilt SDK Tools

将 OpenHarmony device/vendor 源码编译替换为预编译分发模式，供合作伙伴无源码编译产品。

## 目录结构

```
scripts/
  transform_sdk.py              # 核心转换脚本：供应商 out/ → 合作伙伴 tar.gz
  apply_patches_sdk.sh          # 供应商侧 apply 脚本
  apply_patches_sdk_partner.sh  # 合作伙伴侧 apply 脚本（由 transform 生成）

run_scripts/
  run_vendor_730.sh             # OHOS3：供应商编译 730
  run_vendor_735.sh             # OHOS4：供应商编译 735
  run_partner_730.sh            # OHOS2：合作伙伴编译 730
  run_partner_735.sh            # OHOS5：合作伙伴编译 735

patches/
  custom-ohos-patch/            # 持久化的自定义 patch（build/device/developtools）

docs/
  memory/                       # 项目记忆文件（流程/checklist/bug历史）
```

## 服务器环境（192.168.50.88）

| 目录 | 角色 | 产品 |
|------|------|------|
| `/data/huanghao/OHOS3/ohos5` | 供应商编译 | mp_hi3781v730 |
| `/data/huanghao/OHOS4/ohos5` | 供应商编译 | mp_hi3781v735 |
| `/data/huanghao/OHOS2/ohos5` | 合作伙伴编译 | mp_hi3781v730 |
| `/data/huanghao/OHOS5/ohos5` | 合作伙伴编译 | mp_hi3781v735 |

## 标准流程

### 供应商侧
```bash
cd /data/huanghao/OHOS3/ohos5/common_patch && bash apply_patches_sdk.sh
./build.sh --product-name mp_hi3781v730 --cache --patch
./build.sh --product-name mp_hi3781v730 --cache
python3 transform_sdk.py --product mp_hi3781v730
```

### 合作伙伴侧
```bash
cd /data/huanghao/OHOS2/ohos5/common_patch && bash apply_patches_sdk_partner.sh
./build.sh --product-name mp_hi3781v730 --cache --patch
./build.sh --product-name mp_hi3781v730 --cache
```

## 编译前检查清单

见 `docs/memory/project_prebuild_checklist.md`

## 共享缓存（独立于 OHOS 目录）

| 路径 | 内容 |
|------|------|
| `/data/huanghao/prebuilts_cache/` | 编译工具链（~4GB） |
| `/data/huanghao/node_modules_cache/` | node_modules（~309MB） |
