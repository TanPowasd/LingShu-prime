#!/bin/bash
# r7 第 1 次迭代合格读数：同一 sweep 在 loc_dev、LME dev 两口径（语义第二路开）
# 11:01 起：向量缓存放 /tmp（JuiceFS 上的 sqlite WAL 提交使 juicefs 占 40% CPU）；loc_dev 已完成
cd /workspace/work/ls/wt-gen/bench_gen
export G1_FROZEN_CLOCK=1
export GEN_EMBED_CACHE=/tmp/ls_cache/vec
P=/workspace/work/ls/_shared/models/_vec_cache
mkdir -p /tmp/ls_cache/vec; [ -s /tmp/ls_cache/vec/vec.db ] || cp $P/vec.db /tmp/ls_cache/vec/
[ -s /tmp/gen_jobs/lmes_dev.jsonl ] || { python3 v3/r7/mk_lp.py >/dev/null; python3 gen_eval.py prep; python3 -c "import sys;sys.path.insert(0,'v3');import mk_cm_r5 as M;print(M.lme_spk())"; }
( while sleep 600; do python3 -c "import sqlite3;c=sqlite3.connect('/tmp/ls_cache/vec/vec.db',timeout=60);c.execute('PRAGMA wal_checkpoint(TRUNCATE)');c.close()" && cp /tmp/ls_cache/vec/vec.db $P/vec.db.tmp && mv $P/vec.db.tmp $P/vec.db; done ) &
BK=$!
for s in lme_dev; do
  [ -s /tmp/gen_jobs/$s.jsonl ] || continue
  GEN_EMBED=/workspace/work/ls/_shared/models/bge-small-en-v1.5 python3 gen_eval.py run r7_it1 $s --np 2 --sweep v3/r7/r7_sweep1.json
  echo "$(date +%T) it1 $s"
done
kill $BK
python3 -c "import sqlite3;c=sqlite3.connect('/tmp/ls_cache/vec/vec.db',timeout=60);c.execute('PRAGMA wal_checkpoint(TRUNCATE)');c.close()" && cp /tmp/ls_cache/vec/vec.db $P/vec.db
echo R7DEV1BDONE
