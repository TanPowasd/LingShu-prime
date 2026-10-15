# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""原型 hive_official.chat 与 dsh-memory md_cg/qmd_llm.chat 的请求体等价性抽检 + 少量带 key 实调。
零 key 段：桩掉 urlopen，对 hive 主轮 92 道作答 prompt（answer 角色，LLM_SYS=1 / MDCG_QMD_SYS=1）与判官请求（judge 角色）
          逐条比较两边发出的 messages 是否逐字相同；另比较题面扩展、源图抽取提示词与原型逐字相同。
带 key 段（--live N）：经 qmd_llm 实发 N 条作答 + N 条判官 + 1 批题面扩展，报告解析是否成功与和原型产物的一致度。
用法：PYTHONUTF8=1 LLM_SYS=1 LLM_SYS_GRAPH=0 python -X utf8 port_equiv_llm.py <bench> <real目录> --repo <dsh-memory 仓根> [--live 3] [--json out]"""
import argparse, io, json, os, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench")]
import hive_official as HO, hive_retrieval as HR, qx, hive_extract as HX  # noqa: E402


class Cap:
    def __init__(self): self.bodies = []

    def __call__(self, req, timeout=None):
        self.bodies.append(json.loads(req.data.decode("utf-8")))
        b = json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()

        class R(io.BytesIO):
            def __enter__(s): return s
            def __exit__(s, *a): return False
        return R(b)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("bench"); ap.add_argument("real"); ap.add_argument("--repo", required=True)
    ap.add_argument("--live", type=int, default=0); ap.add_argument("--json")
    a = ap.parse_args()
    sys.path.insert(0, a.repo)
    from md_cg import qmd_llm as L  # noqa: E402
    assert HO.SYS_ON, "须在 LLM_SYS=1 下跑（与重跑的 SYS 臂同口径）"
    os.environ["MDCG_QMD_SYS"] = "1"
    bench = pathlib.Path(a.bench)
    man = json.loads((bench / "sut" / "out_QMD_sys" / "_identity.json").read_text(encoding="utf-8"))
    qs = json.loads((bench / "questions" / "题目_主轮.json").read_text(encoding="utf-8"))
    ctx = HO.contexts(bench, "QMD", qs); head = HO.contract(bench)
    prompts = {q["qid"]: f"{head}\n\n======== 正文 ========\n{ctx[q['qid']]}\n\n======== 问题 ========\n{q['qid']}：{q['question']}" for q in qs}
    res = {"answer_prompt_sha_match_rerun": sum(HO.sha(p) == man["inputs"].get(k) for k, p in prompts.items()), "n_answer": len(prompts)}
    cap1, cap2 = Cap(), Cap()
    real_open = HO.urllib.request.urlopen
    HO.urllib.request.urlopen = cap1
    try:
        for p in prompts.values():
            HO.chat(p, HO.MODEL)
        jreq = sorted((bench / "semantic" / "req" / a.real).glob("*.md"))
        for f in jreq:
            HO.chat(f.read_text(encoding="utf-8"), HO.MODEL, system=False)
    finally:
        HO.urllib.request.urlopen = real_open
    cfg = {"base": "http://stub.invalid/v1", "model": HO.MODEL, "key": "GOV-IMPL-DUMMY-KEY"}
    for p in prompts.values():
        L.chat("answer", p, cfg=cfg, opener=cap2)
    for f in jreq:
        L.chat("judge", f.read_text(encoding="utf-8"), cfg=cfg, opener=cap2)
    same = [x["messages"] == y["messages"] and x["model"] == y["model"] and x["temperature"] == y["temperature"]
            for x, y in zip(cap1.bodies, cap2.bodies)]
    res.update({"n_judge": len(jreq), "request_messages_identical": sum(same), "requests": len(same),
                "judge_without_system": all(m["role"] != "system" for b in cap2.bodies[len(prompts):] for m in b["messages"]),
                "query_prompt_identical": L.Q_ZH == qx.P_ZH and L.Q_EN == qx.P_EN, "graph_prompt_identical_zh": L.G_ZH == HX.PROMPT})
    cards = HR.load_cards(bench)
    items = [(c["qid"], c["question"]) for c in cards[:10]]
    res["query_prompt_batch0_identical"] = L.query_prompt(items, "zh") == qx.P_ZH.format(qs="\n".join(f"[{i}] {q}" for i, q in items))
    if a.live:
        lcfg = {"base": "https://api.cline.bot/api/v1", "model": HO.MODEL, "key": "GOV-IMPL-DUMMY-KEY"}   # 网关侧注入真 key
        cnt = {}; live = {"answer": [], "judge": []}
        ans_dir = bench / "sut" / "out_QMD_sys"
        for qid in list(prompts)[: a.live]:
            obj = L.parse_json(L.call("answer", prompts[qid], cfg=lcfg, counter=cnt))
            old = json.loads((ans_dir / f"{qid}.json").read_text(encoding="utf-8"))
            live["answer"].append({"qid": qid, "parsed": isinstance(obj, dict), "keys_same": sorted(k for k in obj if k != "qid") == sorted(k for k in old if k != "qid")})
        out = bench / "semantic" / "out" / a.real
        for f in jreq[: a.live]:
            obj = L.parse_json(L.call("judge", f.read_text(encoding="utf-8"), cfg=lcfg, counter=cnt))
            old = json.loads((out / (f.stem + ".json")).read_text(encoding="utf-8"))
            live["judge"].append({"case": f.stem, "parsed": isinstance(obj, dict), "same_json": obj == old,
                                  "same_keys": sorted(obj) == sorted(old)})
        got, missing = L.extract_hints(items, "zh", batch=10, cfg=lcfg, counter=cnt)
        H = qx.load("hive")
        ov = []
        for i, h in got.items():
            o = H.get(i) or {}
            A, B = set(h["ents"]), set(o.get("ents", []))
            ov.append(len(A & B) / len(A | B) if A | B else 1.0)
        live["hints"] = {"got": len(got), "missing": missing, "ents_jaccard_vs_cache_q_sys_mean": round(sum(ov) / len(ov), 3) if ov else None}
        live["calls"] = cnt.get("calls", 0)
        res["live"] = live
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
