---
name: 不使用--skip-prebuilts参数
description: apply_patches_sdk.sh 不再使用 --skip-prebuilts，prebuilts_download.sh 必须正常执行
type: feedback
---

不要使用 `--skip-prebuilts` 参数，供应商和合作伙伴的 apply 脚本都必须完整执行 `prebuilts_download.sh`。

**Why:** `build/prebuilts_download.sh` 无法被跳过，--skip-prebuilts 方案行不通。

**How to apply:** 凡是涉及 apply_patches_sdk.sh 或 apply_patches_sdk_partner.sh 的命令，都不要加 `--skip-prebuilts`；如果脚本中已有该参数的相关逻辑也应移除。
