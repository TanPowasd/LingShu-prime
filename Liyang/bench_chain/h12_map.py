# -*- coding: utf-8 -*-
"""chain-r16 H12：换实体、换取值（PREREG_R16.md；与 H8–H11 映射都不同的新目标名/新取值，seed 16000）。对 HMB chain 语料的 test 文档（dev 文档 猎户项目/青石镇 不动）做固定映射的一致替换：
主体（项目名/人名/模块名）、取值与并存值（依赖名、秒数、键值对、函数签名、cfg_ 编号、情绪/位置/立场/信任对象词）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）；cfg_ 编号用固定种子 16000 的随机数。不调用被测代码。
  python h12_map.py   → out/heldout_h12/entity_value_map.json + corpus_h12base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h12")
DEVDOCS = {"猎户项目", "青石镇"}

WORDS = {
    # 主体
    "流明": "璇玑", "织女": "太簇", "缓存模块": "存储模块",
    "杜衡": "商陆", "林昭": "凌霄", "沈砚": "石斛", "阿桑": "阿笙", "白芨": "苏合", "雪姑": "葵婆",
    "陆平": "卓远", "程雪": "欧晴", "九爷": "八姑", "顾九": "左三",
    # 情绪 / 位置 / 立场 / 信任对象
    "低落": "郁结", "犹豫": "踟蹰", "戒备": "警觉", "欣慰": "欢欣", "释然": "开怀", "平静": "安宁", "愤怒": "愤懑", "焦虑": "忧惧",
    "祠堂": "箭楼", "渡口": "苇塘", "驿站": "马厩", "粮仓": "谷场", "集市": "夜市", "磨坊": "水碓", "后山": "枫林", "码头": "船埠",
    "暧昧": "模棱", "沉默": "闭口", "反对": "抗议", "支持": "拥戴", "中立": "持中", "观望": "袖手",
    "外人": "陌客",
}
DEPS = {"bbolt": "sanakirja", "rocksdb": "terarkdb", "badger": "voltdb", "sled": "persy", "sqlite": "hsqldb", "lmdb": "ravendb", "redis": "garnet"}
SECS = {"21600": "39600", "300": "960", "1800": "3900", "3600": "5700", "900": "1320", "7200": "8700", "10800": "20400", "600": "1380"}
KEYS = {"batch_size": "fetch_size", "retry": "max_tries", "max_conn": "conn_pool", "timeout_ms": "ttl_ms"}
KNUM = {"16": "62", "32": "68", "64": "104", "128": "208", "256": "416"}
FUNCS = {"load": "intake", "get": "locate", "fetch": "obtain", "resolve": "reconcile", "sync": "replicate"}
PARAMS = {"key": "handle", "ttl": "lease", "tag": "flag", "refresh": "rewarm", "force": "forced", "id": "rid"}

W_RE = re.compile("|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)))
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")


def build():
    rng = random.Random(16000); cfgmap = {}
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
    prev = set()
    for v in ("h8", "h9", "h10", "h11"):
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
    mp = {"words": WORDS, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 16000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h12base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap))


if __name__ == "__main__":
    build()
