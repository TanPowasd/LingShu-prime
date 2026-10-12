# 计算缓存核对与计时（dev：loc_dev 3 段 383 题；v2 快照）。A 旧路径 / B 冷缓存 / C 热缓存（钉住时钟，逐名次核对）；
# D 旧路径 / E 热缓存（真实时钟）；F 热缓存 + route_corpus=-1（调路由只重算排序层）
cd /workspace/work/ls/wt-gen/bench_gen
R=/tmp/ng-gen-9ffe1e9
t() { s=$(date +%s.%N); "$@"; e=$(date +%s.%N); echo "TIME $4 $s $e"; }
export G1_FROZEN_CLOCK=1760000000
rm -rf /tmp/ls_cache/db_bench; rm -rf runs/cc_*
GEN_DB_CACHE=0 t python3 gen_eval.py run cc_A loc_dev --root $R --np 1
GEN_DB_CACHE=/tmp/ls_cache/db_bench t python3 gen_eval.py run cc_B loc_dev --root $R --np 1
GEN_DB_CACHE=/tmp/ls_cache/db_bench t python3 gen_eval.py run cc_C loc_dev --root $R --np 1
unset G1_FROZEN_CLOCK
GEN_DB_CACHE=0 t python3 gen_eval.py run cc_D loc_dev --root $R --np 1
GEN_DB_CACHE=/tmp/ls_cache/db_bench t python3 gen_eval.py run cc_E0 loc_dev --root $R --np 1
GEN_DB_CACHE=/tmp/ls_cache/db_bench t python3 gen_eval.py run cc_E loc_dev --root $R --np 1
GEN_DB_CACHE=/tmp/ls_cache/db_bench t python3 gen_eval.py run cc_F loc_dev --root $R --np 1 --cfg '{"route_corpus":-1}'
echo BENCHDONE
