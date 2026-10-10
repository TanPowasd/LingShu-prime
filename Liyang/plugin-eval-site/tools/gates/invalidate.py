"""失效传播（手册 §13.4）：证据缺失/哈希不符/判分器撤销 → 受影响 analysis → 报告页标「证据不完整/待复核」（保留历史正文）
→ 测试榜单移出有效区 → 徽章撤回。全部写只追加的 invalidations.jsonl；恢复后重新核验通过才复位，并追加复位记录（不覆盖旧记录）。

  python -m tools.gates.invalidate sweep <rid>                    # 核验全部节点并传播失效（发布前/定时巡检）
  python -m tools.gates.invalidate revoke-judge <rid> <sha> <原因>  # 判分器版本撤销 → 传播
  python -m tools.gates.invalidate reinstate <rid>                 # 重新核验；通过的条目复位（追加记录）
"""
from __future__ import annotations
import json, sys

from tools.gates.common import rjson, wjson, append_jsonl, now_cst
from tools.gates.evidence_chain import rdir, dependents
from tools.gates.evidence_verify import verify_nodes

BANNER = "> ⚠ **证据不完整/待复核**（{when}）：{why}。本页保留历史文本，但其结论已退出有效榜单，相应徽章失效。\n\n"


def _apply(rid, man, invalid_nodes, reasons):
    d = rdir(rid)
    pub = d / "published"
    board = rjson(pub / "board.json")
    affected = {"reports": [], "board": [], "badges": []}
    for n in sorted(invalid_nodes):
        t = man["nodes"].get(n, {}).get("type")
        name = n.split(":", 1)[1]
        why = "；".join(reasons.get(n, [])) or "上游证据无效"
        if t == "report":
            p = pub / "reports" / f"{name}.md"
            if p.exists():
                txt = p.read_text(encoding="utf-8")
                if "证据不完整/待复核" not in txt.split("\n", 3)[-1][:400] and "status: invalid" not in txt[:200]:
                    lines = txt.split("\n", 1)
                    head = lines[0].replace("status: valid", "status: invalid")
                    p.write_text(head + "\n" + BANNER.format(when=now_cst(), why=why) + lines[1], encoding="utf-8")
                affected["reports"].append(name)
        elif t == "board":
            keep = []
            for e in board["valid"]:
                if e["entry"] == n:
                    board["invalid"].append({**e, "withdrawn_at": now_cst(), "why": why}); affected["board"].append(n)
                else:
                    keep.append(e)
            board["valid"] = keep
        elif t == "badge":
            bp = pub / "badges" / f"{name}.json"
            if bp.exists():
                b = rjson(bp)
                if b.get("status") != "revoked":
                    b.update(status="revoked", revoked_at=now_cst(), why=why)
                    wjson(bp, b)
                affected["badges"].append(name)
    wjson(pub / "board.json", board)
    return affected


def sweep(rid):
    d = rdir(rid)
    man = rjson(d / "evidence-manifest.json")
    rep = verify_nodes(rid, man, None)
    roots = sorted({e["node"] for e in rep["errors"]})
    inv = dependents(man, roots) if roots else set()
    reasons = {}
    for e in rep["errors"]:
        for n in dependents(man, [e["node"]]):
            reasons.setdefault(n, []).append(f"{e['code']} {e.get('path') or e.get('judge') or e['node']}")
    affected = _apply(rid, man, inv, reasons) if inv else {"reports": [], "board": [], "badges": []}
    rec = {"at": now_cst(), "action": "sweep", "errors": rep["errors"], "invalid_nodes": sorted(inv), "affected": affected}
    append_jsonl(d / "invalidations.jsonl", rec)
    return rec


def revoke_judge(rid, sha, reason):
    d = rdir(rid)
    p = d / "revoked.json"
    rv = rjson(p) if p.exists() else {"judges": {}}
    rv["judges"][sha] = {"reason": reason, "at": now_cst()}
    wjson(p, rv)
    return sweep(rid)


def reinstate(rid, recompute=True):
    """复位：只有重新核验通过（且可重算）的条目回到有效区；追加记录。"""
    from tools.gates.evidence_chain import ANALYSES, recompute_analysis
    d = rdir(rid)
    man = rjson(d / "evidence-manifest.json")
    pub = d / "published"
    board = rjson(pub / "board.json")
    back = []
    for e in list(board["invalid"]):
        aid = e["entry"].split(":", 1)[1]
        rep = verify_nodes(rid, man, [e["entry"]])
        if not rep["ok"]:
            continue
        norm, _ = recompute_analysis(rid, aid) if recompute else (None, None)
        if norm:   # 新结果落盘；旧输出移入 history（重算不覆盖原记录，§13.4）
            from tools.gates.common import rjson as _rj
            ap = d / "analysis" / aid / "result.json"
            if ap.exists():
                h = d / "analysis" / aid / "history"; h.mkdir(exist_ok=True)
                old = _rj(ap); (h / f"result_superseded_{len(list(h.glob('*.json')))}.json").write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
            wjson(ap, {"analysis_id": aid, "result": norm, "computed": now_cst(), "note": "reinstate 重算"})
        board["invalid"].remove(e)
        ne = {k: v for k, v in e.items() if k not in ("withdrawn_at", "why")}
        if norm:
            ne.update(verdict=norm["verdict"], label=norm["label"], items_gain=round(norm.get("items_gain", 0)))
        ne["reinstated_at"] = now_cst(); board["valid"].append(ne); back.append(e["entry"])
        a = ANALYSES[aid]
        bp = pub / "badges" / f"{a['plugin']}.json"
        if bp.exists():
            b = rjson(bp); b.update(status="valid", reinstated_at=now_cst(), verdict=ne.get("verdict"), label=ne.get("label")); wjson(bp, b)
        rp = pub / "reports" / f"{a['report']}.md"
        if rp.exists():
            txt = rp.read_text(encoding="utf-8").replace("status: invalid", "status: valid(reinstated)", 1)
            rp.write_text(txt.replace("> ⚠ **证据不完整/待复核**", f"> ✅ 已于 {now_cst()} 重新核验通过并复位（下方旧失效记录保留）\n> ⚠ ~~证据不完整/待复核~~", 1), encoding="utf-8")
    wjson(pub / "board.json", board)
    rec = {"at": now_cst(), "action": "reinstate", "reinstated": back}
    append_jsonl(d / "invalidations.jsonl", rec)
    return rec


if __name__ == "__main__":
    cmd, rid = sys.argv[1], sys.argv[2]
    if cmd == "sweep":
        print(json.dumps(sweep(rid), ensure_ascii=False, indent=1))
    elif cmd == "revoke-judge":
        print(json.dumps(revoke_judge(rid, sys.argv[3], sys.argv[4]), ensure_ascii=False, indent=1))
    elif cmd == "reinstate":
        print(json.dumps(reinstate(rid), ensure_ascii=False, indent=1))
