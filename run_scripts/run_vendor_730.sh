#!/bin/bash
LOG=/data/huanghao/OHOS3
ROOT=/data/huanghao/OHOS3/ohos5
IMAGES=/data/huanghao/OHOS3/images

mkdir -p $IMAGES

echo "[730] apply"
cd $ROOT/common_patch
bash apply_patches_sdk.sh > $LOG/apply_vendor_730.log 2>&1
echo "[730] apply done"

echo "[730] build --patch"
cd $ROOT
./build.sh --product-name mp_hi3781v730 --cache --patch > $LOG/build_patch_vendor_730.log 2>&1
echo "[730] build --patch done"

echo "[730] build --cache"
./build.sh --product-name mp_hi3781v730 --cache > $LOG/build_cache_vendor_730.log 2>&1
echo "[730] build --cache done"

echo "[730] 打包镜像"
tar -czf $IMAGES/730.tar.gz -C $ROOT/out/wudangstick/packages/phone/images .
echo "[730] 打包完成: $(ls -lh $IMAGES/730.tar.gz)"

echo "[735] apply"
cd $ROOT/common_patch
bash apply_patches_sdk.sh > $LOG/apply_vendor_735.log 2>&1
echo "[735] apply done"

echo "[735] build --patch"
cd $ROOT
./build.sh --product-name mp_hi3781v735 --cache --patch > $LOG/build_patch_vendor_735.log 2>&1
echo "[735] build --patch done"

echo "[735] build --cache"
./build.sh --product-name mp_hi3781v735 --cache > $LOG/build_cache_vendor_735.log 2>&1
echo "[735] build --cache done"

echo "[735] 打包镜像"
tar -czf $IMAGES/735.tar.gz -C $ROOT/out/shaolingun/packages/phone/images .
echo "[735] 打包完成: $(ls -lh $IMAGES/735.tar.gz)"

echo "ALL DONE"
