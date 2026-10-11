# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""TriCue 泛化评测（零模型零 key）：留出数据上的证据召回。口径见 gen_prereg.md，跑测试集前先冻结。

数据
  lme     LongMemEval_S（cleaned）：每题独立建库（全部 haystack 会话按日期顺序写入），查询＝题面；
          指标：会话 recall_any@5/@10（任一证据会话进前 k 个去重会话）、轮 recall_any@10/@50（has_answer 轮）。
          弃答题（_abs）剔除。dev＝md5(question_id) % 10 == 0，其余为 test。
  locomo  LoCoMo-10：每段对话建库（会话按序号，轮文本＝"说话人: 原文"，有图片时附 "[image: 描述]"）；
          查询＝问题；指标：证据轮召回比例 @5/@10/@25（按轮去重）。第 5 类（对抗）剔除。全部为 test。
  hive    hive-memory-bench e2e C 型续接卡：口径同 hive_ccard.py；hit@10/@50、MRR。全部为 test。

臂
  v11        TriCue v1.1（近因 + 字二元组 BM25 + AGM）
  tc11s      v1.1 三路，打分换 BM25+×SDM
  tc2b       v2 线索组合（块 + AGM + 整轮 + 相关近因），打分仍为 v1 BM25（通用分词）
  tc2        TriCue v2（BM25+×SDM，块 + AGM + 整轮 + 相关近因，无全局近因）
  tc2r       tc2 + 全局近因
  turn_v1    基线：整轮字二元组 BM25（#3 口径）
  turn_sdm   基线：整轮 BM25+×SDM
用法：python -B -X utf8 gen_bench.py --data lme --split dev [--limit N] [--json out]
"""
import argparse
import collections
import hashlib
import json
import multiprocessing as mp
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import tricue as T  # noqa: E402

ROOT = HERE.parents[4]                     # 项目根
DATA = pathlib.Path("/workspace/projects/c5e24339-1a72-4448-88c0-70df0ede0917/data_gen")
ARMS = ("v11", "tc11s", "tc2b", "tc2", "tc2r", "turn_v1", "turn_sdm")


def build(turns):
    """turns: [(role, text)] → 三个库共享同一写入序列。"""
    mB = T.TriCueMemory(turn_cue=True)                                   # v1.1 + 整轮 v1
    mM = T.TriCueMemory(tokenizer="mixed", turn_cue=True)                # 通用分词 + v1 打分
    mS = T.TriCueMemory(tokenizer="mixed", turn_cue=True, scorer="bm25p_sdm")
    for r, t in turns:
        for m in (mB, mM, mS):
            m.add_turn(r, t)
    return mB, mM, mS


def turn_order(m, chunks):
    seen, out = set(), []
    for i in chunks:
        t = m.turn_of[i]
        if t not in seen:
            seen.add(t); out.append(t)
    return out


def rankings(mems, q):
    mB, mM, mS = mems
    out = {}
    scB = mB.bm25(q)
    out["v11"] = turn_order(mB, T.rrf([mB.rank_recent(), sorted(scB, key=lambda i: -scB[i]), mB.rank_agm(scB)]))
    tsB = mB.turn_bm25(q)
    out["turn_v1"] = sorted(tsB, key=lambda t: -tsB[t])
    scM = mM.bm25(q)
    out["tc2b"] = turn_order(mM, T.rrf([sorted(scM, key=lambda i: -scM[i]), mM.rank_agm(scM),
                                        mM.rank_turn(q, scM), mM.rank_relrec(scM)]))
    scS = mS.bm25(q)
    oS, aS, tS, rS = sorted(scS, key=lambda i: -scS[i]), mS.rank_agm(scS), mS.rank_turn(q, scS), mS.rank_relrec(scS)
    out["tc11s"] = turn_order(mS, T.rrf([mS.rank_recent(), oS, aS]))
    out["tc2"] = turn_order(mS, T.rrf([oS, aS, tS, rS]))
    out["tc2r"] = turn_order(mS, T.rrf([mS.rank_recent(), oS, aS, tS, rS]))
    tsS = mS.turn_bm25(q)
    out["turn_sdm"] = sorted(tsS, key=lambda t: -tsS[t])
    return out


# ---------------- LongMemEval ----------------
def lme_items(split):
    d = json.loads((DATA / "lme_s.json").read_text(encoding="utf-8"))
    out = []
    for x in d:
        if x["question_id"].endswith("_abs"):
            continue
        dev = int(hashlib.md5(x["question_id"].encode()).hexdigest(), 16) % 10 == 0
        if split == "all" or (split == "dev") == dev:
            out.append(x)
    return out


def lme_one(x):
    sess = sorted(zip(x["haystack_dates"], x["haystack_session_ids"], x["haystack_sessions"]), key=lambda z: z[0])
    turns, s_of, ans_t = [], [], set()
    for _, sid, ss in sess:
        for t in ss:
            if t.get("has_answer"):
                ans_t.add(len(turns))
            turns.append((t["role"], t["content"])); s_of.append(sid)
    t0 = time.time()
    mems = build(turns)
    tb = time.time() - t0
    t0 = time.time()
    rk = rankings(mems, x["question"])
    tr = time.time() - t0
    gold = set(x["answer_session_ids"])
    res = {}
    for a, order in rk.items():
        so, seen = [], set()
        for t in order:
            if s_of[t] not in seen:
                seen.add(s_of[t]); so.append(s_of[t])
        res[a] = {"s@5": bool(gold & set(so[:5])), "s@10": bool(gold & set(so[:10])),
                  "t@10": bool(ans_t & set(order[:10])) if ans_t else None,
                  "t@50": bool(ans_t & set(order[:50])) if ans_t else None}
    return {"id": x["question_id"], "type": x["question_type"], "res": res, "build_s": tb, "rank_s": tr}


# ---------------- LoCoMo ----------------
def locomo_items(split):
    if split == "dev":
        return []
    out = []
    for c in json.loads((DATA / "locomo10.json").read_text(encoding="utf-8")):
        conv = c["conversation"]
        n = sorted(int(k.split("_")[1]) for k in conv if k.startswith("session_") and not k.endswith("date_time"))
        turns, ids = [], []
        for i in n:
            for t in conv[f"session_{i}"]:
                txt = f"{t['speaker']}: {t['text']}"
                if t.get("blip_caption"):
                    txt += f" [image: {t['blip_caption']}]"
                turns.append(("user", txt)); ids.append(t["dia_id"])
        qs = [q for q in c["qa"] if q.get("category") != 5]
        out.append({"id": c["sample_id"], "turns": turns, "ids": ids, "qa": qs})
    return out


def locomo_one(c):
    mems = build(c["turns"])
    idx = {d: i for i, d in enumerate(c["ids"])}
    rows = []
    for q in c["qa"]:
        ev = set()
        for e in q.get("evidence", []):
            for p in str(e).replace(";", ",").split(","):
                p = p.strip()
                if p in idx:
                    ev.add(idx[p])
        if not ev:
            continue
        rk = rankings(mems, q["question"])
        rows.append({"cat": q["category"],
                     "res": {a: {f"r@{k}": len(ev & set(o[:k])) / len(ev) for k in (5, 10, 25)} for a, o in rk.items()}})
    return {"id": c["id"], "rows": rows}


# ---------------- hive C 型卡 ----------------
def hive_run():
    from hive_e2e_stream import parse
    root = ROOT / "hive-memory-bench" / "e2e"
    cards = json.loads((root / "questions/题卡_C型_续接预测_v0.1.json").read_text(encoding="utf-8"))
    turns, where = [], {}
    for f in sorted((root / "corpus").glob("*.md")):
        for t in parse(f):
            g = len(turns)
            turns.append((t["who"], t["text"]))
            for ln, _ in t["lines"]:
                where[(f.name, ln)] = g
    mems = build(turns)
    rows = []
    for c in cards:
        g = where.get((c["file"], c["answer"]["human"]["line"]))
        if g is None:
            continue
        rk = rankings(mems, "\n".join(p["text"] for p in c["pre"]))
        res = {}
        for a, o in rk.items():
            pos = o.index(g) + 1 if g in o else None
            res[a] = {"h@10": bool(pos and pos <= 10), "h@50": bool(pos and pos <= 50), "rr": 1 / pos if pos else 0.0}
        rows.append({"id": c["id"], "res": res})
    return rows


def agg(rows, keys):
    out = {}
    for a in ARMS:
        out[a] = {}
        for k in keys:
            v = [r["res"][a][k] for r in rows if r["res"][a][k] is not None]
            out[a][k] = round(sum(v) / len(v), 4) if v else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, choices=("lme", "locomo", "hive"))
    ap.add_argument("--split", default="dev", choices=("dev", "test", "all"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--json")
    a = ap.parse_args()
    t0 = time.time()
    if a.data == "lme":
        items = lme_items(a.split)[: a.limit or None]
        with mp.Pool(a.procs) as p:
            rows = p.map(lme_one, items, chunksize=1)
        res = {"n": len(rows), "总": agg(rows, ("s@5", "s@10", "t@10", "t@50")),
               "按题型": {ty: agg([r for r in rows if r["type"] == ty], ("s@5", "s@10"))
                       for ty in sorted({r["type"] for r in rows})},
               "建库秒中位": sorted(r["build_s"] for r in rows)[len(rows) // 2] if rows else None,
               "排序秒中位": sorted(r["rank_s"] for r in rows)[len(rows) // 2] if rows else None}
    elif a.data == "locomo":
        items = locomo_items(a.split)[: a.limit or None]
        with mp.Pool(a.procs) as p:
            convs = p.map(locomo_one, items, chunksize=1)
        rows = [r for c in convs for r in c["rows"]]
        res = {"n": len(rows), "总": agg(rows, ("r@5", "r@10", "r@25")),
               "按类别": {str(k): agg([r for r in rows if r["cat"] == k], ("r@10",)) for k in sorted({r["cat"] for r in rows})}}
    else:
        rows = hive_run() if a.split != "dev" else []
        res = {"n": len(rows), "总": agg(rows, ("h@10", "h@50", "rr"))}
    res.update({"data": a.data, "split": a.split, "秒": round(time.time() - t0, 1), "tricue": T.__version__})
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
