#!/bin/bash
# stab-r3 #3：lingshu_ng 打包验收——在干净 venv 里 pip install（非 editable），换到无关目录 import 并跑最小用例。
# 用法：tools/ci/pkg_check.sh <源根> <venv 工作目录> [extras，如 "" | embed | full] [python 解释器]
#   <源根>：含 pyproject.toml（name = lingshu-ng）、lingshu_ng/、LICENSE、README.md 的目录（Liyang/ 发布目录，
#           或 wt-stab：此时用 release/Liyang/pyproject.toml）。
# 构建在临时副本里进行（不在源根留下 build/ 或 *.egg-info），依赖只装进 venv。
set -e
SRC=$(cd "$1" && pwd); WORK=$2; EXTRA=${3:-}; PY=${4:-python3}
mkdir -p "$WORK"; WORK=$(cd "$WORK" && pwd)
STAGE=$(mktemp -d "$WORK/stage.XXXX")
if grep -q '^name = "lingshu-ng"' "$SRC/pyproject.toml" 2>/dev/null; then cp "$SRC/pyproject.toml" "$STAGE/"
else cp "$SRC/release/Liyang/pyproject.toml" "$STAGE/"; fi
cp "$SRC/LICENSE" "$STAGE/"; cp "$SRC/README.md" "$STAGE/" 2>/dev/null || echo "# lingshu_ng" > "$STAGE/README.md"
(cd "$SRC" && tar --exclude=__pycache__ -cf - lingshu_ng) | tar -xf - -C "$STAGE"
V="$WORK/venv${EXTRA:+_$EXTRA}"; rm -rf "$V"
"$PY" -m venv "$V" 2>/dev/null || { rm -rf "$V"; uv venv -q --seed --python "$PY" "$V"; }   # 无 ensurepip 的系统 Python 用 uv 建 venv
"$V/bin/python" -m pip install -q --disable-pip-version-check "$STAGE${EXTRA:+[$EXTRA]}" 2>&1 | grep -v -i "notice" || true
rm -rf "$STAGE"
cd "$WORK"   # 无关目录：确保导入的是装进 venv 的包，不是源树
"$V/bin/python" - "$SRC" <<'PY'
import importlib.metadata as md, json, os, sys, tempfile
import lingshu_ng
src = sys.argv[1]
assert os.path.realpath(lingshu_ng.__file__).startswith(os.path.realpath(sys.prefix)), lingshu_ng.__file__
dist = md.version("lingshu-ng")
assert dist == lingshu_ng.__version__, (dist, lingshu_ng.__version__)
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.capabilities import capabilities, compat_methods
d = tempfile.mkdtemp()
e = MemoryEngine(os.path.join(d, "m.db"))
e.perceive("灵枢打包验收：干净环境里写入一条记忆")
e.perceive("pip install smoke test: write and recall one memory")
r = e.recall("打包验收 写入", limit=3)
e.close()
c = SpacetimeMemoryEngine(os.path.join(d, "c.db"))
c.add_perception("兼容门面最小用例：旧 API 写入")
hits = [n.content for n, _ in c.recall("兼容门面 旧 API", limit=3)]
caps = c.capabilities()
c.close()
tab = compat_methods()
print(json.dumps({"python": sys.version.split()[0], "lingshu_ng": lingshu_ng.__version__, "dist": dist,
                  "recall_native": type(r).__name__, "recall_compat_hit": bool(hits),
                  "deps": {k: v["available"] for k, v in caps["dependencies"].items()},
                  "semantic_tier": caps["semantic_tier"], "schema_version": caps["engine"]["schema_version"],
                  "compat_unsupported": sum(v["status"] == "unsupported" for v in tab.values())}, ensure_ascii=False))
assert hits, "兼容门面召回为空"
PY
# stab-r6：命令行入口（[project.scripts] lingshu-ng）与 python -m lingshu_ng 都可用、版本一致
CLI_V=$("$V/bin/lingshu-ng" version | "$V/bin/python" -c "import json,sys;print(json.load(sys.stdin)['version'])")
MOD_V=$("$V/bin/python" -m lingshu_ng version | "$V/bin/python" -c "import json,sys;print(json.load(sys.stdin)['version'])")
[ -n "$CLI_V" ] && [ "$CLI_V" = "$MOD_V" ] || { echo "CLI_FAIL $CLI_V $MOD_V"; exit 1; }
echo "CLI_OK $CLI_V"
echo "PKG_OK extras=${EXTRA:-none}"
