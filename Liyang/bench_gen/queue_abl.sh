#!/bin/sh
# dev 消融：索引+查询同一分词规则（GEN_PATCH_DEFAULT），其余为 v1 默认（当前工作树代码，默认值与 v1 相同）
cd "$(dirname "$0")"
[ -d /tmp/gen_jobs ] || python3 gen_eval.py prep
for a in nostem:'{"stem": false}' nostop:'{"stop": false}' none:'{"stem": false, "stop": false}'; do
  n=${a%%:*}; j=${a#*:}
  GEN_PATCH_DEFAULT="$j" python3 gen_eval.py run abl_$n loc_dev --np 1
  GEN_PATCH_DEFAULT="$j" python3 gen_eval.py run abl_$n lme_dev --np 1
done
echo ALLDONE
