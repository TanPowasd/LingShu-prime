# -*- coding: utf-8 -*-
"""chain-r21 H17：换实体、换取值（PREREG_R21.md；与 H8–H16 映射都不同的新目标名/新取值，seed 21000）。对 HMB chain 语料的 test 文档（dev 文档 猎户项目/青石镇 不动）做固定映射的一致替换：
主体（项目名/人名/模块名）、取值与并存值（依赖名、秒数、键值对、函数签名、cfg_ 编号、情绪/位置/立场/信任对象词）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）；cfg_ 编号用固定种子 20000 的随机数。不调用被测代码。
  python h17_map.py   → out/heldout_h17/entity_value_map.json + corpus_h17base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h17")
DEVDOCS = {"猎户项目", "青石镇"}

WORDS = {
    # 主体
    "流明": "崦嵫", "织女": "扶桑", "缓存模块": "编目模块",
    "杜衡": "辛夷", "林昭": "钟离曜", "沈砚": "闾丘砺", "阿桑": "阿苒", "白芨": "泽兰", "雪姑": "槿嬷",
    "陆平": "荀叔夜", "程雪": "璩萦", "九爷": "八舅公", "顾九": "庞十一",
    # 情绪 / 位置 / 立场 / 信任对象
    "低落": "萎靡", "犹豫": "迟回", "戒备": "枕戈待旦", "欣慰": "欣忭", "释然": "坦荡", "平静": "安闲", "愤怒": "忿懑", "焦虑": "栗栗",
    "祠堂": "享堂", "渡口": "野渡", "驿站": "铺递", "粮仓": "廪房", "集市": "夜市口", "磨坊": "榨房", "后山": "杉坳", "码头": "埠头",
    "暧昧": "模棱两可", "沉默": "守口如瓶", "反对": "力阻", "支持": "摇旗呐喊", "中立": "置身事外", "观望": "待价而沽",
    "外人": "路人甲",
}
DEPS = {"bbolt": "kestrelkv", "rocksdb": "wrenkv", "badger": "minnowdb", "sled": "grebekv", "sqlite": "pelikv", "lmdb": "nutsdbx", "redis": "valkeyz"}
SECS = {"21600": "29700", "300": "2340", "1800": "3420", "3600": "4860", "900": "2820", "7200": "15600", "10800": "45900", "600": "1260"}
KEYS = {"batch_size": "bundle_size", "retry": "retry_ceiling", "max_conn": "pool_top", "timeout_ms": "lapsetime_ms"}
KNUM = {"16": "67", "32": "83", "64": "146", "128": "308", "256": "536"}
FUNCS = {"load": "devour", "get": "pluck", "fetch": "reel", "resolve": "umpire", "sync": "dovetail"}
PARAMS = {"key": "kref", "ttl": "livespan", "tag": "emblem", "refresh": "refurbish", "force": "override", "id": "ordinal"}

W_RE = re.compile("|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)))
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")


def build():
    rng = random.Random(21000); cfgmap = {}
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
    for v in ("h8", "h9", "h10", "h11", "h12", "h13", "h14", "h15", "h16"):
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
    mp = {"words": WORDS, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 21000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h17base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap))


if __name__ == "__main__":
    build()
