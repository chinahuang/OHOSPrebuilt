---
name: mp_hi3781v730 prebuilt refactor plan
description: 将 device/vendor 下源码编译改为预编译分发模式，供合作伙伴无源码编译产品，支持多产品/持续迭代
type: project
---

## 背景
合作伙伴不能获得 device/ 和 vendor/ 下的 C/C++ 源码，但可以保留：
- `.h` 头文件
- 完整编译产出的预编译二进制（.so、可执行文件）

**Why:** SoC 厂商源码开源合规问题。
**How to apply:** 将涉及源码编译的 BUILD.gn 替换为 ohos_prebuilt_* 模式。

---

## 完整流程

### 开发商侧（每次 SDK 版本更新或 patch 迭代后执行）
```
1. repo init/sync/lfs pull
2. apply_patches_sdk.sh（清理 + 解压 tar.gz + 开源仓 patch）
3. ./build.sh --product-name <product> --cache --patch
4. ./build.sh --product-name <product> --cache
5. python transform_sdk.py --product <product> [--ohos-root /path/to/ohos5]
   → 生成合作伙伴 tar.gz
```

### 合作伙伴侧（拿到新 tar.gz 后）
```
1. repo init/sync/lfs pull
2. apply_patches_sdk.sh（改造后版本）
3. ./build.sh --product-name <product> --cache --patch
4. ./build.sh --product-name <product> --cache
```

---

## 自动化脚本架构（transform_sdk.py）

### 设计原则
- **扫描驱动，非清单驱动**：自动扫描所有 BUILD.gn，无需维护静态列表
- **产品参数化**：--product 参数驱动，配置从 config.json/product.gni 读取
- **全流程幂等**：重复执行结果相同，支持迭代更新
- **产物存在性决定是否改造**：产物不存在 = feature 未开启 = 自动跳过

### 阶段一：读取产品配置（动态，无硬编码）
```python
# 从 vendor/hisilicon/<product>/config.json 读取
board    = product_config['board_name']    # 730→'<board_730>'
out_dir  = f'out/{board}'
# 扫描根目录
device_scan_roots = [
    'device/soc/hisilicon/huanglong/vendor/huanglong',  # symlink→outer vendor
    'device/soc/hisilicon/common',
]
vendor_scan_root = f'vendor/hisilicon/{product}'
```

### 阶段二：扫描发现所有编译目标
```python
COMPILE_TYPES = {'ohos_shared_library', 'ohos_executable', 'ohos_static_library'}
SKIP_TYPES    = {'ohos_prebuilt_*', 'group', 'config', 'ohos_prebuilt_etc', ...}
# 自动发现：target_type, target_name, part_name, subsystem_name, output_extension
```

### 阶段三：定位产物
```
out/<board>/<subsystem>/<part>/<filename>
产物不存在 → feature 未开启 → 自动跳过（无需白名单）
```

### 阶段四：拷贝到预编译存放路径
```
device/ 下  → device/<board>/<subsystem>/<part>/<file>
vendor/     → vendor/hisilicon/<product>/<board>/<subsystem>/<part>/<file>
```

### 阶段五：改写 BUILD.gn
```
ohos_shared_library/executable/static_library → ohos_prebuilt_*
删除：sources/cflags/include_dirs/external_deps/deps/defines/私有configs
保留：install_images/part_name/subsystem_name/output_extension/output_name/public_configs
保留：config("xxx"){} 块完整保留（供外部引用 include/defines）
新增：source = "//device/<board>/..." 或 "//vendor/hisilicon/<product>/<board>/..."
```

### 阶段六：源文件清理
```python
SOURCE_EXTS  = {'.c', '.cpp', '.cc', '.S', '.s', '.cxx'}
KEEP_WHITELIST = {
    'device/board/hisilicon/<board_730>/audio_alsa/vendor_capture.c',
    'device/board/hisilicon/<board_730>/audio_alsa/vendor_render.c',
}
```

### 阶段七：Kernel & Bootloader（参数化）
```python
# chip_revision 从产品配置读取（730→'d'）
# 拷贝 boot_d.img/dtbo_d.img → device/<board>/kernel/
# 拷贝 ko 模块 → device/<board>/kernel/modules/
# 拷贝 fastboot/slaveboot/sbl.bin → device/<board>/bootloader/
# programmer_d.bin 不存在则跳过
# 改写 build_kernel.sh：去掉 make，改为 cp from device/<board>/kernel/
# 改写 build_bootloader.sh：同上
```

### 阶段八：预应用 device custom patches 并从合作伙伴目录移除
```python
# custom-ohos-patch/device/ 下的所有 patch 在打包前预应用
# 防止每次迭代都要手动改 apply_patches_sdk.sh
def pre_apply_device_patches(custom_ohos_patch_dir):
    for patch in glob(f'{custom_ohos_patch_dir}/device/**/*.patch'):
        apply_if_not_already_applied(patch, ohos_root)
        # 在合作伙伴版本的 patch 目录中移除此 patch
```

### 阶段九：打包 tar.gz
```
结构：./vendor/（outer vendor，prebuilt）+ ./ohos5/device/（prebuilt）
```

---

## 产物文件名规则（已验证）

| 情况 | 文件名 |
|---|---|
| `ohos_shared_library("libfoo")` 默认 | `libfoo.z.so` |
| `ohos_shared_library("foo")` 无 lib 前缀 | `libfoo.z.so`（自动补 lib）|
| `output_extension = "so"` | `libfoo.so`（不带 .z）|
| `ohos_executable("foo")` | `foo`（无前缀后缀）|

---

## apply_patches_sdk.sh 改造（已分析）

### 关键发现
`device/soc/hisilicon/huanglong/vendor` 是符号链接：
- `huanglong → ../../../../../../vendor/huanglong`
- 即 outer vendor = device/ 硬件 SDK 源码，同一份内容

### 改造内容
| 函数 | 改造前 | 改造后 |
|---|---|---|
| `apply_sdk_base_patches()` | 打 base/build/drivers/foundation/kernel/third_party | ✅ 不变（全是开源仓）|
| `apply_custom_ohos_patches()` | 含 device/soc/hisilicon/ 多个 patch | 移除 device/ 子目录（已预应用进 tar.gz）|
| `apply_custom_sdk_vendor_patches()` | 打 outer vendor 源码 patch | ❌ 整体删除（已烘焙进预编译）|
| `apply_other_patches()` | 拷贝 vendor/hisilicon/common_patch 等 | ✅ 不变（开源仓 patch.yml）|
| `check_directories()` | 检查 4 个 patch 目录 | 去掉 custom-sdk-vendor-patch 检查 |

---

## 多产品 & 迭代可持续性

| 变化场景 | 是否需要修改脚本 | 处理机制 |
|---|---|---|
| SDK 新版本 tar.gz | ❌ | 重跑全流程 |
| 新增 BUILD.gn 目标 | ❌ | 扫描驱动自动发现 |
| 删除 BUILD.gn 目标 | ❌ | 产物不存在自动跳过 |
| 新增 common_patch | ❌ | 重跑 build + transform |
| 新增 device custom patch | ❌ | transform_sdk.py 自动预应用 |
| 新增产品（mp_hi3781v735）| ❌ | `--product mp_hi3781v735` 参数 |
| 产品 feature 开关变化 | ❌ | 产物存在性自动决定 |

---

## 已验证的产物清单（mp_hi3781v730，out/<board_730>/）

### huanglong_products 子系统
- libuapi_*.so × 43（全部在 device_soc_huanglong/）
- libOMX.uapi.video.decoder/encoder.so（output_extension=so）
- libOMX_Core.z.so
- libslog.so + libalog.so（同一 BUILD.gn，output_extension=so）
- libdftevent.so、libhal.so（output_extension=so）
- libdrv_aicpu/dfx/wrapper/devdrv.so（npu，output_extension=so）
- libvendor_camera.so + libvendor_camera_utils.so（output_extension=so）
- libdisplay_buffer_vdi_impl/buffer_vendor/composer_vdi_impl/composer_vendor/gfx/overlay/utils_vendor/vgu.z.so（display/source/ 8个）
- libdisplay_hwgraphics_driver_1.0.z.so + libhw_graphics_interface_service_1.0.z.so（hwgraphics/hdi_service/）
- libdisplay_hwgraphics_proxy/stub_1.0.z.so（IDL，interfaces/display/hwgraphics/v1_0/）
- libteec_vendor.so + teecd + tlogcat（libteec_vendor/source/）
- libuapi_securec.so（secure_c/source/）
- pdmtool、ohos_ir_user
- sample_* 系列 ~60 个可执行

### hisilicon_common 子系统
- libtvhal_soc.z.so + libtvhal_dtv_demux_soc.z.so + libtvhal_dtv_frontend_soc.z.so（chipset 分区）
- sample_audio_render（测试程序，hdf_audio_hal/）
- 【注意】libaudio_primary_impl_vendor.z.so 来自开源 drivers/peripheral/audio/，不在改造范围

### product_mp_hi3781v730 子系统
- libhlgallery_service.z.so + libhlgallery.z.so（hlgallery_service/）
- libbt_vendor.z.so（rtkbt_wifi/，target:libbt_vendor_rtk，output_name=libbt_vendor）

### Kernel & Bootloader（已验证存在）
- boot_d.img、dtbo_d.img（out/<board_730>/packages/phone/images/）
- eth_gmac.ko、rtk_btusb.ko、rtl8822cu.ko（out/<board_730>/obj/KERNEL_OBJ_D/...）
- fastboot_d.bin、slaveboot_d.bin、sbl_d.bin（packages/phone/images/）
- programmer_d.bin：本产品不存在，跳过

### 不在改造范围（已确认）
- drivers/interface/tvservice、drivers/peripheral/tvservice（patch 注入开源仓）
- drivers/peripheral/audio/（libaudio_primary_impl_vendor.z.so 来源）
- common/binary/.../histreamer_ext/（已是 ohos_prebuilt_etc）
- common/foundation/produce/（feature 全关闭，未编译）
- ble_rcu/libseneasy_rcu_decoder（已是 ohos_prebuilt_etc）
- uapi/omx/omx_audio/*、omx_vdec/secure、omx_jpeg、tvoshal/aihal（feature 未开启）
