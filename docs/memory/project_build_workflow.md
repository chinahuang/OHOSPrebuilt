---
name: mp_hi3781v730 build workflow
description: Complete build workflow for the mp_hi3781v730 product in this OpenHarmony project
type: project
---

Product: `mp_hi3781v730`

## 目录（2026-04-01 迁移后）
- 供应商侧：`/data/<user>/OHOS3/ohos5`
- 合作伙伴侧：`/data/<user>/OHOS2/ohos5`

## 供应商侧（OHOS3）完整流程
1. `repo init ... && repo sync -c && repo forall -c 'git lfs pull'`
2. `cd /data/<user>/OHOS3/ohos5/common_patch && bash apply_patches_sdk.sh`
3. `./build.sh --product-name mp_hi3781v730 --patch`（**必须先执行 --patch**）
4. `./build.sh --product-name mp_hi3781v730 --cache`
5. `python3 transform_sdk.py --product mp_hi3781v730`（生成 partner SDK）

## 合作伙伴侧（OHOS2）完整流程
1. `repo init ... && repo sync -c && repo forall -c 'git lfs pull'`
2. 将 transform_sdk.py 生成的 tar.gz 和 apply_patches_sdk_partner.sh 放入 common_patch/
3. `cd /data/<user>/OHOS2/ohos5/common_patch && bash apply_patches_sdk_partner.sh`
4. `./build.sh --product-name mp_hi3781v730 --patch`（**必须先执行 --patch**）
5. `./build.sh --product-name mp_hi3781v730 --cache`

**Why:** `--patch` 步骤会应用 `vendor/hisilicon/common_patch/drivers/interface/interface-tvservice.patch`，
创建 `drivers/interface/tvservice/` 目录（IDL 接口定义）。跳过 `--patch` 会导致编译报错：
`find component drivers_interface_tvservice failed`。

**How to apply:** 每次从干净环境重新编译时，必须先运行 `--patch` 再运行正式编译，不可省略。
已有 out/ 缓存做增量编译可跳过 `--patch`。

## 供应商镜像参考编译（2026-04-02）

**任务**：串行编译 730 和 735，打包镜像到 `/data/<user>/OHOS3/images/`
- 脚本：`/data/<user>/OHOS3/run_vendor_build.sh`
- 730 镜像：`out/wudangstick/packages/phone/images/` → `images/730.tar.gz`
- 735 镜像：`out/shaolingun/packages/phone/images/` → `images/735.tar.gz`
- 流程：apply → build --patch --cache → build --cache → tar -czf

**apply 脚本优化**（详见 project_prebuilts_cache.md）：
- 哨兵文件 `.prebuilts_done`：同环境 prebuilts 只下载一次（730 完成后 735 跳过）
- symlink `/data/<user>/prebuilts_cache`：新环境只解压不下载（节省 ~1.5h）

## transform_sdk.py 迭代修复工作流（2026-04-02）

OHOS3（vendor 730）和 OHOS4（vendor 735）已有完整编译产物（out/ 目录齐全），
修改 transform_sdk.py 后**无需重新跑供应商编译**，直接对两个目录重跑 transform 即可：

```bash
# 730
python3 transform_sdk.py --product mp_hi3781v730 --ohos-root /data/<user>/OHOS3/ohos5

# 735  
python3 transform_sdk.py --product mp_hi3781v735 --ohos-root /data/<user>/OHOS4/ohos5
```

然后将生成的新 tar.gz 分发给 OHOS2/OHOS5 验证，大幅缩短迭代周期。

**Why:** 供应商编译耗时 2-3 小时，transform 本身只需几分钟，复用已有 out/ 是正确的迭代策略。

## 目录（2026-04-02 新规划）

| 目录 | 用途 | 产品 |
|------|------|------|
| `/data/OHOS2/ohos5` | 合作伙伴编译 | 730 |
| `/data/OHOS3/ohos5` | 供应商编译 | 730 |
| `/data/OHOS4/ohos5` | 供应商编译 | 735 |
| `/data/OHOS5/ohos5` | 合作伙伴编译 | 735 |

合作伙伴使用**同一份 tar.gz + 同一个 apply 脚本**编译 730 和 735。
旧路径 `/data/<user>/OHOS2` 和 `/data/<user>/OHOS3` 为历史环境，730 参考镜像保留在 `/data/<user>/OHOS3/images/`。
