"""性质测试：自写轻量随机化框架（不依赖 hypothesis）。

每条性质 = 生成器 + 不变量：prop(A, rnd) 在一个随机种子上构造场景、执行随机操作，
返回 None（性质成立）或一段违反说明（字符串）。抛 NA → 该实现不具备能力；
其他异常记为「违反（异常）」并按异常类型计数。
run_prop 对 seeds 个种子（random.Random(seed)，seed=0..N-1，可复跑）逐一执行，报违反率与首个反例种子。
"""
import itertools
import json
import math
import random
import threading
import time

from adapters import Adapter, NA

PROPS = {}


def prop(pid, title):
    def deco(fn):
        PROPS[pid] = {"fn": fn, "title": title}
        return fn
    return deco


VOCAB = list("甲乙丙丁戊己庚辛壬癸山水火木金土日月星云风雨雪霜江河湖海")
WORDS = ["服务器", "数据库", "备份", "用户", "配置", "端口", "证书", "日志", "预算", "会议", "合同", "版本",
         "迁移", "告警", "磁盘", "网络", "权限", "密钥", "缓存", "队列"]


def sentence(rnd, n=None):
    n = n or rnd.randint(4, 8)
    return "".join(rnd.choice(WORDS) for _ in range(n)) + f"#{rnd.randint(0, 10 ** 9)}"


def finite01(x):
    return isinstance(x, (int, float)) and math.isfinite(x) and 0.0 <= x <= 1.0


# ---------------------------------------------------------------------------

@prop("P01-layer-immutability", "锚点/结构层在任意维护操作序列后内容与层不变")
def _(A, rnd):
    m = A.open()
    fixed = {}
    for i in range(rnd.randint(1, 4)):
        lay = rnd.choice(["anchor", "structure"])
        c = sentence(rnd)
        fixed[m.add(c, layer=lay)] = (c, lay)
    for _ in range(rnd.randint(3, 10)):
        op = rnd.choice(["k", "c", "decay", "cap", "forget", "consolidate"])
        if op == "k":
            m.add(sentence(rnd), importance=rnd.random())
        elif op == "c":
            m.add(sentence(rnd), layer="context", importance=rnd.random())
        elif op == "decay":
            m.decay(rnd.randint(1, 30), factor=rnd.choice([0.02, 0.2]))
        elif op == "cap":
            m.set_context_cap(rnd.randint(1, 5))
            m.add(sentence(rnd), layer="context")
        elif op == "forget":
            m.forget_advisor()
        else:
            m.consolidate()
    for nid, (c, lay) in fixed.items():
        x = m.get(nid)
        if x is None or x["layer"] != lay or x["content"] != c:
            return f"{lay} 节点 {nid} → {x and (x['layer'], x['content'][:12])}"


@prop("P02-dedup-idempotent", "同一内容重复写入幂等：返回同一 id、库中只有一条")
def _(A, rnd):
    m = A.open()
    for _ in range(rnd.randint(0, 5)):
        m.add(sentence(rnd))
    c = sentence(rnd)
    ids = {m.add(c) for _ in range(rnd.randint(2, 5))}
    n = sum(1 for x in m.all_nodes(1000) if x["content"] == c)
    if len(ids) != 1 or n != 1:
        return f"返回 id 数={len(ids)}，库中条数={n}"


@prop("P03-dedup-polarity", "去重对否定/数值敏感：插入『不』或改一个数字的句子不被合并")
def _(A, rnd):
    m = A.open()
    base = "".join(rnd.choice(WORDS) for _ in range(rnd.randint(8, 14)))
    k = rnd.randint(1, len(base) - 1)
    if rnd.random() < 0.5:
        a, b = base[:k] + "已" + base[k:], base[:k] + "未" + base[k:]
    else:
        a, b = base + f"剂量{rnd.randint(1, 9)}毫克", None
        b = a[:-3] + str((int(a[-3]) % 9) + 1) + "毫克"
    ia, ib = m.add(a), m.add(b)
    if ia == ib:
        return f"『{a[-8:]}』与『{b[-8:]}』被合并"


@prop("P04-decay-monotone", "衰减单调：可衰减节点 importance 不增、被删节点不复活")
def _(A, rnd):
    m = A.open()
    ids = [m.add(sentence(rnd), layer=rnd.choice(["context", "knowledge"]), importance=rnd.random())
           for _ in range(rnd.randint(2, 8))]
    prev = {i: m.get(i)["importance"] for i in ids}
    dead = set()
    for _ in range(rnd.randint(3, 15)):
        m.decay(1, factor=rnd.choice([0.02, 0.1, 0.3]))
        for i in ids:
            x = m.get(i)
            if x is None:
                dead.add(i)
                continue
            if i in dead:
                return f"{i} 被删后复活"
            if x["importance"] > prev[i] + 1e-9:
                return f"importance {prev[i]:.4f}→{x['importance']:.4f}"
            prev[i] = x["importance"]


@prop("P05-decay-termination", "衰减终止：未保护的情境节点在有限轮（factor=0.2，≤150 轮）内被遗忘")
def _(A, rnd):
    m = A.open()
    ids = [m.add(sentence(rnd), layer="context", importance=rnd.choice([0.0, 0.01, 0.05, 0.1, rnd.random()]))
           for _ in range(rnd.randint(1, 6))]
    for _ in range(150):
        m.decay(1, factor=0.2)
        if all(m.get(i) is None for i in ids):
            return None
    alive = [round(m.get(i)["importance"], 4) for i in ids if m.get(i) is not None]
    return f"150 轮后仍存活 importance={alive}"


@prop("P06-export-import-roundtrip", "导出→导入往返：本地层（知识/情境）与其间的边逐项等价；共享层（锚点/结构）要么原样恢复、要么整条不导入（隔离），绝不被改写")
def _(A, rnd):
    # 与探针 i125 口径一致：无密钥导入时，实现可以拒收/隔离共享层（防篡改备份改写结构层），这不算往返失败；
    # 但共享层若被导入，必须与源一致；本地层必须完整往返。
    m = A.open(A.tmpdb("rt"))
    ids = []
    for _ in range(rnd.randint(2, 10)):
        lay = rnd.choice(["knowledge", "knowledge", "context", "structure", "anchor"])
        c = sentence(rnd)
        tags = [rnd.choice(["t1", "标签二", "x_y", "a%b"])] if rnd.random() < 0.6 else None
        if lay == "knowledge":
            ids.append(m.add(c, importance=round(rnd.random(), 3), tags=tags, skip_dedup=True))
        elif lay == "context":
            ids.append(m.add(c, layer="context", tags=tags))
        else:
            ids.append(m.add(c, layer=lay))
    for _ in range(rnd.randint(0, 8)):
        a, b = rnd.sample(ids, 2) if len(ids) > 1 else (ids[0], ids[0])
        m.add_edge(a, b, rnd.choice(["causal", "similar", "sequential"]), round(rnd.random(), 3))
    LOCAL = ("knowledge", "context")

    def view(mm):
        nodes = {x["id"]: x for x in mm.all_nodes(10 ** 6)
                 if x["layer"] != "self" and not x["content"].startswith("[consolidation]")}
        edges = set()
        for nid in nodes:
            for e in mm.edges_of(nid):
                if e["src"] in nodes and e["dst"] in nodes:
                    edges.add((nodes[e["src"]]["content"], nodes[e["dst"]]["content"], e["rel"], round(e["confidence"], 6)))
        return nodes, edges

    def nsig(x):
        return (x["content"], x["layer"], round(x["importance"], 6), tuple(sorted(x["tags"])))
    n0, e0 = view(m)
    p = A.tmpfile(f"rt{rnd.random()}.json")
    m.export(p)
    m2 = A.open(A.tmpdb("rt2"))
    m2.import_(p)
    n1, e1 = view(m2)
    loc0 = sorted(nsig(x) for x in n0.values() if x["layer"] in LOCAL)
    loc1 = sorted(nsig(x) for x in n1.values() if x["layer"] in LOCAL)
    if loc0 != loc1:
        diff = set(loc0) ^ set(loc1)
        return f"本地层签名不等，差 {len(diff)} 项，如 {sorted(diff, key=str)[:1]}"
    sh0 = {nsig(x) for x in n0.values() if x["layer"] not in LOCAL}
    sh1 = {nsig(x) for x in n1.values() if x["layer"] not in LOCAL}
    if not sh1 <= sh0:
        return f"共享层被改写/凭空出现 {len(sh1 - sh0)} 条，如 {sorted(sh1 - sh0, key=str)[:1]}"
    present = {x["content"] for x in n1.values()}
    want = {e for e in e0 if e[0] in present and e[1] in present}
    if want != e1:
        return f"两端都已导入的边不等：期望 {len(want)} 条，实得 {len(e1)} 条"


def _brute_cycles(n, edges):
    """暴力枚举有向简单环（含自环），以最小顶点为起点规范化。"""
    E = set(edges)
    out = set()
    for a, b in E:
        if a == b:
            out.add((a,))
    for k in range(2, n + 1):
        for sub in itertools.combinations(range(n), k):
            s0 = sub[0]
            for perm in itertools.permutations(sub[1:]):
                cyc = (s0,) + perm
                if all((cyc[i], cyc[(i + 1) % k]) in E for i in range(k)):
                    out.add(cyc)
    return out


@prop("P07-cycle-vs-brute", "环检测与暴力枚举一致：has_cycle 判定 + find_cycles 计数（n≤6）")
def _(A, rnd):
    m = A.open()
    n = rnd.randint(1, 6)
    ids = [m.add(f"环节点{i}号{rnd.random()}", skip_dedup=True) for i in range(n)]
    p = rnd.choice([0.1, 0.2, 0.35])
    edges = [(i, j) for i in range(n) for j in range(n) if rnd.random() < p and (i != j or rnd.random() < 0.3)]
    for i, j in edges:
        m.add_edge(ids[i], ids[j], "causal", 0.6)
    truth = _brute_cycles(n, edges)
    h = m.has_cycle()
    if h != bool(truth):
        return f"has_cycle={h} 而真值环数={len(truth)}（边={edges}）"
    got = m.cycles(max_depth=n + 1)
    if len(got) != len(truth):
        return f"find_cycles 报 {len(got)} 个，真值 {len(truth)}（边={edges}）"


@prop("P08-concurrent-no-loss", "并发写不丢：3 线程各写 8 条唯一内容，全部恰好落库一次")
def _(A, rnd):
    m = A.open(A.tmpdb("cc"))
    tag = f"并发{rnd.randint(0, 10 ** 9)}"
    errs = []

    def w(t):
        for i in range(8):
            try:
                m.add(f"{tag} 线程{t} 第{i}条 {rnd.random()}", skip_dedup=True)
            except Exception as ex:
                errs.append(type(ex).__name__)
    ts = [threading.Thread(target=w, args=(t,)) for t in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    n = sum(1 for x in m.all_nodes(10 ** 5) if x["content"].startswith(tag))
    if errs or n != 24:
        return f"落库 {n}/24，异常={errs[:3]}"


@prop("P09-nonfinite-rejected", "非有限数值（NaN/±inf）不进库：要么被拒，要么不以非有限值存储")
def _(A, rnd):
    m = A.open()
    v = rnd.choice([float("nan"), float("inf"), float("-inf")])
    which = rnd.choice(["importance", "context", "edge", "trust", "verify_edge"])
    try:
        if which == "importance":
            x = m.get(m.add(sentence(rnd), importance=v, skip_dedup=True))["importance"]
        elif which == "context":
            x = m.get(m.add(sentence(rnd), layer="context", importance=v))["importance"]
        elif which == "edge":
            a, b = m.add(sentence(rnd), skip_dedup=True), m.add(sentence(rnd), skip_dedup=True)
            x = m.get_edge(m.add_edge(a, b, "causal", v))["confidence"]
        elif which == "verify_edge":
            a, b = m.add(sentence(rnd), skip_dedup=True), m.add(sentence(rnd), skip_dedup=True)
            e = m.add_edge(a, b, "causal", 0.5)
            m.verify_edge(e, v)
            x = m.get_edge(e)["confidence"]
        else:
            m.update_trust(v, 1)
            x = m.self_state()["t_total"]
    except (ValueError, TypeError):
        return None
    if not (isinstance(x, (int, float)) and math.isfinite(x)):
        return f"{which}={v} 存为 {x!r}"


@prop("P10-recall-no-self", "检索不返回 SELF 快照")
def _(A, rnd):
    m = A.open()
    for _ in range(rnd.randint(1, 4)):
        m.add(sentence(rnd))
    q = rnd.choice(WORDS)
    for i in range(rnd.randint(1, 6)):
        if rnd.random() < 0.5:
            m.update_self({"current_goal": f"{q}{sentence(rnd, 2)}"})
        else:
            m.update_trust(round(rnd.random(), 3), i)
    r = m.recall(q, limit=20) + m.recall("信任", limit=20)
    s = [n["id"] for n, _ in r if n["layer"] == "self"]
    if s:
        return f"recall 返回 SELF 节点 {len(s)} 个"


@prop("P11-sub-no-protected-write", "SUB 角色不可改写受保护层（锚点/结构）的节点与边")
def _(A, rnd):
    db = A.tmpdb("sub")
    P = A.open(db)
    S = A.open(db, role="sub")
    a = P.add(sentence(rnd), layer="structure")
    b = P.add(sentence(rnd), layer=rnd.choice(["structure", "anchor"]))
    eid = P.add_edge(a, b, "causal", 0.9)

    def snap():
        xa, xb = P.get(a), P.get(b)
        e = P.get_edge(eid)
        return (xa and (xa["content"], xa["layer"], round(xa["importance"], 6), round(xa["confidence"], 6), tuple(xa["tags"])),
                xb and (xb["content"], xb["layer"], round(xb["importance"], 6)),
                e and (e["src"], e["dst"], e["rel"], round(e["confidence"], 6), e["verified"]),
                len(P.edges_of(a)), a in P.protected())
    s0 = snap()
    ops = [lambda: S.add(sentence(rnd), layer="structure"),
           lambda: S.put_raw_node(a, "篡改", "knowledge"),
           lambda: S.delete(a),
           lambda: S.set_importance_delta(a, -0.3),
           lambda: S.set_confidence_delta(a, -0.3),
           lambda: S.verify_edge(S.add_edge(a, b, "opposite", 0.9), 1.0),
           lambda: S.replace_edge(eid, b, a, "opposite"),
           lambda: S.tag(a, "promotion_pending"),
           lambda: S.protect(a, "sub")]
    tried = []
    for k in rnd.sample(range(len(ops)), rnd.randint(1, 3)):
        tried.append(k)
        try:
            ops[k]()
        except (PermissionError, ValueError):
            pass
    s1 = snap()
    if s1 != s0:
        return f"SUB 操作 {tried} 后共享层发生变化"


@prop("P12-importance-range", "importance 写入后恒在 [0,1]（越界值被拒或钳制）")
def _(A, rnd):
    m = A.open()
    v = rnd.choice([rnd.uniform(-10, 0), rnd.uniform(1, 1e6), rnd.random()])
    lay = rnd.choice(["knowledge", "context"])
    try:
        x = m.get(m.add(sentence(rnd), layer=lay, importance=v))["importance"]
    except ValueError:
        return None
    if not finite01(x):
        return f"{lay} importance={v:.3f} 存为 {x}"


@prop("P13-tag-exact", "按标签检索精确匹配（含 _ % 中文 前缀相同的标签）")
def _(A, rnd):
    m = A.open()
    pool = ["ent:car_1", "ent:car_12", "ent:carX1", "cycle:c1", "cycle:c10", "苹果", "苹果派", "a%b", "a_b", "axb"]
    owners = {}
    for i in range(rnd.randint(3, 8)):
        t = rnd.choice(pool)
        nid = m.add(f"带标签的情境 {i} {rnd.random()}", layer="context", tags=[t])
        owners.setdefault(t, set()).add(nid)
    t = rnd.choice(list(owners))
    got = {x["id"] for x in m.by_tag(t)}
    if got != owners[t]:
        return f"by_tag({t!r}) 返回 {len(got)}，真值 {len(owners[t])}"


@prop("P14-gate-receipt", "门控回执层 = 实际落库层（任意 hint）")
def _(A, rnd):
    m = A.open()
    for _ in range(rnd.randint(0, 3)):
        m.add(sentence(rnd))
    hint = rnd.choice([None, round(rnd.random(), 2)])
    r = m.gate_write(sentence(rnd), hint=hint)
    nid = r.get("node_id")
    if not nid:
        return None if (r.get("status") == "discarded" or r.get("layer") == "discarded") else f"无 node_id 回执 {r}"
    real = m.get(nid)
    if real is None:
        return f"回执 {r.get('layer')} 但节点不存在"
    rec = r.get("stored_layer") or r.get("layer")
    if rec == "long_term" and real["layer"] == "knowledge":
        return None
    if rec != real["layer"]:
        return f"hint={hint} 回执 {rec} 实际 {real['layer']}"


@prop("P15-protected-survive", "被 protect 的节点在衰减/容量淘汰/遗忘建议后仍存在")
def _(A, rnd):
    m = A.open()
    pid = m.add(sentence(rnd), layer=rnd.choice(["context", "knowledge"]), importance=rnd.random() * 0.3)
    m.protect(pid, "性质测试")
    for _ in range(rnd.randint(2, 8)):
        op = rnd.choice(["decay", "cap", "forget", "consolidate"])
        if op == "decay":
            m.decay(rnd.randint(10, 80), factor=0.1)
        elif op == "cap":
            m.set_context_cap(rnd.randint(1, 3))
            for _ in range(4):
                m.add(sentence(rnd), layer="context")
        elif op == "forget":
            m.forget_advisor()
        else:
            m.consolidate()
    if m.get(pid) is None:
        return "受保护节点被删除"


# ---------------------------------------------------------------------------

def run_prop(pid, impl, seeds, budget=None):
    spec = PROPS[pid]
    A = Adapter(impl)
    viol, exc, first = 0, {}, None
    na = None
    done = 0
    t0 = time.perf_counter()
    for s in range(seeds):
        rnd = random.Random(s * 1000003 + 17)
        try:
            r = spec["fn"](A, rnd)
        except NA as ex:
            na = str(ex)
            break
        except Exception as ex:
            r = f"异常 {type(ex).__name__}: {str(ex)[:80]}"
            exc[type(ex).__name__] = exc.get(type(ex).__name__, 0) + 1
        done += 1
        if r is not None:
            viol += 1
            if first is None:
                first = {"seed": s, "detail": str(r)[:200]}
        if budget and time.perf_counter() - t0 > budget:
            break
    if na is not None and done == 0:
        return {"verdict": "NA", "reading": na}
    rate = viol / max(done, 1)
    return {"verdict": "OK" if viol == 0 else "VIOL", "violations": viol, "seeds": done,
            "rate": round(rate, 4), "exceptions": exc, "first": first,
            "reading": f"{viol}/{done} 违反" + (f"；首例 seed={first['seed']}: {first['detail']}" if first else "")}
