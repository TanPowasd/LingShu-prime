#!/bin/bash
# r7b：lme_dev 第 1 分片被 OOM 杀（-9，剩 4 题），断点续跑（worker 按 key 跳过已完成）
cd /workspace/work/ls/wt-gen/bench_gen
export G1_FROZEN_CLOCK=1
export GEN_EMBED_CACHE=/tmp/ls_cache/vec
P=/workspace/work/ls/_shared/models/_vec_cache
mkdir -p /tmp/ls_cache/vec; [ -s /tmp/ls_cache/vec/vec.db ] || cp $P/vec.db /tmp/ls_cache/vec/
GEN_EMBED=/workspace/work/ls/_shared/models/bge-small-en-v1.5 python3 gen_eval.py run r7_it1 lme_dev --np 2 --sweep v3/r7/r7_sweep1.json
python3 -c "import sqlite3;c=sqlite3.connect('/tmp/ls_cache/vec/vec.db',timeout=60);c.execute('PRAGMA wal_checkpoint(TRUNCATE)');c.close()" && cp /tmp/ls_cache/vec/vec.db $P/vec.db.tmp && mv $P/vec.db.tmp $P/vec.db
echo R7DEV1CDONE
