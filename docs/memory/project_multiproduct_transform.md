---
name: 多产品合并tar.gz改造：transform_sdk.py 5项变更
description: 实现单一tar.gz同时支持730和735合作伙伴编译的代码改动及后续构建流程
type: project
---

## 核心方案

用 GNI 变量 `prebuilt_board_dir` 替换 shared device BUILD.gn 中硬编码的 board 名，使同一 BUILD.gn 可被 730（wudangstick）和 735（shaolingun）同时使用。

**Why:** 合作伙伴希望一个 tar.gz 即可编译 730 和 735，原先每产品需单独 tar.gz。

**How to apply:** 生成合并 tar.gz 时必须按"重建流程"执行；partner 收到 tar.gz 后用同一 apply_patches_sdk_partner.sh，只需 `hb set` 切换产品即可。

---

## transform_sdk.py 5项变更（已于2026-03-25应用到 OHOS3/ohos5/transform_sdk.py）

| # | 函数 | 变更内容 |
|---|------|---------|
| 1 | `get_prebuilt_dest` | device src_ref 从 `//device/{board}/...` 改为 `//device/${prebuilt_board_dir}/...`（f-string 写法：`${{prebuilt_board_dir}}`） |
| 2 | 新增 `inject_prebuilt_board_dir(ohos_root, product, board, dry_run)` | 向 `vendor/hisilicon/<product>/product.gni` 末尾追加 `prebuilt_board_dir = "<board>"`，已有则跳过 |
| 3 | `pack_tarball` | 新增 `extra_products=None` 参数，循环将 `vendor/hisilicon/<ep>/` 也打入 tar.gz |
| 4 | `generate_partner_apply_patches_sh` | 新增 `extra_products=None` 参数；tar 命令添加额外产品路径；追加额外产品的 cp 命令；step 7b 跳过额外产品在 apply_other_patches 中的 cp |
| 5 | `main` | 新增 `--extra-products` CLI 参数；在 Phase 2 前调用 inject_prebuilt_board_dir（主产品+额外产品）；pack_tarball 和 generate_partner_apply_patches_sh 均传入 extra_products |

---

## 生成合并 tar.gz 的操作流程

**前提：** OHOS3 当前只有 735 build（out/shaolingun/）和 735 transform 结果；out/wudangstick/ 已被清理。

### Step 1：重建 730（already started 2026-03-25）
```bash
# apply 已在后台启动，日志：/home/wuhan/OHOS3/apply_730_for_combined.log
# apply 完成后：
cd /home/wuhan/OHOS3/ohos5
./build.sh --product-name mp_hi3781v730 --patch   # 日志：build_patch_730_combined.log
./build.sh --product-name mp_hi3781v730 --cache   # 日志：build_cache_730_combined.log
```

### Step 2：730 transform（只做 Phase 4+5，不打包）
```bash
python3 transform_sdk.py --product mp_hi3781v730 --skip-pack
# 产出：device/wudangstick/ (730预编译库) + vendor/hisilicon/mp_hi3781v730/ (预编译BUILD.gn)
```

### Step 3：从现有 735 tar.gz 补充 device/shaolingun 和 vendor/mp_hi3781v735
```bash
cd /home/wuhan/OHOS3
tar -zxf R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz \
    "./ohos5/device/shaolingun" \
    "./ohos5/vendor/hisilicon/mp_hi3781v735"
```

### Step 4：生成合并 tar.gz + partner 脚本
```bash
cd /home/wuhan/OHOS3/ohos5
python3 transform_sdk.py --product mp_hi3781v730 --extra-products mp_hi3781v735 \
    --skip-source-delete --skip-kernel --skip-patches
# 产出：/home/wuhan/OHOS3/R200X_...tar.gz（含730+735）
# 产出：common_patch/apply_patches_sdk_partner.sh（多产品版本）
```

### Step 5：OHOS2 验证
```bash
# 在 OHOS2 执行 apply + build 730 + build 735，对比产物
bash apply_patches_sdk_partner.sh
./build.sh --product-name mp_hi3781v730 --patch && ./build.sh --product-name mp_hi3781v730 --cache
./build.sh --product-name mp_hi3781v735 --patch && ./build.sh --product-name mp_hi3781v735 --cache
```

---

## 技术细节

- `product.gni` 通过 `import("//vendor/${product_company}/${product_name}/product.gni")` 被 shared device BUILD.gn 引入，因此 `prebuilt_board_dir` 变量在共享 SoC BUILD.gn 中可用
- partner 脚本提取 tar.gz 时会一次性展开两个产品的 vendor 目录，`hb set` 选择产品后即可对应编译
- 合并 tar.gz 的 device/ 目录同时包含 device/wudangstick/ 和 device/shaolingun/ 两套预编译库

---

## 验证状态（2026-03-25）

- ✅ transform_sdk.py 5项变更已写入文件（64026 bytes）
- ✅ `python3 transform_sdk.py --help` 已显示 `--extra-products` 参数
- 🔄 apply_patches_sdk.sh 730重建中（/home/wuhan/OHOS3/apply_730_for_combined.log）
- ⏳ 待完成：730 build → transform → 补充735内容 → 合并打包 → OHOS2验证
