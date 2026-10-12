# -*- coding: utf-8 -*-
"""稳健性：把一部分事件句改写成**抽取器句式表之外**的说法（同义改写，值/主体/序号不变），看 ng+chain 是否「抽不到就退回 ng」，
以及「部分抽到」时会不会因为把旧版本当成当前版本而比 ng 更差。读数用零 LLM 检索代理（与读者无关）。
  python perturb.py <frac> <split> [cap] [soft|hard]   hard＝主体挪到属性后、句首换话题标记（连「提及」都认不出）   frac∈[0,1]：改写的事件句比例（按 md5(cid,句号) 确定性抽样）；cap＝非变更问前置编排段上限（0＝不限＝v1；缺省 3＝v2 默认）
改写表（全部不在 extract._SET_VERBS / 撤销 / 并存 句式内）：
  首次确立为→最早定成了  调整为→改成了  转为→成了  移到了→去了  此后确立为→后来定成了
  被撤销，此后不再保留取值→作罢了，此后不再保留取值  出现两种并存的取值：→有两种说法：  的争议就此裁定为→最后拍板为"""
import hashlib, json, os, re, subprocess, sys, tempfile
from cb_common import *  # noqa
sys.path.insert(0, TIT)
import chain_metrics as CM  # noqa: E402

REW = [("首次确立为", "最早定成了"), ("此后确立为", "后来定成了"), ("调整为", "改成了"), ("转为", "成了"), (" 移到了 ", " 去了 "),
       ("被撤销，此后不再保留取值", "作罢了，此后不再保留取值"), ("出现两种并存的取值：", "有两种说法："), ("的争议就此裁定为", "最后拍板为")]
SPLIT = re.compile(r"(?<=[。])")


_HARD = re.compile(r"^(?P<s>[^\s，。]+?)\s*的(?P<a>[^\s，。的]+?)(?P<v>首次确立为|此后确立为|调整为|转为|被撤销|出现两种并存的取值：|的争议就此裁定为)")
_HARD_MOVE = re.compile(r"^(?P<s>[^\s，。]+?) 移到了 ")


def hard(s):
    """难改写：主体挪到属性之后、句首换成话题标记（既不在句式表，也不是「<实体> 的<属性>」开头的提及）。"""
    m = _HARD.match(s)
    if m:
        return f"说到{m.group('a')}，{m.group('s')} 这回" + s[m.end('v'):].replace("，此后不再保留取值", "作废了") if m.group("v") == "被撤销" \
            else f"说到{m.group('a')}，{m.group('s')} 这回定为" + s[m.end('v'):]
    m = _HARD_MOVE.match(s)
    if m:
        return f"说到位置，{m.group('s')} 这回去了 " + s[m.end():]
    return None


def perturb_corpus(frac, mode="soft", salt=""):
    out, n_ev, n_rw = [], 0, 0
    for c in corpus():
        sents = SPLIT.split(c["text"])
        for i, s in enumerate(sents):
            hit = next(((a, b) for a, b in REW if a in s), None)
            if hit is None:
                continue
            n_ev += 1
            h = int(hashlib.md5(f"{salt}{c['cid']}|{i}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
            if h < frac:
                if mode == "hard":
                    t = hard(s)
                    if t is None:
                        continue
                    sents[i] = t
                else:
                    sents[i] = s.replace(hit[0], hit[1], 1)
                n_rw += 1
        out.append(dict(c, text="".join(sents)))
    return out, n_ev, n_rw


def run(arm_chain, C, cap):
    jd = tempfile.mkdtemp(prefix="cbp_", dir="/tmp"); cf = os.path.join(jd, "corpus.json"); of = os.path.join(jd, "out.json")
    json.dump(C, open(cf, "w", encoding="utf-8"), ensure_ascii=False)
    env = dict(os.environ, PYTHONPATH=WT, PYTHONHASHSEED="0", CB_CORPUS=cf, CB_CAP=str(cap))
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "ng_worker.py"), "1" if arm_chain else "0", of, "6", "60"],
                       env=env, cwd="/tmp", capture_output=True, text=True, timeout=300)
    if r.returncode:
        print(r.stderr[-2000:])
    return load(of)


if __name__ == "__main__":
    frac, sp = float(sys.argv[1]), sys.argv[2]
    cap = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    mode = sys.argv[4] if len(sys.argv) > 4 else "soft"
    salt = sys.argv[5] if len(sys.argv) > 5 else ""
    C, n_ev, n_rw = perturb_corpus(frac, mode, salt)
    K = keys_main(); ks = split(K, sp); cidx = CM.chain_index()
    res, pq = {}, {}
    for tag, ch in (("ng", False), ("ngchain", True)):
        R = run(ch, C, cap)
        per = CM.perq(R, K, cidx); pq[tag] = per
        res[tag] = CM.agg({q["qid"]: per[q["qid"]] for q in ks})
    wl = {}
    for f in ("gold6", "gold_first", "chain_full"):
        qs = [q["qid"] for q in ks if f in pq["ng"][q["qid"]] and f in pq["ngchain"][q["qid"]]]
        wl[f] = {"胜": sum(pq["ngchain"][q][f] > pq["ng"][q][f] for q in qs), "负": sum(pq["ngchain"][q][f] < pq["ng"][q][f] for q in qs), "n": len(qs)}
    show = ("gold6_all", "gold6_现值", "gold_first_现值", "stale_first_现值", "future_first_历史时点", "chain_cov", "chain_full")
    row = {"frac": frac, "split": sp, "cap": cap, "mode": mode, "salt": salt, "event_sents": n_ev, "rewritten": n_rw, **{t: {k: res[t][k] for k in show} for t in res}, "ngchain_vs_ng": wl}
    PO = os.environ.get("PERTURB_OUT") or os.path.join(OUT, "perturb.json")
    prev = load(PO, [])
    prev = [p for p in prev if not (p["frac"] == frac and p["split"] == sp and p.get("cap", 0) == cap
                                    and p.get("mode", "soft") == mode and p.get("salt", "") == salt)] + [row]
    dump(PO, prev, indent=1)
    for t in res:
        print(f"{mode}{salt} frac={frac} cap={cap} {sp} {t:8s} rw={n_rw}/{n_ev} " + " ".join(f"{k}={res[t][k]}" for k in show))
    print("  ngchain vs ng 逐题:", wl)
