"""独立状态恢复检查器（检测器）。不 import 被测插件、不读插件自报状态、不读注入器日志。

输入只有：快照契约（对象清单 + 基线哈希 manifest）与当前磁盘。输出机器可读判定：
  {"ok": bool, "objects": [{"object", "class", "status": ok|missing|extra|hash_mismatch, ...}], "reject_pair": bool}

快照契约（state-inventory.json）格式：
  {"roots": {"MDCG_ROOT": "/path", "HOME_MDCG": "/path", ...},
   "classes": [{"class": "主文件(节点)", "glob": "MDCG_ROOT/contextual/*.md"}, ...],   # 分类只用于报告，不影响判定
   "baseline": {"MDCG_ROOT/_index.json": "<sha256>", ...},                          # 全部受控对象
   "not_covered": ["/tmp/md_cg_servers/<pid>.json（服务自报，外部；不在恢复覆盖范围）"]}
"""
from __future__ import annotations
import fnmatch, hashlib, json, os, sys
from pathlib import Path


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def scan(roots: dict) -> dict:
    out = {}
    for name, r in roots.items():
        r = Path(r)
        if not r.exists():
            continue
        for dp, dn, fn in os.walk(r):
            for n in fn:
                p = Path(dp) / n
                if n.endswith(".lock"):          # 0 字节锁文件：插件运行时互斥用，不承载状态（契约中登记为排除项）
                    continue
                out[f"{name}/{p.relative_to(r).as_posix()}"] = _sha(p)
    return out


def classify_obj(obj: str, classes: list) -> str:
    for c in classes:
        if fnmatch.fnmatch(obj, c["glob"]):
            return c["class"]
    return "未分类"


def check(inventory_path) -> dict:
    inv = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
    cur = scan(inv["roots"])
    base = inv["baseline"]
    objs = []
    for k in sorted(set(base) | set(cur)):
        if k in base and k not in cur:
            st = "missing"
        elif k not in base:
            st = "extra"
        elif base[k] != cur[k]:
            st = "hash_mismatch"
        else:
            st = "ok"
        objs.append({"object": k, "class": classify_obj(k, inv.get("classes", [])), "status": st,
                     "baseline": base.get(k, "")[:16], "current": cur.get(k, "")[:16]})
    bad = [o for o in objs if o["status"] != "ok"]
    by_class = {}
    for o in bad:
        by_class.setdefault(o["class"], {}).setdefault(o["status"], 0)
        by_class[o["class"]][o["status"]] += 1
    return {"ok": not bad, "reject_pair": bool(bad), "n_objects": len(objs), "n_bad": len(bad), "bad_by_class": by_class,
            "objects": bad, "reason": None if not bad else "恢复验证失败：受控状态对象与基线快照不一致 → 本次运行不得计入配对样本（手册 §3.2 四要素④）"}


if __name__ == "__main__":
    print(json.dumps(check(sys.argv[1]), ensure_ascii=False, indent=1))
