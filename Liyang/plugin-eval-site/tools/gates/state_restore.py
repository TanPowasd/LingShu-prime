"""门槛 6② 状态恢复失败注入（真实插件 dsh-memory @c8c3655，多个状态对象）。

注入器（本文件）与检测器（tools/gates/state_check.py）分离：检测器只拿快照契约与磁盘，不知道哪次有故障；
注入方式与盲标映射写在 injector_sealed.json，检测完成后才揭盲比对。

状态对象清单（实测，install+ingest 后 MDCG_ROOT 与 HOME 下）：
  主文件(节点)   MDCG_ROOT/contextual/*.md            —— 记忆正文
  索引           MDCG_ROOT/_index.json               —— 节点元数据/访问计数
  摄取游标/缓存  MDCG_ROOT/_sources.json             —— 会话文件增量摄取游标（决定"已摄取过的不再写"）
  审计/访问日志  MDCG_ROOT/_audit.jsonl _access.log _crypto.jsonl _heartbeat.jsonl
  密钥           MDCG_ROOT/_keys.json, HOME/.mdcg/master.key
  宿主侧配置     HOME/.mdcg/theory.json, HOME/.dsh/.dsh-memory/data/**
  外部(不覆盖)   /tmp/md_cg_servers/<pid>.json

  python -m tools.gates.state_restore     # 全流程，结果 validation/_gates/gate6/state_restore/
"""
from __future__ import annotations
import json, os, random, shutil, sys, time
from pathlib import Path

from tools.gates.common import ROOT, VAL, wjson, append_jsonl, now_cst, sha256_file
from tools.gates import state_check

sys.path.insert(0, str(ROOT / "plugins" / "dsh-memory"))
from adapter import DshMemory            # noqa: E402
from harness.recorder import Recorder    # noqa: E402

BASE = "/tmp/gates-dshm-state"
OUT = VAL / "gate6" / "state_restore"
SEED = 20261012

S_A = [{"session_id": "baseline_A.md", "turns": [
    {"idx": 0, "role": "user", "start_line": 1, "end_line": 1, "text": "我的猫叫小橘，今年三岁，最喜欢吃鸡胸肉。"},
    {"idx": 1, "role": "assistant", "start_line": 2, "end_line": 2, "text": "记住了：小橘三岁，爱吃鸡胸肉。"},
    {"idx": 2, "role": "user", "start_line": 3, "end_line": 3, "text": "我住在杭州西湖区，周末常去植物园。"}]}]
S_B = [{"session_id": "task_B.md", "turns": [
    {"idx": 0, "role": "user", "start_line": 1, "end_line": 1, "text": "更新一下：小橘改名叫大橘了，现在四岁，改吃三文鱼。"},
    {"idx": 1, "role": "assistant", "start_line": 2, "end_line": 2, "text": "好的，大橘四岁，改吃三文鱼。"}]}]
QUERIES = ["我的猫叫什么名字，几岁", "猫最喜欢吃什么"]


def roots(p):
    return {"MDCG_ROOT": p.root, "HOME_MDCG": os.path.join(p.home, ".mdcg"), "HOME_DSH": os.path.join(p.home, ".dsh")}


CLASSES = [{"class": "主文件(节点)", "glob": "MDCG_ROOT/contextual/*"}, {"class": "主文件(节点)", "glob": "MDCG_ROOT/*/*.md"},
           {"class": "索引", "glob": "MDCG_ROOT/_index.json"}, {"class": "摄取游标/缓存", "glob": "MDCG_ROOT/_sources.json"},
           {"class": "审计/访问日志", "glob": "MDCG_ROOT/_*.jsonl"}, {"class": "审计/访问日志", "glob": "MDCG_ROOT/_access.log"},
           {"class": "密钥", "glob": "MDCG_ROOT/_keys.json"}, {"class": "密钥", "glob": "HOME_MDCG/master.key"},
           {"class": "宿主侧配置", "glob": "HOME_*"}]


def copy_roots(src_roots, dst):
    for k, r in src_roots.items():
        d = Path(dst) / k
        if d.exists():
            shutil.rmtree(d)
        if os.path.exists(r):
            shutil.copytree(r, d)


def restore_full(p, snap):
    for k, r in roots(p).items():
        if os.path.exists(r):
            shutil.rmtree(r)
        if (Path(snap) / k).exists():
            shutil.copytree(Path(snap) / k, r)


def restore_main_only(p, snap):
    """故障注入：只恢复"主文件"（节点 .md），索引/游标/日志保留任务后的样子。"""
    root = Path(p.root)
    for md in list(root.glob("*/*.md")):
        md.unlink()
    for md in (Path(snap) / "MDCG_ROOT").glob("*/*.md"):
        dst = root / md.relative_to(Path(snap) / "MDCG_ROOT")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md, dst)


def probe(p, rec, label):
    p._start(rec)
    hits = {}
    for q in QUERIES:
        r = p.recall(q, 5, rec)
        hits[q] = [{"src": h["source"], "text": (h["text"].strip().splitlines() or [""])[-1][:60]} for h in r]
    p.mcp.close(); p.mcp = None
    return hits


def run_task(p, rec):
    p._start(rec)
    p.ingest(S_B, rec)
    st = dict(p.stats["ingest"][-1]) if p.stats["ingest"] else {}
    p.mcp.close(); p.mcp = None
    return st


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if os.path.exists(BASE):
        shutil.rmtree(BASE)
    recp = OUT / "recording.jsonl"
    if recp.exists():
        recp.unlink()
    rec = Recorder(recp, "gate6_state_restore")
    p = DshMemory(base=BASE)
    ir = p.install(rec)
    assert ir.ok, ir.errors
    p.ingest(S_A, rec)
    p.mcp.close(); p.mcp = None
    snap = Path(BASE) / "_snap0"
    copy_roots(roots(p), snap)
    base_hashes = state_check.scan(roots(p))
    inv = {"plugin": "dsh-memory", "sha": p.sha, "roots": roots(p), "classes": CLASSES, "baseline": base_hashes,
           "excluded": ["*.lock（0 字节互斥锁）"],
           "not_covered": ["/tmp/md_cg_servers/<pid>.json（服务自报文件，外部；本契约不覆盖，残留单列）"],
           "verify": "tools/gates/state_check.py（独立：sha256 逐对象比对基线；不读插件自报）", "created": now_cst()}
    invp = OUT / "state-inventory.json"
    wjson(invp, inv)
    rec.event("gates.snapshot", n_objects=len(base_hashes))

    # 盲标：X/Y 随机对应 {full, main_only}
    rng = random.Random(SEED)
    methods = ["full", "main_only"]; rng.shuffle(methods)
    blind = {"X": methods[0], "Y": methods[1]}
    wjson(OUT / "injector_sealed.json", {"note": "注入器私有；检测器不读。检测完成后揭盲。", "blind": blind, "seed": SEED})
    detections = {}
    task_stats = {}
    for case in ("X", "Y"):
        restore_full(p, snap)
        task_stats[case] = run_task(p, rec)                      # 一次 P 侧运行，状态被改写
        (restore_full if blind[case] == "full" else restore_main_only)(p, snap)
        detections[case] = state_check.check(invp)               # 检测器：只看契约+磁盘
        rec.event("gates.detect", case=case, ok=detections[case]["ok"], n_bad=detections[case]["n_bad"])
        append_jsonl(OUT / "pairs.jsonl", {"pair_id": f"P-{case}", "side": "P(dsh-memory)", "restore_check": "pass" if detections[case]["ok"] else "fail",
                                            "valid": detections[case]["ok"], "reason": detections[case]["reason"]})
        if not detections[case]["ok"]:
            # 污染后果实测（检测后、仅用于说明为什么必须拒绝）：在被污染状态上召回、再按同一路径重新摄取任务会话
            detections[case]["pollution_probe"] = {"recall_on_polluted_state": probe(p, rec, case)}
            p._start(rec)
            p.ingest(S_B, rec)
            detections[case]["pollution_probe"]["reingest_same_session"] = dict(p.stats["ingest"][-1])
            p.mcp.close(); p.mcp = None
            # 处置：完整恢复 → 再检 → 整对重跑
            restore_full(p, snap)
            re = state_check.check(invp)
            detections[case]["after_full_restore"] = {"ok": re["ok"], "n_bad": re["n_bad"]}
            rerun = run_task(p, rec)
            detections[case]["rerun_pair"] = {"task_ingest": rerun, "recall": None}
            append_jsonl(OUT / "pairs.jsonl", {"pair_id": f"P-{case}-rerun", "side": "B0+P 整对重跑", "restore_check": "pass" if re["ok"] else "fail",
                                                "valid": re["ok"], "replaces": f"P-{case}"})
    # 揭盲
    results = []
    for case in ("X", "Y"):
        expect_reject = blind[case] == "main_only"
        d = detections[case]
        results.append({"case": case, "injected": blind[case], "expected": "拒绝配对" if expect_reject else "通过（无误报）",
                        "observed": "拒绝配对" if d["reject_pair"] else "通过", "pass": d["reject_pair"] == expect_reject,
                        "bad_by_class": d["bad_by_class"], "detail": d})
    # 干净对照：基线本身
    restore_full(p, snap)
    ctrl = state_check.check(invp)
    results.append({"case": "control_baseline", "injected": "无（刚完整恢复）", "expected": "通过", "observed": "通过" if ctrl["ok"] else "拒绝",
                    "pass": ctrl["ok"]})
    rec.close()
    wjson(OUT / "result.json", {"created": now_cst(), "task_ingest": task_stats, "results": results,
                                "all_pass": all(r["pass"] for r in results)})
    print(json.dumps([{k: r[k] for k in ("case", "injected", "expected", "observed", "pass")} | {"bad": r.get("bad_by_class")} for r in results], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
