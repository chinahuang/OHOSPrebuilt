#!/bin/bash
LOG=/data/huanghao/OHOS4
ROOT=/data/huanghao/OHOS4/ohos5
IMAGES=/data/huanghao/OHOS4/images

echo "[OHOS4][735] apply 开始"
cd $ROOT/common_patch
bash apply_patches_sdk.sh > $LOG/apply_vendor_735.log 2>&1
echo "[OHOS4][735] apply 完成，exit=$?"

echo "[OHOS4][735] build --patch 开始"
cd $ROOT
./build.sh --product-name mp_hi3781v735 --cache --patch > $LOG/build_patch_vendor_735.log 2>&1
echo "[OHOS4][735] build --patch 完成，exit=$?"

echo "[OHOS4][735] build --cache 开始"
./build.sh --product-name mp_hi3781v735 --cache > $LOG/build_cache_vendor_735.log 2>&1
echo "[OHOS4][735] build --cache 完成，exit=$?"

echo "[OHOS4][735] 打包镜像"
tar -czf $IMAGES/735.tar.gz -C $ROOT/out/shaolingun/packages/phone/images .
echo "[OHOS4][735] 完成: $(ls -lh $IMAGES/735.tar.gz 2>/dev/null)"
