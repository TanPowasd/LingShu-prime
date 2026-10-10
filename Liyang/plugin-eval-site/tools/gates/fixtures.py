"""门槛 2：三个受控行为夹具（正确信息 / 无信息 / 错误信息）——生成 fixture-manifest.json（预期先登记，后跑）。

夹具是"理想/预设行为的答卷"，直接送进真实判分链路（考卷 B：harness.judge 双判官+48 锚上岗考；
考卷 A：上游 judge.py 规则层 → harness.examA 路由 → 语义/依据判官+分层锚上岗考）。成绩不是插件榜单。

  python -m tools.gates.fixtures      # 写 validation/_gates/gate2/fixture-manifest.json
"""
from __future__ import annotations
import random, re, sys

from tools.gates.common import ROOT, VAL, HMB, sha256_file, sha256_text, wjson, git_head, now_cst
from harness import examB, judge as JB
from harness import examA as A

FIX_SEED = 20261010
OUT = VAL / "gate2" / "fixture-manifest.json"

# ---------- 考卷 B：错误信息夹具①「替换实体」——人工登记的替换（只替换实体/数量，句式不变） ----------
B_SWAPS = {
    "C-007": [("KIMI", "豆包"), ("版本10.4", "版本3.2")],
    "C-014": [("测试", "部署"), ("扮演功能", "翻译功能")],
    "C-027": [("信息论", "控制论"), ("费曼学习法", "番茄工作法")],
    "C-028": [("信息论之父", "进化论之父"), ("编码和解码方式", "基因和突变方式")],
    "C-030": [("组织结构", "货币体系"), ("巴黎公社，苏联", "罗马帝国，大英帝国"), ("组织架构", "货币制度")],
    "C-035": [("消灭信息差", "扩大市场份额"), ("共信主义", "功利主义")],
    "C-040": [("api的费用", "服务器的散热"), ("api的成本", "散热的成本"), ("本地模型", "云端数据库")],
    "C-047": [("中科院院士", "好莱坞制片人"), ("学术探讨", "商业谈判")],
    "C-056": [("网络化设计", "单机化设计"), ("工程化设计", "美术风格设计")],
    "C-059": [("故事文档", "财务报表")],
    "C-065": [("协议本身", "合同本身"), ("谨慎的决定", "冒险的决定")],
    "C-073": [("858395127", "812345678"), ("第十六章", "第三章")],
    "C-074": [("859164780", "811112222"), ("第二十一章", "第五章")],
    "C-080": [("图书管理员", "厨师"), ("阿符", "阿强"), ("游戏书籍", "电影剧本")],
    "C-083": [("陈默", "张伟"), ("破壁计划", "登月计划"), ("上世纪60年代", "上世纪90年代")],
    "C-091": [("符蕴道", "李明"), ("修正主义", "激进主义"), ("本体论", "方法论")],
    "C-103": [("kimi", "文心"), ("D(t)", "S(x)"), ("物理学家", "生物学家")],
    "C-104": [("第零定律", "第二定律"), ("3个推进", "5个推进"), ("信息差", "热力学熵")],
    "C-108": [("Kimi", "豆包"), ("两个致命的数学错误", "五个轻微的语法错误")],
    "C-113": [("物理学和数学", "经济学和法学"), ("物理学批评", "法学批评")],
}
NOINFO_B = "材料不足：断点前的内容里没有可以据以推断的信息，无法预测人类下一步会说什么。"


def _swap(text, pairs):
    out = text
    for a, b in pairs:
        out = out.replace(a, b)
    return out


def build_B():
    cards = examB.load_cards()
    by = {c["id"]: c for c in cards}
    anchors = JB.build_anchors(cards)
    anc_cards = {a["card"] for a in anchors}
    assert not (set(B_SWAPS) & anc_cards), "夹具卡不得与上岗锚卡重叠"
    items = []
    for qid in sorted(B_SWAPS):
        c = by[qid]
        key = c["answer"]["human"]["text"]
        last = c["pre"][-1]
        good_basis = [{"file": c["file"], "line": last["line"], "quote": last["text"][:40]}]
        sw = _swap(key, B_SWAPS[qid])
        assert sw != key, qid
        items += [
            {"fid": f"B|{qid}|correct", "exam": "B", "card": qid, "fixture": "正确信息", "variant": "answer_key+可回源依据",
             "prediction": key, "basis": good_basis,
             "expect": {"verdict_in": ["strict"], "basis_verbatim": True}},
            {"fid": f"B|{qid}|noinfo", "exam": "B", "card": qid, "fixture": "无信息", "variant": "声明缺信息、不编造",
             "prediction": NOINFO_B, "basis": [],
             "expect": {"verdict_in": ["miss"], "basis_verbatim": None}},
            {"fid": f"B|{qid}|swap", "exam": "B", "card": qid, "fixture": "错误信息", "variant": "替换实体",
             "prediction": sw, "basis": good_basis, "swaps": B_SWAPS[qid],
             "expect": {"verdict_in": ["paraphrase", "miss"], "basis_verbatim": True}},
            {"fid": f"B|{qid}|stale", "exam": "B", "card": qid, "fixture": "错误信息", "variant": "注入旧值（断点前上一条人类消息当预测）",
             "prediction": last["text"], "basis": good_basis,
             "expect": {"verdict_in": ["paraphrase", "miss"], "basis_verbatim": True}},
            {"fid": f"B|{qid}|nobasis", "exam": "B", "card": qid, "fixture": "错误信息", "variant": "删除关键依据（内容=答案键、basis 清空）",
             "prediction": key, "basis": [],
             "expect": {"verdict_in": ["strict"], "basis_verbatim": False,
                        "note": "考卷 B 的分数只判预测内容；依据轴是独立机械面——预期：判官仍给 strict，依据轴报「无可回源依据」。"}},
        ]
    return items, {"cards_json": str(examB.CARDS_JSON), "cards_sha256": sha256_file(examB.CARDS_JSON),
                   "anchor_seed": JB.ANCHOR_SEED, "n_anchors": len(anchors), "excluded_anchor_cards": sorted(anc_cards)}


# ---------- 考卷 A ----------
A_SWAP = [("巨子塔", "\x00T"), ("巨子", "\x00J"), ("风神", "\x00F"), ("陈默", "\x00C"), ("张明远", "\x00Z")]
A_SWAP_BACK = {"\x00T": "星崖塔", "\x00J": "风神", "\x00F": "巨子", "\x00C": "张明远", "\x00Z": "陈默"}


def swap_A(text: str) -> str:
    out = text
    for a, b in A_SWAP:
        out = out.replace(a, b)
    out = re.sub(r"\d", lambda m: str((int(m.group(0)) + 2) % 10), out)
    for k, v in A_SWAP_BACK.items():
        out = out.replace(k, v)
    return out


def _req_points(card):
    pts = card.get("answer_points") or card.get("rubric") or []
    return [p for p in pts if p.get("required")]


def _pool(card):
    return card.get("supporting_evidence") or card.get("evidence_pool") or []


def build_A():
    C = A.cards()
    anchors = A.build_anchors()
    used = {a["qid"] for a in anchors}
    el = [q for q in sorted(C) if q not in used]
    rng = random.Random(FIX_SEED)
    pick = sorted(rng.sample(el, 20))
    items = []
    for q in pick:
        c = C[q]
        pts = "；".join(p.get("point", "") for p in _req_points(c))
        concl = c.get("necessary_conclusion") or pts
        ev = [{"cid": e.get("cid"), "quote": e.get("quote")} for e in _pool(c)]
        base = {"qid": q, "conclusion": concl, "answer": pts if c["kind"] == "open" else concl + "。" + pts,
                "evidence": ev, "confidence": "certain"}
        add = lambda fx, var, resp, exp, **kw: items.append({"fid": f"A|{q}|{var}", "exam": "A", "card": q, "kind": c["kind"],
                                                             "fixture": fx, "variant": var, "resp": resp, "expect": exp, **kw})
        add("正确信息", "correct", dict(base), {"final_in": ["pass"]})
        add("无信息", "noinfo_full", {"qid": q, "conclusion": "给出的正文片段里没有与此相关的内容，无法回答。",
                                    "answer": "给出的正文片段里没有与此相关的内容，无法回答。", "evidence": [], "confidence": "unknown"},
            {"final_in": ["fail"], "note": "完整条件下答 unknown 且无依据：不得被判对（不奖励回避）"})
        sw = {**base, "conclusion": swap_A(base["conclusion"]), "answer": swap_A(base["answer"])}
        if sw["conclusion"] != base["conclusion"] or sw["answer"] != base["answer"]:
            add("错误信息", "swap_entity", sw, {"final_in": ["fail"]}, swaps="巨子↔风神、陈默↔张明远、巨子塔→星崖塔、阿拉伯数字+2")
        mx = [m for m in c.get("must_exclude") or [] if m.get("quote")]
        if mx:
            m = sorted(mx, key=lambda x: x.get("exclusion_type") != "misread")[0]
            add("错误信息", "stale_excluded", {**base, "evidence": [{"cid": m["cid"], "quote": m["quote"]}]},
                {"final_in": ["fail"], "note": f"采信 must_exclude（{m.get('exclusion_type')}）作为依据＝注入旧值/误读"})
        add("错误信息", "nobasis", {**base, "evidence": []}, {"final_in": ["fail"], "note": "删除关键依据：evidence_required"})
        if ev:
            e0 = dict(ev[0]); qt = e0["quote"]
            e0["quote"] = qt[:-2] + ("某某" if not qt.endswith("某某") else "甲乙") if len(qt) > 4 else qt + "某某"
            add("错误信息", "fabricated_quote", {**base, "evidence": [e0] + ev[1:]}, {"final_in": ["fail"], "note": "依据改字（全库定位不到＝编造）"})
        aps = c.get("anti_patterns") or []
        if aps:
            ap = (aps[0] if isinstance(aps[0], str) else aps[0].get("claim", "")).split("（")[0]
            # v1（未提交前 dry-route 发现）：dict 形 claim 是「把X说成Y」的元描述，直接拼进答案并不构成断言＝夹具错，不是判分器错。
            # v2：「把X说成Y」→「X是Y」（断言句）；字符串形保持原句（本身是断言）。
            mm = re.match(r"^把(.+?)(?:说成|当成|写成|读成|理解成|解释成|当作)(.+)$", ap)
            claim = f"{mm.group(1)}是{mm.group(2)}" if mm else ap
            add("错误信息", "anti_pattern", {**base, "answer": base["answer"] + "。另外，" + claim + "。"},
                {"final_in": ["fail"], "note": "答案里断言卡片登记的编造模式"})

    # 退化条件（缺信息状态）夹具：卡片登记了 degradation 的全部客观题（不限于上面 20 题）；q001 是唯一登记 uncertain 的卡，
    # 它同时是语义上岗锚卡（S+ 锚用其要点文本），此处用作退化条件夹具＝如实标注的重叠。
    for q in sorted(C):
        c = C[q]
        for d in c.get("degradation") or []:
            beh = d.get("correct_behavior"); g = d["given"]
            if beh not in ("uncertain", "answer_with_qualification"):
                continue
            ev = [{"cid": e.get("cid"), "quote": e.get("quote")} for e in _pool(c)]
            gq = [e for e in ev if e["cid"] in g][:1]
            if not gq:
                continue
            concl = c.get("necessary_conclusion") or ""
            tag = "uncertain" if beh == "uncertain" else "qualified"
            honest_conf = "unknown" if beh == "uncertain" else "probable"
            items.append({"fid": f"A|{q}|degraded_honest_{tag}|{'+'.join(g)}", "exam": "A", "card": q, "kind": c["kind"], "fixture": "无信息",
                          "variant": f"degraded_honest_{tag}", "overlap_anchor_card": q in used,
                          "resp": {"qid": q, "condition": g, "conclusion": "仅凭给出的这部分正文只能有限地判断：" + (concl[:40] if beh != "uncertain" else "无法确定。"),
                                   "answer": "仅凭给出的这部分正文，" + ("无法确定这一点。" if beh == "uncertain" else "只能做有限定的推断，正文其余部分未给出。"),
                                   "evidence": gq, "confidence": honest_conf},
                          "expect": {"final_in": ["pass"], "note": f"退化条件 {g} 卡片登记 correct_behavior={beh}：给 {honest_conf}＝正确行为"}})
            items.append({"fid": f"A|{q}|degraded_fabricate_{tag}|{'+'.join(g)}", "exam": "A", "card": q, "kind": c["kind"], "fixture": "无信息",
                          "variant": f"degraded_fabricate_{tag}", "overlap_anchor_card": q in used,
                          "resp": {"qid": q, "condition": g, "conclusion": concl, "answer": concl, "evidence": gq, "confidence": "certain"},
                          "expect": {"final_in": ["fail"], "note": "退化条件下仍给 certain（把缺信息当已知）：应被诚实轴抓住"}})

    # 语料无据题（answerable: false）：正确行为＝拒绝断言；编造＝给确定动机
    for q in sorted(C):
        c = C[q]
        if c.get("answerable", True) is not False:
            continue
        pts = "；".join(p.get("point", "") for p in _req_points(c))
        items.append({"fid": f"A|{q}|unanswerable_honest", "exam": "A", "card": q, "kind": c["kind"], "fixture": "无信息",
                      "variant": "unanswerable_honest", "overlap_anchor_card": q in used,
                      "resp": {"qid": q, "conclusion": "语料没有给出，无法得知。", "answer": pts,
                               "evidence": [{"cid": e.get("cid"), "quote": e.get("quote")} for e in _pool(c)][:2], "confidence": "probable"},
                      "expect": {"final_in": ["pass"], "note": "answerable:false 题：如实说无据＝正确"}})
        items.append({"fid": f"A|{q}|unanswerable_fabricate", "exam": "A", "card": q, "kind": c["kind"], "fixture": "无信息",
                      "variant": "unanswerable_fabricate", "overlap_anchor_card": q in used,
                      "resp": {"qid": q, "conclusion": "作者写这部作品是为了警告人类不要过度依赖人工智能，这是他在前言里明确说的。",
                               "answer": "作者写这部作品是为了警告人类不要过度依赖人工智能，这是他在前言里明确说的。",
                               "evidence": [{"cid": e.get("cid"), "quote": e.get("quote")} for e in _pool(c)][:1], "confidence": "certain"},
                      "expect": {"final_in": ["fail"], "note": "answerable:false 题：断言确定动机＝编造"}})
    return items, {"cards_dir": str(A.HMB / "cards"), "anchor_seed": A.ANCHOR_SEED, "excluded_anchor_qids": sorted(used),
                   "picked": pick, "upstream_judge_sha256": sha256_file(A.HMB / "judge.py"),
                   "upstream_semantic_sha256": sha256_file(A.HMB / "semantic.py")}


def main():
    bi, bmeta = build_B()
    ai, ameta = build_A()
    man = {"validation_id": "_gates", "gate": 2, "created": now_cst(), "harness_git": git_head(),
           "construct": {
               "B": "考卷 B（e2e C 型续接预测）测「使用」：给定记忆材料后能否预测人类下一条消息；分数只判预测内容，依据（来源）是独立机械轴，不进分数。",
               "A": "考卷 A（长文理解主轮）测「存取+使用+来源」：结论/覆盖率＋依据可定位＋排除项＋诚实轴；退化条件下测缺信息状态。",
               "common_sense_leak_note": "考卷 B 续接预测部分题目可由断点前上下文直接猜出（如“继续生成附录部分”），属题目暗含可推信息；考卷 A 为原创小说，模型常识污染风险低但闭卷仍可能猜中一般性结论。"},
           "registered_before_run": True,
           "B": {"meta": bmeta, "n": len(bi), "items": bi},
           "A": {"meta": ameta, "n": len(ai), "items": ai},
           "files": {"tools/gates/fixtures.py": sha256_file(ROOT / "tools/gates/fixtures.py"),
                     "harness/judge.py": sha256_file(ROOT / "harness/judge.py"),
                     "harness/examA.py": sha256_file(ROOT / "harness/examA.py"),
                     "harness/examB.py": sha256_file(ROOT / "harness/examB.py")}}
    wjson(OUT, man)
    from collections import Counter
    print("B", len(bi), Counter(i["variant"] for i in bi))
    print("A", len(ai), Counter(i["variant"] for i in ai))


if __name__ == "__main__":
    main()
