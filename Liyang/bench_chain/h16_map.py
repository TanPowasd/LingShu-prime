# -*- coding: utf-8 -*-
"""chain-r20 H16：换实体、换取值（PREREG_R20.md；与 H8–H15 映射都不同的新目标名/新取值，seed 20000）。对 HMB chain 语料的 test 文档（dev 文档 猎户项目/青石镇 不动）做固定映射的一致替换：
主体（项目名/人名/模块名）、取值与并存值（依赖名、秒数、键值对、函数签名、cfg_ 编号、情绪/位置/立场/信任对象词）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）；cfg_ 编号用固定种子 20000 的随机数。不调用被测代码。
  python h16_map.py   → out/heldout_h16/entity_value_map.json + corpus_h16base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h16")
DEVDOCS = {"猎户项目", "青石镇"}

WORDS = {
    # 主体
    "流明": "瀛洲", "织女": "昆吾", "缓存模块": "汇聚模块",
    "杜衡": "芸香", "林昭": "殷朔", "沈砚": "窦衡", "阿桑": "阿菱", "白芨": "苍术", "雪姑": "芷婶",
    "陆平": "郗望舒", "程雪": "柏绮", "九爷": "六伯", "顾九": "晏七",
    # 情绪 / 位置 / 立场 / 信任对象
    "低落": "怏怏", "犹豫": "踌躇不前", "戒备": "严阵以待", "欣慰": "宽怀", "释然": "豁然", "平静": "心如止水", "愤怒": "恼恨", "焦虑": "惴惴",
    "祠堂": "宗庙", "渡口": "摆渡处", "驿站": "邮亭", "粮仓": "谷仓", "集市": "市井", "磨坊": "豆腐坊", "后山": "竹岭", "码头": "泊位",
    "暧昧": "含糊其辞", "沉默": "一言不发", "反对": "唱反调", "支持": "鼎力相助", "中立": "两不相帮", "观望": "坐看",
    "外人": "陌路人",
}
DEPS = {"bbolt": "quillkv", "rocksdb": "pebblekv", "badger": "otterdb", "sled": "boltpp", "sqlite": "duckkv", "lmdb": "mdbxx", "redis": "keydbz"}
SECS = {"21600": "27900", "300": "1980", "1800": "3060", "3600": "4380", "900": "2220", "7200": "17400", "10800": "41400", "600": "2580"}
KEYS = {"batch_size": "pack_size", "retry": "redo_limit", "max_conn": "link_max", "timeout_ms": "lapse_ms"}
KNUM = {"16": "61", "32": "93", "64": "152", "128": "296", "256": "472"}
FUNCS = {"load": "slurp", "get": "snag", "fetch": "tug", "resolve": "elect", "sync": "mesh"}
PARAMS = {"key": "kname", "ttl": "lifespan", "tag": "sigil", "refresh": "reheat", "force": "coerce", "id": "serialno"}

W_RE = re.compile("|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)))
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")


def build():
    rng = random.Random(20000); cfgmap = {}
    used = set()

    def cfg(m):
        k = m.group(1)
        if k not in cfgmap:
            while True:
                v = str(rng.randrange(100000, 1000000))
                if v not in used:
                    used.add(v); break
            cfgmap[k] = v
        return "cfg_" + cfgmap[k]

    def kv(m):
        return KEYS[m.group(1)] + "=" + KNUM.get(m.group(2), m.group(2))

    def fn(m):
        ps = ", ".join(PARAMS.get(p.strip(), p.strip()) for p in m.group(2).split(",") if p.strip())
        return FUNCS[m.group(1)] + "(" + ps + ")"

    def sub(t):
        t = FN_RE.sub(fn, t)
        t = KV_RE.sub(kv, t)
        t = CFG_RE.sub(cfg, t)
        t = DEP_RE.sub(lambda m: DEPS[m.group(1)], t)
        t = SEC_RE.sub(lambda m: SECS[m.group(1)], t)
        return W_RE.sub(lambda m: WORDS[m.group(0)], t)

    _all = "".join(c["text"] for c in corpus())
    for t in list(WORDS.values()) + list(DEPS.values()):
        assert t not in _all, t
    for t in list(SECS.values()) + list(KNUM.values()):          # 数值目标不在原语料出现
        assert not re.search(r"(?<!\d)" + t + r"(?!\d)", _all), ("num in corpus", t)
    prev = set()
    for v in ("h8", "h9", "h10", "h11", "h12", "h13", "h14", "h15"):
        m = json.load(open(os.path.join(OUT, f"heldout_{v}", "entity_value_map.json"), encoding="utf-8"))
        for k in ("words", "deps", "secs", "keys", "knum", "funcs", "params"):
            prev |= set(m[k].values())
    for d_ in (WORDS, DEPS, SECS, KEYS, KNUM, FUNCS, PARAMS):
        for t in d_.values():
            assert t not in prev, ("reused", t)
    out = []
    for c in corpus():
        if c["doc"] in DEVDOCS:
            out.append(c); continue
        out.append(dict(c, text=sub(c["text"]), doc=sub(c["doc"]), cid=c["cid"]))
    mp = {"words": WORDS, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 20000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h16base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap))


if __name__ == "__main__":
    build()
