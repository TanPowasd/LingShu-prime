#!/usr/bin/env bash
# 用法：bash verify/run_verify.sh <上游 lingshu 仓路径>
# 产出：verify/out/*.json 与终端摘要。全部在临时 venv 内进行，不改上游。
set -euo pipefail
UP="$(cd "$1" && pwd)"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PK="$HERE/packages"; OUT="$HERE/verify/out"; WORK="$(mktemp -d)"
mkdir -p "$OUT"
# 拷到临时目录再安装，避免 pip 在源码树里留下 build/ 与 egg-info
cp -r "$UP" "$WORK/up"; cp -r "$PK" "$WORK/pk"; UPSRC="$UP"; UP="$WORK/up"; PK="$WORK/pk"
export PYTHONWARNINGS=ignore
echo "upstream HEAD: $(git -C "$UPSRC" rev-parse --short HEAD)" | tee "$OUT/env.txt"
python3 --version | tee -a "$OUT/env.txt"

python3 "$HERE/verify/lint_imports.py" | tee "$OUT/lint_imports.json"
# 反证：往底座副本注入一条违规 import，门禁必须变红
cp -r "$HERE" "$WORK/mut"; echo "import lspi_voxel" >> "$WORK/mut/packages/lspi-core/lspi/host.py"
if python3 "$WORK/mut/verify/lint_imports.py" > "$OUT/lint_mutant.json"; then echo "MUTANT NOT CAUGHT" ; exit 1; else echo "mutant caught: $(cat "$OUT/lint_mutant.json")"; fi

mk() { python3 -m venv "$WORK/$1"; }
PIPQ="--disable-pip-version-check"

# A：只装 lingshu（无 extras，无 numpy）+ lspi-core
mk A
"$WORK/A/bin/pip" install $PIPQ -q --no-deps "$UP" "$PK/lspi-core"
"$WORK/A/bin/python" "$HERE/verify/scenario.py" A_core_only | tee "$OUT/A.json"

# B：A + lspi-voxel
mk B
"$WORK/B/bin/pip" install $PIPQ -q --no-deps "$UP" "$PK/lspi-core" "$PK/lspi-voxel"
"$WORK/B/bin/python" "$HERE/verify/scenario.py" B_plus_voxel | tee "$OUT/B.json"

# C：B + lspi-trail；随后卸载 voxel 得 D
mk C
"$WORK/C/bin/pip" install $PIPQ -q --no-deps "$UP" "$PK/lspi-core" "$PK/lspi-voxel" "$PK/lspi-trail"
"$WORK/C/bin/pip" install $PIPQ -q pytest
"$WORK/C/bin/python" "$HERE/verify/scenario.py" C_voxel_and_trail | tee "$OUT/C.json"
(cd "$HERE" && "$WORK/C/bin/python" -m pytest tests -q -p no:cacheprovider 2>&1 | tail -3) | tee "$OUT/conformance.txt"
"$WORK/C/bin/pip" uninstall $PIPQ -q -y lspi-voxel
"$WORK/C/bin/python" "$HERE/verify/scenario.py" D_trail_without_voxel | tee "$OUT/D.json"

rm -rf "$WORK"
