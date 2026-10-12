# -*- coding: utf-8 -*-
"""跨命名空间同名实体（X1）：把某几份文档整份复制成「镜像文档」（段首括注换成新命名空间名，正文不变），
于是同一批实体名同时出现在两个命名空间里。每道原题生成 4 个变体：
  orig_ns   「在<原命名空间>里，」+ 原题      金标＝原文档的段
  mir_ns    「在<镜像命名空间>里，」+ 原题    金标＝镜像文档的同序号段
  orig_none / mir_none  原题不变（没有任何消歧线索，两份历史逐字相同 → 本就不可判，只看是否偏向某一份）
镜像名故意包含难点：dev 的「青石镇外传」包含原名「青石镇」；A 类实体名「猎户项目」与原命名空间同名。
指标＝零 LLM 代理（chain_metrics，按文档前缀判段归属）＋ wrong_ns_first（前 6 名里第一个属于两份之一的段来自错误那份）。
  python xns.py <dev|test> [tag]   → out/xns_<split>[_tag].json"""
import json, os, re, subprocess, sys, tempfile
from cb_common import *  # noqa
from lingshu_ng.chain.extract import extract  # noqa: E402   先占住本 worktree 的 lingshu_ng
from paired import sign  # noqa: E402
sys.path[1:1] = [TIT]
import chain_metrics as CM  # noqa: E402

MIRROR = {"dev": {"猎户项目": "猎户二期", "青石镇": "青石镇外传"},
          "test": {"流明项目": "流明二期", "织女项目": "织女二期", "雾港": "雾港旧事", "孤山驿": "孤山驿续"}}
_HEAD = re.compile(r"^(第 \d+ (?:次提交|章))（([^）]+)）")


SPL = re.compile(r"(?<=[。])")


def value_rotation(C, mp):
    """镜像文档的取值换成「同一链里按出现顺序的下一个值」（循环置换）：结构/序号不变、历史不同（否则逐字相同会被 ng 去重合并）。"""
    seen = {}
    for c in C:
        if c["doc"] not in mp:
            continue
        for s in SPL.split(c["text"]):
            for e in extract(s):
                if e.op in ("set", "unresolve", "resolve"):
                    for v in (e.value, e.alt):
                        if v:
                            lst = seen.setdefault((c["doc"], e.entity, e.attr), [])
                            if v not in lst:
                                lst.append(v)
    return {k: {v: lst[(i + 1) % len(lst)] for i, v in enumerate(lst)} for k, lst in seen.items() if len(lst) > 1}


def filler_pool(C, mp):
    """各文档的「无事件、无实体提及」句（铺垫/细节/收尾句），镜像段用它重抽，免得两份只差几个字而被 ng 近重复合并。"""
    pool = {}
    for c in C:
        if c["doc"] in mp:
            for k, s in enumerate(SPL.split(c["text"])):
                if k and s and not extract(s) and "改名为" not in s:
                    pool.setdefault(c["doc"], set()).add(s)
    return {d: sorted(v) for d, v in pool.items()}


def mirror_text(text, doc, rot, pool, cid):
    import hashlib
    sents = SPL.split(text)
    for i, s in enumerate(sents):
        ev = [e for e in extract(s) if e.op in ("set", "unresolve", "resolve")]
        if i and s and s in pool.get(doc, ()) :
            h = int(hashlib.md5(f"{cid}|{i}".encode()).hexdigest()[:8], 16)
            sents[i] = pool[doc][h % len(pool[doc])]
            continue
        if not ev:
            continue
        e = ev[0]; mp = rot.get((doc, e.entity, e.attr))
        if not mp:
            continue
        core, sep, tail = s.partition("，起因是")
        for v in sorted({x for x in (e.value, e.alt) if x}, key=len, reverse=True):
            j = core.rfind(v)
            if j >= 0:
                core = core[:j] + mp.get(v, v) + core[j + len(v):]
        sents[i] = core + sep + tail
    return "".join(sents)


def build(sp):
    mp = MIRROR[sp]
    C = corpus()
    rot = value_rotation(C, mp); pool = filler_pool(C, mp)
    #: 成对文档每段末尾各加一句「此段属<命名空间>。」（对称）：无事件的段两份才不会逐字相同而被 ng 去重合并
    out = [dict(c, text=c["text"] + f"此段属{c['doc']}。") if c["doc"] in mp else c for c in C]
    for c in C:
        if c["doc"] in mp:
            m = mp[c["doc"]]
            t = _HEAD.sub(lambda g: f"{g.group(1)}（{m}）", c["text"], count=1)
            assert t != c["text"]
            out.append(dict(c, cid=f"{m}#{c['seq']}", doc=m, text=mirror_text(t, c["doc"], rot, pool, c["cid"]) + f"此段属{m}。"))
    keys = []
    for q in keys_main():
        if q["doc"] not in mp:
            continue
        m = mp[q["doc"]]
        for var, doc, pre in (("orig_ns", q["doc"], f"在{q['doc']}里，"), ("mir_ns", m, f"在{m}里，"),
                              ("orig_none", q["doc"], ""), ("mir_none", m, "")):
            keys.append(dict(q, qid=f"{q['qid']}~{var}", doc=doc, question=pre + q["question"], var=var, pair=q["doc"] + "|" + m))
    return out, keys


def cidx_ext(sp):
    idx = CM.chain_index()
    for (doc, s, slot), c in list(idx.items()):
        if doc in MIRROR[sp]:
            idx[(MIRROR[sp][doc], s, slot)] = dict(c, doc=MIRROR[sp][doc])
    return idx


def run(chain, C, keys):
    jd = tempfile.mkdtemp(prefix="cbx_", dir="/tmp"); cf, kf, of = (os.path.join(jd, f) for f in ("c.json", "k.json", "o.json"))
    json.dump(C, open(cf, "w", encoding="utf-8"), ensure_ascii=False); json.dump(keys, open(kf, "w", encoding="utf-8"), ensure_ascii=False)
    env = dict(os.environ, PYTHONPATH=os.environ.get("XNS_WT") or WT, PYTHONHASHSEED="0", CB_CORPUS=cf, CB_KEYS=kf)
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "ng_worker.py"), "1" if chain else "0", of, "6", "60"],
                       env=env, cwd="/tmp", capture_output=True, text=True, timeout=110)
    if r.returncode:
        print(r.stderr[-2000:])
    return load(of)


def wrong_first(R, keys):
    rows = {}
    for q in keys:
        a, b = q["pair"].split("|"); other = b if q["doc"] == a else a
        top = [c.split("#")[0] for c in R["ranked"].get(q["qid"], [])[:6]]
        first = next((d for d in top if d in (a, b)), None)
        rows[q["qid"]] = float(first == other)
    return rows


if __name__ == "__main__":
    sp = sys.argv[1]; tag = sys.argv[2] if len(sys.argv) > 2 else ""
    C, keys = build(sp); cidx = cidx_ext(sp); res, pq = {}, {}
    for arm, ch in (("ng", False), ("ngchain", True)):
        R = run(ch, C, keys)
        R = dict(R, ranked={q: v[:CHAIN_K] for q, v in R["ranked"].items()})
        per = CM.perq(R, keys, cidx); wf = wrong_first(R, keys)
        for q in keys:
            per[q["qid"]]["wrong_ns_first"] = wf[q["qid"]]
        pq[arm] = per
        for var in ("orig_ns", "mir_ns", "orig_none", "mir_none"):
            sel = {q["qid"]: per[q["qid"]] for q in keys if q["var"] == var}
            a = CM.agg(sel)
            res.setdefault(arm, {})[var] = {k: a[k] for k in ("gold6_all", "gold_first_现值", "stale_first_现值", "chain_full")}
            res[arm][var]["wrong_ns_first"] = round(sum(r["wrong_ns_first"] for r in sel.values()) / len(sel), 4)
    paired = {}
    for var in ("orig_ns", "mir_ns", "orig_none", "mir_none"):
        for f in ("gold6", "gold_first", "chain_full", "wrong_ns_first"):
            qs = [q["qid"] for q in keys if q["var"] == var and f in pq["ng"][q["qid"]] and f in pq["ngchain"][q["qid"]]]
            paired[f"{var}.{f}"] = sign([pq["ngchain"][q][f] for q in qs], [pq["ng"][q][f] for q in qs])
    dump(os.path.join(OUT, f"xns_{sp}{('_' + tag) if tag else ''}.json"), {"split": sp, "mirror": MIRROR[sp], "n_keys": len(keys), "metrics": res, "paired": paired}, indent=1)
    for arm in res:
        for var, v in res[arm].items():
            print(sp, arm, var, v)
    for k, v in paired.items():
        print(k, v)
