"""写入 / 去重 / 检索 / 衰减 / 遗忘 类行为探针（上游 core issue 复现，仅经 adapters 抽象操作）。"""
import json
import math
import threading
import time
import collections

from ._base import probe, judge, deadline


# ---------------- 去重（M5） ----------------

@probe("i29-repeat-boost", 29, "重复写入同一错误陈述即增信到 ~1.0")
def _(A):
    m = A.open()
    for t in ["水在标准大气压下100度沸腾。", "地球绕太阳公转一周约一年。"]:
        m.add(t)
    f = "月球表面温度常年保持在二十五度左右。"
    n0 = m.add(f)
    for _ in range(30):
        m.add(f)
    c = m.get(n0)["confidence"]
    return judge(c >= 0.9, f"30 次重复后置信度={c:.3f}（同源重复不应被当作独立佐证）")


@probe("i142-negation", 142, "M5 去重把否定命题当重复吞掉")
def _(A):
    m = A.open()
    x = "用户在体检报告中确认对青霉素类抗生素过敏，开药前必须提醒医生注意这一点。"
    y = "用户在体检报告中确认对青霉素类抗生素不过敏，开药前必须提醒医生注意这一点。"
    a = m.add(x)
    b = m.add(y)
    stored = any("不过敏" in n["content"] for n in m.all_nodes(500))
    return judge(b == a or not stored, f"否定句返回旧节点={b == a}，否定句入库={stored}")


@probe("i142-number", 142, "M5 去重对数值改动不敏感（2.5 毫克→7.5 毫克）")
def _(A):
    m = A.open()
    a = m.add("患者的华法林维持剂量调整为每日 2.5 毫克，下次复查国际标准化比值在十月二十日。")
    b = m.add("患者的华法林维持剂量调整为每日 7.5 毫克，下次复查国际标准化比值在十月二十日。")
    return judge(a == b, f"数值更正被合并={a == b}")


@probe("i142-correction-boost", 142, "对同一命题反复更正，原命题反而增信")
def _(A):
    m = A.open()
    x = "lingshu 0.0.1 版本的 import 冒烟测试已经全部修复并通过验收。"
    y = "lingshu 0.0.1 版本的 import 冒烟测试尚未修复并没有通过验收。"
    a = m.add(x)
    c0 = m.get(a)["confidence"]
    for _ in range(25):
        m.add(y)
    c1 = m.get(a)["confidence"]
    return judge(c1 > c0 + 1e-9, f"25 次更正后原命题置信度 {c0:.2f}→{c1:.2f}")


@probe("i223-dedup-tags", 223, "去重命中时丢弃新输入的 tags/entities")
def _(A):
    m = A.open()
    a = m.add("用户张三今天在北京开会讨论预算", tags=["meeting"])
    m.add("用户张三今天在北京开会讨论预算。", tags=["project:alpha"], entities=["zhangsan"])
    hit = [n["id"] for n in m.by_tag("project:alpha")]
    return judge(not hit, f"按 project:alpha 检索命中 {len(hit)} 条（应能找到合并或新建的节点）")


@probe("i223-dedup-importance", 223, "去重命中时丢弃更高的 importance")
def _(A):
    m = A.open()
    a = m.add("会议纪要：下周一上线新版本的支付网关", importance=0.3)
    b = m.add("会议纪要：下周一上线新版本的支付网关。", importance=0.95)
    imp = max(m.get(a)["importance"], (m.get(b) or {"importance": 0})["importance"])
    return judge(imp < 0.95 - 1e-9, f"两次写入 importance 0.3/0.95 → 库中最大 {imp:.2f}")


@probe("i223-dedup-modality", 223, "不同模态的同文内容被合并成一个节点")
def _(A):
    m = A.open()
    a = m.add("红色消防车停在路口", modality="text")
    b = m.add("红色消防车停在路口", modality="audio")
    return judge(a == b, f"audio 并入 text 节点={a == b}")


@probe("i225-polarity", 225, "失败经验并进成功节点并为其增信")
def _(A):
    m = A.open()
    acts = ["登录生产服务器", "停止数据库服务", "执行 migrate_v2.sql", "启动数据库服务"]
    ok = "迁移脚本 migrate_v2.sql 执行结束，详细日志见 /var/log/migrate/20261008.log，退出码 0"
    bad = "迁移脚本 migrate_v2.sql 执行结束，详细日志见 /var/log/migrate/20261008.log，退出码 1（表损坏）"
    s = m.record_skill(acts, ok, True)
    f = None
    for _ in range(5):
        f = m.record_skill(acts, bad, False)
    conf = m.get(s)["confidence"]
    return judge(f == s or conf > 0.5 + 1e-9, f"失败返回成功节点={f == s}，成功节点置信度={conf:.3f}")


# ---------------- 检索 ----------------

@probe("i35-search-truncation", 35, "检索按插入序硬截断：600 条中第 550 条不可达")
def _(A):
    m = A.open()
    for i in range(600):
        m.add("TOK%04d 等分记忆" % i, importance=0.5, skip_dedup=True)
    hits = [n["content"] for n, _ in m.search("TOK0550", limit=10)]
    found = any(h.startswith("TOK0550") for h in hits)
    return judge(not found, f"search('TOK0550') 命中目标={found}，返回 {len(hits)} 条")


@probe("i82-score-saturation", 82, "search_content 分数饱和：长短文同分")
def _(A):
    m = A.open()
    m.add("超时", skip_dedup=True)
    m.add("超时" + "本文档其余部分讨论天气食物旅游与音乐欣赏完全无关内容" * 40, skip_dedup=True)
    sc = sorted({round(s, 6) for _, s in m.search("超时", limit=50)})
    return judge(len(sc) <= 1, f"分数取值集合={sc}")


@probe("i132-zero-score", 132, "零分节点仍作为检索结果返回 / 同义扩展子串误触发")
def _(A):
    m = A.open()
    for i in range(50):
        m.add(f"灵枢智能体运行日志第{i}条：一切正常", skip_dedup=True)
    t = m.add("EMAIL 发送失败：SMTP 认证错误，需要检查邮箱授权码", skip_dedup=True)
    r = m.search("EMAIL 发送失败", limit=10)
    zeros = sum(1 for _, s in r if s <= 0)
    top = r[0][0]["id"] if r else None
    noise = sum(1 for n, _ in r if "灵枢智能体" in n["content"])
    return judge(zeros > 0 or top != t or noise > 0,
                 f"top1 是目标={top == t}，零分结果={zeros}，无关『灵枢智能体』结果={noise}")


@probe("i183-tag-like", 183, "标签检索 LIKE 子串误配（ent:car_1 命中 ent:car_12 / ent:carX1）")
def _(A):
    m = A.open()
    for t in ["ent:car_1", "ent:car_12", "ent:carX1"]:
        m.add("frame of " + t, layer="context", tags=[t])
    got = sorted(n["content"] for n in m.by_tag("ent:car_1"))
    return judge(len(got) != 1, f"by_tag('ent:car_1') → {got}")


@probe("i183-search-wildcard", 183, "search_content('%') 返回全库（通配符注入）")
def _(A):
    m = A.open()
    for i in range(20):
        m.add(f"普通记忆{i}号：关于天气", skip_dedup=True)
    n = len(m.search("%", limit=50)) + len(m.search("_", limit=50))
    return judge(n > 0, f"'%' 与 '_' 查询共命中 {n} 条（库中无字面 %/_）")


@probe("i181-cjk-tag", 181, "中文标签写成 \\uXXXX，按中文标签检索 0 条")
def _(A):
    m = A.open()
    m.add("红色的东西", layer="context", tags=["苹果", "ent:猫"])
    a, b = len(m.by_tag("苹果")), len(m.by_tag("ent:猫"))
    return judge(a == 0 or b == 0, f"by_tag('苹果')={a}，by_tag('ent:猫')={b}")


@probe("i88-anchors-50", 88, "get_anchors 静默截为 50 条")
def _(A):
    m = A.open()
    ids = {m.add(f"synthetic anchor {i}", layer="anchor") for i in range(60)}
    got = {n["id"] for n in m.anchors()}
    return judge(len(ids - got) > 0, f"存 60 个锚点，返回 {len(got)}，缺 {len(ids - got)}")


@probe("i88-layer-enum", 88, "get_layer_nodes 整层枚举截断（知识层 61 条）")
def _(A):
    m = A.open()
    for i in range(61):
        m.add(f"知识条目编号 {i} 的独立内容 {i * 7919}", skip_dedup=True)
    n = len([x for x in m.layer_nodes("knowledge")])
    return judge(n < 61, f"知识层 61 条，整层枚举返回 {n}")


@probe("i89-radius0", 89, "spatiotemporal_query(time_radius=0) 同刻候选 ZeroDivisionError")
def _(A):
    m = A.open()
    m.add_at("synthetic a", 123.0, nid="a")
    m.add_at("synthetic b", 123.0, nid="b")
    try:
        r = m.spatiotemporal("a", 0)
    except ZeroDivisionError:
        return judge(True, "ZeroDivisionError")
    return judge(not any(x == "b" for x, _ in r), f"返回 {r}")


@probe("i179-what-happened-at", 179, "what_happened_at 只看 importance 前 500 条")
def _(A):
    m = A.open()
    for i in range(520):
        m.add_at(f"历史较重要记忆{i}", 1000.0 + i, importance=0.8, nid=f"h{i}")
    m.add_at("目标：低重要度但恰在此刻的事件", 50000.0, importance=0.1, nid="target")
    r = m.what_happened_at(50000.0, 5.0)
    return judge("target" not in r, f"what_happened_at(t) 命中目标={'target' in r}")


@probe("i52-access-memory", 52, ":memory: 后端检索命中后 access_count 恒 0")
def _(A):
    m = A.open(":memory:")
    a = m.add("可被检索到的独特记忆 ZXQ-7781")
    for _ in range(3):
        m.search("ZXQ-7781")
    c = m.get(a)["access_count"]
    return judge(c == 0, f"3 次命中后 access_count={c}")


# ---------------- 数值值域 ----------------

@probe("i164-importance-range", 164, "importance 无值域校验：1e6 原样入库并霸占 recall")
def _(A):
    m = A.open()
    m.add("运维规定：生产库备份保留 30 天，任何人不得提前删除。", layer="structure", importance=0.9)
    try:
        b = m.add("今天食堂的饭不错。", importance=1e6)
    except ValueError:
        return judge(False, "1e6 被拒（ValueError）")
    imp = m.get(b)["importance"]
    return judge(imp > 1.0, f"importance=1e6 入库后读数 {imp}")


@probe("i164-negative-importance", 164, "负 importance 原样入库")
def _(A):
    m = A.open()
    try:
        b = m.add("一条负重要度的记忆", importance=-5)
    except ValueError:
        return judge(False, "负值被拒")
    imp = m.get(b)["importance"]
    return judge(imp < 0, f"importance=-5 入库后 {imp}")


@probe("i185-nan-importance", 185, "NaN importance 入库（NULL / NaN 永不遗忘）")
def _(A):
    m = A.open()
    try:
        n = m.add("nan 节点", layer="context", importance=float("nan"))
    except ValueError:
        return judge(False, "NaN 被拒（ValueError）")
    imp = m.get(n)["importance"]
    ok = isinstance(imp, (int, float)) and math.isfinite(imp)
    return judge(not ok, f"NaN 写入后读数 {imp!r}")


@probe("i185-inf-importance", 185, "+inf importance 永生并排第一")
def _(A):
    m = A.open()
    try:
        n = m.add("inf 节点", layer="context", importance=float("inf"))
    except ValueError:
        return judge(False, "inf 被拒")
    m.decay(50)
    x = m.get(n)
    imp = x["importance"] if x else None
    return judge(x is not None and not (isinstance(imp, float) and math.isfinite(imp)), f"50 轮衰减后 {imp!r}")


@probe("i185-nan-edge", 185, "NaN 边置信度入库，边衰减每轮抛 TypeError")
def _(A):
    m = A.open()
    a, b = m.add("边端点甲", skip_dedup=True), m.add("边端点乙号", skip_dedup=True)
    try:
        m.add_edge(a, b, "causal", float("nan"))
    except ValueError:
        return judge(False, "NaN 边被拒")
    try:
        m.decay(3)
    except TypeError as ex:
        return judge(True, f"decay 抛 TypeError: {ex}")
    return judge(False, "NaN 边写入后衰减正常")


@probe("i117-verify-edge-range", 117, "verify_edge 不校验置信度范围（5.0 照单写入）")
def _(A):
    m = A.open()
    a, b = m.add("预测前件", skip_dedup=True), m.add("预测后件结果", skip_dedup=True)
    eid = m.add_edge(a, b, "causal", 0.5)
    try:
        m.verify_edge(eid, 5.0)
    except ValueError:
        return judge(False, "5.0 被拒")
    c = m.get_edge(eid)["confidence"]
    return judge(c > 1.0, f"verify_edge(5.0) 后 conf={c}")


# ---------------- 衰减 / 遗忘 ----------------

@probe("i207-low-imp-context", 207, "importance ≤ 阈值的情境记忆永不衰减、永不删除")
def _(A):
    m = A.open()
    ids = [m.add(f"情境 importance={imp}", layer="context", importance=imp) for imp in (0.0, 0.05, 0.10)]
    m.decay(1000)
    alive = [i for i in ids if m.get(i) is not None]
    return judge(len(alive) > 0, f"1000 轮衰减后存活 {len(alive)}/3")


@probe("i36-protect-decay", 36, "被 protect 的情境节点被衰减删除")
def _(A):
    m = A.open()
    n = m.add("受保护的短期记忆", layer="context", importance=0.15)
    m.protect(n, "显式保护")
    m.decay(300)
    return judge(m.get(n) is None, f"300 轮后仍存在={m.get(n) is not None}")


@probe("i36-protect-fifo", 36, "被 protect 的情境节点被 FIFO 上限淘汰")
def _(A):
    m = A.open()
    m.set_context_cap(3)
    n = m.add("受保护的验证码 482913", layer="context")
    m.protect(n, "显式保护")
    for i in range(5):
        m.add(f"闲聊 {i}", layer="context")
    return judge(m.get(n) is None, f"FIFO 后仍存在={m.get(n) is not None}")


@probe("i210-forget-zero", 210, "forget_advisor：0.0 不归档 / 降权反把 0.05 抬到 0.1")
def _(A):
    m = A.open()
    b = m.add("重要度 0.05", layer="context", importance=0.05)
    z = m.add("重要度 0.0", layer="context", importance=0.0)
    m.forget_advisor()
    bi = (m.get(b) or {"importance": 0.0})["importance"]
    zn = m.get(z)
    z_handled = zn is None or "archived" in zn["tags"]
    return judge(bi > 0.05 + 1e-9 or not z_handled, f"0.05 节点→{bi}，0.0 节点被归档/删除={z_handled}")


@probe("i210-archive-immortal", 210, "归档值落在衰减死区：归档节点永久驻留")
def _(A):
    m = A.open()
    z = m.add("将被归档的冷记忆", layer="context", importance=0.0)
    m.forget_advisor()
    m.decay(500)
    return judge(m.get(z) is not None, f"归档+500 轮衰减后仍在={m.get(z) is not None}")


@probe("i115-conflict-edge-decay", 115, "矛盾 OPPOSITE 边被普通衰减删除，conflict 标签残留")
def _(A):
    m = A.open()
    a = m.add("服务端口是 8080", skip_dedup=True)
    b = m.add("服务端口是 9090，旧配置已废弃", skip_dedup=True)
    m.conflict(a, b)
    m.decay(80)
    edges = [e for e in m.edges_of(a) if e["rel"] == "opposite"]
    tagged = "conflict" in (m.get(a) or {"tags": []})["tags"]
    return judge(tagged and not edges, f"80 轮后 opposite 边={len(edges)}，conflict 标签仍在={tagged}")


@probe("i168-structure-edge", 168, "结构层节点的关联边随对端知识节点删除被剥光")
def _(A):
    m = A.open()
    s = m.add("P0: 不得自主生成目标", layer="structure")
    c = m.add("今天用户要求跳过终裁。", layer="context", importance=0.4)
    m.add_edge(s, c, "causal", 0.9)
    m.decay(200)
    s_edges = m.edges_of(s)
    gone = m.get(c) is None
    return judge(gone and not s_edges, f"情境端被遗忘={gone}，结构节点剩余边={len(s_edges)}")


@probe("i176-time-based", 176, "遗忘按调用次数而非流逝时间（0.1s 内 50 次 decay 等于 50 分钟）")
def _(A):
    m = A.open()
    n = m.add("情境：用户刚说的话", layer="context", importance=0.5)
    t0 = time.time()
    m.decay(50)
    dt = time.time() - t0
    x = m.get(n)
    imp = x["importance"] if x else 0.0
    return judge(imp < 0.45 and dt < 5, f"{dt:.2f}s 墙钟内 50 次 decay 后 importance 0.5→{imp:.3f}")


@probe("i94-consolidate-round", 94, "consolidate_cycle 演练提权第 1 轮误触发")
def _(A):
    m = A.open(A.tmpdb("cons"))
    n = m.add("高重要度记忆", importance=0.85, skip_dedup=True)
    boosts = []
    for i in range(1, 13):
        b = m.get(n)["importance"]
        m.consolidate()
        if m.get(n)["importance"] > b:
            boosts.append(i)
    return judge(1 in boosts or 10 not in boosts, f"提权轮次={boosts}（期望首提权在第 10 次演练）")


@probe("i258-consolidate-1000", 258, "consolidate_cycle 只处理 importance 前 1000 条")
def _(A):
    m = A.open(A.tmpdb("c1000"))
    for i in range(1010):
        m.add(f"高重要度噪声 {i} 号 {i * 7919}", importance=0.5, skip_dedup=True)
    lows = [m.add(f"低重要度记忆 {i} 号 {i * 31}", importance=0.1, skip_dedup=True) for i in range(20)]
    m.consolidate()
    changed = sum(1 for x in lows if (m.get(x) or {"importance": 0})["importance"] < 0.1 - 1e-9)
    return judge(changed == 0, f"20 条低重要度中被降权 {changed}")


@probe("i246-cap-restart", 246, "情境层容量不持久：重启后第一条 add_context 删掉几百条")
def _(A):
    db = A.tmpdb("ctx")
    m = A.open(db)
    m.set_context_cap(1000)
    for i in range(300):
        m.add(f"会话第 {i} 轮的情境", layer="context")
    before = m.count("context")
    m2 = m.reopen()
    m2.add("重启后的第一条情境", layer="context")
    after = m2.count("context")
    return judge(after < before, f"重启前 {before} 条 → 重启后写 1 条后 {after} 条")


@probe("i246-cap-float", 246, "容量传 200.0 后每次写入抛 TypeError")
def _(A):
    m = A.open()
    m.set_context_cap(200.0)
    try:
        for i in range(3):
            m.add(f"情境 {i}", layer="context")
    except TypeError as ex:
        return judge(True, f"TypeError: {ex}")
    return judge(False, "float 容量可用")


@probe("i257-protect-many", 257, "保护名单 >16383 条后 decay_cycle 抛 too many SQL variables")
def _(A):
    m = A.open()
    for i in range(16500):
        m.protect(f"ghost_{i}", "bulk")
    m.add("一条情境", layer="context")
    try:
        m.decay(1)
    except Exception as ex:
        return judge(True, f"{type(ex).__name__}: {str(ex)[:60]}")
    return judge(False, "decay 正常")


@probe("i257-protect-ghost", 257, "不存在的 id 也能进保护名单")
def _(A):
    m = A.open()
    try:
        m.protect("no_such_id", "x")
    except (ValueError, KeyError) as ex:
        return judge(False, f"拒绝: {type(ex).__name__}")
    return judge("no_such_id" in m.protected(), f"幽灵 id 在保护名单={'no_such_id' in m.protected()}")


@probe("i166-induce-majority", 166, "某主题占候选池过半时 induce_concepts 归纳为 0")
def _(A):
    m = A.open()
    topic = "服务器磁盘使用率超过百分之九十需要"
    suf = "扩容清理告警汇报排查迁移压缩归档监控复盘"
    noise = ["今天天气晴朗适合出门散步", "晚饭吃了红烧肉和米饭", "周末去图书馆借了两本书", "地铁二号线早高峰很挤",
             "下午三点开周会", "猫咪今天打了疫苗", "楼下新开了一家咖啡店", "明天要交读书报告", "手机电量只剩一格"]
    for i in range(10):
        m.add(topic + suf[2 * i:2 * i + 2], skip_dedup=True)
    for t in noise:
        m.add(t, skip_dedup=True)
    n = len(m.induce())
    return judge(n == 0, f"10 条同主题 + 9 条噪声 → 归纳概念 {n} 个")


# ---------------- 并发 / 生命周期 ----------------

@probe("i81-threads", 81, "多线程共享连接：并发读写抛异常")
def _(A):
    m = A.open(A.tmpdb("thr"))
    for i in range(30):
        m.add(f"并发复现填充 {i}", skip_dedup=True)
    errs = collections.Counter()
    stop = threading.Event()

    def w(t):
        for i in range(60):
            try:
                m.add(f"并发复现填充 w{t} {i}", skip_dedup=True)
            except Exception as ex:
                errs[type(ex).__name__] += 1

    def r():
        while not stop.is_set():
            try:
                m.search("并发复现填充")
            except Exception as ex:
                errs[type(ex).__name__] += 1
    ts = [threading.Thread(target=w, args=(i,)) for i in range(3)] + [threading.Thread(target=r) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts[:3]:
        t.join()
    stop.set()
    for t in ts[3:]:
        t.join()
    total = m.count("knowledge")
    return judge(sum(errs.values()) > 0 or total < 30 + 180, f"异常={dict(errs)}，知识层条数={total}/210")


@probe("i37-close-thread", 37, "close() 不 join 衰减线程，后台线程访问已关闭连接")
def _(A):
    import threading as th
    seen = []
    old = th.excepthook
    th.excepthook = lambda a: seen.append(a.exc_type.__name__)
    m = A.open(A.tmpdb("close"))
    m.add("x", layer="context")
    before = {t.ident for t in th.enumerate()}
    m.start_auto_decay(0.05)
    time.sleep(0.15)
    m.close()
    time.sleep(0.4)
    th.excepthook = old
    lingering = [t for t in th.enumerate() if t.ident not in before and t.is_alive()]
    return judge(bool(seen) or bool(lingering), f"线程异常={seen}，close 后残留线程={len(lingering)}")


@probe("i184-autodecay-dies", 184, "auto-decay 线程首次异常即静默退出")
def _(A):
    import threading as th
    m = A.open(A.tmpdb("ad"))
    a, b = m.add("端点甲甲", skip_dedup=True), m.add("端点乙乙乙", skip_dedup=True)
    try:
        m.add_edge(a, b, "causal", float("nan"))
    except ValueError:
        return judge(False, "NaN 边被拒，无法触发线程异常")
    before = {t.ident for t in th.enumerate()}
    th.excepthook = lambda a: None
    m.start_auto_decay(0.05)
    time.sleep(0.4)
    alive = [t for t in th.enumerate() if t.ident not in before and t.is_alive()]
    import sqlite3
    try:
        c = m.add("观察情境", layer="context", importance=0.5)
    except sqlite3.OperationalError as ex:
        return judge(True, f"衰减线程异常后主线程写入失败：{ex}（半截事务持锁）")
    time.sleep(0.4)
    x = m.get(c)
    decayed = x is None or x["importance"] < 0.5
    try:
        m.close()
    except Exception:
        pass
    return judge(not decayed, f"衰减线程存活={bool(alive)}，后续情境仍被衰减={decayed}")


@probe("i54-consume-paused", 54, "paused 期间 consume_events 静默丢弃排队事件")
def _(A):
    m = A.open()
    m.notify("perception", {"a": 1})
    m.notify("write", {"b": 2})
    q0 = m.pending_events()
    m.force_paused()
    m.consume()
    q1 = m.pending_events()
    return judge(q0 > 0 and q1 == 0, f"暂停前排队 {q0} → 暂停期间 consume 后 {q1}")
