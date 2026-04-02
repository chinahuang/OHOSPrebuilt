---
name: 编译前检查清单
description: 四目录(OHOS2~5)编译前必须逐项检查的清单，避免常见错误导致重试浪费时间
type: project
---

## 编译前检查清单（每次启动编译前执行）

### 1. 清理残留进程和锁文件

```bash
# 检查是否有上次遗留的编译/apply进程
ps aux | grep -E 'build\.sh|apply_patches|ninja|repo forall' | grep -v grep

# 清理所有 index.lock（被kill的git进程会留下）
find /data/<user>/OHOS2/ohos5 -name 'index.lock' -delete
find /data/<user>/OHOS5/ohos5 -name 'index.lock' -delete
# OHOS3/OHOS4 同理

# 确认清理完毕
find /data/<user> -name 'index.lock' 2>/dev/null | wc -l  # 应为0
```

**Why:** kill 进程后 git 会留下 index.lock，下次 repo forall 时报错退出。

---

### 2. 检查 node_modules symlink

**共享缓存位置：** `/data/<user>/node_modules_cache/`（309MB，独立于 OHOS 目录，删除 OHOS 不影响）

四个目录均已改为 symlink 指向共享缓存：
- `developtools/ace_ets2bundle/compiler/node_modules` → `node_modules_cache/ace_ets2bundle/node_modules`（283个包）
- `developtools/ace_js2bundle/ace-loader/node_modules` → `node_modules_cache/ace_js2bundle/node_modules`（346个包）

```bash
# 检查 symlink 是否完好
for DIR in OHOS2 OHOS3 OHOS4 OHOS5; do
  echo -n "$DIR ets2bundle: "; ls -la /data/<user>/$DIR/ohos5/developtools/ace_ets2bundle/compiler/node_modules 2>/dev/null | grep -o '\-> .*'
  echo -n "$DIR js2bundle:  "; ls -la /data/<user>/$DIR/ohos5/developtools/ace_js2bundle/ace-loader/node_modules 2>/dev/null | grep -o '\-> .*'
done
```

**重建 OHOS 目录后恢复 symlink：**
```bash
DIR=OHOS5  # 改为目标目录
ln -s /data/<user>/node_modules_cache/ace_ets2bundle/node_modules \
      /data/<user>/$DIR/ohos5/developtools/ace_ets2bundle/compiler/node_modules
ln -s /data/<user>/node_modules_cache/ace_js2bundle/node_modules \
      /data/<user>/$DIR/ohos5/developtools/ace_js2bundle/ace-loader/node_modules
```

---

### 3. 检查 prebuilts 哨兵文件和 build-tools

```bash
for DIR in OHOS2 OHOS3 OHOS4 OHOS5; do
  echo -n "$DIR prebuilts: "
  ls /data/<user>/$DIR/ohos5/prebuilts/build-tools 2>/dev/null && echo OK || echo "缺失！"
  ls /data/<user>/$DIR/ohos5/prebuilts/.prebuilts_done 2>/dev/null && echo "哨兵: OK" || echo "哨兵: 无"
done
```

**如果 build-tools 不存在：** 需要先跑 apply 脚本执行 prebuilts_download（约 15 分钟，共享缓存）

---

### 4. 确认 apply 脚本注释掉 git lfs pull

```bash
grep 'git lfs pull' /data/<user>/OHOS2/ohos5/common_patch/apply_patches_sdk_partner.sh
grep 'git lfs pull' /data/<user>/OHOS5/ohos5/common_patch/apply_patches_sdk_partner.sh
```

**期望：** 该行应被注释掉（`# repo forall -c "git lfs pull"`）
**Why:** 四个目录代码均来自 ohos5_2026_03_14.tar.gz，LFS 对象已在本地，拉取耗时 15-30 分钟属冗余。

---

### 5. 确认 tar.gz 和 apply 脚本就位（合作伙伴目录）

```bash
# OHOS2 (partner 730)
ls -lh /data/<user>/OHOS2/ohos5/common_patch/R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz
ls -lh /data/<user>/OHOS2/ohos5/common_patch/apply_patches_sdk_partner.sh

# OHOS5 (partner 735) - 同一份 tar.gz symlink
ls -lh /data/<user>/OHOS5/ohos5/common_patch/R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz
```

**期望：** tar.gz 约 1183MB，apply_patches_sdk_partner.sh 约 9KB

---

### 6. 确认没有启动多个实例

```bash
# 启动脚本前检查是否已有实例在运行
ps aux | grep 'run_partner\|run_vendor\|apply_patches_sdk' | grep -v grep
```

**Why:** 多实例并发会导致 git index.lock 冲突，两个实例都失败。

---

### 7. 磁盘空间检查

```bash
df -h /data
```

**期望：** /data 分区可用空间 > 200GB（每次完整编译约需 80-100GB out 目录）

---

## 共享缓存目录（独立于 OHOS 目录，删除 OHOS 不影响）

| 路径 | 内容 | 大小 |
|------|------|------|
| `/data/<user>/prebuilts_cache/` | 编译工具链（clang/gcc/node/rust等）| ~4GB |
| `/data/<user>/node_modules_cache/ace_ets2bundle/node_modules` | ace_ets2bundle 依赖 | 173MB |
| `/data/<user>/node_modules_cache/ace_js2bundle/node_modules` | ace_js2bundle 依赖 | 136MB |

新建 OHOS 目录后，需要建立两种 symlink：
1. `ohos5/../openharmony_prebuilts` → `/data/<user>/prebuilts_cache`（apply 脚本自动建立）
2. `developtools/ace_*/node_modules` → `/data/<user>/node_modules_cache/*/node_modules`（手动建立）

## 代码重置方法（需要干净重建时）

```bash
# 以 OHOS5 为例
rm -Rf /data/<user>/OHOS5/ohos5
cd /data/<user>/OHOS5
tar -xf /data/<user>/OHOS5/ohos5_2026_03_14.tar.gz
# 重置后需重新检查上述清单第2、3、4项
```

**tar.gz 基线位置：** `/data/<user>/OHOS5/ohos5_2026_03_14.tar.gz`（55G，2026-03-14）

---

## 编译顺序规则

1. apply 必须在 build --patch 之前运行
2. build --patch 必须在 build --cache 之前运行（--patch 会创建 drivers/interface/tvservice/ 等目录）
3. build --patch 失败后**不可直接重试**，必须重新跑 apply 清理状态
4. 两个产品切换之间必须重跑 apply（重置 workspace）
5. 不要同时启动两个使用同一 ohos5 目录的编译任务
