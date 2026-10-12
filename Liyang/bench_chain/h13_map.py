# -*- coding: utf-8 -*-
"""chain-r17 H13：换实体、换取值（PREREG_R17.md；与 H8–H12 映射都不同的新目标名/新取值，seed 17000）。对 HMB chain 语料的 test 文档（dev 文档 猎户项目/青石镇 不动）做固定映射的一致替换：
主体（项目名/人名/模块名）、取值与并存值（依赖名、秒数、键值对、函数签名、cfg_ 编号、情绪/位置/立场/信任对象词）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）；cfg_ 编号用固定种子 17000 的随机数。不调用被测代码。
  python h13_map.py   → out/heldout_h13/entity_value_map.json + corpus_h13base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h13")
DEVDOCS = {"猎户项目", "青石镇"}

WORDS = {
    # 主体
    "流明": "天枢", "织女": "瑶光", "缓存模块": "路由模块",
    "杜衡": "柯远", "林昭": "邝宁", "沈砚": "薛棣", "阿桑": "阿鸢", "白芨": "钟离", "雪姑": "荞姨",
    "陆平": "岑川", "程雪": "闵雯", "九爷": "十一伯", "顾九": "戚五",
    # 情绪 / 位置 / 立场 / 信任对象
    "低落": "颓唐", "犹豫": "逡巡", "戒备": "戒惧", "欣慰": "宽心", "释然": "洒脱", "平静": "澄明", "愤怒": "气恼", "焦虑": "烦忧",
    "祠堂": "塔院", "渡口": "芦洲", "驿站": "茶寮", "粮仓": "米铺", "集市": "灯市", "磨坊": "碾房", "后山": "竹坞", "码头": "津口",
    "暧昧": "游离", "沉默": "噤口", "反对": "异议", "支持": "声援", "中立": "不偏", "观望": "静候",
    "外人": "生客",
}
DEPS = {"bbolt": "xtdb", "rocksdb": "lsmtree", "badger": "lotusdb", "sled": "sanakv", "sqlite": "litestore", "lmdb": "mdbm", "redis": "skytable"}
SECS = {"21600": "30600", "300": "840", "1800": "4500", "3600": "6900", "900": "1560", "7200": "9900", "10800": "25800", "600": "1020"}
KEYS = {"batch_size": "group_size", "retry": "retry_max", "max_conn": "pool_cap", "timeout_ms": "grace_ms"}
KNUM = {"16": "66", "32": "76", "64": "112", "128": "232", "256": "488"}
FUNCS = {"load": "hydrate", "get": "glean", "fetch": "harvest", "resolve": "arbitrate", "sync": "propagate"}
PARAMS = {"key": "cell", "ttl": "keepalive", "tag": "mark", "refresh": "rehydrate", "force": "eager", "id": "nid"}

W_RE = re.compile("|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)))
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")


def build():
    rng = random.Random(17000); cfgmap = {}
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
    for v in ("h8", "h9", "h10", "h11", "h12"):
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
    mp = {"words": WORDS, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 17000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h13base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap))


if __name__ == "__main__":
    build()
