# -*- coding: utf-8 -*-
"""chain-r26 H22：换实体、换取值 + 分块换名（PREREG_R26.md；seed 29000；由 h21_map.py 改值表/名库/种子，口径同 H19/H20）。对 HMB chain 语料 test 文档（dev 文档 猎户项目/青石镇 不动）：
取值与并存值做固定映射（与 H8–H21 目标值、H19–H21 别名都不同）；主体（项目名/人名/模块名）按「段号块」换名：同一文档每 BLOCK=3 段一个块，
块内一致、块间不同（模拟真实记忆流里主体不断换新：冷启动主体占事件句约 1/3，H8–H18 只有约 4%）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）。不调用被测代码。
  python h22_map.py   → out/heldout_h22/entity_value_map.json + corpus_h22base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h22"); os.makedirs(D, exist_ok=True)
DEVDOCS = {"猎户项目", "青石镇"}
BLOCK = 3
SUBJ = ["流明", "织女", "缓存模块", "杜衡", "林昭", "沈砚", "阿桑", "白芨", "雪姑", "陆平", "程雪", "九爷", "顾九"]
VALW = {
    "低落": "意兴阑珊", "犹豫": "犹犹豫豫", "戒备": "处处设防", "欣慰": "心花怒放", "释然": "豁然开朗", "平静": "气定神闲", "愤怒": "七窍生烟", "焦虑": "坐立难安",
    "祠堂": "家庙院", "渡口": "桃叶渡", "驿站": "邮亭驿", "粮仓": "储粮窖", "集市": "草市口", "磨坊": "油坊间", "后山": "北峰梁", "码头": "泊舟湾",
    "暧昧": "欲言又止", "沉默": "噤若寒蝉", "反对": "百般阻拦", "支持": "一力担保", "中立": "持平公允", "观望": "等风看雨",
    "外人": "过路人",
}
DEPS = {"bbolt": "petrelvault", "rocksdb": "egretdb", "badger": "martenledger", "sled": "pipitstore", "sqlite": "curlewbase", "lmdb": "ruffkv", "redis": "sanderlingcache"}
SECS = {"21600": "26460", "300": "3330", "1800": "5670", "3600": "8730", "900": "3870", "7200": "18180", "10800": "41310", "600": "1710"}
KEYS = {"batch_size": "flock_size", "retry": "retry_allot", "max_conn": "conn_brim", "timeout_ms": "drowse_ms"}
KNUM = {"16": "87", "32": "127", "64": "223", "128": "421", "256": "701"}
FUNCS = {"load": "heave", "get": "glom", "fetch": "courier", "resolve": "arbit", "sync": "knit"}
PARAMS = {"key": "knotch", "ttl": "abidance", "tag": "tagline", "refresh": "spool", "force": "wrangle", "id": "stud"}

SURN = list("闵蔺缪卞饶苑滕仝茹郦莘鞠酆阚桓戚甄蒙卜巩")
GIV = list("湛澈潇沅浥渟淼滢澄洵涟漱翀翮翊翦羿霁")
PROJ = list("嶝岫崤崦嵫岵屺岌崮峋嵝嶓峣嶔崒岿嵚峧嵽嶅")
MOD = ["楔块", "锁舌", "摇臂", "舵盘", "卡箍", "套筒", "拉杆", "叶轮", "托辊", "棘爪", "凸缘", "扣件", "铰链", "挡板", "滑块", "推杆", "锥齿", "卷簧", "吊环", "压环", "连轴", "机匣", "棘轮盘", "卡爪"]
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")


def build():
    rng = random.Random(29000)
    _all = "".join(c["text"] + c["doc"] for c in corpus())
    nblk = max(c["seq"] for c in corpus()) // BLOCK + 1
    prev = set()
    for v in range(8, 22):
        m = json.load(open(os.path.join(OUT, f"heldout_h{v}", "entity_value_map.json"), encoding="utf-8"))
        for k in ("words", "deps", "secs", "keys", "knum", "funcs", "params", "alias"):
            prev |= set(m.get(k, {}).values())
    used = set(); alias = {}

    def fresh(kind):
        for _ in range(10000):
            if kind == "proj":
                t = rng.choice(PROJ) + rng.choice(PROJ)
            elif kind == "mod":
                t = rng.choice(MOD) + "模块"
            else:
                t = rng.choice(SURN) + rng.choice(GIV) + (rng.choice(GIV) if rng.random() < .3 else "")
            if t in used or t in _all or t in prev or any(t in p_ or p_ in t for p_ in prev if not p_.isdigit() and len(p_) > 1) or len(set(t)) < len(t):
                continue
            if any(t in u or u in t for u in used):
                continue
            used.add(t); return t
        raise RuntimeError(kind)
    for b in range(nblk):
        for s in SUBJ:
            alias[f"{s}@{b}"] = fresh("proj" if s in ("流明", "织女") else "mod" if s == "缓存模块" else "person")
    vals = list(VALW.values()) + list(DEPS.values())
    for t in vals:
        assert t not in _all, t
        assert not any(t in a or a in t for a in alias.values()), ("overlap", t)
    for t in list(SECS.values()) + list(KNUM.values()):
        assert not re.search(r"(?<!\d)" + t + r"(?!\d)", _all), ("num in corpus", t)
    for d_ in (VALW, DEPS, SECS, KEYS, KNUM, FUNCS, PARAMS, alias):
        for t in d_.values():
            assert t not in prev, ("reused", t)
    rngc = random.Random(29001); cfgmap = {}; cused = set()

    def cfg(m):
        k = m.group(1)
        if k not in cfgmap:
            while True:
                v = str(rngc.randrange(100000, 1000000))
                if v not in cused and v not in _all:
                    cused.add(v); break
            cfgmap[k] = v
        return "cfg_" + cfgmap[k]

    def kv(m):
        return KEYS[m.group(1)] + "=" + KNUM.get(m.group(2), m.group(2))

    def fn(m):
        ps = ", ".join(PARAMS.get(p.strip(), p.strip()) for p in m.group(2).split(",") if p.strip())
        return FUNCS[m.group(1)] + "(" + ps + ")"

    def sub(t, b):
        words = dict(VALW); words.update({s: alias[f"{s}@{b}"] for s in SUBJ})
        w_re = re.compile("|".join(sorted(map(re.escape, words), key=len, reverse=True)))
        t = FN_RE.sub(fn, t); t = KV_RE.sub(kv, t); t = CFG_RE.sub(cfg, t)
        t = DEP_RE.sub(lambda m: DEPS[m.group(1)], t); t = SEC_RE.sub(lambda m: SECS[m.group(1)], t)
        return w_re.sub(lambda m: words[m.group(0)], t)
    out = []
    for c in corpus():
        if c["doc"] in DEVDOCS:
            out.append(c); continue
        b = (c["seq"] - 1) // BLOCK
        out.append(dict(c, text=sub(c["text"], b), doc=sub(c["doc"], 0), cid=c["cid"]))
    mp = {"words": VALW, "alias": alias, "block": BLOCK, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 29000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h22base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap), "aliases", len(alias))


if __name__ == "__main__":
    build()
