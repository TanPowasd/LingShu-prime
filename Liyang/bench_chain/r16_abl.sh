#!/bin/bash
# usage: r16_abl.sh tag "ENV=.." sets
cd /workspace/work/ls/wt-chain/bench_chain
env $2 timeout 110 python3 r16_diag.py ${3:-h6,h7,h8,h9,h10,h11} /tmp/d_$1.json | python3 -c "
import sys,ast
ex=w=n=0
for l in sys.stdin:
    k,d=l.split(' ',1); d=ast.literal_eval(d); ex+=d['exact'];w+=d['wrong'];n+=d['none']; print(' ',k,d['rate'],d['wrong'],end='')
print('\n$1 TOTAL exact',ex,'wrong',w,'none',n)"
