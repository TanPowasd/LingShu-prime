# -*- coding: utf-8 -*-
"""e2e C 型（续接预测）89 卡全量档：四方检索 + 闭卷 → 同一生成器作答 → 两判官盲混判分 → judge_audit。

  python e2e_track.py gen <arm>      # arm ∈ base integrated ng bm25 closed
  python e2e_track.py judge          # 全部答卷 + 48 锚，盲混交 J1/J2（thinking off、temperature 0）
  python e2e_track.py final          # 读数 + 锚自证 + 一致率 + 依据轴逐字回源
口径（复刻作者 docs/真实史端到端测评_初测_v1.0.md §一–§二）：
  · 1,611 块（10,000 字符行边界）；k=10；同文件 hit 跨答案行截断、整块在答案行之后剔除；材料上限 12,000 字符/卡；
  · 判据三档 strict/paraphrase/miss，加权 1/0.5/0；判官不看材料、不看臂名、不看 file/行号，给「断点前上下文」（卡 pre 原文）；
  · 锚 48：24 正（answer.human 原文当预测）＋12 跨卡负（他卡下文，8-gram 无交集）＋12 无关负；锚排除 C-116；seed 20261006。
差异（如实）：作者的判官提示词未公开，本件按其公开判据自写；作者为「同一判官两轮重放」，本件为「同模型（cline-pass/deepseek-v4.1-flash）两个独立实例」（温度/种子不同、题序各自打乱）——独立性弱于异模型。
"""
import json
import os
import random
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmb_lib as H  # noqa: E402
import llm  # noqa: E402

ARMS = H.arms()
ED = os.path.join(H.OUT, "_e2e")
CONTRACT = open(os.path.join(H.HMB, "e2e", "questions", "作答契约_C型_v0.1.md"), encoding="utf-8").read()

JUDGE_PROMPT = """你是「真实史端到端测评 · C 型续接预测」的判官。任务：判断被测系统对「人类在断点后的下一步」的预测，与真实下文是否一致。

你会看到：①断点前上下文（人类在断点前说过的话，原文逐条）；②真实下文（人类在断点后真正说的下一条）；③被测预测。
你看不到被测系统的材料与身份，也不需要。

判定（三选一）：
- strict：预测抓住了真实下文的核心行为/内容（他要做什么、问什么、说什么），措辞不同也能直接相认；
- paraphrase：方向一致、沾边，但细节或重点明显不同；
- miss：不一致、跑偏，或是放之四海皆准的空泛套话（如「他会继续提问」「他会表示认可」而无具体内容）。

纪律：只比较「预测」与「真实下文」；不要因为预测写得长、写得漂亮而加分；不确定时在 paraphrase 与 miss 之间取更保守的一档。
输出：只输出一个 JSON 对象，不要其他文字：{"verdict": "strict|paraphrase|miss", "why": "≤30字理由"}"""


def cards():
    return {c["id"]: c for c in H.e2e_cards()}


def gen(arm):
    C = cards()
    eby = {c["id"]: c for c in H.e2e_chunks()}
    R = None if arm == "closed" else H.load(os.path.join(H.WORK, f"retr_{arm}_e2e.json"))["recall"]
    od = os.path.join(ED, "ans", arm)
    os.makedirs(od, exist_ok=True)
    matlog = {}

    def one(cid):
        fp = os.path.join(od, f"{cid}.json")
        card = C[cid]
        parts = [] if R is None else H.e2e_material(card, [h["chunk"] for h in R[cid]["hits"]], eby)
        matlog[cid] = [{"file": p["file"], "start": p["start"], "end": p["end"], "chars": len(p["text"])} for p in parts]
        if os.path.exists(fp):
            return "skip"
        pre = "\n".join(f"- （{card['file']} L{p['line']}）{p['text']}" for p in card.get("pre") or [])
        if parts:
            mat = "\n\n".join(f"【材料块｜{p['file']}｜行 {p['start']}–{p['end']}】\n{p['text']}" for p in parts)
            cond = ("【作答条件（评测方说明）】下面的「材料」是某个记忆系统按断点检索出的语料块（已截到断点之前，"
                    "上限 12,000 字符）；basis 的 file/line/quote 请据材料块头的文件名与行号区间填写，quote 必须逐字复制。")
        else:
            mat = "（闭卷条件：不提供任何材料）" if arm == "closed" else "（检索结果经断点截断后为空）"
            cond = "【作答条件（评测方说明）】本次没有可用材料；basis 若无可引原文可给空列表。"
        msg = (CONTRACT + "\n\n" + cond + "\n\n## 材料\n\n" + mat + f"\n\n## 题卡\n\nqid: {cid}\n文件：{card['file']}\n"
               f"断点前·我说（材料终点前人类的最后发言）：\n{pre}\n\n问题：预测人类（「我」）在断点后的下一步——"
               "他接着要做什么／说什么。只输出一个 JSON 对象。")
        r = llm.call([{"role": "user", "content": msg}], max_tokens=16000, tag=f"gen_e2e:{arm}")
        if r.get("content") is None:
            return "api_err"  # 接口失败（重试 2 次后）不落答卷，重跑时补
        obj = llm.parse_json(r.get("content"))
        if not isinstance(obj, dict):
            obj = {"qid": cid, "prediction": r.get("content") or "", "basis": [], "_parse_error": r.get("error") or "not json"}
        obj["qid"] = cid
        H.dump(fp, obj)
        return "ok"
    res = llm.pmap(one, sorted(C))
    H.dump(os.path.join(ED, f"material_{arm}.json"), matlog)
    print(arm, Counter(res), "累计 $%.4f" % llm.total_cost())


def _no8(a, b):
    na, nb = re.sub(r"\s", "", a), re.sub(r"\s", "", b)
    return not (H.grams(na, 8) & H.grams(nb, 8))


def anchors():
    C = cards()
    ids = sorted(k for k in C if k != "C-116")
    rnd = random.Random(20261006)
    pos = rnd.sample(ids, 24)
    rest = [k for k in ids if k not in pos]
    rows = [(k, C[k]["answer"]["human"]["text"], "correct") for k in pos]
    for k in rest[:12]:
        donors = [d for d in ids if d != k and _no8(C[d]["answer"]["human"]["text"], C[k]["answer"]["human"]["text"])]
        d = donors[rnd.randrange(len(donors))]
        rows.append((k, C[d]["answer"]["human"]["text"], "incorrect"))
    unrel = ["今天中午吃什么比较好？我想点一份牛肉面。", "帮我查一下明天上海到杭州的高铁时刻表。", "我的打印机又卡纸了，怎么处理？",
             "推荐几本适合周末读的轻松小说吧。"]
    for i, k in enumerate(rest[12:24]):
        rows.append((k, unrel[i % 4], "incorrect"))
    return rows


def _judge_msg(card, pred):
    pre = "\n".join(f"- {p['text']}" for p in card.get("pre") or [])
    return (JUDGE_PROMPT + f"\n\n---\n\n## ①断点前上下文\n{pre}\n\n## ②真实下文（人类下一条）\n{card['answer']['human']['text']}"
            f"\n\n## ③被测预测\n{pred}")


def judge():
    C = cards()
    items = []
    for arm in ARMS:
        for cid in sorted(C):
            a = H.load(os.path.join(ED, "ans", arm, f"{cid}.json"))
            if a is not None:
                items.append((f"{arm}|{cid}", cid, str(a.get("prediction") or "")))
    for i, (k, text, exp) in enumerate(anchors()):
        items.append((f"anc{i:02d}|{k}|{exp}", k, text))
    per = []
    for i, j in enumerate(sorted(llm.JUDGES)):  # 两判官实例各自独立打乱题序
        lst = [(j, it) for it in items]
        random.Random(20261009 + 1000 * (i + 1)).shuffle(lst)
        per.append(lst)
    import itertools
    jobs = [x for pair in itertools.zip_longest(*per) for x in pair if x]
    outp = os.path.join(ED, "judge")
    os.makedirs(outp, exist_ok=True)

    def one(job):
        j, (key, cid, pred) = job
        fp = os.path.join(outp, f"{j}__{key.replace('|', '__')}.json")
        if os.path.exists(fp):
            return "skip"
        r = llm.call([{"role": "user", "content": _judge_msg(C[cid], pred)}], model=llm.JUDGES[j], max_tokens=800,
                     thinking=False, tag=f"judge_e2e:{j}", **llm.JUDGE_PARAMS[j])
        if r.get("content") is None:
            return "api_err"
        o = llm.parse_json(r.get("content")) or {}
        v = str(o.get("verdict", "")).strip().lower()
        H.dump(fp, {"verdict": v if v in ("strict", "paraphrase", "miss") else "parse_err", "why": o.get("why"),
                    "raw": (r.get("content") or "")[:300]})
        return "ok"
    print(Counter(llm.pmap(one, jobs)), "累计 $%.4f" % llm.total_cost())


W = {"strict": 1.0, "paraphrase": 0.5, "miss": 0.0, "parse_err": 0.0}
ORDER = {"strict": 2, "paraphrase": 1, "miss": 0, "parse_err": 0}


def final():
    C = cards()
    jd = os.path.join(ED, "judge")
    V = {j: {} for j in llm.JUDGES}
    for f in os.listdir(jd):
        j, rest = f[:-5].split("__", 1)
        V[j][rest] = H.load(os.path.join(jd, f))["verdict"]
    anc = anchors()
    sys.path.insert(0, H.HMB)
    import judge_audit as JA
    job = {"round": "HMB·e2e C 型（evalsuite_hmb r2）", "stratum": "机械构造锚 48（24正/12跨卡负/12无关负，seed 20261006）",
           "anchors": [{"qid": f"anc{i:02d}", "expected": e} for i, (_, _, e) in enumerate(anc)],
           "judges": {j: {f"anc{i:02d}": {"strict": "correct", "miss": "incorrect"}.get(V[j].get(f"anc{i:02d}__{k}__{e}"), "borderline")
                          for i, (k, _, e) in enumerate(anc)} for j in llm.JUDGES}}
    jp = os.path.join(ED, "audit_e2e_job.json")
    H.dump(jp, job)
    import subprocess
    p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(H.HMB, "judge_audit.py"), "check", jp, "--out",
                        os.path.join(ED, "audit_e2e_rec.json")], capture_output=True, text=True)
    out = {"audit_rc": p.returncode, "audit_stdout": p.stdout[-1500:], "arms": {}}
    xs, ys = [], []
    files = {}
    # 作者 31 卡子集口径：file ∈ {确认协议内容.md（25）, 用户与AI交换称呼.md（6）}（docs/真实史端到端测评_初测_v1.0.md:29-30）
    SUB31 = {cid for cid, c in C.items() if c["file"] in ("确认协议内容.md", "用户与AI交换称呼.md")}
    out["sub31_n"] = len(SUB31)
    for arm in ARMS:
        tab = {}
        for mode in ("J1", "J2", "lenient", "strict", "lenient31", "strict31", "J1_31"):
            cnt = Counter()
            base_mode = mode.replace("31", "").rstrip("_")
            for cid in sorted(C):
                if mode.endswith("31") and cid not in SUB31:
                    continue
                v1, v2 = V["J1"].get(f"{arm}__{cid}"), V["J2"].get(f"{arm}__{cid}")
                if base_mode in ("J1", "J2"):
                    v = V[base_mode].get(f"{arm}__{cid}")
                elif v1 is None or v2 is None:
                    v = None
                else:
                    v = max((v1, v2), key=ORDER.get) if base_mode == "lenient" else min((v1, v2), key=ORDER.get)
                if v is not None:
                    cnt[v] += 1
            n = sum(cnt.values())
            tab[mode] = {**cnt, "n": n, "weighted": round(sum(W[k] * c for k, c in cnt.items()) / max(1, n), 4)}
        for cid in sorted(C):
            v1, v2 = V["J1"].get(f"{arm}__{cid}"), V["J2"].get(f"{arm}__{cid}")
            if v1 and v2:
                xs.append(v1); ys.append(v2)
        # 依据轴：basis 引文逐字回源
        nb = loc = cards_with = 0
        nb31 = loc31 = cw31 = 0
        for cid in sorted(C):
            a = H.load(os.path.join(ED, "ans", arm, f"{cid}.json")) or {}
            bs = [b for b in (a.get("basis") or []) if isinstance(b, dict) and str(b.get("quote") or "").strip()]
            cards_with += bool(bs)
            cw31 += bool(bs) and cid in SUB31
            for b in bs:
                nb += 1
                nb31 += cid in SUB31
                fn = b.get("file") or C[cid]["file"]
                if fn not in files:
                    fpth = os.path.join(H.HMB, "e2e", "corpus", fn)
                    files[fn] = open(fpth, encoding="utf-8").read() if os.path.exists(fpth) else ""
                q = str(b["quote"]).strip()
                if q in files[fn] or any(q in t for t in [files.get(C[cid]["file"]) or ""]):
                    loc += 1
                    loc31 += cid in SUB31
        tab["basis"] = {"n": nb, "verbatim": loc, "rate": round(loc / max(1, nb), 4), "cards_with_basis": cards_with}
        tab["basis31"] = {"n": nb31, "verbatim": loc31, "rate": round(loc31 / max(1, nb31), 4), "cards_with_basis": cw31}
        mat = H.load(os.path.join(ED, f"material_{arm}.json"), {})
        tab["material_chars_mean"] = round(sum(sum(p["chars"] for p in v) for v in mat.values()) / max(1, len(mat)), 1)
        out["arms"][arm] = tab
    out["real_agreement"] = {"n": len(xs), "identical": round(sum(x == y for x, y in zip(xs, ys)) / max(1, len(xs)), 4),
                             "kappa": round(JA.cohen_kappa(xs, ys), 4)}
    H.dump(os.path.join(ED, "e2e_final.json"), out)
    print(out["audit_stdout"])
    print(json.dumps({a: {m: out["arms"][a][m] for m in ("J1", "J2", "lenient", "basis")} for a in ARMS},
                     ensure_ascii=False, indent=0)[:4000])
    print(out["real_agreement"])


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "gen":
        gen(sys.argv[2])
    elif c == "judge":
        judge()
    elif c == "final":
        final()
