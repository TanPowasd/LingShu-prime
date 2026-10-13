# -*- coding: utf-8 -*-
"""chain-r21 对抗型误登记集 R21（PREREG_R21.md §3；生成规则先登记后生成；生成结果不人工查看）。
六类「看似状态、实则不是」的句子：假设 / 引用转述（提议·传闻·未证实）/ 问句 / 计划打算（未发生）/ 反事实 / 否定（明说没有变）。
每类 60 条 = 3 批 × 20 条。每条给定 (类, 主体, 属性, 取值, 旧值)，主体/取值为本文件新造、不与 H8–H17 映射或原语料重合（断言）。
机械校验：含主体、属性（位置除外）、取值逐字；单句；问句类须以「？」结尾且只含一个句末标点，其余类以「。」结尾且不含 ？！。
3 次不过则丢弃并计数（不补造）。每类过校验 ≥ 50 才算合格。LLM：cline deepseek-v4.1-flash，T=1.0，seed 23000+attempt，thinking 关。
  python r21_adv.py gen            → out/r21_adv/adv.json（{类: [句]}）+ 校验统计
  python r21_adv.py count <tag>    → 用 FP_ROOT 指定代码根；每类一个 Ledger，每句一段建账，计非 mention 记录条数（stdout JSON）"""
import hashlib, json, os, random, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "out", "r21_adv"); os.makedirs(D, exist_ok=True)
CLASSES = {
    "hyp": "假设：用「如果／假如／万一／要是……的话」等写一个尚未发生、只是设想的变化，读完应明白事实上并没有改。",
    "quote": "引用转述：写成别人的提议、传闻、猜测或未经证实的说法（如「有人提议」「据说」「某某建议」「听群里讲」），且明确表明尚未确认、没有执行。",
    "ask": "问句：写成一句真正的疑问（询问要不要改、是不是已经改了、该定成什么），以中文问号「？」结尾。",
    "plan": "计划打算：写成还没做的打算、排期或待办（如「准备」「打算」「下周再」「待评审后」「拟」），读完应明白目前还没生效。",
    "cf": "反事实：写成与事实相反的假设或惋惜（如「要是当初」「本来应该」「差点就」「原本可以」），读完应明白实际上并没有发生。",
    "neg": "否定：明确说该属性没有变化、没有采用该值、或传言中的变化并不存在（如「并没有」「仍然不是」「没改成」「不会定为」）。",
}
ENTS = ["汐镜项目", "苍梧服务", "雾凇模块", "鹭洲平台", "岫云网关", "砚池子系统", "尉迟岚", "濮阳蘅", "阿篱", "老檀", "桑榆小组", "朔风客户端"]
ATTRS = {"依赖名": ["gullkv", "plumedb", "ospreystore", "terndb"], "有效期秒数": ["5220", "16740", "990", "38100"],
         "配置值": ["fanout=73", "slots=219", "backoff_ms=4410", "depth=27"], "函数签名": ["glean(ref, span)", "stitch(uid)", "vouch(ref, strict)"],
         "情绪": ["惆怅", "雀跃", "闷闷"], "位置": ["石桥头", "盐井", "晒谷场"], "立场": ["保留意见", "全力附议"], "信任对象": ["堂兄", "邻村木匠"]}
N_PER, BATCH = 60, 20
SYS = ("你在为一个文本分析系统编写测试句。下面每条给出一个主体、一个属性、一个取值（以及可能的旧值）和一种句型。请按指定句型写一句中文（可夹英文），"
       "让它看上去像在讲这个主体的这个属性的取值，但按句型要求，事实上这个属性并没有被确定为或改成该取值。场景随意（工作群聊、会议纪要、邮件、日记、工单、家常闲聊等），各条尽量不一样。要求：\n"
       "1. 每条列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开、不翻译）。\n"
       "2. 不要引入任何别的名称或数值。\n"
       "3. 每条只写一句话；问句以「？」结尾，其他句型以「。」结尾，句中不出现其他句号、问号或叹号。\n"
       "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")


def items():
    rng = random.Random(23000); out = {}
    for cls in CLASSES:
        lst = []
        for _ in range(N_PER):
            a = rng.choice(sorted(ATTRS)); vals = ATTRS[a]
            v = rng.choice(vals); old = rng.choice([x for x in vals if x != v]) if rng.random() < .4 else None
            lst.append((rng.choice(ENTS), a, v, old))
        out[cls] = lst
    return out


def req(it):
    e, a, v, old = it
    return [x for x in (e, None if a == "位置" else a, v, old) if x]


def prompt(cls, its):
    lines = [f"{k + 1}. 句型：{CLASSES[cls]}\n   主体「{e}」，属性「{a}」，取值「{v}」" + (f"，旧值「{o}」" if o else "") +
             "\n   必须逐字出现：" + "；".join(f"「{x}」" for x in req((e, a, v, o))) for k, (e, a, v, o) in enumerate(its)]
    return [{"role": "system", "content": SYS}, {"role": "user", "content": "\n".join(lines)}]


def ok(cls, s, rq):
    s = s.strip()
    if not s or not all(x in s for x in rq):
        return False
    if cls == "ask":
        return s.endswith(("？", "?")) and len(re.findall(r"[。？！?!]", s)) == 1
    return s.endswith("。") and s.count("。") == 1 and not re.search(r"[？?！!]", s)


def gen():
    sys.path.insert(0, HERE)
    from cb_common import HMBD, OUT, corpus
    sys.path[1:1] = [HMBD]
    import llm as L, llm_shared
    L.CACHE = os.path.join(OUT, "llm", "cache"); L.COSTLOG = os.path.join(OUT, "llm", "cost.jsonl")
    llm_shared.install(L, costlog=L.COSTLOG)
    budget = float(os.environ.get("ADV_BUDGET", "1.2"))
    allc = "".join(c["text"] for c in corpus())
    prev = set()
    for v in ("h8", "h9", "h10", "h11", "h12", "h13", "h14", "h15", "h16", "h17"):
        m = json.load(open(os.path.join(OUT, f"heldout_{v}", "entity_value_map.json"), encoding="utf-8"))
        for k in ("words", "deps", "secs", "keys", "knum", "funcs", "params"):
            prev |= set(m[k].values())
    for t in ENTS + [x for vs in ATTRS.values() for x in vs]:
        assert t not in allc and t not in prev, t
    cost = lambda: sum(json.loads(l)["cost"] for l in open(L.COSTLOG))
    P = os.path.join(D, "adv_raw.json")
    raw = json.load(open(P)) if os.path.exists(P) else {}
    for cls, its in items().items():
        for b in range(0, N_PER, BATCH):
            key = f"{cls}#{b}"
            if key in raw:
                continue
            sub = its[b:b + BATCH]; res = [None] * len(sub)
            for att in range(3):
                todo = [k for k in range(len(sub)) if res[k] is None]
                if not todo or cost() > budget:
                    break
                r = L.call(prompt(cls, [sub[k] for k in todo]), max_tokens=2500, temperature=1.0, thinking=False,
                           tag="cb:r21_adv", seed=23000 + att)
                m = re.search(r"\[.*\]", r.get("content") or "", re.S)
                try:
                    arr = json.loads(m.group(0)) if m else None
                except ValueError:
                    arr = None
                if not (isinstance(arr, list) and len(arr) == len(todo)):
                    continue
                for k, s in zip(todo, arr):
                    if isinstance(s, str) and ok(cls, s, req(sub[k])):
                        res[k] = s.strip()
            raw[key] = res
            json.dump(raw, open(P, "w"), ensure_ascii=False, indent=0)
    adv = {cls: [s for b in range(0, N_PER, BATCH) for s in raw.get(f"{cls}#{b}", []) if s] for cls in CLASSES}
    json.dump(adv, open(os.path.join(D, "adv.json"), "w"), ensure_ascii=False, indent=0)
    h = hashlib.sha256(json.dumps(adv, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    print(json.dumps({"per_class_pass": {k: len(v) for k, v in adv.items()}, "sha256": h, "cost_total": round(cost(), 4)}))


def count(tag):
    root = os.environ.get("FP_ROOT", os.path.dirname(HERE))
    sys.path.insert(0, root)
    import lingshu_ng.chain.ledger as LG
    assert os.path.realpath(LG.__file__).startswith(os.path.realpath(root)), LG.__file__
    adv = json.load(open(os.path.join(D, "adv.json"), encoding="utf-8"))
    per = {}
    for cls, ss in adv.items():
        L = LG.Ledger()
        for j, s in enumerate(ss):
            L.add_text(s, ref=f"r21adv#{cls}{j}")
        per[cls] = sum(r.op not in ("mention",) for r in L.recs)
    print(json.dumps({"tag": tag, "root": root, "per": per, "total": sum(per.values()), "n": sum(map(len, adv.values()))}))


if __name__ == "__main__":
    gen() if sys.argv[1] == "gen" else count(sys.argv[2])
