# -*- coding: utf-8 -*-
"""r7 新轮级金标集：LoCoMo-Plus（Cognitive 类，401 条；xjtuleeyf/Locomo-Plus@059f4e3，arXiv:2602.10715，ACL 2026）。

构造 = 官方 data/unified_input.py 的拼接口径：第 i 条 cue/trigger 拼进 locomo10[i % 10]，
插入位置由官方 build_conv.build_context 按 time_gap 计算（只 import 官方脚本，不复制）。
- 记忆写入 docs = 拼接后的全部对话轮，去掉 trigger 轮本身（trigger 是查询）；
  W0（lmelp_*）= 原文（有图则追加 " [image: caption]"，同 gen_eval.prep 的 LoCoMo 口径）；
  W1（lmelps_*）= "speaker: 原文"。
- 查询 = trigger 轮原文（去 "A:"，不带说话人；两种写入口径用同一查询）。
- 金标（轮级）= cue 轮在 docs 中的下标；会话 = LoCoMo session_n → "S<n>"，cue 轮 → "CUE"。
- 切分：key = "lp%03d" % i；md5(key) % 10 ∈ {0,1,2} → dev，其余 → hold（保留集，冻结后只跑一次）。
  python v3/r7/mk_lp.py   → /tmp/gen_jobs/{lmelp,lmelps}_{dev,hold}.jsonl + meta_*.json；打印 sha1
"""
import hashlib, json, os, sys

LP = "/workspace/work/ls/_shared/locomo_plus"
LOCOMO = "/workspace/work/ls/prime-test/data/locomo10.json"
JOBS = "/tmp/gen_jobs"
LIMIT = 60
sys.path.insert(0, LP)
import build_conv as BC  # noqa: E402  官方脚本，只 import


def split(key):
    return "dev" if int(hashlib.md5(key.encode()).hexdigest(), 16) % 10 in (0, 1, 2) else "hold"


def main():
    plus = json.load(open(os.path.join(LP, "locomo_plus.json"), encoding="utf-8"))
    loc = json.load(open(LOCOMO, encoding="utf-8"))
    os.makedirs(JOBS, exist_ok=True)
    F = {(w, s): open(os.path.join(JOBS, f"{w}_{s}.jsonl"), "w", encoding="utf-8")
         for w in ("lmelp", "lmelps") for s in ("dev", "hold")}
    META = {s: {} for s in ("dev", "hold")}
    for i, p in enumerate(plus):
        key = f"lp{i:03d}"
        item = loc[i % len(loc)]
        conv = item["conversation"]
        ctx = BC.build_context(p, item)
        cue_ids = {id(t) for t in ctx["cue_turns"]}
        q_ids = {id(t) for t in ctx["query_turns"]}
        # 会话标记：按对象身份回查 LoCoMo 会话号
        sess_of = {}
        n = 1
        while f"session_{n}" in conv:
            for t in conv[f"session_{n}"]:
                sess_of[id(t)] = f"S{n}"
            n += 1
        w0, w1, s_of, ans = [], [], [], []
        for t in ctx["dialogue"]:
            if id(t) in q_ids:
                continue
            txt = (t.get("text") or "").strip()
            if not txt:
                continue
            if t.get("blip_caption"):
                txt += f" [image: {t['blip_caption']}]"
            if id(t) in cue_ids:
                ans.append(len(w0)); s_of.append("CUE")
            else:
                s_of.append(sess_of[id(t)])
            w0.append(txt); w1.append(f"{t['speaker']}: {txt}")
        q = " ".join(t["text"].strip() for t in ctx["query_turns"])
        assert ans and q, key
        s = split(key)
        for w, docs in (("lmelp", w0), ("lmelps", w1)):
            F[(w, s)].write(json.dumps({"key": key, "docs": docs, "queries": [{"qid": "q", "q": q, "limit": LIMIT}]},
                                       ensure_ascii=False) + "\n")
        META[s][key] = {"type": p["relation_type"], "s_of": s_of, "ans": ans, "ans_full": len(ans), "gold": ["CUE"],
                        "conv": item["sample_id"], "time_gap": p["time_gap"]}
    for f in F.values():
        f.close()
    for s, m in META.items():
        for w in ("lmelp", "lmelps"):
            with open(os.path.join(JOBS, f"meta_{w}_{s}.json"), "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False, indent=1)
    out = {}
    for w in ("lmelp", "lmelps"):
        for s in ("dev", "hold"):
            for fn in (f"{w}_{s}.jsonl", f"meta_{w}_{s}.json"):
                out[fn] = hashlib.sha1(open(os.path.join(JOBS, fn), "rb").read()).hexdigest()
    print(json.dumps({"n": {s: len(m) for s, m in META.items()}, "sha1": out}, indent=1))


if __name__ == "__main__":
    main()
