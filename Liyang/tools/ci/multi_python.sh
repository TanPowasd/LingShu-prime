#!/bin/bash
# stab-r2：多 Python 版本复跑 tests_ng（CI 用）。每个版本一个独立 venv，依赖只装进 venv，不碰全局 site-packages。
#   用法：tools/ci/multi_python.sh [版本 ...] [-- pytest 额外参数]
#   缺省版本：3.11 3.13（3.12 是开发主环境，另行跑）。
#   解释器：先找系统里的 pythonX.Y；没有就用 uv（`uv python install X.Y`，装到 $UV_PYTHON_INSTALL_DIR）。
#   环境变量：
#     MP_VENV_ROOT  venv 存放目录（缺省 .venvs-ci，位于仓库根）
#     MP_EXTRAS     额外装的包（缺省 "numpy Pillow"；设 "numpy Pillow onnxruntime tokenizers" 跑完整环境）
#     MP_MINIMAL=1  只装 pytest（最小环境）
#     LINGSHU_NG_SEM  模型目录或 off（缺省 off：多版本复跑看的是解释器差异，不依赖本机模型）
#   每个版本的结果写到 $MP_VENV_ROOT/<版本>.log，末尾汇总一行「py<版本>: <pytest 摘要>」；任一版本有 failed / error 即返回 1。
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
VERS=(); EXTRA=()
while [ $# -gt 0 ]; do if [ "$1" = "--" ]; then shift; EXTRA=("$@"); break; fi; VERS+=("$1"); shift; done
[ ${#VERS[@]} -eq 0 ] && VERS=(3.11 3.13)
VR=${MP_VENV_ROOT:-$ROOT/.venvs-ci}; mkdir -p "$VR"
PKGS="pytest"; [ "${MP_MINIMAL:-0}" = "1" ] || PKGS="pytest ${MP_EXTRAS:-numpy Pillow}"
export LINGSHU_NG_SEM=${LINGSHU_NG_SEM:-off}
rc=0; SUM=()
for v in "${VERS[@]}"; do
  py=$(command -v python$v || true)
  if [ -z "$py" ]; then
    command -v uv >/dev/null || { SUM+=("py$v: 跳过（系统无 python$v，也没有 uv）"); continue; }
    uv python install "$v" >/dev/null 2>&1 || { SUM+=("py$v: 跳过（uv python install 失败）"); continue; }
    py=$(uv python find "$v")
  fi
  ve="$VR/py$v"
  if [ ! -x "$ve/bin/python" ]; then
    if command -v uv >/dev/null; then uv venv -q --python "$py" "$ve"; else "$py" -m venv "$ve"; fi
  fi
  if command -v uv >/dev/null; then uv pip install -q --python "$ve/bin/python" $PKGS; else "$ve/bin/python" -m pip install -q $PKGS; fi
  log="$VR/py$v.log"
  ( cd "$ROOT" && PYTHONDONTWRITEBYTECODE=1 "$ve/bin/python" -m pytest tests_ng -q -p no:cacheprovider "${EXTRA[@]}" ) > "$log" 2>&1
  r=$?; last=$(grep -E "[0-9]+ (passed|failed|error)" "$log" | tail -n 1)
  SUM+=("py$v ($("$ve/bin/python" -V 2>&1)): ${last:-无摘要，见 $log}（exit $r）")
  [ $r -ne 0 ] && rc=1
done
printf '%s\n' "${SUM[@]}"
exit $rc
