---
name: 原始SDK包路径
description: 原始vendor SDK tar.gz的固定存放路径，只读，需要时从此处拷贝到编译工程
type: project
---

原始 SDK 包固定存放在 `BUILD_SERVER` 服务器上：

```
/home/<user>/sdk/R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz
```

**Why:** 该文件是供应商原始 SDK，不能被修改，只能拷贝使用。

**How to apply:** 每次 apply_patches_sdk.sh 运行前，如果 common_patch 下的 tar.gz 丢失，从此路径 cp 过来：
```bash
cp /home/<user>/sdk/R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz \
   /home/<user>/OHOS/ohos5/common_patch/
```
不要修改 `/home/<user>/sdk/` 下的文件。
