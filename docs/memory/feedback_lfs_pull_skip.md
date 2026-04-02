---
name: git lfs pull 可跳过
description: apply脚本中的 repo forall -c "git lfs pull" 可注释掉，四目录代码均来自同一 tar.gz
type: feedback
---

apply_patches_sdk.sh 和 apply_patches_sdk_partner.sh 中的 `repo forall -c "git lfs pull"` 可以注释掉。

**Why:** 四个目录（OHOS2~OHOS5）的源码都是从 `/data/huanghao/OHOS5/ohos5_2026_03_14.tar.gz` 解压的，LFS 对象已完整存在于本地，无需重新拉取。该步骤每次耗时 15-30 分钟，属于冗余操作。

**How to apply:** 每次修改 apply 脚本时，找到 `repo forall -c "git lfs pull"` 这行注释掉。通常在 `clean_workspace()` 函数内，行号约 72。

---

## 代码重置方法

如果需要将某个目录的 ohos5 源码完全重置为干净状态：

```bash
# 以 OHOS2 为例
rm -Rf /data/huanghao/OHOS2/ohos5
cd /data/huanghao/OHOS2
tar -xf /data/huanghao/OHOS5/ohos5_2026_03_14.tar.gz
```

**tar.gz 位置**：`/data/huanghao/OHOS5/ohos5_2026_03_14.tar.gz`（55G，2026-03-14 基线）

该 tar.gz 包含干净的 ohos5 源码树（无 device/vendor/out），是所有四个目录的共同基线。
