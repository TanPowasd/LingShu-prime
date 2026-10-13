#!/bin/bash
# split-r1：核心 + 4 个插件包的打包验收——每组一个干净 venv，pip install（非 editable）后换到无关目录导入并跑最小用例。
# 用法：tools/ci/pkg_check_plugins.sh <源根> <venv 工作目录> <组> [python 解释器]
#   <源根>：仓库根 / Liyang/ 发布目录（含 lingshu_ng/、plugins/、LICENSE、README.md；核心 pyproject 为 <源根>/pyproject.toml
#           且 name = lingshu-ng，否则用 <源根>/release/Liyang/pyproject.toml）
#   <组>：core | embed | world | nn | gen（gen 组同时装 nn，gen 依赖它）
# 构建在临时副本里进行（不在源根留下 build/ 或 *.egg-info）；依赖只装进 venv；本地包用 --no-index 之外的正常解析
# （lingshu-ng / lingshu-ng-nn 先从本地副本装好，pip 不会去索引找它们）。
set -e
SRC=$(cd "$1" && pwd); WORK=$2; GROUP=$3; PY=${4:-python3}
mkdir -p "$WORK"; WORK=$(cd "$WORK" && pwd)
stage_core() {
  local S; S=$(mktemp -d "$WORK/stage_core.XXXX")
  if grep -q '^name = "lingshu-ng"' "$SRC/pyproject.toml" 2>/dev/null; then cp "$SRC/pyproject.toml" "$S/"
  else cp "$SRC/release/Liyang/pyproject.toml" "$S/"; fi
  cp "$SRC/LICENSE" "$S/"; cp "$SRC/README.md" "$S/" 2>/dev/null || echo "# lingshu_ng" > "$S/README.md"
  (cd "$SRC" && tar --exclude=__pycache__ -cf - lingshu_ng) | tar -xf - -C "$S"
  echo "$S"
}
stage_plugin() {
  local S; S=$(mktemp -d "$WORK/stage_$1.XXXX")
  (cd "$SRC/plugins/lingshu-ng-$1" && tar --exclude=__pycache__ -cf - pyproject.toml README.md src) | tar -xf - -C "$S"
  cp "$SRC/LICENSE" "$S/"
  echo "$S"
}
V="$WORK/venv_$GROUP"; rm -rf "$V"
"$PY" -m venv "$V" 2>/dev/null || { rm -rf "$V"; uv venv -q --seed --python "$PY" "$V"; }
PIP="$V/bin/python -m pip install -q --disable-pip-version-check"
C=$(stage_core); $PIP "$C" 2>&1 | grep -v -i "notice" || true; rm -rf "$C"
case $GROUP in
  core) PLUGS="";;
  gen) PLUGS="nn gen";;
  *) PLUGS="$GROUP";;
esac
for p in $PLUGS; do P=$(stage_plugin $p); $PIP "$P" 2>&1 | grep -v -i "notice" || true; rm -rf "$P"; done
cd "$WORK"   # 无关目录：导入的是装进 venv 的包，不是源树
"$V/bin/python" - "$GROUP" <<'PY'
import importlib.metadata as md, importlib.util, json, os, sys, tempfile
group = sys.argv[1]
import lingshu_ng
assert os.path.realpath(lingshu_ng.__file__).startswith(os.path.realpath(sys.prefix)), lingshu_ng.__file__
assert md.version("lingshu-ng") == lingshu_ng.__version__
assert md.requires("lingshu-ng") is None, md.requires("lingshu-ng")          # 核心零依赖：元数据里没有 Requires-Dist
for sub in ("world", "nn", "gen"):                                            # 核心发行包里没有插件子包
    assert not os.path.isdir(os.path.join(os.path.dirname(lingshu_ng.__file__), sub)), sub
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.capabilities import capabilities
d = tempfile.mkdtemp()
e = MemoryEngine(os.path.join(d, "m.db")); e.perceive("灵枢拆包验收：干净环境里写入一条记忆"); r = e.recall("拆包验收 写入", limit=3); e.close()
c = SpacetimeMemoryEngine(os.path.join(d, "c.db")); c.add_perception("兼容门面最小用例"); w3 = c.world3d("status", {})["status"]
caps = c.capabilities(); c.close()
third = {m: importlib.util.find_spec(m) is not None for m in ("numpy", "onnxruntime", "tokenizers", "PIL")}
out = {"python": sys.version.split()[0], "group": group, "lingshu_ng": lingshu_ng.__version__,
       "plugins": {k: (v["version"], v["source"], v["error"]) for k, v in caps["plugins"].items()},
       "third_party_installed": third, "semantic_tier": caps["semantic_tier"], "world3d": w3,
       "recall_hits": len(r["hits"]) if isinstance(r, dict) else None}
want = {"core": set(), "embed": {"embed"}, "world": {"world"}, "nn": {"nn"}, "gen": {"nn", "gen"}}[group]
assert set(caps["plugins"]) == want, caps["plugins"]
assert all(v[1] == "entry_point" and v[2] is None for v in out["plugins"].values()), out["plugins"]
if group == "core":
    assert not any(third.values()), third                                     # 核心安装不带任何第三方包
    for m, dist in (("lingshu_ng.world", "lingshu-ng-world"), ("lingshu_ng.nn", "lingshu-ng-nn"), ("lingshu_ng.gen", "lingshu-ng-gen")):
        try:
            __import__(m); raise AssertionError(m)
        except ModuleNotFoundError as ex:
            assert f"pip install {dist}" in str(ex), ex
    try:
        from lingshu_ng.embed import OnnxEmbedder  # noqa: F401
        raise AssertionError("OnnxEmbedder")
    except ImportError as ex:
        assert "pip install lingshu-ng-embed" in str(ex), ex
    assert w3 == "world3d_not_ready" and caps["semantic_tier"] == "v4"
if group == "embed":
    from lingshu_ng.embed import OnnxEmbedder
    from lingshu_ng.embed.cross import OnnxCrossEncoder
    assert OnnxEmbedder.__module__ == "lingshu_ng_embed.onnx_embed" and OnnxCrossEncoder.__module__ == "lingshu_ng_embed.cross"
    import lingshu_ng.semrank as S
    assert S.DenseEmbedder.INST == S.DENSE_INST
if group in ("world",):
    import lingshu_ng.world.voxel as v
    assert v.__name__ == "lingshu_ng.world.voxel" and v.VoxelWorld.__module__ == "lingshu_ng.world.voxel"
    assert os.path.realpath(v.__file__).startswith(os.path.realpath(sys.prefix))
if group in ("nn", "gen"):
    import lingshu_ng.nn.render as rr
    assert rr.__name__ == "lingshu_ng.nn.render"
if group == "gen":
    import lingshu_ng.gen.hexgen as hg, lingshu_ng.nn.compat.hex_gen as hcg
    assert hg.__name__ == "lingshu_ng.gen.hexgen" and hcg.__name__ == "lingshu_ng.nn.compat.hex_gen"
print(json.dumps(out, ensure_ascii=False))
PY
echo "PKG_OK group=$GROUP"
