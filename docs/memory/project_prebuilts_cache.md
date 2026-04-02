---
name: prebuilts 共享缓存与 apply 脚本优化
description: openharmony_prebuilts 共享缓存目录、symlink 机制、哨兵文件跳过逻辑，避免每次 apply 重新下载 4GB prebuilts
type: project
---

## 问题背景
`apply_patches_sdk.sh` 的 `clean_workspace()` 每次都会：
1. `rm -Rf prebuilts/` — 删除已安装的 prebuilts
2. `build/prebuilts_download.sh` — 重新从网络下载 ~4GB 工具包（约 1.5 小时）

下载包的缓存目录是 `$OHOS_PATH/../openharmony_prebuilts/`（即 `ohos5/` 同级），并非 `prebuilts/`，
不会被清理。`prebuilts_download.py` 按文件名（含 MD5）判断是否已下载，存在即跳过。

## 共享缓存目录
- 路径：`/data/huanghao/prebuilts_cache/`
- 内容：28 个 tar.gz/zip，共 ~4GB（2026-04-02 从 OHOS2 复制）
- 包含：clang, gcc, node, rust, ark_js, cmake, ninja 等全套构建工具

## apply_patches_sdk.sh 修改（OHOS3，2026-04-02）
路径：`/data/huanghao/OHOS3/ohos5/common_patch/apply_patches_sdk.sh`

`clean_workspace()` 中新增两项优化：

### 1. 哨兵文件：同一环境 prebuilts 只下载一次
```bash
PREBUILTS_DONE_FLAG="$OHOS_PATH/prebuilts/.prebuilts_done"
if [ -f "$PREBUILTS_DONE_FLAG" ]; then
    log_info "=== prebuilts 已存在，跳过下载 ==="
else
    rm -Rf "$OHOS_PATH/prebuilts"
    # ... 下载逻辑 ...
    touch "$PREBUILTS_DONE_FLAG"
fi
```
730 apply 完成后写入哨兵，735 apply 直接跳过整个下载+解压流程。

### 2. symlink：openharmony_prebuilts 指向共享缓存
```bash
CACHE_DIR="/data/huanghao/prebuilts_cache"
PREBUILTS_CACHE="$OHOS_PATH/../openharmony_prebuilts"
if [ -d "$CACHE_DIR" ] && [ ! -L "$PREBUILTS_CACHE" ]; then
    rm -Rf "$PREBUILTS_CACHE"
    ln -s "$CACHE_DIR" "$PREBUILTS_CACHE"
fi
```
新环境首次 apply 时，自动把 openharmony_prebuilts 链接到共享缓存，
prebuilts_download.py 发现所有包已存在，只执行解压（约 10-15 分钟），跳过下载。

## 收尾脚本
`/data/huanghao/setup_prebuilts_cache.sh`：
当前 730 apply 结束后执行，把 OHOS3 的 openharmony_prebuilts 也替换为 symlink：
```bash
rsync -a /data/huanghao/OHOS3/openharmony_prebuilts/ /data/huanghao/prebuilts_cache/
rm -Rf /data/huanghao/OHOS3/openharmony_prebuilts
ln -s /data/huanghao/prebuilts_cache /data/huanghao/OHOS3/openharmony_prebuilts
rm -Rf /data/huanghao/OHOS2/openharmony_prebuilts
ln -s /data/huanghao/prebuilts_cache /data/huanghao/OHOS2/openharmony_prebuilts
```

## 效果
| 场景 | 优化前 | 优化后 |
|------|--------|--------|
| 同环境第 2 次 apply（如 730→735） | ~1.5h 下载+解压 | 跳过（哨兵文件） |
| 新环境首次 apply | ~1.5h 下载+解压 | ~15min 仅解压（共享缓存） |

**How to apply:** 新建 OHOS 工作目录时，确保 `/data/huanghao/prebuilts_cache/` 存在，
apply 脚本会自动建立 symlink。若缓存目录不存在则退化为完整下载流程，无副作用。
