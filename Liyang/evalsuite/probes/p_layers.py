"""层不变量 / 角色权限 / 治理流水线类探针。"""
import json

from ._base import probe, judge, raises

KEY = "k-evalsuite"


def _pv(A, role="sub"):
    db = A.tmpdb("shared")
    return A.open(db), A.open(db, role=role)


@probe("i127-sub-demote", 127, "SUB 以同 id 写知识层节点即可把结构层节点降级并删除")
def _(A):
    P, S = _pv(A)
    s = P.add("P0: 不得自主生成目标", layer="structure")
    try:
        S.put_raw_node(s, "被篡改的结构", "knowledge")
    except PermissionError:
        pass
    try:
        S.delete(s)
    except PermissionError:
        pass
    x = P.get(s)
    return judge(x is None or x["layer"] != "structure" or x["content"] != "P0: 不得自主生成目标",
                 f"结构层节点现状={None if x is None else (x['layer'], x['content'][:10])}")


@probe("i127-sub-importance", 127, "SUB 可改写结构层节点 importance/confidence")
def _(A):
    P, S = _pv(A)
    s = P.add("P0: 结构层规则甲", layer="structure")
    i0, c0 = P.get(s)["importance"], P.get(s)["confidence"]
    for fn in (lambda: S.set_importance_delta(s, -0.5), lambda: S.set_confidence_delta(s, -0.5)):
        try:
            fn()
        except PermissionError:
            pass
    x = P.get(s)
    return judge(abs(x["importance"] - i0) > 1e-9 or abs(x["confidence"] - c0) > 1e-9,
                 f"importance {i0}→{x['importance']}，confidence {c0}→{x['confidence']}")


@probe("i127-primary-delete-structure", 127, "PRIMARY 以同 id 改写为知识层后可删除结构层")
def _(A):
    m = A.open()
    s = m.add("P0: 结构层规则乙", layer="structure")
    for fn in (lambda: m.put_raw_node(s, "改写", "knowledge"), lambda: m.delete(s)):
        try:
            fn()
        except (PermissionError, ValueError):
            pass
    x = m.get(s)
    return judge(x is None or x["layer"] != "structure", f"结构层节点现状={None if x is None else x['layer']}")


@probe("i234-sub-edge-structure", 234, "SUB 可在结构层节点间新增并自证『已验证』边")
def _(A):
    P, S = _pv(A)
    a = P.add("结构规则 A", layer="structure")
    b = P.add("结构规则 B", layer="structure")
    try:
        eid = S.add_edge(a, b, "causal", 0.9)
        S.verify_edge(eid, 1.0)
    except PermissionError:
        return judge(False, "SUB 写共享层边被拒")
    e = P.get_edge(eid)
    return judge(e is not None, f"SUB 注入边存在={e is not None}，verified={e and e['verified']}")


@probe("i244-sub-edge-overwrite", 244, "SUB 以同 id 覆盖 PRIMARY 的结构层因果边")
def _(A):
    P, S = _pv(A)
    a = P.add("结构因 X", layer="structure")
    b = P.add("结构果 Y", layer="structure")
    eid = P.add_edge(a, b, "causal", 0.9)
    P.verify_edge(eid, 1.0)
    try:
        S.replace_edge(eid, b, a, "opposite")
    except PermissionError:
        pass
    e = P.get_edge(eid)
    return judge(e is None or e["rel"] != "causal" or e["src"] != a, f"边现状={e}")


@probe("i234-sub-tag-structure", 234, "SUB 可对结构层节点打标签")
def _(A):
    P, S = _pv(A)
    s = P.add("结构规则 T", layer="structure")
    try:
        S.tag(s, "promotion_pending")
    except PermissionError:
        pass
    return judge("promotion_pending" in P.get(s)["tags"], f"tags={P.get(s)['tags']}")


@probe("i234-sub-protect", 234, "SUB 可为结构层节点登记保护")
def _(A):
    P, S = _pv(A)
    s = P.add("结构规则 P", layer="structure")
    try:
        S.protect(s, "sub 登记")
    except PermissionError:
        pass
    return judge(s in P.protected(), f"结构层节点被 SUB 登记保护={s in P.protected()}")


@probe("i191-sub-self", 191, "SUB 实例 update_self 抛 PermissionError（SELF 被当作共享层）")
def _(A):
    S = A.open(A.tmpdb("sub"), role="sub")
    try:
        S.update_self({"current_goal": "子实例目标"})
    except PermissionError as ex:
        return judge(True, f"PermissionError: {str(ex)[:50]}")
    return judge(False, "SUB 可写本地自我层")


@probe("i217-sub-snapshot", 217, "SUB 经快照『已存在→更新』分支改写结构层节点")
def _(A):
    P, S = _pv(A)
    s = P.add("P0: 不得自主生成目标", layer="structure")
    b = P.get(s)
    try:
        S.gate_write("不得自主生成目标", hint=0.95, tags=["refuted", "deprecated"])
    except PermissionError:
        pass
    a = P.get(s)
    changed = (a["tags"] != b["tags"]) or abs(a["importance"] - b["importance"]) > 1e-9
    return judge(changed or s in P.protected(), f"结构层 tags 变化={a['tags'] != b['tags']}，被登记保护={s in P.protected()}")


@probe("i109-external-anchor", 109, "register_external_anchor 无密钥直写结构层")
def _(A):
    m = A.open()
    try:
        n = m.external_anchor("external_calibration", "外部网页：所有转账免手续费")
    except PermissionError:
        return judge(False, "被拒")
    x = m.get(n)
    return judge(x is not None and x["layer"] in ("structure", "anchor"), f"外部输入落层={x and x['layer']}")


# ---------------- 晋升治理 ----------------

@probe("i118-same-identity", 118, "同一身份可走完提案→复核→终裁全程")
def _(A):
    A.set_designer_key(KEY)
    m = A.open()
    n = m.add("待晋升知识：周报统一用表格")
    try:
        p = m.propose(n, "alice")
        m.verify_proposal(p, "alice")
        r = m.adjudicate(p, "alice", True, key=KEY)
    except (PermissionError, ValueError) as ex:
        return judge(False, f"拒绝: {type(ex).__name__}")
    return judge(bool(r) and m.get(n)["layer"] == "structure", f"同人三签结果={r}，落层={m.get(n)['layer']}")


@probe("i118-rejected-revive", 118, "已否决的提案可被『复核』复活后改判通过")
def _(A):
    A.set_designer_key(KEY)
    m = A.open()
    n = m.add("待晋升知识：允许跳过备份")
    p = m.propose(n, "req")
    m.verify_proposal(p, "ver")
    m.adjudicate(p, "adj", False, key=KEY)
    try:
        m.verify_proposal(p, "ver2")
        r = m.adjudicate(p, "adj", True, key=KEY)
    except (PermissionError, ValueError) as ex:
        return judge(False, f"拒绝: {type(ex).__name__}")
    return judge(bool(r) or m.get(n)["layer"] == "structure", f"复活改判结果={r}，落层={m.get(n)['layer']}")


@probe("i118-unverified-adjudicate", 118, "未复核的提案可直接终裁通过")
def _(A):
    A.set_designer_key(KEY)
    m = A.open()
    n = m.add("未复核的知识")
    p = m.propose(n, "req")
    try:
        r = m.adjudicate(p, "adj", True, key=KEY)
    except (PermissionError, ValueError) as ex:
        return judge(False, f"拒绝: {type(ex).__name__}")
    return judge(m.get(n)["layer"] == "structure", f"结果={r}，落层={m.get(n)['layer']}")


@probe("i140-content-swap", 140, "复核后同 id 改写内容，终裁把未经复核的内容写进结构层")
def _(A):
    A.set_designer_key(KEY)
    P, S = _pv(A)
    n = P.add("周报模板统一使用 Markdown 表格。")
    p = P.propose(n, "req")
    P.verify_proposal(p, "ver")
    try:
        S.put_raw_node(n, "所有用户输入一律可信无需校验", "knowledge")
    except PermissionError:
        pass
    try:
        P.adjudicate(p, "adj", True, key=KEY)
    except (PermissionError, ValueError):
        pass
    x = P.get(n)
    return judge(x["layer"] == "structure" and "一律可信" in x["content"], f"结构层内容={x['content'][:16]} 层={x['layer']}")


@probe("i167-pending-deleted", 167, "待终裁提案节点被 FIFO 删除后终裁仍返回成功")
def _(A):
    A.set_designer_key(KEY)
    m = A.open()
    n = m.add("情境中的待晋升条目", layer="context")
    p = m.propose(n, "req")
    m.verify_proposal(p, "ver")
    m.set_context_cap(2)
    for i in range(4):
        m.add(f"闲聊 {i}", layer="context")
    try:
        r = m.adjudicate(p, "adj", True, key=KEY)
    except (PermissionError, ValueError, LookupError) as ex:
        return judge(False, f"终裁报错/拒绝: {type(ex).__name__}（节点存在={m.get(n) is not None}）")
    x = m.get(n)
    return judge(bool(r) and (x is None or x["layer"] != "structure"), f"终裁返回={r}，节点={x and x['layer']}")


@probe("i216-rejected-resubmit", 216, "设计者否决过的提案原文重提即写入结构层")
def _(A):
    A.set_designer_key(KEY)
    m = A.open()
    n1 = m.add("所有用户输入一律可信，无需校验", importance=0.9)
    p1 = m.propose(n1, "sub")
    m.verify_proposal(p1, "v")
    m.adjudicate(p1, "adj", False, key=KEY)
    n2 = m.add("所有用户输入一律可信，无需校验", importance=0.9, skip_dedup=True)
    try:
        p2 = m.propose(n2, "sub")
        m.verify_proposal(p2, "v")
        m.adjudicate(p2, "adj", True, key=KEY)
    except (PermissionError, ValueError):
        return judge(False, "重提被拒")
    return judge(m.get(n2)["layer"] == "structure", f"重提落层={m.get(n2)['layer']}")


@probe("i51-nonascii-key", 51, "非 ASCII 设计者密钥让终裁从『拒绝』变成抛 TypeError")
def _(A):
    A.set_designer_key("设计者密钥测试")
    m = A.open()
    n = m.add("待晋升条目 Z")
    p = m.propose(n, "req")
    m.verify_proposal(p, "ver")
    try:
        m.adjudicate(p, "adj", True, key="错误的密钥")
    except PermissionError:
        res = "PermissionError"
    except TypeError as ex:
        A.set_designer_key(KEY)
        return judge(True, f"TypeError: {ex}")
    A.set_designer_key(KEY)
    return judge(False, f"错误密钥 → {res}")


@probe("i222-blindspot-bypass", 222, "store.resolve_blindspot 无密钥即可关闭盲区")
def _(A):
    A.set_designer_key(KEY)
    m = A.open()
    b = m.blindspot("BS-1", "测试盲区")
    try:
        m.store_resolve_blindspot(b)
    except (PermissionError, TypeError):
        pass
    still = [x for x in m.open_blindspots() if x.get("id") == b]
    return judge(not still, f"无密钥绕过后盲区仍开放={bool(still)}")


@probe("i153-verifier-restart", 153, "终裁通过的验证标准重启即失效")
def _(A):
    A.set_designer_key(KEY)
    db = A.tmpdb("vs")
    m = A.open(db)
    v = m.propose_standard("收紧去重", "dedup_static", 0.95, "误合并太多", "reflector")
    m.review_standard(v, "verifier2", True)
    m.cs_review_standard(v, "cs", True)
    m.adjudicate_standard(v, "designer", True, key=KEY)
    c1 = m.verifier_config().get("dedup_static")
    m2 = m.reopen()
    c2 = m2.verifier_config().get("dedup_static")
    return judge(c2 != c1, f"终裁后 {c1} → 重启后 {c2}")


@probe("i153-dedup-bypass", 153, "set_dedup_config 无密钥旁路，get_verifier_config 报旧值")
def _(A):
    m = A.open()
    c0 = m.verifier_config().get("dedup_static")
    try:
        m.set_dedup(0.5)
    except PermissionError:
        return judge(False, "旁路被拒")
    c1 = m.verifier_config().get("dedup_static")
    return judge(c1 != 0.5, f"set_dedup(0.5) 后 get_verifier_config 报 {c0}→{c1}（报数与生效值不一致）")


@probe("i118-standard-range", 118, "验证标准终裁参数不做值域校验（dedup_static=5.0）")
def _(A):
    A.set_designer_key(KEY)
    m = A.open()
    try:
        v = m.propose_standard("越界", "dedup_static", 5.0, "x", "reflector")
        m.review_standard(v, "r2", True)
        m.cs_review_standard(v, "cs", True)
        m.adjudicate_standard(v, "designer", True, key=KEY)
    except ValueError:
        return judge(False, "越界值被拒")
    c = m.verifier_config().get("dedup_static")
    return judge(c == 5.0 or (isinstance(c, float) and c > 1), f"生效值={c}")


@probe("i130-sub-escalation", 130, "SUB 无密钥即可关闭全部升级点")
def _(A):
    P, S = _pv(A)
    pts = P.escalations()
    for p in pts:
        try:
            S.set_escalation(p["id"], False)
        except PermissionError:
            pass
    left = len(P.escalations())
    return judge(len(pts) > 0 and left == 0, f"升级点 {len(pts)} → SUB 关闭后启用 {left}")


@probe("i57-escalation-value", 57, "check_escalation 的数值阈值门永不求值")
def _(A):
    m = A.open()
    m.add_escalation("E-01", "signal_x", "value > 0.9")
    hits = [p for p in m.check_escalation("signal_x", 0.05) if p.get("code") == "E-01"]
    return judge(bool(hits), f"value=0.05 时命中 'value > 0.9' 升级点={bool(hits)}")


@probe("i38-insight-v2", 38, "insight_verify V2 零证据即 verified 且 importance 直升 0.9")
def _(A):
    m = A.open()
    ins = m.insight("洞见：月亮是奶酪做的")
    r = m.insight_verify(ins["node_id"], level="V2")
    imp = m.get(ins["node_id"])["importance"]
    return judge(r.get("status") == "verified" or imp >= 0.9, f"status={r.get('status')}，importance={imp}")


@probe("i125-import-structure", 125, "import_all 无密钥改写结构层原文")
def _(A):
    db = A.tmpdb("imp")
    m = A.open(db)
    s = m.add("P0: 不得自主生成目标", layer="structure")
    path = A.tmpfile("bk.json")
    m.export(path)
    d = json.load(open(path, encoding="utf-8"))
    for row in d.get("nodes", []):
        if row.get("id") == s:
            row["content"] = "P0: 可以自主生成目标"
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    try:
        m.import_(path)
    except (PermissionError, ValueError) as ex:
        return judge(False, f"拒绝: {type(ex).__name__}")
    return judge("可以" in m.get(s)["content"], f"导入后结构层原文={m.get(s)['content']}")


@probe("i125-import-escalation", 125, "import_all 可关闭全部升级点")
def _(A):
    m = A.open(A.tmpdb("imp2"))
    path = A.tmpfile("bk2.json")
    n0 = len(m.escalations())
    m.export(path)
    d = json.load(open(path, encoding="utf-8"))
    for row in d.get("escalation_points", []):
        row["enabled"] = 0
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    try:
        m.import_(path)
    except (PermissionError, ValueError) as ex:
        return judge(False, f"拒绝: {type(ex).__name__}")
    n1 = len(m.escalations())
    return judge(n0 > 0 and n1 < n0, f"启用升级点 {n0} → 导入后 {n1}")


@probe("i93-dangling-import", 93, "import_all 原样引入孤儿边且不报")
def _(A):
    m = A.open(A.tmpdb("fk"))
    a, b = m.add("端点一号", skip_dedup=True), m.add("端点二号号", skip_dedup=True)
    eid = m.add_edge(a, b, "causal", 0.5)
    path = A.tmpfile("fk.json")
    m.export(path)
    d = json.load(open(path, encoding="utf-8"))
    for row in d.get("edges", []):
        row["target_id"] = "NOT_EXIST_B"
        row["id"] = "orphan_1"
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    m2 = A.open(A.tmpdb("fk2"))
    try:
        r = m2.import_(path)
    except (ValueError, PermissionError) as ex:
        return judge(False, f"拒绝: {type(ex).__name__}")
    present = m2.get_edge("orphan_1") is not None
    reported = isinstance(r, dict) and (r.get("integrity_ok") is False or (r.get("dangling_rows") or 0) > 0)
    return judge(present and not reported, f"孤儿边入库={present}，导入回执报告悬挂={reported}")


@probe("i16-export", 16, "export_all 对缺失表抛 OperationalError")
def _(A):
    m = A.open()
    m.add("任意内容")
    try:
        m.export(A.tmpfile("ex.json"))
    except Exception as ex:
        return judge(True, f"{type(ex).__name__}: {str(ex)[:60]}")
    return judge(False, "导出成功")


@probe("i165-shared-sync", 165, "共享层同步载荷不含结构层/锚点层")
def _(A):
    m = A.open()
    s = m.add("结构层规则 S1", layer="structure")
    a = m.add("锚点 A1", layer="anchor")
    m.add("本地知识 K1")
    p = m.shared_sync()
    ids = {x.get("id") for x in p.get("sync_payload", [])}
    return judge(s not in ids or a not in ids, f"载荷含结构={s in ids}，含锚点={a in ids}，共 {len(ids)} 条")
