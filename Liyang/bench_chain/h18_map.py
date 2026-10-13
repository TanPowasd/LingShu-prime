# -*- coding: utf-8 -*-
"""chain-r22 H18：换实体、换取值（PREREG_R22.md；与 H8–H17 映射都不同的新目标名/新取值，seed 24000）。对 HMB chain 语料的 test 文档（dev 文档 猎户项目/青石镇 不动）做固定映射的一致替换：
主体（项目名/人名/模块名）、取值与并存值（依赖名、秒数、键值对、函数签名、cfg_ 编号、情绪/位置/立场/信任对象词）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）；cfg_ 编号用固定种子 20000 的随机数。不调用被测代码。
  python h18_map.py   → out/heldout_h18/entity_value_map.json + corpus_h18base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h18")
DEVDOCS = {"猎户项目", "青石镇"}

WORDS = {
    # 主体
    "流明": "钩吾", "织女": "毕方", "缓存模块": "检波模块",
    "杜衡": "款冬", "林昭": "宇文瑾", "沈砚": "司空朔", "阿桑": "阿荇", "白芨": "佩兰", "雪姑": "桂婶",
    "陆平": "上官遥", "程雪": "甄绮", "九爷": "七姑丈", "顾九": "晏十三",
    # 情绪 / 位置 / 立场 / 信任对象
    "低落": "嗒然", "犹豫": "首鼠两端", "戒备": "如临大敌", "欣慰": "惆怅", "释然": "豁达", "平静": "淡泊", "愤怒": "恚怒", "焦虑": "惶惶",
    "祠堂": "宗祠", "渡口": "津头", "驿站": "马站", "粮仓": "囤廒", "集市": "赶街处", "磨坊": "水碾房", "后山": "柏树坪", "码头": "系缆处",
    "暧昧": "闪烁其词", "沉默": "缄口不言", "反对": "坚拒", "支持": "全力声援", "中立": "不偏不倚", "观望": "静观其变",
    "外人": "陌生客",
}
DEPS = {"bbolt": "ospreykv", "rocksdb": "heronkv", "badger": "martendb", "sled": "ploverkv", "sqlite": "larkdbx", "lmdb": "ibiskv", "redis": "cachyz"}
SECS = {"21600": "31500", "300": "2730", "1800": "3540", "3600": "5220", "900": "2940", "7200": "16800", "10800": "47700", "600": "1530"}
KEYS = {"batch_size": "parcel_size", "retry": "retry_bound", "max_conn": "conn_roof", "timeout_ms": "waitcap_ms"}
KNUM = {"16": "71", "32": "89", "64": "151", "128": "317", "256": "547"}
FUNCS = {"load": "scoop", "get": "nab", "fetch": "tow", "resolve": "arbiter", "sync": "twine"}
PARAMS = {"key": "kslot", "ttl": "agelimit", "tag": "tally", "refresh": "refreshen", "force": "compel", "id": "serial"}

W_RE = re.compile("|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)))
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")


def build():
    rng = random.Random(24000); cfgmap = {}
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
    for v in ("h8", "h9", "h10", "h11", "h12", "h13", "h14", "h15", "h16", "h17"):
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
    mp = {"words": WORDS, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 24000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h18base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap))


if __name__ == "__main__":
    build()
