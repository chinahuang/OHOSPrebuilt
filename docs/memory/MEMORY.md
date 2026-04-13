# Memory Index

## Feedback
- [feedback_skip_prebuilts.md](feedback_skip_prebuilts.md) — 不使用 --skip-prebuilts，prebuilts_download.sh 必须正常执行
- [feedback_lfs_pull_skip.md](feedback_lfs_pull_skip.md) — apply脚本中 git lfs pull 可注释掉；代码重置从 ohos5_2026_03_14.tar.gz 解压

## Checklist
- [project_prebuild_checklist.md](project_prebuild_checklist.md) — 编译前7项检查清单：index.lock/node_modules/prebuilts/lfs/tar.gz/多实例/磁盘

## Project
- [project_multiproduct_merge_analysis.md](project_multiproduct_merge_analysis.md) — 730/735 tar.gz合并可行性分析：shared device/soc BUILD.gn硬编码board路径是核心障碍
- [project_multiproduct_transform.md](project_multiproduct_transform.md) — 多产品合并tar.gz：transform_sdk.py 5项变更详情及730重建→合并打包完整流程（2026-03-25）
- [project_735_bug_fix.md](project_735_bug_fix.md) — 735 partner vendor缺失9个库的根因分析、3个Fix修复动作及持久化方案（2026-03-25）
- [project_sdk_source.md](project_sdk_source.md) — 原始SDK包固定路径：/home/<user>/sdk/R200X_...tar.gz，只读，只能拷贝使用
- [project_build_workflow.md](project_build_workflow.md) — Build workflow：四套目录(OHOS2~5)分工、完整编译流程、apply脚本优化说明
- [project_component_analysis.md](project_component_analysis.md) — 完整组件分析：各子系统/component 的 bundle.json 和 build.gn 路径及构建目标
- [project_prebuilt_refactor.md](project_prebuilt_refactor.md) — 预编译分发改造需求：将 device/vendor 源码编译替换为 ohos_prebuilt_* 模式，供合作伙伴无源码编译产品
- [project_validation_progress.md](project_validation_progress.md) — 当前验证进展：新环境重头执行供应商→合作伙伴全流程，当前在Step1(apply_patches_sdk.sh)
- [project_prebuilts_cache.md](project_prebuilts_cache.md) — prebuilts共享缓存(<build_root>/prebuilts_cache)：哨兵文件+symlink机制，避免每次apply重新下载4GB工具包
- [project_boot_failure.md](project_boot_failure.md) — 合作伙伴镜像启动失败：dtbo/boot/sbl等被重新编译覆盖预编译产物，transform_sdk.py Phase7 board硬编码bug，已修复（v2）
- [prebuilt_work.md](prebuilt_work.md) — 操作日志（2026-04-03 v2完成）：源码过滤+启动修复验证通过，tar.gz 943MB，关键镜像730/735全部与供应商一致；下阶段：烧录验证+剩余21个测试源码清理+TEE prebuilt改造
- [prebuilt_plan.md](prebuilt_plan.md) — 完整方案归档：完整方案概述(9 Phase)、供应商编译流程、合作伙伴编译流程细节、v5残留64个源码文件分析及不可删原因
