#!/bin/bash
LOG=/data/<user>/OHOS5
ROOT=/data/<user>/OHOS5/ohos5
IMAGES=/data/<user>/OHOS5/images

echo "[OHOS5][735] apply 开始"
cd $ROOT/common_patch
bash apply_patches_sdk_partner.sh > $LOG/apply_partner_735.log 2>&1
echo "[OHOS5][735] apply 完成，exit=$?"

echo "[OHOS5][735] build --patch 开始"
cd $ROOT
./build.sh --product-name mp_hi3781v735 --cache --patch > $LOG/build_patch_partner_735.log 2>&1
echo "[OHOS5][735] build --patch 完成，exit=$?"

echo "[OHOS5][735] build --cache 开始"
./build.sh --product-name mp_hi3781v735 --cache > $LOG/build_cache_partner_735.log 2>&1
echo "[OHOS5][735] build --cache 完成，exit=$?"

echo "[OHOS5][735] 打包镜像"
tar -czf $IMAGES/735.tar.gz -C $ROOT/out/shaolingun/packages/phone/images .
echo "[OHOS5][735] 完成: $(ls -lh $IMAGES/735.tar.gz 2>/dev/null)"
