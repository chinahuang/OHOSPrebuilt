---
name: prebuilt改造验证进展
description: 从供应商角度重新编译打包、再从合作伙伴角度验证的完整操作进展与步骤
type: project
---

## 背景
旧环境（OLD_SERVER）patch 打乱，需要在新环境重头来过，完整走通供应商→合作伙伴全流程验证。

**Why:** 旧环境不干净，验证结果不可信，需要干净环境重新验证 transform_sdk.py 的正确性。
**How to apply:** 按下方步骤顺序执行，遇到问题记录在"已知问题"中。

---

## 环境信息

| 角色 | 地址 | 用户名 | 路径 |
|---|---|---|---|
| 旧环境（参考） | OLD_SERVER | - | //OLD_SERVER/ohos/OHOS2 |
| 新环境（供应商侧） | BUILD_SERVER | <user> | /home/<user>/OHOS |
| Windows（操作机） | 本机 | 1 | - |

SSH 连接方式：`ssh -o StrictHostKeyChecking=no <user>@BUILD_SERVER`（已配置公钥免密）

---

## 新环境（BUILD_SERVER）初始状态
- ohos5 源码目录：`/home/<user>/OHOS/ohos5/`（干净，无 device/vendor）
- common_patch 目录完整：`apply_patches_sdk.sh` / `custom-ohos-patch` / `custom-sdk-vendor-patch` / `other-patches` / `sdk-base-patch`
- SDK 包：`/home/<user>/OHOS/ohos5/common_patch/<SDK_PKG>.tar.gz` 已存在
- `transform_sdk.py` 已从旧环境拷贝到 `/home/<user>/OHOS/ohos5/transform_sdk.py` ✅
- 磁盘：2TB，已用 860G，剩余 1.1T
- 内存：125GB
- Python：3.11.14

---

## ✅ 第二轮验证已完成（2026-03-20）

**结论：OHOS2 与 OHOS3 images/vendor/system 完全一致（19/407/3096 文件）**

详见 prebuilt_work.md 获取完整修复日志和流程。

---

## 完整执行步骤

### 【供应商侧】在 BUILD_SERVER 执行

#### Step 1: 执行 apply_patches_sdk.sh（原版完整版）
```bash
cd /home/<user>/OHOS/ohos5/common_patch
bash apply_patches_sdk.sh
```
- 作用：解压 SDK tar.gz → 恢复 device/ vendor/ → 打所有 patch
- 状态：待执行

#### Step 2: 完整编译
```bash
cd /home/<user>/OHOS/ohos5
./build.sh --product-name mp_hi3781v730 --cache
```
- 状态：待执行

#### Step 3: 执行 transform_sdk.py
```bash
cd /home/<user>/OHOS/ohos5
python3 transform_sdk.py --product mp_hi3781v730
```
- 产出1：`/home/<user>/OHOS/<SDK_PKG>.tar.gz`（partner SDK）
- 产出2：`/home/<user>/OHOS/apply_patches_sdk_partner.sh`
- 状态：待执行

### 【合作伙伴侧】另起干净环境验证

#### Step 4: 准备合作伙伴环境
- 干净 ohos5 源码树（无 device/vendor）
- 将 Step 3 产出的 tar.gz 放入 common_patch 目录
- 将 Step 3 产出的 apply_patches_sdk_partner.sh 替换 apply_patches_sdk.sh

#### Step 5: 执行合作伙伴 patch 脚本
```bash
cd common_patch
bash apply_patches_sdk_partner.sh
```

#### Step 6: 编译验证
```bash
./build.sh --product-name mp_hi3781v730 --cache
```
- 预期：编译成功，产出完整镜像
- 状态：待执行

---

## 脚本位置

| 脚本 | 位置 |
|---|---|
| transform_sdk.py（主脚本） | /home/<user>/OHOS/ohos5/transform_sdk.py（新环境） |
| transform_sdk.py（参考） | //OLD_SERVER/ohos/OHOS2/ohos5/transform_sdk.py |
| apply_patches_sdk_partner.sh（参考） | //OLD_SERVER/ohos/OHOS2/apply_patches_sdk_partner.sh |
| restore_transform.sh（参考） | //OLD_SERVER/ohos/OHOS2/restore_transform.sh |

---

## 已知问题 / 注意事项
- restore_transform.sh 中路径硬编码为 /home/my/OHOS2（旧环境路径），新环境需调整
- apply_patches_sdk_partner.sh 中包含 mp_hi3781v735 的 cp 操作（为未来 735 产品预留，正常）
- 旧环境 patch 已乱，不可作为参考基线
