"""证据核验器（检测器）：按 evidence-manifest 逐对象核对存在性与 sha256，判分器撤销表，以及外部输入哈希。

不读任何"这次有故障"的标记；只读 manifest、撤销表（revoked.json，由治理流程写）与磁盘。
错误码（机器可读）：
  MISSING_FILE      登记的产物不存在                {"code","node","path"}
  HASH_MISMATCH     文件在、内容与登记哈希不符        {"code","node","path","expected","actual"}
  UNREGISTERED_FILE run 目录里出现未登记的必要产物（如补跑多出的一边）
  JUDGE_REVOKED     依赖的判分器版本已撤销          {"code","node","judge"}
  INPUT_CHANGED     外部输入（题卡/语料）哈希变化
  DEP_INVALID       上游依赖无效（传递）              {"code","node","because"}

  python -m tools.gates.evidence_verify <rid> [--node analysis:B_dsh_vs_null]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

from tools.gates.common import HMB, sha256_file, sha256_text, rjson, wjson, now_cst
from tools.gates.evidence_chain import rdir, RUN_GLOBS


def _revoked(rid):
    p = rdir(rid) / "revoked.json"
    return rjson(p) if p.exists() else {"judges": {}}


def check_node(rid, man, name):
    d = rdir(rid)
    v = man["nodes"][name]
    errs = []
    for a in v.get("artifacts", []):
        p = d / a["path"]
        if not p.exists():
            errs.append({"code": "MISSING_FILE", "node": name, "path": a["path"]})
        else:
            h = sha256_file(p)
            if h != a["sha256"]:
                errs.append({"code": "HASH_MISMATCH", "node": name, "path": a["path"], "expected": a["sha256"][:16], "actual": h[:16]})
    if v["type"] == "run":
        reg = {a["path"] for a in v["artifacts"]}
        rd = d / "runs" / name.split(":", 1)[1]
        for g in RUN_GLOBS:
            for p in rd.glob(g):
                rel = p.relative_to(d).as_posix()
                if rel not in reg:
                    errs.append({"code": "UNREGISTERED_FILE", "node": name, "path": rel})
    if v["type"] == "judge":
        rv = _revoked(rid)["judges"]
        h = name.split(":", 1)[1]
        if h in rv:
            errs.append({"code": "JUDGE_REVOKED", "node": name, "judge": h[:16], "reason": rv[h].get("reason")})
    if v["type"] == "input":
        p = Path(v["external"])
        if p.is_file():
            cur = sha256_file(p) if p.exists() else None
        else:
            cur = sha256_text("".join(sha256_file(x) for x in sorted(p.glob("*.md")))) if p.exists() else None
        if cur != v["sha256"]:
            errs.append({"code": "INPUT_CHANGED", "node": name, "path": str(p)})
    return errs


def verify_nodes(rid, man, targets=None):
    """核验 targets 及其全部上游；返回每节点状态（含传递失效）。targets=None ⇒ 全部节点。"""
    nodes = man["nodes"]
    memo = {}

    def status(n, stack=()):
        if n in memo:
            return memo[n]
        if n not in nodes:
            memo[n] = [{"code": "MISSING_NODE", "node": n}]
            return memo[n]
        own = check_node(rid, man, n)
        up = []
        for dep in nodes[n].get("deps", []):
            if dep in stack:
                continue
            if status(dep, stack + (n,)):
                up.append({"code": "DEP_INVALID", "node": n, "because": dep})
        memo[n] = own + up
        return memo[n]

    for t in (targets or list(nodes)):
        status(t)
    errors = [e for es in memo.values() for e in es]
    own = [e for e in errors if e["code"] != "DEP_INVALID"]
    return {"ok": not errors, "checked": len(memo), "errors": own, "invalid_nodes": sorted(n for n, es in memo.items() if es),
            "dep_chain": [e for e in errors if e["code"] == "DEP_INVALID"]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("rid"); ap.add_argument("--node", action="append")
    a = ap.parse_args()
    man = rjson(rdir(a.rid) / "evidence-manifest.json")
    r = verify_nodes(a.rid, man, a.node)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
