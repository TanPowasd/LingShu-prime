#!/bin/bash
# usage: tools/gc.sh "commit msg" "progress line"
cd /workspace/work/pes
G="git -c user.name=pes-harness -c user.email=pes-harness@local"
$G commit -qm "$1" || exit 1
C=$(git log --oneline -1|cut -c1-7)
T=$(TZ=Asia/Shanghai date +%H:%M)
echo "- $T CST · pes-harness · $2 · $C" >> OVERNIGHT.md
git add OVERNIGHT.md && $G commit -qm "progress: ${2:0:60}" && echo "$C"
