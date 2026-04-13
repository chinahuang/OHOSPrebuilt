---
name: mp_hi3781v730 完整组件分析
description: config.json 和 product.gni 中各子系统/组件的 build.gn 梳理结果
type: project
---

## 产品基本信息
- product_name: mp_hi3781v730
- board: <board_730> (device_build_path: device/board/hisilicon/<board_730>)
- device_company: hisilicon
- target_cpu: arm64
- type: standard
- SDK包: <SDK_PKG>.tar.gz

## 子系统一览

### 1. huanglong_products（芯片厂商自定义）
所有 component 在 out/sdk/build_configs/huanglong_products/ 下有 build_configs BUILD.gn

**device_soc_huanglong**（核心）
- bundle.json: device/soc/hisilicon/huanglong/bundle.json
- BUILD.gn: device/soc/hisilicon/huanglong/BUILD.gn
- 构建: kernel + bootloader + 40+个 libuapi_*.so + huanglong_binary + development_group
- sdk_dir = //device/soc/hisilicon/huanglong
- huanglong_uapi_dir = sdk_dir/vendor/huanglong/uapi

**sample_* 系列**（示例程序，安装到 vendor 分区）
- sample_frontend: sample/frontend/BUILD.gn → sample_frontend
- sample_demux: sample/demux/BUILD.gn → 8个可执行
- sample_cast: sample/vo/BUILD.gn → sample_cast
- sample_pwm: sample/pwm/BUILD.gn → sample_pwm, sample_moto_pwm
- sample_aihal: sample/intelligence/aihalsample/BUILD.gn → sample_aihal
- sample_lsadc: sample/lsadc/BUILD.gn → sample_lsadc
- sample_spi: sample/spi/BUILD.gn → read/write/loopback
- sample_gpio: sample/gpio/BUILD.gn → dir/read/write
- sample_i2c: sample/i2c/BUILD.gn → read/write
- sample_uart: sample/uart/BUILD.gn → sample_uart
- sample_ir: sample/ir/BUILD.gn → sample_ir
- sample_wdg: sample/wdg/BUILD.gn → sample_wdg
- sample_pmoc: sample/pmoc/BUILD.gn → sample_pmoc, sample_active_standby
- sample_xplay: sample/xplay/BUILD.gn → sample_esplay, sample_tsplay
- sample_audio_ao: sample/audio/ao/BUILD.gn → sample_audio_play, sample_mixengine
- sample_klad: sample/klad/BUILD.gn → 13个可执行
- sample_otp: sample/otp/BUILD.gn → 31个可执行
- sample_venc: sample/venc/BUILD.gn → sample_venc
- sample_vi: sample/vi/BUILD.gn → sample_vi
- sample_hdmirx: sample/hdmirx/BUILD.gn → sample_hdmirx
- sample_hdmi_tsplay: sample/hdmitx/BUILD.gn → sample_hdmi_tsplay

**平台层**
- histreamer_ext: common/binary/.../histreamer_ext/BUILD.gn → nx_format_ext（已预编译.so）
- drivers_interface_display_hwgraphics: ohos/interfaces/display/hwgraphics/v1_0/ → IDL proxy/stub
- drivers_graphics_display: ohos/hardware/graphics/display/source/ → display_overlay
- drivers_graphics_hwgraphics: ohos/hardware/graphics/hwgraphics/ → hwgraphics_entry
- libteec_vendor: vendor/platform/libteec_vendor/source/ → libteec_vendor.so + teecd + tlogcat
- libuapi_securec: vendor/platform/secure_c/source/ → libuapi_securec.so
- modules_ir_user: modules/ir_user/source/BUILD.gn → ohos_ir_user + ir配置文件
- pdmtool: vendor/tools/board/huanglong/pdm/BUILD.gn → pdmtool

### 2. hisilicon_common（SoC通用层）
- hdf_soc_hal: common/driverbase/hal/BUILD.gn → tvhal_soc(AmpHal/AudioHal/DisplayHal/PqHal/VideoHal) + tvhal_dtv_demux_soc + tvhal_dtv_frontend_soc（chipset分区）
- hdf_audio_hal: common/hardware/audio/source/BUILD.gn → audio_primary_impl_vendor.z.so
- histreamer_ext: common/binary/.../histreamer_ext/BUILD.gn（已预编译）
- production_construct: common/foundation/produce/BUILD.gn → produce_server（本产品feature全关闭）

### 3. security
- selinux_adapter: selinux_adapter_build_path → device/soc/hisilicon/huanglong/vendor/huanglong/ohos/sepolicy

### 4. hdf（驱动框架层）
- hdf_core: drivers/hdf_core/ → libhdi + hdf_devhost + hdf_devmgr + libhdf_platform等
- drivers_interface_tvservice: 通过patch注入 drivers/interface/tvservice/ → IDL(video/audio/hdmi/dtv_demux/dtv_frontend)
- drivers_peripheral_tvservice: 通过patch注入 drivers/peripheral/tvservice/ → 各service.so + driver.so（chipset分区）
- drivers_peripheral_display: drivers/peripheral/display/ → community=true(跳过vdi_default)
- drivers_interface_audio: drivers/interface/audio/ → IAudio v4_0 IDL（language=c）
- drivers_peripheral_audio: drivers/peripheral/audio/ → ALSA后端 + community=true
- drivers_peripheral_codec: drivers/peripheral/codec/ → OMX编解码驱动 + image service（support_hdi_v1=true）
- drivers_peripheral_input: drivers/peripheral/input/ → feature_model=true

### 5. multimedia
- audio_framework: foundation/multimedia/audio_framework/ → PulseAudio + OpenSLES + NAPI（dtmf_tone=true, opensl_es=true）
- tvservice: foundation/multimedia/tvservice/ → TVService SA + JS API，依赖 drivers_peripheral_tvservice

### 6. arkui
- ace_engine: feature enable_accessibility=true, enable_web=true
- ui_appearance: 标准

### 7. graphic
- graphic_2d: feature gpu=true, eglimage=true, bootanimation=true, picture_overlay=true
- graphic_surface/graphic_3d/vulkan-loader/vulkan-headers: 标准

### 8. product_mp_hi3781v730（产品级）
- product_mp_hi3781v730: vendor/hisilicon/mp_hi3781v730/ → hdf_audio_config + etc + partition + image_cfg + preinstall + power_config + hdf_config + window_config + bluetoothKeyMapping + rtkbt_wifi + vendor_config + ble_rcu
- hlgallery_service_part: vendor/hisilicon/mp_hi3781v730/hlgallery_service/BUILD.gn → hlgallery_service.so（IPC SA服务）+ NAPI + sa_profile + init

### 9. 其他标准子系统（含产品定制feature）
- usb/usb_manager: pop_up_func_switch_model=false
- communication: netmanager_ext + bluetooth_service（标准）
- thirdparty: libuv(ffrt=true) + wpa_supplicant(nl80211=true) + sqlite + toybox(debug_cmd=true)
- startup/init: 标准
- hiviewdfx/hiview: leak_detector=true, performance_monitor=true
- applications/prebuilt_hap: 标准
- castplus: cast_engine_dlna + cast_engine + sharing_framework
- resourceschedule/memmgr: hyperhold_memory=false

## product.gni 关键变量
- soc_name = "<board_730>"
- sdk_dir = "//device/soc/hisilicon/huanglong"
- common_dir = "//device/soc/hisilicon/common"
- huanglong_uapi_dir = "$sdk_dir/vendor/huanglong/uapi"
- huanglong_binary_uapi_dir = "$sdk_dir/vendor/huanglong/binary/uapi"
- sdk_include_dir = "$sdk_dir/vendor/huanglong/linux/include"
- boot_partition_file = "vendor/hisilicon/mp_hi3781v730/partition/blkdevparts.txt"
- public_sdk_config = "$sdk_dir:public_sdk_config"
