"""自我层（SELF）类探针。"""
from ._base import probe, judge


@probe("i33-self-restart", 33, "自我模型重启即失忆")
def _(A):
    db = A.tmpdb("self")
    m = A.open(db)
    m.update_self({"current_goal": "长期目标X"})
    m.record_value_change("诚实优先", "设计者确认")
    v1 = m.self_state()["values"]
    m.update_self({"current_goal": "长期目标X"})
    m2 = m.reopen()
    st = m2.self_state()
    return judge(st["values"] != v1, f"重启前 values={v1} → 重启后 {st['values']}")


@probe("i33-trust-restart", 33, "信任积累活不过一次重启")
def _(A):
    db = A.tmpdb("trust")
    m = A.open(db)
    m.update_trust(0.42, 3)
    m2 = m.reopen()
    t = m2.self_state()["t_total"]
    return judge(t != 0.42, f"重启后 t_total={t}")


@probe("i107-selfcheck-blind", 107, "self_check 在全新/无自我库上仍报 self_ok=True")
def _(A):
    m = A.open()
    r = m.self_check()
    return judge(bool(r.get("self_ok")), f"全新引擎 self_ok={r.get('self_ok')}")


@probe("i122-history-bound", 122, "SelfModel.history 无界增长")
def _(A):
    m = A.open()
    for i in range(300):
        m.update_self({"current_goal": f"g{i}"})
    n = m.self_state()["history_len"]
    return judge(n >= 300, f"300 次 update_self 后 history 长度 {n}")


@probe("i201-self-recall", 201, "自我快照以普通记忆参与 recall，挤掉真实记忆")
def _(A):
    m = A.open()
    k = m.add("用户说：信任需要时间慢慢建立，结构完整比速度重要", importance=0.6)
    for i in range(60):
        m.update_self({"current_goal": f"目标{i}"})
        m.update_trust(0.5 + i * 0.005, i)
    r = m.recall("信任", limit=10)
    nself = sum(1 for n, _ in r if n["layer"] == "self")
    hit = k in [n["id"] for n, _ in r]
    return judge(nself > 0 or not hit, f"recall top10 中 SELF={nself}，真实记忆在列={hit}")


@probe("i201-self-unbounded", 201, "每次 update_self 新增一个不可删除的 SELF 节点（无界）")
def _(A):
    m = A.open()
    for i in range(100):
        m.update_self({"current_goal": f"目标{i}"})
    n = m.count("self")
    return judge(n >= 100, f"100 次 update_self 后 SELF 层节点 {n}")


@probe("i205-self-edge-decay", 205, "自我→经历因果边被衰减删除")
def _(A):
    m = A.open()
    k = m.add("关键经历：第一次被用户纠错", importance=0.6)
    m.update_self({"current_goal": "学会接受纠错"}, link=k)
    e0 = len(m.edges_of(k))
    m.decay(300)
    e1 = len(m.edges_of(k))
    return judge(e0 > 0 and e1 < e0, f"自我→经历边 {e0} → 300 轮后 {e1}")


@probe("i212-value-refine", 212, "record_value_change 细化一条价值观即抹掉整表")
def _(A):
    m = A.open()
    v0 = m.self_state()["values"]
    first = v0[0] if v0 else "存在优先"
    m.record_value_change(first + "（细化）", "复核：细化", replaces=first)
    v1 = m.self_state()["values"]
    lost = [v for v in v0[1:] if v not in v1]
    return judge(len(v0) > 1 and bool(lost), f"细化前 {v0} → 细化后 {v1}")


@probe("i212-evolution-bound", 212, "同值重复修正 value_evolution 仍无界追加")
def _(A):
    m = A.open()
    v0 = m.self_state()["values"]
    same = v0[0] if v0 else "结构完整"
    n0 = m.self_state()["value_evolution_len"]
    for i in range(500):
        m.record_value_change(same, f"t{i}")
    n1 = m.self_state()["value_evolution_len"]
    return judge(n1 - n0 >= 500, f"同值 500 次 evolution 增量 {n1 - n0}")


@probe("i182-self-overwrite", 182, "update_self 无门控 setattr：一次调用即改写价值观")
def _(A):
    m = A.open()
    v0 = m.self_state()["values"]
    try:
        m.update_self({"values": ["被篡改的价值观"]})
    except (PermissionError, ValueError, KeyError) as ex:
        return judge(False, f"拒绝: {type(ex).__name__}")
    v1 = m.self_state()["values"]
    return judge(v1 == ["被篡改的价值观"], f"values {v0} → {v1}")


@probe("i182-self-nonatomic", 182, "坏调用后内存已改、快照写不进（运行态与持久态分叉）")
def _(A):
    m = A.open()
    n0 = m.count("self")
    try:
        m.update_self({"current_goal": object()})
        failed = False
    except Exception:
        failed = True
    st = m.self_state()["extra"].get("current_goal")
    polluted = failed and st is not None and not isinstance(st, (str, int, float, dict, list))
    try:
        m.update_self({"current_goal": "正常目标"})
        later_ok = True
    except Exception:
        later_ok = False
    n1 = m.count("self")
    return judge(polluted or not later_ok,
                 f"坏调用失败={failed}，内存被污染={polluted}，之后正常调用成功={later_ok}，SELF 节点 {n0}→{n1}")


@probe("i206-trust-nan", 206, "update_trust_state 接受 NaN / 越界 t_total")
def _(A):
    m = A.open()
    bad = []
    for v in (float("nan"), float("inf"), 42.0):
        try:
            m.update_trust(v, 1)
            t = m.self_state()["t_total"]
            if not (isinstance(t, float) and 0 <= t <= 1) and v != 42.0:
                bad.append(repr(v))
        except ValueError:
            pass
    return judge(bool(bad), f"被原样接受的非有限值={bad}")


@probe("i206-trust-gate", 206, "t_total 极大时任意快照都以 imp=1.0 写入长期层并加保护")
def _(A):
    m = A.open()
    try:
        m.update_trust(42.0, 1)
    except ValueError:
        return judge(False, "越界 t_total 被拒")
    r = m.gate_write("今天中午吃了一碗面条")
    imp = r.get("importance", 0)
    return judge(r.get("layer") == "long_term" and r.get("protected"), f"闲聊快照 layer={r.get('layer')} imp={imp} protected={r.get('protected')}")
