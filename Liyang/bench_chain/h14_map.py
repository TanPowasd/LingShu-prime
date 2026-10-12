# -*- coding: utf-8 -*-
"""chain-r18 H14：换实体、换取值（PREREG_R18.md；与 H8–H13 映射都不同的新目标名/新取值，seed 18000）。对 HMB chain 语料的 test 文档（dev 文档 猎户项目/青石镇 不动）做固定映射的一致替换：
主体（项目名/人名/模块名）、取值与并存值（依赖名、秒数、键值对、函数签名、cfg_ 编号、情绪/位置/立场/信任对象词）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）；cfg_ 编号用固定种子 18000 的随机数。不调用被测代码。
  python h14_map.py   → out/heldout_h14/entity_value_map.json + corpus_h14base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h14")
DEVDOCS = {"猎户项目", "青石镇"}

WORDS = {
    # 主体
    "流明": "岱舆", "织女": "员峤", "缓存模块": "编排模块",
    "杜衡": "聂桐", "林昭": "晏青", "沈砚": "骆舟", "阿桑": "阿檀", "白芨": "卜萸", "雪姑": "椿婆",
    "陆平": "宁朔", "程雪": "蔺瑶", "九爷": "五舅", "顾九": "秦七",
    # 情绪 / 位置 / 立场 / 信任对象
    "低落": "怅惘", "犹豫": "趑趄", "戒备": "惕厉", "欣慰": "熨帖", "释然": "豁朗", "平静": "恬静", "愤怒": "恚恨", "焦虑": "惶急",
    "祠堂": "家庙", "渡口": "沙洲", "驿站": "客舍", "粮仓": "盐栈", "集市": "圩口", "磨坊": "油车", "后山": "樵岭", "码头": "河湾",
    "暧昧": "依违", "沉默": "缄唇", "反对": "非议", "支持": "襄助", "中立": "折中", "观望": "坐视",
    "外人": "闲客",
}
DEPS = {"bbolt": "tidesdb", "rocksdb": "speedydb", "badger": "rosedb", "sled": "agatedb", "sqlite": "limbo", "lmdb": "sophia", "redis": "kvdb"}
SECS = {"21600": "37800", "300": "1740", "1800": "6300", "3600": "7800", "900": "2160", "7200": "11400", "10800": "27000", "600": "1860"}
KEYS = {"batch_size": "slab_size", "retry": "retry_budget", "max_conn": "link_cap", "timeout_ms": "cutoff_ms"}
KNUM = {"16": "74", "32": "92", "64": "124", "128": "248", "256": "392"}
FUNCS = {"load": "inhale", "get": "fetchone", "fetch": "draw", "resolve": "adjudge", "sync": "converge"}
PARAMS = {"key": "kid", "ttl": "ttl_s", "tag": "tagset", "refresh": "rerun", "force": "brute", "id": "xid"}

W_RE = re.compile("|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)))
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")


def build():
    rng = random.Random(18000); cfgmap = {}
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
    for v in ("h8", "h9", "h10", "h11", "h12", "h13"):
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
    mp = {"words": WORDS, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 18000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h14base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap))


if __name__ == "__main__":
    build()
