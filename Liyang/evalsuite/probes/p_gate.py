"""长期门控 / 新奇度 / 技能 / 反思 / 子模块契约类探针。"""
import sys

from ._base import probe, judge
from adapters import submodule, NA, Adapter


# ---------------- 长期门控 ----------------

@probe("i224-receipt-layer", 224, "write_snapshot 回执 layer 与实际落库层不一致")
def _(A):
    m = A.open()
    bad = []
    for hint, text in ((0.2, "周三下午三点和导师讨论开题报告的修改意见"), (0.9, "实验室服务器的备份策略改为每日增量每周全量"),
                       (0.5, "组会改到每周四上午十点")):
        r = m.gate_write(text, hint=hint)
        nid = r.get("node_id")
        if not nid:
            continue
        real = m.get(nid)["layer"]
        rec = r.get("stored_layer") or r.get("layer")
        if rec == "long_term":
            rec = "knowledge" if real == "knowledge" else rec
        if rec != real:
            bad.append(f"hint={hint}: 回执 {r.get('layer')}/{r.get('stored_layer')} 实际 {real}")
    return judge(bool(bad), "; ".join(bad) or "回执与落库一致")


@probe("i224-context-hit", 224, "快照命中情境层旧节点报 long_term+protected，节点仍留在情境层被删")
def _(A):
    m = A.open()
    c = m.add("服务器 root 密码轮换周期改为 30 天", layer="context")
    r = m.gate_write("服务器 root 密码轮换周期改为 30 天", hint=0.9)
    m.set_context_cap(2)
    for i in range(3):
        m.add(f"闲聊 {i}", layer="context")
    x = m.get(c)
    return judge(x is None or x["layer"] == "context", f"回执 {r.get('layer')}，旧情境节点现状={x and x['layer']}")


@probe("i114-gate-unreachable", 114, "默认 t_total=0 时全新内容快照一律 discarded / 长期层不可达")
def _(A):
    m = A.open()
    outs = [m.gate_write(f"全新且重要的事实 {i}：生产集群迁移到新机房 R{i * 13}") for i in range(5)]
    st = [o.get("status") or o.get("layer") for o in outs]
    return judge(all(s == "discarded" for s in st), f"5 条全新快照状态={st}")


@probe("i44-gate-links", 44, "长期层关联边从未建成（links 恒 0）")
def _(A):
    m = A.open()
    m.add("实验室服务器的备份策略改为每日增量", skip_dedup=True)
    m.add("实验室服务器的备份策略需要监控", skip_dedup=True)
    r = m.gate_write("实验室服务器的备份策略改为每日增量每周全量", hint=0.9)
    nid = r.get("node_id")
    edges = m.edges_of(nid) if nid else []
    return judge(r.get("links", 0) == 0 and not edges, f"links={r.get('links')}，实际边={len(edges)}")


@probe("i213-novelty-english", 213, "新奇检测对英文/代码/西里尔失明（恒 0.5）")
def _(A):
    m = A.open()
    m.add("水在标准大气压下一百度沸腾。")
    vs = {s[:14]: round(m.novelty(s), 3) for s in
          ["The production database password was rotated today", "rm -rf /var/lib/postgresql/data", "Москва столица России"]}
    return judge(any(v < 0.75 for v in vs.values()), f"首见新奇度={vs}")


@probe("i213-novelty-repeat-en", 213, "英文内容重复仍判 0.5（无法识别已知）")
def _(A):
    m = A.open()
    s = "The production database password was rotated today"
    m.add(s, skip_dedup=True)
    v = m.novelty(s)
    return judge(v > 0.25, f"重复英文新奇度={v:.3f}")


@probe("i213-novelty-identifier", 213, "只改数字/标识符（收款账号、IP）被判完全已知")
def _(A):
    out = {}
    for old, new in [("收款账户改为 6222020200112233", "收款账户改为 6222029999999999"),
                     ("服务器IP改为10.0.0.4", "服务器IP改为10.0.0.5")]:
        m = A.open()
        m.add(old, skip_dedup=True)
        out[new[-6:]] = round(m.novelty(new), 3)
    return judge(any(v < 0.75 for v in out.values()), f"新奇度={out}")


@probe("i48-novelty-window", 48, "新奇度只看 top-80：较老的既有知识被判为新")
def _(A):
    m = A.open()
    target = "六边形蜂窝网格的等距邻居编码方式"
    m.add(target, importance=0.2, skip_dedup=True)
    for i in range(200):
        m.add(f"无关知识第{i}条：关于不同主题{i * 37}的说明", importance=0.5, skip_dedup=True)
    v = m.novelty(target)
    return judge(v > 0.5, f"已存在内容的新奇度={v:.3f}")


@probe("i214-promote-context", 214, "情境层→知识层巩固通路不存在（维护周期从不提升）")
def _(A):
    m = A.open()
    c = m.add("用户的过敏史：青霉素过敏，务必提醒医生", layer="context", importance=0.9)
    for _ in range(3):
        m.maintenance()
    x = m.get(c)
    return judge(x is None or x["layer"] == "context", f"3 次维护后层={x and x['layer']}")


@probe("i83-provenance-gate", 83, "显式来源被 gate/novel_prefeed 覆盖（user→fixture）")
def _(A):
    pv = submodule(A, "provenance")
    p = pv.new_provenance("测试台", "dsh", "user", observed_at=1234567890)
    q = pv.from_legacy(p.to_tags(["gate"]), condition_space=p.to_condition_space())
    return judge(q.source != "user", f"往返后 source={q.source}")


@probe("i146-provenance-roundtrip", 146, "to_tags 的 verify_methods / vref 凭证读不回（strong→weak）")
def _(A):
    pv = submodule(A, "provenance")
    p = pv.new_provenance("测试台", "bench_fixture", "fixture", verify_status="partial",
                          verify_methods=["whitebox_code", "action_world"], verify_ref="test://ref1")
    q = pv.from_legacy(p.to_tags(), condition_space=p.to_condition_space())
    return judge(q.strength() != p.strength(), f"强度 {p.strength()}→{q.strength()}")


@probe("i20-provenance-human-review", 20, "from_legacy 永远推不出 human_review")
def _(A):
    pv = submodule(A, "provenance")
    p = pv.new_provenance("测试台", "dsh", "user", session_id="s1", verify_status="partial",
                          verify_methods=["human_review"], verify_ref="review://1")
    q = pv.from_legacy(p.to_tags(), condition_space=p.to_condition_space())
    return judge("human_review" not in (q.verify_methods or []), f"往返后 methods={q.verify_methods}")


@probe("i138-cond-unasserted", 138, "非法/带空格的条件值静默折叠为 UNASSERTED，同 cond_hash")
def _(A):
    cn = submodule(A, "condition_normalize")
    base = {"subject": "人物", "style": "动漫"}
    try:
        same = cn.cond_hash({"subject": "人物"}) == cn.cond_hash({**base, "style": "油画"})
    except ValueError:
        return judge(False, "非法值被拒")
    return judge(same, f"非法 style 与未声明同哈希={same}")


@probe("i180-cred-step", 180, "cred_step 与 cred_factor 语义反转，混用单步归零")
def _(A):
    tc = submodule(A, "time_core")
    x1 = tc.cred_step(100.0, tc.cred_factor(0.1, 1.0))
    return judge(x1 < 50, f"cred_step(100, cred_factor(0.1,1)) = {x1:.3f}（期望 ≈90.48）")


@probe("i7-numpy-free", 7, "core 轻核承诺：屏蔽 numpy 后 activation 模块不可导入", raw=True)
def _(impl):
    sys.modules["numpy"] = None
    for k in list(sys.modules):
        if k.startswith("lingshu"):
            del sys.modules[k]
    try:
        A = Adapter(impl)
    except NA as ex:
        if "numpy" in str(ex):
            return judge(True, f"主模块导入即失败: {ex}")
        raise
    try:
        A.activation_engine(A.tmpdb("np"))
    except NA as ex:
        if "numpy" in str(ex):
            return judge(True, f"激活模块: {ex}")
        raise
    except ImportError as ex:
        return judge(True, f"激活模块: {ex}")
    except Exception as ex:
        return judge(True, f"激活模块: {type(ex).__name__}: {ex}")
    return judge(False, "无 numpy 可用")


# ---------------- 技能 ----------------

@probe("i200-skill-substring", 200, "record_action_sequence 用子串把『备份』追加进『删除备份』")
def _(A):
    m = A.open()
    m.store_skill("删除备份", "清理过期备份", "rm -rf /backup/old")
    m.record_skill(["tar czf db.tgz /data", "scp db.tgz nas:/backup"], "ok", True, hint="备份")
    d = [s for s in m.skills("") if s["name"] == "删除备份"][0]
    return judge(d["procedure"] != "rm -rf /backup/old" or d["confidence"] > 0.5 + 1e-9,
                 f"删除备份 程序={d['procedure'][:40]!r} conf={d['confidence']:.2f}")


@probe("i200-skill-wildcard", 200, "技能检索 hint 含 _ / % 命中任意技能")
def _(A):
    m = A.open()
    m.store_skill("删除备份", "清理过期备份", "rm -rf /backup/old")
    hit = [s["name"] for s in m.skills("_", 5)] + [s["name"] for s in m.skills("%", 5)]
    return judge(bool(hit), f"'_'/'%' 命中 {hit}")


@probe("i200-skill-failure", 200, "技能失败从不降信（50 败 10 胜置信度仍高）")
def _(A):
    m = A.open()
    for ok, n in ((False, 50), (True, 10)):
        for _ in range(n):
            m.record_skill(["deploy"], "x", ok, hint="部署")
    sk = [s for s in m.skills("") if s["name"] == "部署"]
    if not sk:
        return judge(False, "未提取技能")
    c = sk[0]["confidence"]
    return judge(c >= 0.5, f"50 败 10 胜 confidence={c:.2f}")


@probe("i216-skill-from-failures", 216, "同一失败犯 21 次，技能照常提取 / 负记忆不参与")
def _(A):
    m = A.open()
    for _ in range(21):
        m.record_skill(["rm -rf /", "reboot"], "系统崩溃", False, hint="清理磁盘")
    m.record_skill(["rm -rf /", "reboot"], "碰巧成功", True, hint="清理磁盘")
    sk = [s for s in m.skills("") if s["name"] == "清理磁盘"]
    c = sk[0]["confidence"] if sk else 0.0
    return judge(bool(sk) and c >= 0.5, f"技能存在={bool(sk)} conf={c:.2f}")


@probe("i216-failure-importance", 216, "失败经验 importance 低于成功（负记忆不同价）")
def _(A):
    m = A.open()
    s = m.record_skill(["部署 v1"], "成功上线", True)
    f = m.record_skill(["部署 v2 跳过测试"], "线上事故回滚", False)
    si, fi = m.get(s)["importance"], m.get(f)["importance"]
    return judge(fi < si, f"成功 importance={si} 失败={fi}")


# ---------------- 反思 ----------------

@probe("i154-reflect-self-evidence", 154, "recursive_reflect 把自己的归档当证据：第二次起偏差恒 False")
def _(A):
    m = A.open()
    c = "生产数据库凌晨三点自动备份已经连续两周失败"
    devs = [m.reflect(c).get("verification", {}).get("deviation") for _ in range(3)]
    return judge(devs[0] != devs[1], f"三次 deviation={devs}")


@probe("i154-reflect-negation", 154, "可逆性按子串判：『不删除』判为不可逆+需设计者")
def _(A):
    m = A.open()
    r = m.reflect("只读取配置，不删除任何文件")
    tj = r.get("terminal_judgment") or r.get("judgment") or {}
    nd = tj.get("needs_designer") if isinstance(tj, dict) else None
    if nd is None:
        nd = r.get("needs_designer")
        if nd is None:
            nd = "不可逆" in str(r)
    return judge(bool(nd), f"needs_designer={nd}")


@probe("i130-reflect-escalation", 130, "反思判出需设计者后不调用升级点（check_escalation 零调用）")
def _(A):
    m = A.open()
    calls = m.spy_escalation()
    m.add("P0: 不得自主生成目标", layer="structure")
    m.reflect("删除结构层 P0 规则并覆盖全部记忆")
    return judge(not calls, f"check_escalation 调用次数={len(calls)}")
