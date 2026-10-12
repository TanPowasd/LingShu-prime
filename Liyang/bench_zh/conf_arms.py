# -*- coding: utf-8 -*-
"""队友「汇流多维 v3×3」三个对照臂（TanPowasd/agm/confluence @182b134，只 import / runpy 调用，不复制、不修改）：
  md_heur  多维v3×3（启发式源图）：runpy 执行 confluence/hive_md.py（它是脚本，无可 import 的函数）取其全局 mds["多维v3×3"]；
           执行期间屏蔽 pathlib.Path.write_text，不覆盖其 results/；同时把它自算的 out 与发布的 hive_md_zerokey.json 逐项对照（校验）。
  md_llm   多维v3×3（LLM 源图）：hive_mdllm.build(root)（读 cache_hive/，不调 LLM）→ g.rank。只有 hive 语料有源图缓存，T2 语料不可用。
  tricue   TriCue v3：g.base.v3_turns（与 hive_md / hive_lingshu 相同取法）。
T2（evalsuite_hmb 178 块）语料上：用 hive_md 的 HiveMD 类与同一源图构造口径（每块 AGM 显著二元组按出现顺序相邻连「共现」边）
在 T2 块上实例化——这几行胶水与 hive_md.py 第 14–19 行同构，为口径一致而写（如实声明）。
  python conf_arms.py <arm> <hive|hmb> <tcards|t1h|hq> <out.json>"""
import json, os, pathlib, runpy, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
CONF = pathlib.Path("/workspace/work/ls/prime-test/prime/TanPowasd/agm/confluence")
sys.path[:0] = [str(CONF), str(CONF.parent / "bench")]
import zh_eval as Z  # noqa: E402
HR = Z.HR


def questions(qset):
    d = Z.data()
    if qset == "tcards":
        return [(c["qid"], c["question"]) for c in d["tcards"]]
    if qset in ("t1h", "t1h2"):
        Z.set_t1h("2" if qset == "t1h2" else "")
        return [(c["qid"], c["question"]) for c in Z.t1h()["cards"]]
    return [(q["qid"], q["q"]) for q in d["hq"]]


def heur_glue():
    orig = pathlib.Path.write_text
    pathlib.Path.write_text = lambda self, *a, **k: None
    argv = sys.argv
    sys.argv = ["hive_md.py", str(Z.ROOT)]
    try:
        G = runpy.run_path(str(CONF / "hive_md.py"), run_name="hive_md_glue")
    finally:
        pathlib.Path.write_text = orig
        sys.argv = argv
    pub = json.load(open(CONF / "results" / "hive_md_zerokey.json", encoding="utf-8"))
    G["_check"] = {"identical_to_published": G["out"] == pub,
                   "diff_keys": [f"{b}/{k}" for b in pub for k in pub[b] if G["out"].get(b, {}).get(k) != pub[b][k]]}
    return G


def md_on_chunks(G, items):
    """在任意语料（[(cid, text)]）上按 hive_md.py 第 14–19 行同构口径实例化 HiveMD（启发式源图：每块 AGM 显著二元组按出现顺序相邻连「共现」边）。
    T2（evalsuite_hmb）与 T2R（PREREG_ZH 修订 4）共用。返回 HiveMD 对象：.rank = 多维v3×3（启发），.base.v3_turns = TriCue v3。"""
    hc = [{"cid": cid, "text": t, "i": i, "n": HR.norm(t)} for i, (cid, t) in enumerate(items)]
    bm = HR.BM25(hc); agm = HR.AGM(hc, bm)
    tri = []
    for c, T in zip(hc, agm.T):
        pos = sorted((c["n"].find(t), t) for t in T)
        tri.append([[a, "共现", b] for (_, a), (_, b) in zip(pos, pos[1:])])
    return G["HiveMD"]([c["text"] for c in hc], [f"{c['cid']}:{c['i']}" for c in hc], tri, w_v3=3.0)


def main():
    arm, corpus, qset, outp = sys.argv[1:5]
    qs = questions(qset)
    meta = {}
    if arm == "md_llm":
        assert corpus == "hive", "LLM 源图只覆盖 hive 303 块"
        import hive_mdllm
        chunks, g, cov = hive_mdllm.build(Z.ROOT)
        meta["llm_cover"] = cov
        fn = g.rank
    else:
        G = heur_glue()
        meta["check_hive_md"] = G["_check"]
        if corpus == "hive":
            g = G["mds"]["多维v3×3"]
        else:
            g = md_on_chunks(G, [(c["cid"], c["text"]) for c in Z.data()["hc"]])
        fn = g.rank if arm == "md_heur" else g.base.v3_turns
    rank = {qid: list(fn(q)) for qid, q in qs}
    json.dump({"arm": arm, "corpus": corpus, "qset": qset, "meta": meta, "rank": rank}, open(outp, "w", encoding="utf-8"), ensure_ascii=False)
    print(arm, corpus, qset, json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
