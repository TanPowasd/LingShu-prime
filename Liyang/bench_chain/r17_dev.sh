#!/bin/bash
# usage: r17_dev.sh tag "ENV=.."   → dev 全集（含已暴露 H12）读数 + 合计
cd /workspace/work/ls/wt-chain/bench_chain
env LC_ML=1 $2 timeout 110 python3 r16_diag.py ${3:-h1,d2,d3,d4,d5,h4,h5,h6,h7,h8,h9,h10,h11,h12} /workspace/work/ls/_r17/d_$1.json | python3 -c "
import sys,ast
ex=w=n=0
for l in sys.stdin:
    k,d=l.split(' ',1); d=ast.literal_eval(d); ex+=d['exact'];w+=d['wrong'];n+=d['none']; print(' ',k,d['rate'],d['wrong'],end='')
print('\n$1 TOTAL exact',ex,'wrong',w,'none',n)"
