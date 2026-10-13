# -*- coding: utf-8 -*-
"""R/D oracle 阶段 1 · 零 key 准备：建英文代理池 → 分层抽 100 题 → 三臂输入定稿。

口径（英文代理，与原中文 17.2% 不可直接比）：LoCoMo 英文原文 5882 turn 逐条
MdCGOS.add（与 <brain_e2e>/base_en.py 同法）；英文自然问句；cg.search(k=10,
judge=False, record=False)；排除 cat5。
环境：DSH_MEMORY_ROOT=<dsh-memory 仓根>，LOCOMO_JSON=<locomo10.json>，
POOL_ROOT（缺省 %TEMP%/pool_en）。
跑法：python -X utf8 prep.py
产出：sample.json（抽样与三臂输入，含逐题 gold/top10 id 与卡片文本）
"""
import hashlib, json, os, random, re, shutil, sys, tempfile, time

DSH = os.environ["DSH_MEMORY_ROOT"]
sys.path.insert(0, DSH)
from md_cg.mdcos import MdCGOS, est_tokens, DEFAULT_BUDGET, DEFAULT_MAX_ITEM_TOKENS  # noqa: E402

SEED = 20261014
N_TOTAL = 100
HERE = os.path.dirname(os.path.abspath(__file__))
POOL = os.environ.get("POOL_ROOT") or os.path.join(tempfile.gettempdir(), "pool_en")


def build(d):
    texts, order, ids = {}, {}, {}
    for si, c in enumerate(d):
        conv = c["conversation"]
        for k in conv:
            m = re.fullmatch(r"session_(\d+)", k)
            if not m:
                continue
            for ti, t in enumerate(conv[k]):
                nid = f"scene_{si}_session_{m.group(1)}_turn_{ti}"
                ids[(si, t["dia_id"])] = nid
                texts[nid] = f"{t['speaker']}: {t['text']}"
                order[nid] = (si, int(m.group(1)), ti)
    return texts, order, ids


def main():
    d = json.load(open(os.environ["LOCOMO_JSON"], encoding="utf-8"))
    texts, order, ids = build(d)
    fresh = not os.path.isfile(os.path.join(POOL, "_manifest.json"))
    if not fresh:
        fresh = json.load(open(os.path.join(POOL, "_manifest.json"))) != {"turns": len(texts)}
    t0 = time.time()
    if fresh:
        shutil.rmtree(POOL, ignore_errors=True)
        cg = MdCGOS(os.path.join(POOL, "mem"))
        for nid in texts:   # dict 插入序 = base_en.py 写入序
            cg.add(nid, texts[nid], layer="knowledge", verification_basis="data")
        json.dump({"turns": len(texts)}, open(os.path.join(POOL, "_manifest.json"), "w"))
    else:
        cg = MdCGOS(os.path.join(POOL, "mem"))
    print("turns", len(texts), "pool", "rebuilt" if fresh else "reused", round(time.time() - t0, 1), "s")

    # 题全集：排除 cat5、要求 gold 可映射（与 base_en.py 同判据）
    allq = []
    for si, c in enumerate(d):
        for qi, qa in enumerate(c["qa"]):
            if qa.get("category") == 5:
                continue
            gold = sorted({ids.get((si, e.strip())) for e in qa.get("evidence", [])} - {None},
                          key=lambda x: order[x])
            if not gold:
                continue
            allq.append({"qid": f"scene_{si}_q_{qi}", "conv": si, "cat": qa["category"],
                         "q": qa["question"], "gold_answer": str(qa.get("answer", "")),
                         "gold_ids": gold})
    print("全集", len(allq))
    # 分层抽样：按 category 比例分配（最大余数法），层内固定种子 random.sample
    by = {}
    for q in allq:
        by.setdefault(q["cat"], []).append(q)
    quota = {c: N_TOTAL * len(v) / len(allq) for c, v in by.items()}
    alloc = {c: int(x) for c, x in quota.items()}
    for c in sorted(quota, key=lambda c: -(quota[c] - alloc[c]))[:N_TOTAL - sum(alloc.values())]:
        alloc[c] += 1
    rng = random.Random(SEED)
    sample = []
    for c in sorted(by):
        sample += rng.sample(by[c], alloc[c])
    sample.sort(key=lambda q: (q["conv"], int(q["qid"].split("_q_")[1])))
    print("分配", dict(sorted(alloc.items())), "抽中", len(sample))

    nh, trunc_any = 0, 0
    for q in sample:
        r, _ = cg.search(q["q"], k=10, judge=False, record=False)
        got = [x[0]["id"] for x in r]
        q["top10_ids"] = got
        q["hit10"] = bool(set(got) & set(q["gold_ids"]))
        q["gold_cov10"] = len(set(got) & set(q["gold_ids"])) / len(q["gold_ids"])
        nh += q["hit10"]
        # 卡片格式与 bench_e2e_locomo_qa.py retrieval 臂逐字同形：「【i】原文」以 \n\n 连接
        q["cards_sys"] = "\n\n".join(f"【{i}】{texts[n]}" for i, n in enumerate(got, 1))
        q["cards_R"] = "\n\n".join(f"【{i}】{texts[n]}" for i, n in enumerate(q["gold_ids"], 1))
        # 生产查询交付面（mdcos.recall 装包）对同一节点列表会否截断/跳过：机械核
        used, cut = 0, 0
        for n in got:
            t = est_tokens(texts[n])
            if used + t > DEFAULT_BUDGET or t > DEFAULT_MAX_ITEM_TOKENS:
                cut += 1
            used += t
        q["recall_pack_tokens"] = used
        q["recall_pack_would_cut"] = cut
        trunc_any += bool(cut)
    print("样本 hit@10 %d/100；recall 装包（budget=%d,item=%d）会截断的题数 %d"
          % (nh, DEFAULT_BUDGET, DEFAULT_MAX_ITEM_TOKENS, trunc_any))
    sig = hashlib.sha256(json.dumps([q["qid"] for q in sample]).encode()).hexdigest()[:16]
    json.dump({"seed": SEED, "alloc": alloc, "n_pool": len(allq), "qid_sha": sig,
               "sample": sample}, open(os.path.join(HERE, "sample.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("qid_sha", sig)
    # 与既有零 key 基线 per_en.json 交叉核对（若给出）
    pe = os.environ.get("PER_EN_JSON")
    if pe and os.path.isfile(pe):
        base = {x["qid"]: x for x in json.load(open(pe))}
        same = sum(base[q["qid"]]["got"] == q["top10_ids"] for q in sample)
        print("与 per_en.json top10 逐位一致", same, "/ 100")


if __name__ == "__main__":
    main()
