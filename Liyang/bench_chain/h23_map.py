# -*- coding: utf-8 -*-
"""chain-r27 H23：换实体、换取值 + 分块换名（PREREG_R27.md；seed 30000；由 h22_map.py 改值表/名库/种子，口径同 H19/H20）。对 HMB chain 语料 test 文档（dev 文档 猎户项目/青石镇 不动）：
取值与并存值做固定映射（与 H8–H22 目标值、H19–H22 别名都不同）；主体（项目名/人名/模块名）按「段号块」换名：同一文档每 BLOCK=3 段一个块，
块内一致、块间不同（模拟真实记忆流里主体不断换新：冷启动主体占事件句约 1/3，H8–H18 只有约 4%）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）。不调用被测代码。
  python h23_map.py   → out/heldout_h23/entity_value_map.json + corpus_h23base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h23"); os.makedirs(D, exist_ok=True)
DEVDOCS = {"猎户项目", "青石镇"}
BLOCK = 3
SUBJ = ["流明", "织女", "缓存模块", "杜衡", "林昭", "沈砚", "阿桑", "白芨", "雪姑", "陆平", "程雪", "九爷", "顾九"]
VALW = {
    "低落": "愁眉不展", "犹豫": "举棋难定", "戒备": "步步为营", "欣慰": "笑逐颜开", "释然": "心宽体舒", "平静": "神色自如", "愤怒": "怒发冲冠", "焦虑": "忧心忡忡",
    "祠堂": "宗祠厅", "渡口": "杏花渡", "驿站": "递铺亭", "粮仓": "义仓院", "集市": "赶场坝", "磨坊": "水碓房", "后山": "东岗坡", "码头": "停篙埠",
    "暧昧": "支支吾吾", "沉默": "一声不吭", "反对": "极力劝阻", "支持": "全心力挺", "中立": "中正持衡", "观望": "按下不表",
    "外人": "远来人",
}
DEPS = {"bbolt": "tealvault", "rocksdb": "ibisdb", "badger": "stoatledger", "sled": "wrenstore", "sqlite": "jaybase", "lmdb": "knotkv", "redis": "rookcache"}
SECS = {"21600": "25740", "300": "3450", "1800": "5850", "3600": "9090", "900": "4050", "7200": "18900", "10800": "39690", "600": "2070"}
KEYS = {"batch_size": "herd_size", "retry": "retry_stint", "max_conn": "conn_crest", "timeout_ms": "doze_ms"}
KNUM = {"16": "91", "32": "131", "64": "227", "128": "433", "256": "719"}
FUNCS = {"load": "winch", "get": "clutch", "fetch": "convey", "resolve": "rule", "sync": "weave"}
PARAMS = {"key": "keystub", "ttl": "tenure", "tag": "labelet", "refresh": "refill", "force": "press", "id": "rowtag"}

SURN = list("尉晏闻宓阙邰靳郜冼佘殷奚璩濮荀柯蓟祁晁韦")
GIV = list("珩琮璟玥琛珺瑾璠琬琰瑀璘珣玹琨珧琭瑢")
PROJ = list("岷峨巉崆峒嵘崚岍岘峁峂嵖崀嶕岙崶嵒峇崾岨")
MOD = ["卡簧", "飞轮", "轴瓦", "偏心轮", "摆杆", "定位销", "锁扣", "齿条", "钩爪", "扭簧", "支架", "托架", "轴套", "闸片", "合页", "拨盘", "螺杆", "销轴", "夹板", "阀芯", "弹片", "齿圈", "端盖", "衬板", "滤网", "导板", "离合片"]
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")


def build():
    rng = random.Random(30000)
    _all = "".join(c["text"] + c["doc"] for c in corpus())
    nblk = max(c["seq"] for c in corpus()) // BLOCK + 1
    prev = set()
    for v in range(8, 23):
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
    rngc = random.Random(30001); cfgmap = {}; cused = set()

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
    mp = {"words": VALW, "alias": alias, "block": BLOCK, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 30000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h23base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap), "aliases", len(alias))


if __name__ == "__main__":
    build()
