---
name: 730/735多产品tar.gz合并可行性分析
description: 分析730和735 partner tar.gz能否合并为单一包，以及核心障碍
type: project
---

## 结论：不能直接合并，shared device/soc BUILD.gn 硬编码了 board 路径

**Why:** 730（board=<board_730>）和 735（board=<board_735>）共用 `device/soc/hisilicon/huanglong/vendor/huanglong/` 目录。transform 后该目录下 BUILD.gn 的 prebuilt source 路径写死为当前 board 名，两次 transform 互相覆盖。当前 OHOS3 中 150 处引用是 <board_735>，仅 2 处是 <board_730>。

**How to apply:** 若讨论合并方案，需先解决 shared BUILD.gn board 路径硬编码问题，不可简单叠加两个 tar.gz。

## 各部分差异对比

| 内容 | 730 tar.gz | 735 tar.gz | 可否共存 |
|------|-----------|-----------|---------|
| `./vendor/` | 相同 | 相同 | 可以 |
| `./ohos5/vendor/hisilicon/mp_hi3781v730/` | 有 | 无 | 可以（路径不同） |
| `./ohos5/vendor/hisilicon/mp_hi3781v735/` | 无 | 有 | 可以（路径不同） |
| `./ohos5/device/<board_735>/`（kernel/bootloader prebuilt） | 无 | 有 | 可以 |
| `./ohos5/device/soc/hisilicon/.../BUILD.gn` | 写死 <board_730> | 写死 <board_735> | **冲突，互相覆盖** |

## 要合并所需改动

需修改 `transform_sdk.py`，让 shared device/soc BUILD.gn 在打包时不写死 board 名，改为在 partner apply 时根据目标产品动态替换，或将 shared BUILD.gn 按 board 分叉存储。改动量较大。

## 短期推荐方案

保持两个 tar.gz，改名加产品后缀：
- `R200X_..._v730_...tar.gz`
- `R200X_..._v735_...tar.gz`
