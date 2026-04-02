#!/bin/bash

set -e  # 遇到错误立即退出
#set -x
# 定义颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 基础变量
COMMON_PATCH_DIR=$(cd $(dirname "$0") && pwd)
OHOS_PATH=$COMMON_PATCH_DIR/../
PATCH_SDK_BASE_DIR=$COMMON_PATCH_DIR/sdk-base-patch/
PATCH_CUSTOM_OHOS_DIR=$COMMON_PATCH_DIR/custom-ohos-patch/
PATCH_CUSTOM_SDK_VENDOR_DIR=$COMMON_PATCH_DIR/custom-sdk-vendor-patch/
PATCH_OTHER_DIR=$COMMON_PATCH_DIR/other-patches/
[[ $1 = "sync" ]] && REPO_SYNC=true || REPO_SYNC=false

export PATCH_ROOT_PATH=
declare -a error_patch_name_arr
declare -a error_patch_directory_arr
declare -i error_patch_count=0

# 检查必要目录
check_directories() {
    if [ ! -d $OHOS_PATH ]; then
        log_error "源码目录不存在: $OHOS_PATH"
        exit 1
    fi
    if [ ! -d $PATCH_SDK_BASE_DIR ]; then
        log_error "sdk base patch目录不存在: $PATCH_SDK_BASE_DIR"
        exit 1
    fi
    if [ ! -d $PATCH_CUSTOM_OHOS_DIR ]; then
        log_error "custom ohos patch目录不存在: $PATCH_CUSTOM_OHOS_DIR"
        exit 1
    fi
    if [ ! -d $PATCH_CUSTOM_SDK_VENDOR_DIR ]; then
        log_error "custom sdk vendor patch目录不存在: $PATCH_CUSTOM_SDK_VENDOR_DIR"
        exit 1
    fi
    if [ ! -d $PATCH_OTHER_DIR ]; then
        log_error "other patch目录不存在: $PATCH_OTHER_DIR"
        exit 1
    fi
}

# 清理工作目录
clean_workspace() {
    log_info ""
    log_info "=== 开始清理工作目录... ==="

    rm -Rf "$OHOS_PATH/device"
    rm -Rf "$OHOS_PATH/vendor"
    rm -Rf "$OHOS_PATH/out"
    rm -Rf "$OHOS_PATH/../vendor"

    # 每次都重置源码仓库（确保补丁可干净应用）
    repo forall $(repo list | grep -v common_patch | cut -d':' -f1) -c "git reset -q .; git checkout -q .; git clean -q -dfx;"
    if [[ $REPO_SYNC = "true" ]]; then
        log_info "=== 开始更新repo仓库... ==="
        git -C .repo/manifests/ reset --hard
        git -C .repo/manifests/ pull
        sed -i "s/git\@gitee\.com\:/https\:\/\/gitee\.com\//g" .repo/manifests/default.xml
        repo sync -c -d
        log_info "=== 更新repo仓库完成! ==="
    fi
    repo forall -c "timeout 300 git lfs pull || true"  # with timeout
    # 补充 lfs pull 可能超时未恢复的 node_modules（每次 apply 都同步，确保完整）
    NM_SRC="/data/<user>/OHOS2/ohos5"
    NM_DST="$OHOS_PATH"
    for NM_PATH in         "developtools/ace_js2bundle/ace-loader/node_modules"         "developtools/ace_ets2bundle/compiler/node_modules"         "arkcompiler/ets_frontend/arkguard/node_modules"         "interface/sdk-js/build-tools/node_modules"         "third_party/jsframework/node_modules"         "third_party/parse5/packages/parse5/node_modules"         "third_party/weex-loader/node_modules"; do
        if [ -d "$NM_SRC/$NM_PATH" ]; then
            log_info "=== 同步 node_modules: $NM_PATH ==="
            mkdir -p "$NM_DST/$(dirname $NM_PATH)"
            rsync -a "$NM_SRC/$NM_PATH/" "$NM_DST/$NM_PATH/"
        fi
    done

    # prebuilts 仅下载一次：若已存在哨兵文件则跳过
    PREBUILTS_DONE_FLAG="$OHOS_PATH/prebuilts/.prebuilts_done"
    if [ -f "$PREBUILTS_DONE_FLAG" ]; then
        log_info "=== prebuilts 已存在，跳过下载 ==="
    else
        rm -Rf "$OHOS_PATH/prebuilts"
        # 确保 openharmony_prebuilts 指向共享缓存，避免重复下载
        CACHE_DIR="/data/<user>/prebuilts_cache"
        PREBUILTS_CACHE="$OHOS_PATH/../openharmony_prebuilts"
        if [ -d "$CACHE_DIR" ] && [ ! -L "$PREBUILTS_CACHE" ]; then
            rm -Rf "$PREBUILTS_CACHE"
            ln -s "$CACHE_DIR" "$PREBUILTS_CACHE"
            log_info "=== openharmony_prebuilts 已链接到共享缓存 ==="
        fi
        build/prebuilts_download.sh --pypi-url="http://mirrors.aliyun.com/pypi/simple/" --skip-ssl
        touch "$PREBUILTS_DONE_FLAG"
        log_info "=== prebuilts 下载完成，已记录哨兵文件 ==="
    fi

    log_info "=== 工作目录清理完成! ==="
}

# SDK升级
upgrade_sdk() {
    log_info ""
    log_info "=== 开始SDK升级... ==="

    # 检查SDK包是否存在
    local base_pkg="R200X_V730R001C10SPC003TB020_Software_Ohos5_Base-package.tar.gz"
    if [ ! -f $COMMON_PATCH_DIR/$base_pkg ]; then
        log_error "基础包不存在: $COMMON_PATCH_DIR/$base_pkg"
        exit 1
    fi

    # 解压SDK包
    log_info "解压R200X_V730R001C10SPC003TB020 Software Base package..."
    rm -Rf $COMMON_PATCH_DIR/tmp/
    mkdir $COMMON_PATCH_DIR/tmp/
    tar -zxf $COMMON_PATCH_DIR/$base_pkg -C $COMMON_PATCH_DIR/tmp/ "./vendor" "./ohos5/device"
    cp -Rf $COMMON_PATCH_DIR/tmp/vendor/ $OHOS_PATH/../
    cp -Rf $COMMON_PATCH_DIR/tmp/ohos5/device/ $OHOS_PATH/
    rm -Rf $COMMON_PATCH_DIR/tmp/

    # 应用sdk base patch
    apply_sdk_base_patches

    log_info "=== SDK升级完成! ==="
}

apply_sdk_base_patches() {
    log_info "=== 开始应用sdk base patch..."

    PATCH_ROOT_PATH=$PATCH_SDK_BASE_DIR
    ergodic_patch $PATCH_ROOT_PATH

    if [ $error_patch_count -eq 0 ]; then
        log_info "=== 应用sdk base patch成功! ==="
    else
        log_error "=== 应用sdk base patch失败!请手动检查以下patch! ==="
        for (( i = 0; i < $error_patch_count; i++ )); do
            echo ${error_patch_directory_arr[$i]}${error_patch_name_arr[$i]}
        done
        exit -1
    fi
}

apply_custom_ohos_patches() {
    log_info ""
    log_info "=== 开始应用custom ohos patch... ==="

    mkdir -p $OHOS_PATH/device/soc/hisilicon/common
    PATCH_ROOT_PATH=$PATCH_CUSTOM_OHOS_DIR
    ergodic_patch $PATCH_ROOT_PATH

    if [ $error_patch_count -eq 0 ]; then
        log_info "=== 应用custom ohos patch成功! ==="
    else
        log_error "=== 应用custom ohos patch失败!请手动检查以下patch! ==="
        for (( i = 0; i < $error_patch_count; i++ )); do
            echo ${error_patch_directory_arr[$i]}${error_patch_name_arr[$i]}
        done
        exit -1
    fi
}

apply_custom_sdk_vendor_patches() {
    log_info ""
    log_info "=== 开始应用custom sdk vendor patch... ==="

    cd $OHOS_PATH/../vendor/
    PATCH_ROOT_PATH=$PATCH_CUSTOM_SDK_VENDOR_DIR
    ergodic_patch $PATCH_ROOT_PATH
    cd $OHOS_PATH

    if [ $error_patch_count -eq 0 ]; then
        log_info "=== 应用custom sdk vendor patch成功! ==="
    else
        log_error "=== 应用custom sdk vendor patch失败!请手动检查以下patch! ==="
        for (( i = 0; i < $error_patch_count; i++ )); do
            echo ${error_patch_directory_arr[$i]}${error_patch_name_arr[$i]}
        done
        exit -1
    fi
}

apply_other_patches() {
    log_info ""
    log_info "=== 开始应用other patch... ==="

    log_info "=== load ohos vendor file... ==="
    mkdir -p $OHOS_PATH/vendor/hisilicon
    cp -Rf $PATCH_OTHER_DIR/vendor_hisilicon/common_patch $OHOS_PATH/vendor/hisilicon/
    cp -Rf $PATCH_OTHER_DIR/vendor_hisilicon/mp_hi3781v730 $OHOS_PATH/vendor/hisilicon/
    cp -Rf $PATCH_OTHER_DIR/vendor_hisilicon/mp_hi3781v735 $OHOS_PATH/vendor/hisilicon/

    log_info "=== load applications hap file... ==="
    cp -Rf $PATCH_OTHER_DIR/applications_standard_hap/* $OHOS_PATH/applications/standard/hap/
    log_info "=== 应用other patch成功! ==="
}

function ergodic_patch(){
    #log_info $PATCH_ROOT_PATH
    for file in $(ls $1); do
        if [ -d $1"/"$file ]; then
            #log_info $file
            ergodic_patch $1"/"$file
        else
            local path=$1"/"$file
            local name=$file
            # log_info $path
            local foloder=${path#${PATCH_ROOT_PATH}/}
            # log_info $foloder
            local foloder2=${foloder%${name}}
            # log_info $foloder2

            if [[ $name != *.patch ]]; then
                # log_info "文件: ${foloder2}${name} 不是patch文件! 跳过"
                # log_info ""
                continue
            fi

            log_info ""
            log_info "检查patch: ${foloder2}${name}"
            git apply --check --directory=${foloder2} ${path}
            if [ $? -eq 0 ]; then
                log_info "应用patch: ${foloder2}${name}"
                git apply --whitespace=nowarn --directory=${foloder2} ${path}
            else
                error_name_arr[error_count]=${name}
                error_directory_arr[error_count]=${foloder2}
                ((error_count++))
                log_error "补丁冲突！取消应用"
            fi
        fi
    done
}

# 主函数
main() {
    log_info "=== OHOS Patch自动化脚本 ==="
    cd $OHOS_PATH

    # 检查环境
    check_directories

    # 执行清理
    clean_workspace

    # 升级SDK
    upgrade_sdk

    # 应用custom patch
    apply_custom_ohos_patches
    apply_custom_sdk_vendor_patches

    # 应用other patch
    apply_other_patches

    log_info "=== 所有操作完成 ==="
}

# 执行主函数
main "$@"
