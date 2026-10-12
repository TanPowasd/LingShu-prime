#!/bin/bash
for st in gen_loc_dev gen_lme_dev; do bash /workspace/work/ls/wt-rel/bench_rel/gate_rel.sh $st; done; echo GATE_GEN_DONE
