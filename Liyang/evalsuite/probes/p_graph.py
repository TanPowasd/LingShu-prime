"""因果图 / 环检测 / 激活 / 子图替换类探针。"""
import random
import time

from ._base import probe, judge, deadline


def _mk(m, n):
    return [m.add(f"事件节点{i}：独立观察记录{i * 7919}", skip_dedup=True) for i in range(n)]


@probe("i145-long-chain", 145, "reason_causal 链长超过 max_depth 时返回 0 条")
def _(A):
    m = A.open()
    ids = _mk(m, 8)
    for a, b in zip(ids, ids[1:]):
        m.add_edge(a, b, "causal")
    n = len(m.reason(ids[0], max_depth=5))
    return judge(n == 0, f"7 步链 max_depth=5 → {n} 条（应返回截断链而不是全丢）")


@probe("i145-cycle-branch", 145, "reason_causal 遇环的分支整条丢弃")
def _(A):
    m = A.open()
    a, b, c, d = _mk(m, 4)
    m.add_edge(a, b, "causal")
    m.add_edge(b, c, "causal")
    m.add_edge(c, b, "causal")
    m.add_edge(b, d, "causal")
    ch = m.reason(a, max_depth=5)
    reach_c = any(any(getattr(e, "target_id", None) == c for e in chain) for chain in ch)
    return judge(not reach_c, f"返回 {len(ch)} 条链，含到环上节点 c 的链={reach_c}")


@probe("i145-two-cycle", 145, "find_cycles 漏报 2 环 A⇄B")
def _(A):
    m = A.open()
    a, b = _mk(m, 2)
    m.add_edge(a, b, "causal")
    m.add_edge(b, a, "causal")
    n = len(m.cycles(10))
    return judge(n == 0, f"A⇄B 报环 {n} 个")


@probe("i145-self-loop", 145, "find_cycles 漏报自环")
def _(A):
    m = A.open()
    (a,) = _mk(m, 1)
    m.add_edge(a, a, "causal")
    n = len(m.cycles(10))
    return judge(n == 0, f"自环报环 {n} 个")


@probe("i145-dup-report", 145, "同一个环被每个节点重复报告")
def _(A):
    m = A.open()
    ids = _mk(m, 4)
    for i in range(4):
        m.add_edge(ids[i], ids[(i + 1) % 4], "causal")
    n = len(m.cycles(10))
    return judge(n != 1, f"唯一 4 环报 {n} 个")


@probe("i215-cycle-consistency", 215, "环长 > max_depth 时 has_cycle=True 而 self_check 报 0")
def _(A):
    m = A.open()
    ids = _mk(m, 30)
    for i in range(29):
        m.add_edge(ids[i], ids[i + 1], "causal")
    m.add_edge(ids[11], ids[0], "causal")
    h = m.has_cycle()
    sc = m.self_check().get("cycles_found")
    return judge(h and not sc, f"has_cycle={h}，self_check cycles_found={sc}")


@probe("i215-selfcheck-time", 215, "有环稠密图 self_check 仍整趟深搜（45 节点/211 边）")
def _(A):
    m = A.open()
    ids = _mk(m, 45)
    rnd = random.Random(1)
    seen = set()
    while len(seen) < 211:
        a, b = rnd.sample(range(45), 2)
        if (a, b) not in seen:
            seen.add((a, b))
            m.add_edge(ids[a], ids[b], "causal")
    fin, r, dt = deadline(m.self_check, 10)
    return judge((not fin) or dt > 0.5, f"self_check 用时 {dt:.2f}s 完成={fin}")


@probe("i252-dense-scc", 252, "11 节点互为因果：self_check 全枚举（14s/3GB）")
def _(A):
    m = A.open()
    ids = _mk(m, 11)
    for a in ids:
        for b in ids:
            if a != b:
                m.add_edge(a, b, "causal", 0.6)
    fin, r, dt = deadline(m.self_check, 8)
    import os
    if not fin:
        print("BUG", "self_check 8s 未完成", flush=True)
        os._exit(0)
    return judge(dt > 1.0, f"self_check 用时 {dt:.2f}s")


@probe("i252-find-cycles-budget", 252, "find_cycles 在稠密 SCC 上无预算（9 节点完全图）")
def _(A):
    m = A.open()
    ids = _mk(m, 9)
    for a in ids:
        for b in ids:
            if a != b:
                m.add_edge(a, b, "causal", 0.6)
    fin, r, dt = deadline(lambda: m.cycles(8), 8)
    import os
    if not fin:
        print("BUG", "find_cycles 8s 未完成", flush=True)
        os._exit(0)
    return judge(dt > 2.0, f"find_cycles 用时 {dt:.2f}s，返回 {len(r) if isinstance(r, list) else r}")


# ---------------- 激活 ----------------

def _act_db(A, n_nodes=4, edges=True):
    m = A.open(A.tmpdb("act"))
    ids = [m.add(f"激活测试节点{i}：主题{'ABCD'[i % 4]}内容", skip_dedup=True) for i in range(n_nodes)]
    if edges:
        for a, b in zip(ids, ids[1:]):
            m.add_edge(a, b, "causal", 0.8)
    return m, ids


@probe("i95-activation-empty-graph", 95, "空认知图默认 hops=2 激活抛 ValueError")
def _(A):
    m = A.open(A.tmpdb("act0"))
    try:
        r = m.activate("任意查询", hops=2)
    except ValueError as ex:
        return judge(True, f"ValueError: {ex}")
    return judge(False, f"空图激活 size={r.get('size')}")


@probe("i199-activation-empty-query", 199, "空查询把全图节点当满分种子")
def _(A):
    m, ids = _act_db(A)
    r = m.activate("", hops=0)
    return judge(r.get("seeds", 0) > 0, f"空查询 seeds={r.get('seeds')}")


@probe("i161-activation-space-query", 161, "纯空格查询命中全部节点")
def _(A):
    m, ids = _act_db(A)
    r = m.activate(" ", hops=0)
    return judge(r.get("seeds", 0) > 0, f"空格查询 seeds={r.get('seeds')}")


@probe("i126-activation-cache", 126, "激活引擎图缓存不刷新：新增节点被丢弃")
def _(A):
    m, ids = _act_db(A)
    m.activate("激活测试节点", hops=1)
    nid = m.add("新增节点：绝无仅有词元 QWZX", skip_dedup=True)
    m.add_edge(ids[0], nid, "causal", 0.8)
    r = m.activate("QWZX", hops=1)
    top = [x[0] for x in r.get("top", [])]
    return judge(nid not in top, f"新增节点在激活结果={nid in top}，seeds={r.get('seeds')}")


@probe("i229-activation-opposite", 229, "OPPOSITE（矛盾）边按兴奋传导，被反驳结论激活")
def _(A):
    m = A.open(A.tmpdb("act_opp"))
    old = m.add("旧结论：服务器内存足够无需扩容", skip_dedup=True)
    evs = [m.add(f"证据{i}：监控显示内存使用率 9{i}% 告警 KQV", skip_dedup=True) for i in range(3)]
    for e in evs:
        m.conflict(e, old)
    r = m.activate("KQV", hops=2)
    acts = dict(r.get("top", []))
    return judge(acts.get(old, 0) > 0, f"被三条证据反驳的旧结论激活值={acts.get(old, 0)}")


# ---------------- 子图替换 ----------------

def _tree(m):
    p = m.add("父部件：汽车", skip_dedup=True)
    old = m.add("子部件：旧车轮", skip_dedup=True)
    leaf = m.add("子部件：旧轮毂", skip_dedup=True)
    m.add_edge(old, p, "hierarchical", 0.9)
    m.add_edge(leaf, old, "hierarchical", 0.9)
    return p, old, leaf


@probe("i139-replace-nonatomic", 139, "subgraph_replace 新子树缺键时旧子树已被删（非原子）")
def _(A):
    m = A.open()
    p, old, leaf = _tree(m)
    try:
        m.subgraph_replace(p, old, {"content": "新车轮（缺 id）"})
    except Exception:
        pass
    return judge(m.get(old) is None, f"失败后旧子树根仍在={m.get(old) is not None}")


@probe("i139-replace-parent", 139, "old_sub_root_id==parent_id 时父节点自身被删")
def _(A):
    m = A.open()
    p, old, leaf = _tree(m)
    try:
        m.subgraph_replace(p, p, {"id": "new_root", "content": "新子树"})
    except (ValueError, LookupError):
        return judge(False, "被拒")
    return judge(m.get(p) is None, f"父节点仍在={m.get(p) is not None}")


@probe("i139-replace-protected", 139, "subgraph_replace 级联删除受保护节点")
def _(A):
    m = A.open()
    p, old, leaf = _tree(m)
    m.protect(leaf, "保护")
    try:
        m.subgraph_replace(p, old, {"id": "new_root2", "content": "新车轮"})
    except (ValueError, PermissionError):
        return judge(m.get(leaf) is None, "被拒")
    return judge(m.get(leaf) is None, f"受保护叶子仍在={m.get(leaf) is not None}")
