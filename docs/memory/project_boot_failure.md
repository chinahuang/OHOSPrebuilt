---
name: 合作伙伴镜像启动失败问题分析
description: partner build 的 bootloader/kernel 文件被重新编译，与供应商产物不一致，导致单板启动失败
type: project
---

## 问题现象（2026-04-02 发现）
合作伙伴编译的镜像（OHOS2/images/730.tar.gz，4月1日构建）烧录到单板后启动失败。

## 对比分析结论

| 文件 | tar.gz预编译 | OHOS2 partner构建产出 | OHOS3 vendor构建产出 |
|------|------------|---------------------|-------------------|
| sbl_d.bin | 1,261,056 | **1,273,344 ❌** | 1,261,056 ✓ |
| slaveboot_d.bin | 1,361,616 | **1,404,496 ❌** | 1,361,624 ≈✓ |
| programmer_d.bin | 1,514,440 | **1,526,728 ❌** | 1,514,440 ✓ |
| boot_d.img | 36,917,760 | **37,255,680 ❌** | 36,917,760 ✓ |
| dtbo_d.img | 884,624 | **742,384 ❌** | 884,624 ✓ |
| system.img | 2,147,483,648 | ✓ 相同 | ✓ 相同 |
| vendor.img | 314,572,800 | ✓ 相同 | ✓ 相同 |

**system.img 和 vendor.img 完全一致，transform_sdk.py 的主体功能正常。**

## 根本原因
- partner tar.gz 中已包含正确的预编译文件（大小与 vendor 一致）：
  - `ohos5/device/wudangstick/bootloader/sbl_d.bin` 等
  - `ohos5/device/wudangstick/kernel/dtbo_d.img`（884624 bytes）
- apply 脚本正确提取到 `device/wudangstick/` 目录
- 但 build 过程**重新从源码编译**了这些文件并覆盖了预编译产物
- transform_sdk.py **未覆盖** bootloader/kernel 的构建目标转换

## 机制说明
- 供应商：bootloader/kernel 由 sh 脚本编译，产出放入 `device/wudangstick/bootloader/` 和 `device/wudangstick/kernel/`
- 合作伙伴设计意图：编译动作替换为拷贝（copy 预编译），实际不执行编译
- 当前问题：拷贝机制未生效，build 仍然触发了源码编译

## 待查方向
1. 找到 dtbo/bootloader 的 BUILD.gn 或 Makefile 构建规则
2. 确认 partner 环境下为何没有走 copy 分支而是走了源码编译分支
3. 补充 transform_sdk.py 对 bootloader/kernel 目标的转换逻辑

**Why:** 一份 tar.gz + 一个 apply 脚本同时支持 730 和 735，bootloader/kernel 必须使用预编译，不能重编。
**How to apply:** 下次调试时，在 partner build 过程中追踪 dtbo_d.img 何时被覆盖（strace 或 inotifywait）。
