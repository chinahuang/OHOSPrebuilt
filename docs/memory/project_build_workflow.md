---
name: mp_hi3781v730 build workflow
description: Complete build workflow for the mp_hi3781v730/v735 products in this OpenHarmony project
type: project
---

Product: `mp_hi3781v730` / `mp_hi3781v735`

## 目录规划（参考）

| 目录 | 用途 | 产品 |
|------|------|------|
| `<build_root>/OHOS2/ohos5` | 合作伙伴编译 | 730 |
| `<build_root>/OHOS3/ohos5` | 供应商编译 | 730 |
| `<build_root>/OHOS4/ohos5` | 供应商编译 | 735 |
| `<build_root>/OHOS5/ohos5` | 合作伙伴编译 | 735 |

## 供应商侧完整流程
1. `cd <ohos_root>/common_patch && bash apply_patches_sdk.sh`
2. `./build.sh --product-name mp_hi3781v730 --patch`（**必须先执行 --patch**）
3. `./build.sh --product-name mp_hi3781v730 --cache`
4. `python3 transform_sdk.py --product mp_hi3781v730`（生成 partner SDK）

## 合作伙伴侧完整流程
1. 将 tar.gz 和 apply_patches_sdk_partner.sh 放入 common_patch/
2. `cd <ohos_root>/common_patch && bash apply_patches_sdk_partner.sh`
3. 重建 node_modules symlink（apply 中 git clean -df 会删掉）：
   ```bash
   ln -sfn <node_modules_cache>/ace_ets2bundle/node_modules \
       <ohos_root>/developtools/ace_ets2bundle/compiler/node_modules
   ln -sfn <node_modules_cache>/ace_js2bundle/node_modules \
       <ohos_root>/developtools/ace_js2bundle/ace-loader/node_modules
   ```
4. `./build.sh --product-name mp_hi3781v730 --patch`（**必须先执行 --patch**）
5. `./build.sh --product-name mp_hi3781v730 --cache`

## transform 迭代工作流
供应商 out/ 已有完整产物时，无需重新编译，直接重跑 transform：

```bash
# 730
python3 transform_sdk.py --product mp_hi3781v730 --ohos-root <ohos_root_730>

# 735
python3 transform_sdk.py --product mp_hi3781v735 --ohos-root <ohos_root_735>
```

## merge 工作流
```bash
python3 merge_sdk.py \
    --base  <730_tar.gz> \
    --merge <735_tar.gz> \
    --output R200X_combined_730_735.tar.gz
```

## 归档版本记录

| 版本 | SDK 大小 | 说明 |
|------|----------|------|
| v1 | ~1.2GB | 初始版本（含 Phase7 board 硬编码 bug）|
| v2 | 943MB | Phase7 动态 board + 大块源码过滤（u-boot/liteos/av/opus 等）|
| v3 | 944MB | 追加过滤 alsa 工具源码 + display 测试代码（当前最新）|
