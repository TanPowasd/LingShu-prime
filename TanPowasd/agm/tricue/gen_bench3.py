# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""TriCue v3 开发与评测（零模型零 key）：只看真实对话（hive e2e）和跨会话写入（LongMemEval、LoCoMo）。
切分与判定写在 gen_prereg3.md；开发阶段只跑 --split dev。

数据
  lme     LongMemEval_S：dev＝md5(qid)%10==0（同 v2），会话 recall_any@5/@10、轮 recall_any@10
  locomo  LoCoMo-10：dev＝md5(sample_id)%3==0（conv-30、conv-47），证据轮召回 @5/@10/@25
  cards   hive C 型续接卡：dev＝md5(文件名)%3==0（6 个文件、32 张卡），hit@10/@50、MRR
  stream  hive e2e 流式：每个文件独立按轮写入，每个人类问句（下一轮是 AI）取 4000 字上下文，
          指标为覆盖和窗口外（口径同 hive_variants.py）；dev＝md5(文件名)%3==0
臂（库配置 / 排序）
  v11        v1.1：近因 + 字二元组 BM25 + AGM
  tc2        v2：BM25+×SDM（中文单字词项）块 + AGM + 整轮 + 相关近因
  tc3        候选：同 tc2，但中文词项取字二元组，无序窗口只在前 1000 篇内算
  tc3r       tc3 + 全局近因
  chunk3     基线：tc3 的块级 BM25+×SDM 单路
  turn3      基线：tc3 的整轮 BM25+×SDM 单路
  turn_okapi 基线：整轮 Okapi BM25（k1 1.2，b .75，词项同 tc3），带词频
  AGM 泛化消融：agm1＝v1.1 的 AGM 单路（字二元组 BM25 种子扩散），agm3＝tc3 的 AGM 单路
  （BM25+×SDM 种子扩散），tc3_noagm、v11_noagm＝各自去掉 AGM 一路
  开发集看过之后加的候选：tc3a2＝tc3 中 AGM 一路权重加倍，tc3ca＝只融合块级 SDM 与 AGM
"""
import argparse
import collections
import hashlib
import json
import math
import multiprocessing as mp
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import tricue as T  # noqa: E402

ROOT = HERE.parents[4]
DATA = ROOT / "data_gen"
ARMS = ("v11", "tc2", "tc3", "tc3r", "chunk3", "turn3", "turn_okapi", "agm1", "agm3", "tc3_noagm", "v11_noagm", "tc3a2", "tc3ca")
H3 = lambda s: int(hashlib.md5(s.encode()).hexdigest(), 16) % 3 == 0  # noqa: E731


class OkapiTurn:
    def __init__(self):
        self.tf, self.dl, self.inv = [], [], collections.defaultdict(list)

    def add(self, toks):
        c = collections.Counter(toks); d = len(self.dl)
        self.tf.append(c); self.dl.append(len(toks))
        for t in c:
            self.inv[t].append(d)

    def score(self, q):
        N = len(self.dl)
        if not N:
            return {}
        avg = sum(self.dl) / N or 1.0
        sc = collections.defaultdict(float)
        for t in set(q):
            post = self.inv.get(t)
            if not post:
                continue
            idf = math.log(1 + (N - len(post) + .5) / (len(post) + .5))
            for d in post:
                f = self.tf[d][t]
                sc[d] += idf * f * 2.2 / (f + 1.2 * (.25 + .75 * self.dl[d] / avg))
        return sc


class Mems:
    def __init__(self, s2=True):
        self.B = T.TriCueMemory()
        self.S2 = T.TriCueMemory(tokenizer="mixed", turn_cue=True, scorer="bm25p_sdm") if s2 else None
        self.S3 = T.TriCueMemory(tokenizer="mixed", turn_cue=True, scorer="bm25p_sdm", cjk="bigram", uw_top=1000)
        self.O = OkapiTurn()

    def add(self, role, text):
        for m in (self.B, self.S2, self.S3):
            if m is not None:
                m.add_turn(role, text)
        self.O.add(T.seq_tokens(text, "bigram"))

    def chunks(self, q):
        """各臂的块排序。"""
        out = {}
        B, S2, S3 = self.B, self.S2, self.S3
        sc = B.bm25(q)
        ag1 = B.rank_agm(sc)
        out["v11"] = T.rrf([B.rank_recent(), sorted(sc, key=lambda i: -sc[i]), ag1])
        out["v11_noagm"] = T.rrf([B.rank_recent(), sorted(sc, key=lambda i: -sc[i])])
        out["agm1"] = ag1
        if S2 is not None:
            sc = S2.bm25(q)
            out["tc2"] = T.rrf([sorted(sc, key=lambda i: -sc[i]), S2.rank_agm(sc), S2.rank_turn(q, sc), S2.rank_relrec(sc)])
        sc = S3.bm25(q)
        o = sorted(sc, key=lambda i: -sc[i])
        ways = [o, S3.rank_agm(sc), S3.rank_turn(q, sc), S3.rank_relrec(sc)]
        out["tc3"] = T.rrf(ways)
        out["tc3r"] = T.rrf([S3.rank_recent()] + ways)
        out["tc3_noagm"] = T.rrf([ways[0], ways[2], ways[3]])
        out["agm3"] = ways[1]
        out["tc3a2"] = T.rrf(ways + [ways[1]])
        out["tc3ca"] = T.rrf([ways[0], ways[1]])
        out["chunk3"] = o
        out["turn3"] = ways[2]
        ts = self.O.score(T.seq_tokens(q, "bigram"))
        out["turn_okapi"] = [i for t in sorted(ts, key=lambda t: -ts[t]) for i in S3.t_chunks[t]]
        return out

    def turn_of(self, arm):
        return (self.B if arm in ("v11", "v11_noagm", "agm1") else self.S2 if arm == "tc2" else self.S3).turn_of


def turns_from(mm, arm, chunks):
    tof, seen, out = mm.turn_of(arm), set(), []
    for i in chunks:
        if tof[i] not in seen:
            seen.add(tof[i]); out.append(tof[i])
    return out


# ---------- LongMemEval ----------
def lme_items(split):
    out = []
    for x in json.loads((DATA / "lme_s.json").read_text(encoding="utf-8")):
        if x["question_id"].endswith("_abs"):
            continue
        dev = int(hashlib.md5(x["question_id"].encode()).hexdigest(), 16) % 10 == 0
        if split == "all" or (split == "dev") == dev:
            out.append(x)
    return out


def lme_one(x):
    sess = sorted(zip(x["haystack_dates"], x["haystack_session_ids"], x["haystack_sessions"]), key=lambda z: z[0])
    mm, s_of, ans = Mems(), [], set()
    for _, sid, ss in sess:
        for t in ss:
            if t.get("has_answer"):
                ans.add(len(s_of))
            mm.add(t["role"], t["content"]); s_of.append(sid)
    gold, res = set(x["answer_session_ids"]), {}
    for a, ch in mm.chunks(x["question"]).items():
        to = turns_from(mm, a, ch)
        so, seen = [], set()
        for t in to:
            if s_of[t] not in seen:
                seen.add(s_of[t]); so.append(s_of[t])
        res[a] = {"s@5": bool(gold & set(so[:5])), "s@10": bool(gold & set(so[:10])),
                  "t@10": bool(ans & set(to[:10])) if ans else None}
    return {"type": x["question_type"], "res": res}


# ---------- LoCoMo ----------
def locomo_items(split):
    out = []
    for c in json.loads((DATA / "locomo10.json").read_text(encoding="utf-8")):
        if split != "all" and (split == "dev") != H3(c["sample_id"]):
            continue
        conv = c["conversation"]
        n = sorted(int(k.split("_")[1]) for k in conv if k.startswith("session_") and not k.endswith("date_time"))
        turns, ids = [], []
        for i in n:
            for t in conv[f"session_{i}"]:
                txt = f"{t['speaker']}: {t['text']}"
                if t.get("blip_caption"):
                    txt += f" [image: {t['blip_caption']}]"
                turns.append(txt); ids.append(t["dia_id"])
        out.append({"turns": turns, "ids": ids, "qa": [q for q in c["qa"] if q.get("category") != 5]})
    return out


def locomo_one(c):
    mm = Mems()
    for t in c["turns"]:
        mm.add("user", t)
    idx = {d: i for i, d in enumerate(c["ids"])}
    rows = []
    for q in c["qa"]:
        ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
        if not ev:
            continue
        res = {}
        for a, ch in mm.chunks(q["question"]).items():
            to = turns_from(mm, a, ch)
            res[a] = {f"r@{k}": len(ev & set(to[:k])) / len(ev) for k in (5, 10, 25)}
        rows.append({"cat": q["category"], "res": res})
    return rows


# ---------- hive ----------
def hive_files(split):
    fs = sorted((ROOT / "hive-memory-bench" / "e2e" / "corpus").glob("*.md"))
    return [f for f in fs if split == "all" or (split == "dev") == H3(f.name)]


def cards_run(split):
    from hive_e2e_stream import parse
    root = ROOT / "hive-memory-bench" / "e2e"
    cards = [c for c in json.loads((root / "questions/题卡_C型_续接预测_v0.1.json").read_text(encoding="utf-8"))
             if split == "all" or (split == "dev") == H3(c["file"])]
    mm, where = Mems(s2=False), {}                   # tc2 的续接卡读数已在 v2 留出集包里，这里省内存
    for f in hive_files("all"):                     # 库始终是全部 16 个文件（同 #3 口径），只切题
        for t in parse(f):
            g = mm.O.dl.__len__()
            mm.add(t["who"], t["text"])
            for ln, _ in t["lines"]:
                where[(f.name, ln)] = g
    rows = []
    for c in cards:
        g = where.get((c["file"], c["answer"]["human"]["line"]))
        if g is None:
            continue
        res = {}
        for a, ch in mm.chunks("\n".join(p["text"] for p in c["pre"])).items():
            to = turns_from(mm, a, ch)
            pos = to.index(g) + 1 if g in to else None
            res[a] = {"h@10": bool(pos and pos <= 10), "h@50": bool(pos and pos <= 50), "rr": 1 / pos if pos else 0.0}
        rows.append({"res": res})
    return rows


def stream_one(path, shard=0, nshard=1):
    from hive_e2e_stream import bset, chunk_turn, parse
    path = pathlib.Path(path)
    turns = parse(path)
    allc = [c for t in turns for c in chunk_turn(t)]
    dfc = collections.Counter(g for _, x in allc for g in bset(x))
    capf = max(2, int(0.02 * len(allc)))
    mm, budget = Mems(), 4000
    s = {a: [0.0, 0.0] for a in ARMS}; n = qi = 0
    for ti, t in enumerate(turns):
        tgt = None
        if t["who"] == "human" and ti + 1 < len(turns) and turns[ti + 1]["who"] == "ai" and mm.B.N:
            tgt = {g for g in bset(turns[ti + 1]["text"]) if dfc.get(g, 0) <= capf} - bset(t["text"])
            if tgt:
                qi += 1
                if (qi - 1) % nshard != shard:  # 分片：所有轮照常写入，只评本片的查询
                    tgt = None
                else:
                    n += 1
            if tgt:
                rec, used = set(), 0
                for i in mm.B.rank_recent():
                    if used + mm.B.size[i] > budget and used:
                        break
                    rec |= bset(mm.B.raw[i]); used += mm.B.size[i]
                for a, ch in mm.chunks(t["text"]).items():
                    mem = mm.B if a in ("v11", "v11_noagm", "agm1") else mm.S2 if a == "tc2" else mm.S3
                    cx, used = set(), 0
                    for i in ch:
                        if used + mem.size[i] > budget and used:
                            break
                        cx |= bset(mem.raw[i]); used += mem.size[i]
                    s[a][0] += len(tgt & cx) / len(tgt); s[a][1] += len((tgt & cx) - rec) / len(tgt)
        mm.add(t["who"], t["text"])
    return {"file": path.name, "n": n, "s": s}


def agg(rows, keys):
    out = {}
    for a in [a for a in ARMS if rows and a in rows[0]["res"]]:
        out[a] = {}
        for k in keys:
            v = [r["res"][a][k] for r in rows if r["res"][a][k] is not None]
            out[a][k] = round(sum(v) / len(v), 4) if v else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, choices=("lme", "locomo", "cards", "stream"))
    ap.add_argument("--split", default="dev", choices=("dev", "test", "all"))
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--json")
    a = ap.parse_args()
    t0 = time.time()
    if a.data == "lme":
        with mp.Pool(a.procs) as p:
            rows = p.map(lme_one, lme_items(a.split), chunksize=1)
        res = {"n": len(rows), "总": agg(rows, ("s@5", "s@10", "t@10")),
               "按题型": {ty: agg([r for r in rows if r["type"] == ty], ("s@5",)) for ty in sorted({r["type"] for r in rows})}}
    elif a.data == "locomo":
        with mp.Pool(a.procs) as p:
            rows = [r for rs in p.map(locomo_one, locomo_items(a.split), chunksize=1) for r in rs]
        res = {"n": len(rows), "总": agg(rows, ("r@5", "r@10", "r@25"))}
    elif a.data == "cards":
        rows = cards_run(a.split)
        res = {"n": len(rows), "总": agg(rows, ("h@10", "h@50", "rr"))}
    else:
        with mp.Pool(a.procs) as p:
            per = p.map(stream_one, [str(f) for f in hive_files(a.split)], chunksize=1)
        N = sum(x["n"] for x in per)
        res = {"n": N, "文件": len(per), "总": {}}
        for arm in ARMS:
            wo = [x["s"][arm][1] / x["n"] for x in per]; wb = [x["s"]["v11"][1] / x["n"] for x in per]
            res["总"][arm] = {"覆盖": round(sum(x["s"][arm][0] for x in per) / N, 4),
                             "窗口外": round(sum(x["s"][arm][1] for x in per) / N, 4),
                             "窗口外逐文件胜负(对v11)": f"{sum(p > q + 1e-12 for p, q in zip(wo, wb))}/{sum(p < q - 1e-12 for p, q in zip(wo, wb))}"}
    res.update({"data": a.data, "split": a.split, "秒": round(time.time() - t0, 1)})
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
