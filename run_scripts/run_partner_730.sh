#!/bin/bash
LOG=/data/<user>/OHOS2
ROOT=/data/<user>/OHOS2/ohos5
IMAGES=/data/<user>/OHOS2/images

echo '[OHOS2][730] apply 开始'
cd $ROOT/common_patch
bash apply_patches_sdk_partner.sh > $LOG/apply_partner_730.log 2>&1
echo "[OHOS2][730] apply 完成，exit=$?"

echo '[OHOS2][730] build --patch 开始'
cd $ROOT
./build.sh --product-name mp_hi3781v730 --cache --patch > $LOG/build_patch_partner_730.log 2>&1
echo "[OHOS2][730] build --patch 完成，exit=$?"

echo '[OHOS2][730] build --cache 开始'
./build.sh --product-name mp_hi3781v730 --cache > $LOG/build_cache_partner_730.log 2>&1
echo "[OHOS2][730] build --cache 完成，exit=$?"

echo '[OHOS2][730] 打包镜像'
tar -czf $IMAGES/730_new.tar.gz -C $ROOT/out/wudangstick/packages/phone/images .
echo "[OHOS2][730] 完成: $(ls -lh $IMAGES/730_new.tar.gz 2>/dev/null)"
