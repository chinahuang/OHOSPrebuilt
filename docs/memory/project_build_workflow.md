---
name: mp_hi3781v730 build workflow
description: Complete build workflow for the mp_hi3781v730/v735 products in this OpenHarmony project
type: project
---

Product: `mp_hi3781v730` / `mp_hi3781v735`

## 目录（当前有效，2026-04-03）

| 目录 | 用途 | 产品 |
|------|------|------|
| `/data/huanghao/OHOS2/ohos5` | 合作伙伴编译 | 730 |
| `/data/huanghao/OHOS3/ohos5` | 供应商编译 | 730 |
| `/data/huanghao/OHOS4/ohos5` | 供应商编译 | 735 |
| `/data/huanghao/OHOS5/ohos5` | 合作伙伴编译 | 735 |

## 供应商侧完整流程
1. `cd /data/huanghao/OHOS3/ohos5/common_patch && bash apply_patches_sdk.sh`
2. `./build.sh --product-name mp_hi3781v730 --patch`（**必须先执行 --patch**）
3. `./build.sh --product-name mp_hi3781v730 --cache`
4. `python3 transform_sdk.py --product mp_hi3781v730`（生成 partner SDK）

## 合作伙伴侧完整流程
1. 将 tar.gz 和 apply_patches_sdk_partner.sh 放入 common_patch/
2. `cd /data/huanghao/OHOS2/ohos5/common_patch && bash apply_patches_sdk_partner.sh`
3. 重建 node_modules symlink（apply 中 git clean -df 会删掉）：
   ```bash
   ln -sfn /data/huanghao/node_modules_cache/ace_ets2bundle/node_modules \
       /data/huanghao/OHOS2/ohos5/developtools/ace_ets2bundle/compiler/node_modules
   ln -sfn /data/huanghao/node_modules_cache/ace_js2bundle/node_modules \
       /data/huanghao/OHOS2/ohos5/developtools/ace_js2bundle/ace-loader/node_modules
   ```
4. `./build.sh --product-name mp_hi3781v730 --patch`（**必须先执行 --patch**）
5. `./build.sh --product-name mp_hi3781v730 --cache`

## transform 迭代工作流
供应商 out/ 已有完整产物时，无需重新编译，直接重跑 transform：

```bash
# 730
python3 /data/huanghao/OHOS3/ohos5/transform_sdk.py --product mp_hi3781v730 --ohos-root /data/huanghao/OHOS3/ohos5

# 735
python3 /data/huanghao/OHOS4/ohos5/transform_sdk.py --product mp_hi3781v735 --ohos-root /data/huanghao/OHOS4/ohos5
```

## merge 工作流
```bash
python3 /data/huanghao/merge_sdk.py \
    --base  /data/huanghao/OHOS3/R200X_...tar.gz \
    --merge /data/huanghao/OHOS4/R200X_...tar.gz \
    --output /data/huanghao/OHOS3/R200X_combined_730_735_v2.tar.gz
```

## 归档位置
- v1（含 bug，已备份）：`/home/<user>/erjinzhi/0403/backup_v1/`
- v2（当前版本，源码过滤 + 启动修复）：`/home/<user>/erjinzhi/0403/archive_v2/`
  - SDK 包：`R200X_combined_730_735_v2.tar.gz`（943MB）
  - 镜像：`images/730_partner_v2_0403.tar.gz`（待烧录）/ `images/735_partner_v2_0403.tar.gz`（待烧录）
