# -*- coding: utf-8 -*-
"""HMB 检索轨（零 LLM）读数 → out/hmb_r1.json（{snapshot: {metric: value}} + 参考上限）。

  python metrics_r1.py            # 需先跑 run_retrieval.py（novel/e2e 四方 + retire 三方）
"""
import json
import os
import statistics
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmb_lib as H  # noqa: E402

SN = ["base", "integrated", "ng", "ng_1a2bc2b", "ng_head", "bm25"]
W = H.WORK


def bigr(s):
    s = H.norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def build_proxies(cards, qtext):
    """代理清单（作者 9 对矛盾题与地基句清单未公开 ⇒ 从公开 cards 机械构造，报告中写明是代理）。"""
    pairs = []
    for qid, c in sorted(cards.items()):
        ev = H.card_evidence(c)
        if len({e["cid"] for e in ev}) < 2:
            continue
        qb = bigr(qtext[qid])
        sc = [(len(bigr(e["quote"]) & qb) / max(1, len(bigr(e["quote"]))), e) for e in ev]
        a = max(sc, key=lambda x: x[0])
        others = [x for x in sc if x[1]["cid"] != a[1]["cid"]]
        b = min(others, key=lambda x: x[0])
        pairs.append({"qid": qid, "a": a[1]["quote"], "a_cid": a[1]["cid"], "a_overlap": round(a[0], 3),
                      "b": b[1]["quote"], "b_cid": b[1]["cid"], "b_overlap": round(b[0], 3)})
    hard = sorted(pairs, key=lambda p: (p["b_overlap"] - p["a_overlap"], p["qid"]))[:9]
    found, keyterms, seen = [], {}, set()
    for qid, c in sorted(cards.items()):
        pts = {p["id"]: p for p in H.card_points(c)}
        for e in H.card_evidence(c):
            if not e["required"] or e["quote"] in seen or len(H.norm(e["quote"])) < 8:
                continue
            seen.add(e["quote"])
            found.append({"text": e["quote"], "group": e["cid"][:3], "qid": qid})
            terms = []
            for sid in e["supports"]:
                for t in (pts.get(sid) or {}).get("any_of") or []:
                    t = str(t)
                    if not t.startswith("re:") and t in e["quote"] and t not in terms:
                        terms.append(t)
            if terms:
                keyterms[e["quote"]] = terms
    return {"pairs_all": pairs, "pairs_hard9": hard, "foundations": found, "keyterms": keyterms}


def run_tools(snap, R, prox, mat_dir):
    d = os.path.join(W, f"tool_{snap}")
    rd = os.path.join(d, "retrieval")
    os.makedirs(rd, exist_ok=True)
    for qid, v in R.items():
        if qid.endswith("i"):
            continue
        H.dump(os.path.join(rd, f"{qid}.json"), {"hits": [{"text": h["text"]} for h in v["hits"]]})
    fp, kp = os.path.join(d, "f.json"), os.path.join(d, "k.json")
    H.dump(fp, prox["foundations"])
    H.dump(kp, prox["keyterms"])
    oj = os.path.join(d, "triaxis.json")
    p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(H.HMB, "systems", "三轴诊断.py"), "--material",
                        mat_dir, "--retrieval", rd, "--foundations", fp, "--keyterms", kp, "--json", oj],
                       capture_output=True, text=True)
    tri = H.load(oj, {})
    tri["_stdout"] = p.stdout[-1500:]
    res = {}
    for name in ("pairs_all", "pairs_hard9"):
        pp = os.path.join(d, f"{name}.json")
        H.dump(pp, [{"qid": x["qid"], "a": x["a"], "b": x["b"]} for x in prox[name]])
        out = {}
        for n in (8, 20):
            q = subprocess.run([sys.executable, "-X", "utf8", os.path.join(H.HMB, "systems", "压缩代价.py"),
                                "--material", mat_dir, "--retrieval", rd, "--pairs", pp, "--n", str(n)],
                               capture_output=True, text=True)
            line = [l for l in q.stdout.splitlines() if l.startswith("① 两侧存活")]
            out[f"n{n}"] = line[0] if line else q.stdout[-400:] + q.stderr[-400:]
            rows = [l.split() for l in q.stdout.splitlines() if l[:1] in "oq" and len(l.split()) >= 3]
            out[f"n{n}_b_side"] = sum(1 for r in rows if r[2] == "✓")
            out[f"n{n}_both"] = sum(1 for r in rows if r[1] == "✓" and r[2] == "✓")
            out[f"n{n}_total"] = len(rows)
        res[name] = out
    return tri, res


def main():
    cards = H.load_cards()
    qtext = {q["qid"]: q["question"] for q in H.load_questions("main")}
    prox = build_proxies(cards, qtext)
    H.dump(os.path.join(H.OUT, "hmb_proxy_lists.json"),
           {"note": "代理清单：作者 9 条矛盾对/地基句清单未公开，此为从公开 cards/ 机械构造（见 metrics_r1.build_proxies）",
            **prox})
    mat_dir = os.path.join(H.HMB, "corpus")
    MAT = H.norm("".join(ch["text"] for ch in H.load_units()))
    MATG20 = H.grams(MAT, 20)
    chunks = {c["id"]: c for c in H.novel_chunks()}
    res, detail = {}, {}
    for snap in SN:
        D = H.load(os.path.join(W, f"retr_{snap}_novel.json"))
        if D is None:
            continue
        m = {}
        for path in ("recall", "search"):
            if snap == "bm25" and path == "search":
                continue
            R = D[path]
            cidr, cidfull, qr, pc, exc, nchars = [], [], [], [], [], []
            per_q = {}
            for qid, c in cards.items():
                hits = R.get(qid, {}).get("hits", [])
                got_cids = {chunks[h["chunk"]]["cid"] for h in hits if h.get("chunk") in chunks}
                need = {e["cid"] for e in H.card_evidence(c)}
                blob = "\n".join(h["text"] for h in hits)
                nb = H.norm(blob)
                ev = H.card_evidence(c)
                cr = len(need & got_cids) / max(1, len(need))
                qq = sum(1 for e in ev if H.norm(e["quote"]) and H.norm(e["quote"]) in nb) / max(1, len(ev))
                pts = H.card_points(c)
                pp = sum(1 for p in pts if H.point_hit(p, blob)) / max(1, len(pts))
                me = c.get("must_exclude") or []
                if me:
                    exc.append(sum(1 for e in me if H.norm(e["quote"]) in nb) / len(me))
                cidr.append(cr); cidfull.append(cr == 1.0); qr.append(qq); pc.append(pp); nchars.append(len(blob))
                per_q[qid] = {"cid": round(cr, 3), "quote": round(qq, 3), "point": round(pp, 3)}
            frags = [h["text"] for qid, v in R.items() if not qid.endswith("i") for h in v["hits"]]
            strict = sum(1 for t in frags if H.norm(t) and H.norm(t) in MAT)
            l1 = sum(1 for t in frags if H.grams(H.norm(t), 20) & MATG20)
            pre = "" if path == "recall" else "search."
            m.update({
                pre + "cid_recall": round(statistics.mean(cidr), 4),
                pre + "cid_full_rate": round(sum(cidfull) / len(cidfull), 4),
                pre + "quote_recall": round(statistics.mean(qr), 4),
                pre + "point_keyword_cov": round(statistics.mean(pc), 4),
                pre + "must_exclude_mix": round(statistics.mean(exc), 4) if exc else None,
                pre + "ctx_chars_mean": round(statistics.mean(nchars), 1),
                pre + "frag_verbatim_strict": round(strict / max(1, len(frags)), 4),
                pre + "frag_L1_20": round(l1 / max(1, len(frags)), 4),
                pre + "n_frags": len(frags),
            })
            if path == "recall":
                detail[snap] = per_q
                tri, comp = run_tools(snap, R, prox, mat_dir)
                m.update({"tri.L1": tri.get("L1_逐字率"), "tri.L2": tri.get("L2_逐字保地基"),
                          "tri.L2p": tri.get("L2p_关键词覆盖"), "tri.L2_frac": tri.get("L2"),
                          "pairs_all.b_side_n8": comp["pairs_all"]["n8_b_side"],
                          "pairs_all.both_n8": comp["pairs_all"]["n8_both"],
                          "pairs_all.total": comp["pairs_all"]["n8_total"],
                          "pairs_all.both_n20": comp["pairs_all"]["n20_both"],
                          "pairs_hard9.both_n8": comp["pairs_hard9"]["n8_both"],
                          "pairs_hard9.b_side_n8": comp["pairs_hard9"]["n8_b_side"],
                          "pairs_hard9.both_n20": comp["pairs_hard9"]["n20_both"]})
        st = D["store"]
        m["store_verbatim_strict"] = round(sum(1 for r in st if H.norm(r["text"]) in MAT) / max(1, len(st)), 4)
        m["store_records"] = len(st)
        m["store_merged"] = len(D["merged"])
        m["write_sec_novel"] = D["write_sec"]
        m["write_ms_per_chunk_novel"] = round(1000 * D["write_sec"] / max(1, D["n_chunks"]), 3)
        m["query_ms_median_novel"] = statistics.median(D["query_ms"]["recall"])
        res[snap] = m
    # ---- e2e (f)
    cardsE = {c["id"]: c for c in H.e2e_cards()}
    ech = H.e2e_chunks()
    eby = {c["id"]: c for c in ech}
    files = {os.path.basename(f): open(f, encoding="utf-8").read().split("\n") for f in H.e2e_files()}

    def nn(s):
        import re
        return re.sub(r"[^\w]", "", s or "")

    def cov(ans, mat, n=4):
        a = nn(ans)
        g = H.grams(a, n)
        if not g:
            return 0.0, False
        m = nn(mat)
        return sum(1 for x in g if x in m) / len(g), any(x in m for x in H.grams(a, 12))

    def e2e_scores(mats):
        c4, s12, ai4, sizes = [], [], [], []
        for cid, mat in mats.items():
            card = cardsE[cid]
            v, s = cov(card["answer"]["human"]["text"], mat)
            c4.append(v); s12.append(s); sizes.append(len(mat))
            ai4.append(cov((card["answer"].get("ai_opening") or {}).get("text", ""), mat)[0])
        return {"e2e.human_4gram_cov": round(statistics.mean(c4), 4),
                "e2e.human_strict12_rate": round(sum(s12) / len(s12), 4),
                "e2e.ai_open_4gram_cov": round(statistics.mean(ai4), 4),
                "e2e.material_chars_mean": round(statistics.mean(sizes), 1),
                "e2e.empty_material": sum(1 for x in sizes if x == 0)}
    for snap in SN:
        D = H.load(os.path.join(W, f"retr_{snap}_e2e.json"))
        if D is None:
            continue
        mats = {}
        for cid, card in cardsE.items():
            parts = H.e2e_material(card, [h["chunk"] for h in D["recall"][cid]["hits"]], eby)
            mats[cid] = "\n".join(p["text"] for p in parts)
        res.setdefault(snap, {}).update(e2e_scores(mats))
        res[snap]["write_sec_e2e"] = D["write_sec"]
        res[snap]["write_ms_per_chunk_e2e"] = round(1000 * D["write_sec"] / max(1, D["n_chunks"]), 3)
        res[snap]["query_ms_median_e2e"] = statistics.median(D["query_ms"]["recall"])
        res[snap]["e2e.store_merged"] = len(D["merged"])
    # O 参照：同文件答案行之前全部原文（无上限）
    omats = {cid: "\n".join(files[c["file"]][:c["answer"]["human"]["line"] - 1]) for cid, c in cardsE.items()}
    O = e2e_scores(omats)
    # ---- 退役
    for snap in ("base", "integrated", "ng", "ng_1a2bc2b", "ng_head"):
        R = H.load(os.path.join(W, f"retire_{snap}.json"))
        if R:
            res.setdefault(snap, {})
            res[snap]["retire.leak_base_path"] = f"{R['summary']['base']['leak']}/{R['summary']['base']['n']}"
            res[snap]["retire.leak_prod_path"] = f"{R['summary']['prod']['leak']}/{R['summary']['prod']['n']}"
            res[snap]["retire.archived_applied"] = f"{R['archived_ok']}/6"
    res.setdefault("bm25", {})["retire.leak_base_path"] = "N/A（无退役原语）"
    ref = {
        "cid_recall": {"bm25": res["bm25"].get("cid_recall"), "O_fullbook": 1.0},
        "quote_recall": {"bm25": res["bm25"].get("quote_recall"), "O_fullbook": 1.0},
        "point_keyword_cov": {"bm25": res["bm25"].get("point_keyword_cov"),
                              "O_fullbook": round(statistics.mean(
                                  sum(1 for p in H.card_points(c) if H.point_hit(p, "".join(ch["text"] for ch in H.load_units())))
                                  / max(1, len(H.card_points(c))) for c in cards.values()), 4)},
        "frag_verbatim_strict": {"bm25": res["bm25"].get("frag_verbatim_strict"), "author_BM25_OV": 1.0},
        "store_verbatim_strict": {"bm25": res["bm25"].get("store_verbatim_strict"), "author_BM25_OV": 1.0,
                                  "author_lingshu": 0.478},
        "tri.L1": {"bm25": res["bm25"].get("tri.L1"), "author_lingshu_v071": 100.0},
        "pairs_hard9.both_n8": {"bm25": res["bm25"].get("pairs_hard9.both_n8"), "max": 9,
                                "author_BM25_real9": 9, "author_lingshu_v071_real9": 2},
        "retire.leak_prod_path": {"ideal": "0/6", "author_lingshu_before_fix": "6/6", "author_MdCGOS_after_9d26266d": "0/6"},
        "write_sec_novel": {"author_lingshu_v071": "0.011–0.019 s（8/16 节点）", "author_OV": "76–165 s"},
        **{k: {"bm25": res["bm25"].get(k), "O_same_file_prefix": O[k]} for k in O},
    }
    meta = {"generated": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "hmb_commit": subprocess.run(["git", "-C", H.HMB, "rev-parse", "--short", "HEAD"], capture_output=True,
                                         text=True).stdout.strip(),
            "snapshots": {k: v["rev"] for k, v in H.SNAPS.items()}, "k": H.K,
            "novel_chunks": len(chunks), "e2e_chunks": len(ech),
            "primary_path": "recall（engine.recall）；search.* 为 store.search_content 基类路径",
            "proxies": "pairs_*/tri.L2* 用代理清单（out/hmb_proxy_lists.json），非作者未公开的 9 对/地基句"}
    H.dump(os.path.join(H.OUT, "hmb_r1.json"), {"meta": meta, "results": res, "reference": ref})
    H.dump(os.path.join(W, "r1_detail.json"), detail)
    print(json.dumps(res, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
