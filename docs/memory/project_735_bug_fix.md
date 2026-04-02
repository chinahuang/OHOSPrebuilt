---
name: 735 prebuilt缺失9个vendor库修复记录
description: 735合作伙伴侧vendor分区缺失9个库的根因、修复动作和持久化方案
type: project
---

## 问题：735 OHOS2 vendor 缺失 9 个库

**Why:** 730 的三个修复补丁（0012/0022/Fix3）没有带入 735 流程，导致 partner 侧这 9 个库不在依赖链上，build 时不安装到 vendor 分区。

| 缺失文件 | 根因 | 对应修复 |
|---------|------|---------|
| libdftevent.so | huanglong_uapi group 缺 dep | Fix 1 (0012) |
| libuapi_flash.so | 同上 | Fix 1 (0012) |
| libuapi_jpgd.so | 同上 | Fix 1 (0012) |
| libuapi_so.so | 同上 | Fix 1 (0012) |
| libuapi_stat.so | 同上 | Fix 1 (0012) |
| libuapi_subtitle.so | 同上 | Fix 1 (0012) |
| libvendor_camera_utils.so | 同上 | Fix 1 (0012) |
| libdisplay_utils_vendor.z.so | display_composer_model 缺 dep | Fix 2 (0022) |
| libbt_vendor.z.so | rtkbt_wifi group 在 transform 后失去 libbt_vendor_rtk 但未引用 bluetooth:libbt_vendor | Fix 3 |

---

## 修复动作（2026-03-25）

### 即时修复（已直接应用到 OHOS3 post-transform 工作区）

**Fix 1** — `device/soc/hisilicon/huanglong/BUILD.gn`
- 在 `group("huanglong_uapi")` 的 `$libuapi_amp` 之后添加 7 个 dep：
  `$libdftevent`, `$libuapi_flash`, `$libuapi_jpgd`, `$libuapi_so`, `$libuapi_stat`, `$libuapi_subtitle`, `$libvendor_camera_utils`

**Fix 2** — `device/soc/hisilicon/huanglong/vendor/huanglong/ohos/hardware/graphics/display/source/BUILD.gn`
- 在 `group("display_composer_model")` 的 deps 中添加 `":libdisplay_utils_vendor"`

**Fix 3** — `vendor/hisilicon/mp_hi3781v735/rtkbt_wifi/BUILD.gn`
- 在 `group("rtkbt_wifi")` 的 deps 中添加 `"//vendor/hisilicon/mp_hi3781v735/bluetooth:libbt_vendor"`

### 持久化方案

**Fix 1 patch（供未来 transform 自动应用）：**
- 文件：`common_patch/custom-ohos-patch/device/soc/hisilicon/0012-Fix-huanglong-uapi-extra-deps.patch`
- 作用：Phase 8 预应用，730/735 通用（groups 结构相同，source/post-transform 均有效）

**Fix 2 patch：**
- 文件：`common_patch/custom-ohos-patch/device/soc/hisilicon/0022-fix-display-composer-deps.patch`
- 作用：同上，730/735 通用

**Fix 3（transform_sdk.py Phase 5.10）：**
- 新增函数 `fix_rtkbt_wifi_libbt_vendor(ohos_root, product, dry_run)`
- 逻辑：transform 后自动检测 rtkbt_wifi/bluetooth 目录，若 bluetooth 有 libbt_vendor prebuilt 则向 rtkbt_wifi group 添加 dep
- 触发条件：bluetooth/BUILD.gn 包含 `ohos_prebuilt_shared_library("libbt_vendor")` 且 rtkbt_wifi group 尚未引用

### 不影响 730 的原因
- Fix 1/2 patch 作用在 source BUILD.gn，730 transform 时同样生效，结果与 730 已验证状态一致（等于补上之前手动修的步骤）
- Fix 3 Phase 5.10 检测 bluetooth:libbt_vendor 是否存在才执行，730 的 rtkbt_wifi 已有 libbt_vendor_rtk 源码编译路径，不受影响

---

## 验证状态（2026-03-25）

- ✅ OHOS3 3 个 BUILD.gn 已修改
- ✅ 新 tar.gz 已重新打包（1148.5 MB）
- ✅ 新 tar.gz 已拷贝到 OHOS2/ohos5/common_patch/
- ✅ OHOS2 apply + build --patch（11m41s）+ build --cache（6m16s）全部成功
- ✅ vendor 对比：只在OHOS3=0，只在OHOS2=0，不同=239（均为源码编译产物，正常）
- ✅ images 对比：无缺失，6 个 img 内容不同（包含源码编译内容，正常）

**Round2 验证通过，9 个缺失库全部修复。**
