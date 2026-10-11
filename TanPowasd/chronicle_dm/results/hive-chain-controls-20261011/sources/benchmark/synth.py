# -*- coding: utf-8 -*-
"""状态链召回探针 · 合成语料生成器（真值内生 · 零判官）

口径（一句话一件）
  · 语料 = 主体 × 属性 × 值 × 生效区间 + 状态；A 类＝代码迭代史（3 项目 × 60 提交），
    B 类＝关系状态史（3 故事 × 30 章，主体 4）。
  · 真值 = 本文件生成的事件日志（synth_log.json）；keys.json 由该日志**复算**得出
    （main() 末尾逐字段比对，不符即打印计数），不引入任何人工标注或 LLM 判断。
  · 题量 ≈ 600：每条主链取 5 个取样点（链首 / 链尾 / 两个变更点 / 一个未决或退役点），
    六类问（现值/历史/变更/时点/缘由/状态归属）各覆盖到。
  · 不可重建性：每题机械计算 reconstructible（见 reconstructible()），并在文末跑一次
    「正控」自检，证明该探测器不是恒 false（否则标记无意义）。

固定随机种子 SEED，结果可复现。运行： python -X utf8 chain/tools/synth.py
（产物写入本脚本同级的 out/ 目录。）
"""
from __future__ import annotations

import json
import math
import random
import re
from pathlib import Path

SEED = 20261010
HERE = Path(__file__).resolve().parent
OUT = HERE / 'out'

# ================= 词池 =================
A_PROJECTS = ['猎户项目', '流明项目', '织女项目']
A_DOCID = {'猎户项目': 'A1', '流明项目': 'A2', '织女项目': 'A3'}
A_SLOTS = ['函数签名', '有效期秒数', '依赖名', '配置值']
A_FORMER = {'猎户项目': '猎户服务', '流明项目': '流明工具', '织女项目': '织女组件'}
A_MODULE_SUFFIX = '·缓存模块'
A_NESTED_SLOT = '有效期秒数'

B_STORIES = [
    ('青石镇', ['阿禾', '老陈', '小满', '周舟'], ['禾生', '陈伯', '满儿', '舟子'], 'B1'),
    ('雾港', ['林昭', '沈砚', '阿桑', '杜衡'], ['昭儿', '砚郎', '桑娘', '衡哥'], 'B2'),
    ('孤山驿', ['程雪', '陆平', '白芨', '顾九'], ['雪姑', '平叔', '芨妹', '九爷'], 'B3'),
]
B_SLOTS = ['信任对象', '位置', '立场', '情绪']
B_PLACES = ['渡口', '粮仓', '后山', '祠堂', '码头', '驿站', '集市', '磨坊']
B_STANCES = ['支持', '反对', '中立', '观望', '暧昧', '沉默']
B_EMOTIONS = ['平静', '焦虑', '愤怒', '欣慰', '犹豫', '戒备', '释然', '低落']
TRUST_EXTRA = ['无人', '外人']

SIG_FUNCS = ['get', 'fetch', 'load', 'resolve', 'sync']
SIG_ARGS = [['key'], ['key', 'ttl'], ['key', 'ttl', 'refresh'], ['key', 'ttl', 'force'],
            ['id', 'key', 'ttl'], ['key', 'ttl', 'tag', 'refresh']]
TTL_POOL = [300, 600, 900, 1800, 3600, 7200, 10800, 21600]
DEP_POOL = ['redis', 'sqlite', 'lmdb', 'bbolt', 'rocksdb', 'badger', 'sled']
CONF_KEYS = ['max_conn', 'batch_size', 'timeout_ms', 'retry']
CONF_VALS = [16, 32, 64, 128, 256]

A_REASONS = ['压测暴露并发缺陷', '依赖库升级', '安全审计要求', '线上故障复盘',
             '代码评审意见', '容量评估结论', '接口兼容性调整', '灰度观测数据']
B_REASONS = ['一场误会', '一次救助', '利益冲突', '私下承诺',
             '旧事重提', '第三方的劝说', '共同的外敌', '一桩旧账']

FILLER_A = ['这一批改动随当日的发布一起上线。', '评审在午后结束，没有人提出反对。',
            '监控面板上的曲线仍在波动。', '这份改动随后进入了灰度。',
            '构建流水线在夜里跑完。', '相关日志已按发布批次归档。',
            '值班同学记录了当时的资源占用。', '上游接口的响应时间保持稳定。',
            '测试用例在提交后全部通过。', '变更窗口比预计的稍长一些。',
            '会议纪要里留下了几处待办。', '回滚脚本也一并更新了。',
            '发布单上的时间戳没有改动。', '这一轮没有触发额外的告警。',
            '压测机在夜里还开着。', '评审记录同步到了协作平台。',
            '构建缓存这次没有命中。', '灰度观察期按惯例是两天。']
FILLER_B = ['夜里的风从水面吹来。', '镇上的灯一盏盏亮起来。',
            '这一日过得并不平静。', '远处的山影压得很低。', '集市散得比往常早。',
            '渡口的船停了一整天。', '有人在院子里低声说话。', '雨下了半宿才停。',
            '祠堂前的石阶上落了叶子。', '灶上的火一直没有灭。',
            '更夫敲过了三遍锣。', '山道上许久不见人影。',
            '井台边有人在打水。', '屋檐下挂着晒干的辣椒。',
            '远处传来几声犬吠。', '田里的活计还没做完。',
            '日头偏西时起了风。', '街面上的人渐渐散了。']
DETAIL_A = ['改动已在预发环境通过回归。', '相关指标在监控面板上保持平稳。',
            '变更单已归档到发布记录。', '下游调用方收到通知。',
            '回滚预案同时更新。', '接口文档随之同步。', '压测结果附在变更单里。',
            '评审意见逐条闭环。', '构建产物已推送到制品库。', '灰度批次按计划扩大。']
DETAIL_B = ['众人都看在眼里。', '这件事在镇上议论了好几天。', '没有人当面提起。',
            '消息传得很快。', '当时只有少数人知情。', '事后回想起来仍有分歧。',
            '这话是隔着院墙说的。', '在场的人各自沉默了一会儿。', '屋里的灯还亮着。',
            '这件事后来再没人提。']
CONTEXT_A = ['这一轮改动先动了缓存层。', '当天的变更窗口开得比往常早。',
             '发布单上列着几项待办。', '值班同学先复现了问题。',
             '这次改动来自一份评审意见。', '压测报告在下午送到了。',
             '上游的接口刚刚调整过。', '构建失败的记录还挂在流水线上。',
             '运维在群里提了一句容量。', '这一批改动排在发布队列里。']
CONTEXT_B = ['那一日的天色阴沉。', '事情起于一次寻常的照面。',
             '镇上的风声不太对。', '这段日子谁都不太安生。',
             '话是从别处传来的。', '在场的人各有各的打算。',
             '这件事牵动着好几家。', '局势比看上去的要紧。',
             '有人先开了口。', '往后的几天里谁也没闲着。']

INTF = ['none', '同名异体', '同体异名', '同值异时', '嵌套主体']
INTF_B = ['none', '同名异体', '同体异名', '同值异时']   # 嵌套主体只挂 A（项目/模块），B 用其余四档

TYPE_CODE = {'现值': 'present', '历史': 'history', '变更': 'change',
             '时点': 'timepoint', '缘由': 'reason', '状态归属': 'state'}

N_SEQ = {'A': 60, 'B': 30}
# ★ 每 seq 事件上限**分主链/影子链两档**（2026-10-10 修）：
#   A 类语料口径要求「每次提交改 1–3 个属性」——主链必须 ≤3；影子链（同名异体/嵌套主体
#   的干扰实体）是额外实体，单独给 2 的额度，两者相加仍 ≤ MAX_PER_SEQ。旧实现把主链与
#   影子链混在同一个上限 5 里排期，实测主链单次提交会到 4 个属性（超出口径）。
MAX_PER_SEQ = {'A': 5, 'B': 8}            # 主链＋影子链的合计上限（保留作总闸）
MAX_PER_SEQ_PRIM = {'A': 3, 'B': 8}       # 主链上限（A 类＝「1–3 个属性」）
MAX_PER_SEQ_DECOY = {'A': 2, 'B': 2}      # 影子链上限
UNIT = {'A': '次提交', 'B': '章'}
LEAK_RATE = 0.10        # 故意注入「历史值另见他处」句的链占比（供 reconstructible 标记识别）

POOL_OF = {'有效期秒数': [str(x) for x in TTL_POOL], '依赖名': DEP_POOL,
           '位置': B_PLACES, '立场': B_STANCES, '情绪': B_EMOTIONS}

_WORD = re.compile(r'[\W_]+', re.UNICODE)
_SPLIT = re.compile(r'[。；\n]+')


def norm(s) -> str:
    """去空白与非词字符（保留字母/数字/汉字），小写。判分链同口径。"""
    return _WORD.sub('', '' if s is None else str(s)).lower()


# ================= 1. 建链 =================
def build_chains(rng):
    prim, decoys = [], []
    # ---- A 类：3 项目 × 5 链（4 个主属性 + 1 个嵌套模块属性） ----
    # 目标链长 8/15/30/45/60 ⇒ 长链桶可覆盖设计稿的「5→20→80」压力轴（上限受 60 次提交约束）
    a_targets = [60, 45, 30, 15, 8]
    for proj in A_PROJECTS:
        ts = a_targets[:]
        rng.shuffle(ts)
        slots = A_SLOTS[:]
        rng.shuffle(slots)
        for slot, t in zip(slots, ts[:4]):
            prim.append(dict(doc=proj, doc_id=A_DOCID[proj], subject=proj, slot=slot,
                             kind='A', target=t))
        prim.append(dict(doc=proj, doc_id=A_DOCID[proj], subject=proj + A_MODULE_SUFFIX,
                         slot=A_NESTED_SLOT, kind='A', target=ts[4]))
    # ---- B 类：3 故事 × 4 主体 × 4 属性 = 48 链 ----
    b_targets = [14, 12, 11, 10, 9, 8, 7, 6, 6, 5, 5, 5, 5, 5, 5, 5]
    for doc, subs, _former, did in B_STORIES:
        ts = b_targets[:]
        rng.shuffle(ts)
        i = 0
        for sub in subs:
            for slot in B_SLOTS:
                prim.append(dict(doc=doc, doc_id=did, subject=sub, slot=slot,
                                 kind='B', target=ts[i]))
                i += 1
    # ---- 干扰档：每条主链随机取一档 ----
    for c in prim:
        c['interference'] = rng.choice(INTF if c['kind'] == 'A' else INTF_B)
    # ---- 干扰链（同名异体 / 嵌套主体 各配一条影子链，不入题，只做检索干扰） ----
    for c in prim:
        suffix = None
        if c['interference'] == '同名异体':
            suffix = '·同名者'
        elif c['interference'] == '嵌套主体':
            suffix = '·下属'
        if suffix is None:
            continue
        d = dict(c)
        d['subject'] = c['subject'] + suffix
        d['target'] = min(12, max(5, c['target'] // 2))
        d['is_decoy'] = True
        d['decoy_of'] = (c['doc'], c['subject'], c['slot'])
        d['interference'] = 'none'
        decoys.append(d)
    return prim, decoys


# ================= 2. 排期（每条链的 seq 分配） =================
def schedule(chains, n_seq, max_per_seq, rng, prim_limit=None):
    """把各链的事件铺到 1..n_seq 上：列和 ≤ max_per_seq，行和 = target（严格）。

    贪心：每格先算 base=ceil(总剩余/剩余格数)（鸽巢下界），再按「剩余需求降序」取前 k 条
    链各铺一格——降序保证需求最大的链不被拖到最后（rem=1 时单链需求 >1 即不可行，
    此处显式抛错，不静默少铺）。
    `prim_limit`：主链在该 seq 的**独立**额度（影子链另算），用于把 A 类主链压到
    「每次提交 1–3 个属性」的口径内。影子链（is_decoy）不进主链额度。
    """
    need = {i: chains[i]['target'] for i in range(len(chains))}
    seqs = {i: [] for i in range(len(chains))}
    for s in range(1, n_seq + 1):
        tot = sum(need.values())
        if tot == 0:
            break
        rem = n_seq - s + 1
        base = math.ceil(tot / rem)
        if base > max_per_seq:
            raise RuntimeError(f'排期不可行：seq={s} 需要 {base} > 上限 {max_per_seq}')
        if rem == 1 and tot > max_per_seq:
            raise RuntimeError(f'排期不可行：末格需铺 {tot} > 上限 {max_per_seq}')
        k = base + 1 if (base < max_per_seq and rng.random() < 0.35) else base
        active = sorted([i for i in need if need[i] > 0], key=lambda i: -need[i])
        k = max(1, min(k, max_per_seq, len(active), tot))
        n_prim = 0
        placed = 0
        for i in active:
            if placed >= k:
                break
            is_decoy = bool(chains[i].get('is_decoy'))
            if (not is_decoy) and prim_limit is not None and n_prim >= prim_limit:
                continue                       # 主链额度已满，本格不再铺主链
            need[i] -= 1
            seqs[i].append(s)
            placed += 1
            if not is_decoy:
                n_prim += 1
    if sum(need.values()) != 0:
        raise RuntimeError(f'排期未铺完：剩余 {sum(need.values())}')
    return seqs


# ================= 3. 值生成 =================
def gen_one(slot, cur, used, banned, rng, extra_pool):
    if slot == '函数签名':
        for _ in range(400):
            s = f"{rng.choice(SIG_FUNCS)}({', '.join(rng.choice(SIG_ARGS))})"
            if s != cur and s not in used:
                return s
        return f"fn_{rng.randrange(10 ** 6)}()"
    if slot == '配置值':
        for _ in range(400):
            s = f"{rng.choice(CONF_KEYS)}={rng.choice(CONF_VALS)}"
            if s != cur and s not in used:
                return s
        return f"cfg_{rng.randrange(10 ** 6)}"
    pool = extra_pool if slot == '信任对象' else POOL_OF.get(slot, [])
    fresh = [v for v in pool if v != cur and v not in banned]
    if not fresh:
        fresh = [v for v in pool if v != cur]
    if not fresh:
        fresh = list(pool) or ['?']
    return rng.choice(fresh)


def make_values(chain, k, rng, banned, extra_pool):
    slot = chain['slot']
    vals, cur, used = [], None, set()
    for _ in range(k):
        v = gen_one(slot, cur, used, banned, rng, extra_pool)
        vals.append(v)
        used.add(v)
        cur = v
    if chain['interference'] == '同值异时' and k >= 4:
        for _ in range(60):
            i = rng.randrange(0, k - 2)
            j = rng.randrange(i + 2, k)
            if vals[j] != vals[j - 1] and vals[i] != vals[j - 1]:
                vals[j] = vals[i]
                break
    return vals


# ================= 4. 事件序列 =================
def build_events(chain, seqs, rng, banned, extra_pool):
    k = len(seqs)
    vals = make_values(chain, k, rng, banned, extra_pool)
    slot = chain['slot']
    special = rng.choice(['retire', 'unresolved'])
    if special == 'retire':
        sp = k - 1 if rng.random() < 0.5 else rng.randrange(1, max(2, k - 1))
    else:
        sp = rng.randrange(1, max(2, k - 1))          # 未决后必有一次裁定
    sp = min(sp, k - 1)
    alt = None
    if special == 'unresolved':
        base = vals[sp]
        if slot in POOL_OF:
            cand = [v for v in POOL_OF[slot] if v != base]
        elif slot == '信任对象':
            cand = [v for v in extra_pool if v != base]
        else:
            cand = None
        alt = rng.choice(cand) if cand else gen_one(slot, base, set(), set(), rng, extra_pool)
    events, prev = [], None
    for i in range(k):
        to = vals[i]
        if i == sp and special == 'retire':
            to = None
        if i == 0:
            kev = 'create'
        elif to is None:
            kev = 'retire'
        elif prev is None:                                # 退役后重新确立
            kev = 'restore'
        elif i == sp and special == 'unresolved':
            kev = 'unresolve'
        elif i == sp + 1 and special == 'unresolved':
            kev = 'resolve'
        else:
            kev = 'change'
        state = 'retired' if to is None else ('unresolved' if kev == 'unresolve' else 'active')
        reason = '初始建立' if i == 0 else rng.choice(A_REASONS if chain['kind'] == 'A'
                                                     else B_REASONS)
        events.append(dict(seq=seqs[i], frm=prev, to=to,
                           alt=(alt if kev == 'unresolve' else None),
                           state=state, reason=reason, kev=kev))
        prev = to
    out = dict(chain)
    out['seqs'] = list(seqs)
    out['events'] = events
    out['sp'] = sp
    return out


# ================= 5. 渲染 =================
def core_sentence(e, subj, kind):
    slot = e['slot']
    if e['kev'] == 'create':
        return f'{subj} 的{slot}首次确立为 {e["to"]}'
    if e['kev'] == 'change':
        # ★ 不可重建性（2026-10-10 修，编排侧独立核验抓出）：变更句**只写新值**。
        #   旧写法「{subj} 的{slot}由 X 改为 Y」把**前值直接摆在句面上**——历史问
        #   （第 k 次修改前是什么值）于是退化成「找到那句话就能抄」，探针测不到版本化
        #   召回。改为只报新值后，前值必须由**链式追踪**（上一事件的值）得到，这正是
        #   本探针要测的能力。措辞仍取自然语（调整/转为/移到），不含「回退/重新」类暗示。
        if kind == 'B' and slot == '位置':
            return f'{subj} 移到了 {e["to"]}'
        if kind == 'B' and slot == '信任对象':
            return f'{subj} 的信任对象转为 {e["to"]}'
        if kind == 'B' and slot == '立场':
            return f'{subj} 的立场转为 {e["to"]}'
        if kind == 'B' and slot == '情绪':
            return f'{subj} 的情绪转为 {e["to"]}'
        return f'{subj} 的{slot}调整为 {e["to"]}'
    if e['kev'] == 'retire':
        return f'{subj} 的{slot}被撤销，此后不再保留取值'
    if e['kev'] == 'restore':
        # 措辞不含「重新/再次/回退」等反推提示词（见不可重建性约束）
        return f'{subj} 的{slot}此后确立为 {e["to"]}'
    if e['kev'] == 'unresolve':
        return f'{subj} 的{slot}出现两种并存的取值：{e["to"]} 与 {e["alt"]}，尚未裁定'
    return f'{subj} 的{slot}的争议就此裁定为 {e["to"]}'


def render_subject(subject, doc, seq, rename_map):
    key = (doc, subject)
    if key in rename_map and seq < rename_map[key][0]:
        return rename_map[key][1]
    return subject


def build_corpus(chains_by_doc, rename_map, decoy_note, leak_plan, rng):
    """把事件铺成人读自然段：铺垫句 + 事件句（+ 缘由）+ 日常细节句 + 收尾句。
    与状态无关的句子不携带任何值/主体对，只是让段落像人写的、并撑起文本量。
    `leak_plan[(doc,seq)]` 是**故意注入**的「别处另有一处提及历史值」的句子——
    它让部分题目的答案可从本链证据之外获得，供 reconstructible 标记识别与下游剔除。"""
    corpus = []
    for doc, chains in chains_by_doc.items():
        n_seq = N_SEQ[chains[0]['kind']]
        kind = chains[0]['kind']
        ctx_pool = CONTEXT_A if kind == 'A' else CONTEXT_B
        detail_pool = DETAIL_A if kind == 'A' else DETAIL_B
        fill_pool = FILLER_A if kind == 'A' else FILLER_B
        by_seq = {}
        for c in chains:
            for e in c['events']:
                by_seq.setdefault(e['seq'], []).append((c, e))
        renamed = set()
        for s in range(1, n_seq + 1):
            head = (f'第 {s} 次提交（{doc}）。' if kind == 'A'
                    else f'第 {s} 章（{doc}）。')
            sents = [head]
            items = sorted(by_seq.get(s, []), key=lambda t: (t[0]['subject'], t[0]['slot']))
            for c, e in items:
                subj = render_subject(c['subject'], doc, s, rename_map)
                sents.append(rng.choice(ctx_pool))
                core = core_sentence(dict(e, slot=c['slot']), subj, kind)
                if e['kev'] == 'create':
                    sents.append(f'{core}。')
                else:
                    sents.append(f'{core}，起因是{e["reason"]}。')
                sents.append(rng.choice(detail_pool))
                sents.append(rng.choice(detail_pool))
                note = decoy_note.get((doc, c['subject'], s))
                if note:
                    sents.append(note)
                rk = (doc, c['subject'])
                if (rk in rename_map and rename_map[rk][0] == s and not c.get('is_decoy')
                        and rk not in renamed):
                    renamed.add(rk)
                    sents.append(f'{rename_map[rk][1]} 自第 {s} '
                                 f'{"次提交" if kind == "A" else "章"}起改名为 {c["subject"]}。')
            if (doc, s) in leak_plan:
                sents.append(rng.choice(detail_pool))
                sents.append(leak_plan[(doc, s)])
            for _ in range(12):
                sents.append(rng.choice(fill_pool))
            corpus.append(dict(cid=f'{doc}#{s}', doc=doc, seq=s, text=''.join(sents)))
    return corpus


# ================= 6. 从事件日志取真值 =================
def state_at(events, T):
    j = None
    for i, e in enumerate(events):
        if e['seq'] <= T:
            j = i
    if j is None:
        return dict(value=None, state='absent', at_seq=None)
    e = events[j]
    return dict(value=e['to'], state=e['state'], at_seq=e['seq'])


def chain_view(events):
    return [{'seq': e['seq'], 'from': e['frm'], 'to': e['to']} for e in events]


def change_view(events):
    """题面要的「每一次变更前后的值」＝**前后值都有值**的转移。

    首次确立（from=null）不是「变更」；退役后重新确立（from=null）同理；撤回（to=null）
    的语料句只写「被撤销，此后不再保留取值」、不携带前值，要求答卷逐字对上等于要求它
    从别处反推。故 `change_chain` 只留 from/to 皆非空的转移（判分器同口径，见
    probe_judge.want_changes）。`answer.chain` 仍保留全量事件视图供混淆/结构指标使用。

    ★ 2026-10-10 复核整改（甲-3）：**未决/裁定（unresolve/resolve）也不进 change_chain**。
    旧实现只看「from/to 皆非空」，于是把这两个事件也算成「值→值变更」；但语料从不这样
    叙述它们——unresolve 句写的是「出现两种并存的取值：X 与 Y，尚未裁定」（没写「由前值
    变为 X」，也没写 from），resolve 句只写「裁定为 X」（不写前值）。一个忠实读出「此处
    两值并存」的答卷在旧口径下会被判链不完整、行召回记 0——变更链完整率被一个语料从未
    叙述成「变更」的事件系统性压低。故这里按 `kev` 显式排除 unresolve/resolve。
    """
    return [{'seq': e['seq'], 'from': e['frm'], 'to': e['to']} for e in events
            if e['frm'] is not None and e['to'] is not None
            and e.get('kev') not in ('unresolve', 'resolve')]


def build_keys(prim, rng):
    keys = []
    n = 0
    for c in prim:
        evs = c['events']
        k = len(evs)
        N = N_SEQ[c['kind']]
        unit = UNIT[c['kind']]
        s_head = evs[0]['seq']
        i_a = min(max(1, round(k / 3)), k - 2)
        i_b = min(max(2, round(2 * k / 3)), k - 1)
        if i_b <= i_a:
            i_b = min(i_a + 1, k - 1)
        s_a, s_b = evs[i_a]['seq'], evs[i_b]['seq']
        s_sp = evs[c['sp']]['seq']
        ch = chain_view(evs)
        chg = change_view(evs)

        def mk(qtype, at, question, accept=None):
            nonlocal n
            n += 1
            st = state_at(evs, at)
            ans = dict(value=st['value'], state=st['state'], at_seq=st['at_seq'],
                       chain=ch, change_chain=chg)
            if accept:
                ans['accept'] = list(accept)
            if qtype == '缘由':
                ev = [e for e in evs if e['seq'] == s_b][0]
                ans = dict(value=ev['reason'], state=state_at(evs, s_b)['state'],
                           at_seq=s_b, chain=ch, change_chain=chg)
            qid = f'{c["doc_id"]}-{at:03d}-{TYPE_CODE[qtype]}-{n:04d}'
            return dict(qid=qid, type=qtype, doc=c['doc'], doc_id=c['doc_id'],
                        subject=c['subject'], slot=c['slot'], question=question,
                        answer=ans, sample_at_seq=at, chain_len=k,
                        interference=c['interference'], reconstructible=False)

        keys.append(mk('现值', N,
                       f'截至第 {N} {unit}，{c["subject"]} 的{c["slot"]}当前是什么值？'
                       f'（请给出值、状态，以及该值生效的序号）'))
        keys.append(mk('状态归属', N,
                       f'截至第 {N} {unit}，{c["subject"]} 的{c["slot"]}处于什么状态？'
                       f'（现行 active / 退役 retired / 未决 unresolved / 不存在 absent）'))
        keys.append(mk('历史', s_head,
                       f'在第 {s_head} {unit}时，{c["subject"]} 的{c["slot"]}是什么值？'))
        keys.append(mk('历史', s_a,
                       f'在第 {s_a} {unit}时，{c["subject"]} 的{c["slot"]}是什么值？'))
        keys.append(mk('历史', s_b,
                       f'在第 {s_b} {unit}时，{c["subject"]} 的{c["slot"]}是什么值？'))
        # ★ 时点问（2026-10-10 复核整改·甲-5）：取样点 s_sp 落在 unresolve 事件时，语料
        #   把两个取值**平等并列**（「出现两种并存的取值：X 与 Y」），X 记 to、Y 记 alt 只
        #   是句面词序，不是可判定的正确性差异。故此时把 alt 一并列为**可接受替代值**
        #   （accept），判分器 value_correct / future_confused 都认它（见 probe_judge）。
        #   若 alt 在后文才复现（仅 7 道），它仍是「时点之后才生效」——但那 7 道的 alt 由
        #   accept 直接豁免，不再被 value_correct 判错、也不再被 future_confused 记一次。
        sp_ev = evs[c['sp']]
        tpoint_accept = [sp_ev['alt']] if (sp_ev['kev'] == 'unresolve'
                                           and sp_ev.get('alt')) else None
        keys.append(mk('时点', s_sp,
                       f'在第 {s_sp} {unit}这个时间点，{c["subject"]} 的{c["slot"]}'
                       f'的值和状态分别是什么？', accept=tpoint_accept))
        keys.append(mk('变更', N,
                       f'{c["subject"]} 的{c["slot"]}从最初到现在经历过哪些变更？'
                       f'请按序号顺序列出每一次变更前后的值。'))
        keys.append(mk('缘由', s_b,
                       f'{c["subject"]} 的{c["slot"]}为什么在第 {s_b} {unit}被修改？'))
        keys.append(mk('状态归属', s_sp,
                       f'在第 {s_sp} {unit}这个时间点，{c["subject"]} 的{c["slot"]}'
                       f'处于什么状态？'))
        keys.append(mk('状态归属', s_a,
                       f'在第 {s_a} {unit}这个时间点，{c["subject"]} 的{c["slot"]}'
                       f'处于什么状态？'))
    # ---- 补四态之「不存在」：问一对从未出现过的（主体, 属性） ----
    absent_pairs = []
    for proj in A_PROJECTS:
        absent_pairs.append((A_DOCID[proj], proj, '信任对象'))
        absent_pairs.append((A_DOCID[proj], proj + A_MODULE_SUFFIX, '依赖名'))
    for doc, subs, _f, did in B_STORIES:
        absent_pairs.append((did, subs[0], '配置值'))
        absent_pairs.append((did, subs[1], '有效期秒数'))
    for did, subj, slot in absent_pairs:
        doc = ([p for p in A_PROJECTS if A_DOCID[p] == did] or
               [d for d, _s, _f, x in B_STORIES if x == did])[0]
        kind = 'A' if did.startswith('A') else 'B'
        N = N_SEQ[kind]
        unit = UNIT[kind]
        n += 1
        qid = f'{did}-{N:03d}-state-{n:04d}'
        keys.append(dict(
            qid=qid, type='状态归属', doc=doc, doc_id=did, subject=subj, slot=slot,
            question=(f'截至第 {N} {unit}，{subj} 的{slot}处于什么状态？'
                      f'（现行 active / 退役 retired / 未决 unresolved / 不存在 absent）'),
            answer=dict(value=None, state='absent', at_seq=None, chain=[], change_chain=[]),
            sample_at_seq=N, chain_len=0, interference='none', reconstructible=False))
    return keys


# ================= 7. 不可重建性 =================
# 提示词护栏：出现这些措辞即「前值/当前值被句面摆明」。
# ★ 2026-10-10 补：旧版只列「回退/重新/改回」类暗示词，漏掉了「由 X 改为 Y」这种
#   **把旧值直接写在同一句**的句式（编排侧独立核验实测 261/270 段命中，是最大的泄漏面）。
#   现在把该句式一并纳入，作为生成后的机械泄漏扫描（应命中 0）。
_HINT = re.compile(r'(回退到|恢复为|改回|回到原来的|重新|再次|又是|照旧|和之前一样|复归'
                   r'|(由|从)[^，。；]{0,20}(改为|改成|变成|换成|变更为|调整为|转为|移到了|变为))')


def _alias_hit(sent_raw, aliases):
    """主体名命中：句子**以别名开头**（且别名后不紧跟 '·'）才算「提到本主体」。

    两道护栏的理由：
      · '·' 护栏：'猎户项目·缓存模块' 里含子串 '猎户项目'，不设护栏则嵌套主体/同名异体
        的影子链会把无关句子全判成「提到本主体」；
      · 句首护栏：主体名也可能作为**别的属性的值**出现在句中（如 信任对象 的取值就是
        别的故事人物）——「阿禾 的信任对象由 周舟 变为 无人」与周舟无关，若按子串命中
        会把大量 信任对象 题误判成可重建。本生成器一律把主体写在句首，故此护栏成立。
    """
    s = sent_raw.strip()
    for a in aliases:
        if not a:
            continue
        if s.startswith(a) and (len(s) == len(a) or s[len(a)] != '·'):
            return True
    return False


def reconstructible(q, chain_events, subject_aliases, corpus, doc):
    """机械判定：答案值能否在「本链证据之外」的句子里连同主体名一起被找到。

    证据 = 本链全部事件的 (doc, seq)；「之外」= 同 doc 的其他 seq。
    另加提示词扫描（回退到/重新/改回/由…改为…）。
    ★ 2026-10-10 复核整改（甲-6）：**变更问要查整条链的行，而不只是最终值**。
    旧实现只测 norm(answer.value)（＝链尾值）能否在链外找到；中间值（change_chain 各行
    的 from/to）被泄漏句逐字写进语料时**完全不查**，于是这些变更题仍留在主读数里——
    但它们的链条行可以直接从泄漏句抄，测的不是版本化召回。现在对变更问把 change_chain
    每行的 from/to 一并纳入目标集合。
    豁免两条：
      · 缘由问：答案是「起因」而非状态值，题面已给 seq，不需要重建；
      · 归一化后长度 < 2 的值（如「中立」「支持」）：单字在任何含该字的无关句里都会
        命中，判「可重建」是假阳性。
    命中任一 ⇒ 可重建。
    """
    if q.get('type') == '缘由':
        return False
    targets = {norm(q['answer']['value'])}
    if q.get('type') == '变更':          # 变更问：链内**每一行的前后值**都算目标
        for r in (q['answer'].get('change_chain') or []):
            targets.add(norm(r.get('from')))
            targets.add(norm(r.get('to')))
    targets = {t for t in targets if len(t) >= 2}
    if not targets:
        return False
    ev_pairs = {(doc, e['seq']) for e in chain_events}
    aliases = [a for a in subject_aliases if a]
    for c in corpus:
        if c['doc'] != doc or (c['doc'], c['seq']) in ev_pairs:
            continue
        for sent in _SPLIT.split(c['text']):
            s = norm(sent)
            for tgt in targets:
                if tgt in s and _alias_hit(sent, aliases):
                    return True
                if tgt in s and _HINT.search(sent):
                    return True
    return False


def reconstructible_hint_only(q, chain_events, corpus, doc):
    """诊断用：只看**提示词护栏**（_HINT，不看主体名命中）能否在真实语料上触发。

    生成器刻意不写「回退/重新/改回/由…改为…」这类把前值摆明的措辞（见 core_sentence），
    所以这道护栏在生产语料上应当一条都不命中——把命中数打出来，避免「两道护栏」
    里有一道形同虚设却看不出来。
    """
    if q.get('type') == '缘由':
        return False
    tgt = norm(q['answer']['value'])
    if len(tgt) < 2:
        return False
    ev_pairs = {(doc, e['seq']) for e in chain_events}
    for c in corpus:
        if c['doc'] != doc or (c['doc'], c['seq']) in ev_pairs:
            continue
        for sent in _SPLIT.split(c['text']):
            if tgt in norm(sent) and _HINT.search(sent):
                return True
    return False


def leak_scan(corpus):
    """生成后机械泄漏扫描：语料里有没有把「前值/当前值」摆在句面的句式。

    命中数**应为 0**（`core_sentence` 的变更句只写新值）。返回 (命中段 cid 列表, 样例)。
    这是「不可重建性约束」的生成侧守卫——不是靠人眼，而是逐句正则。
    """
    hit_cids, samples = [], []
    for c in corpus:
        for sent in _SPLIT.split(c['text']):
            if _HINT.search(sent):
                hit_cids.append(c['cid'])
                if len(samples) < 3:
                    samples.append(f'{c["cid"]}: {sent.strip()[:60]}')
                break
    return hit_cids, samples


# ================= 8. 主流程 =================
def main() -> None:
    rng = random.Random(SEED)
    prim, decoys = build_chains(rng)

    # 主体别名（同体异名用曾用名；同名异体/嵌套主体用影子名）
    former_of = {}
    for doc, subs, formers, _did in B_STORIES:
        for s, f in zip(subs, formers):
            former_of[(doc, s)] = f
    for p in A_PROJECTS:
        former_of[(p, p)] = A_FORMER[p]

    chains_by_doc = {}
    for c in prim + decoys:
        chains_by_doc.setdefault(c['doc'], []).append(c)

    # 信任对象的值池 = 同文档的其它主体（只用主链主体，不含影子名）+ 无人/外人
    subs_by_doc = {}
    for c in prim:
        subs_by_doc.setdefault(c['doc'], set()).add(c['subject'])

    # 排期 + 事件
    built_by_doc = {}
    for doc, cs in chains_by_doc.items():
        kind = cs[0]['kind']
        seqs = schedule(cs, N_SEQ[kind], MAX_PER_SEQ[kind], rng,
                        prim_limit=MAX_PER_SEQ_PRIM[kind])
        built, used_by_key = [], {}
        for i, c in enumerate(cs):                        # 先主链
            if c.get('is_decoy'):
                continue
            extra = sorted(subs_by_doc.get(doc, set()) - {c['subject']}) + TRUST_EXTRA
            b = build_events(c, seqs[i], rng, set(), extra)
            built.append(b)
            used_by_key[(b['subject'], b['slot'])] = {e['to'] for e in b['events'] if e['to']}
        for i, c in enumerate(cs):                        # 影子链：避开主链用过的值
            if not c.get('is_decoy'):
                continue
            extra = sorted(subs_by_doc.get(doc, set())) + TRUST_EXTRA
            b = build_events(c, seqs[i], rng, used_by_key.get(c['decoy_of'][1:], set()), extra)
            built.append(b)
        built_by_doc[doc] = built

    # 改名点（同体异名：以该主体各链第 2 个事件的 seq 之最小值作为改名点）
    rename_map = {}
    for doc, cs in built_by_doc.items():
        for c in cs:
            if c.get('is_decoy') or c['interference'] != '同体异名':
                continue
            if len(c['events']) < 2:
                continue
            key = (doc, c['subject'])
            rs = c['events'][1]['seq']
            if key not in rename_map or rs < rename_map[key][0]:
                rename_map[key] = (rs, former_of.get(key, c['subject'] + '旧称'))

    # 影子链说明句（每个影子链在其首个事件 seq 处点明「并非同一主体」）
    decoy_note = {}
    for doc, cs in built_by_doc.items():
        for c in cs:
            if not c.get('is_decoy'):
                continue
            primary = c['decoy_of'][1]
            note = (f'需要说明的是，{c["subject"]} 与 {primary} 同名但并非同一主体。'
                    if '同名者' in c['subject'] else
                    f'需要说明的是，{c["subject"]} 是 {primary} 的下属单元，'
                    f'与 {primary} 本身并非同一主体。')
            decoy_note[(doc, c['subject'], c['events'][0]['seq'])] = note

    # 故意注入的「历史值另见他处」句（LEAK_RATE 比例的链各注入一句；见 build_corpus 文档）
    leak_plan = {}
    for doc, cs in built_by_doc.items():
        for c in cs:
            if c.get('is_decoy') or rng.random() >= LEAK_RATE:
                continue
            evs = c['events']
            cands = [i for i in range(max(1, len(evs) - 2))
                     if evs[i]['to'] and len(norm(evs[i]['to'])) >= 2]
            if not cands:
                continue
            i = rng.choice(cands)
            used_seqs = set(c['seqs'])
            free = [s for s in range(1, N_SEQ[c['kind']] + 1) if s not in used_seqs]
            if not free:
                continue
            s_star = rng.choice(free)
            subj = render_subject(c['subject'], doc, s_star, rename_map)
            leak_plan[(doc, s_star)] = (
                leak_plan.get((doc, s_star), '') +
                f'{subj} 的{c["slot"]}早先一度为 {evs[i]["to"]}。')

    corpus = build_corpus(built_by_doc, rename_map, decoy_note, leak_plan, rng)

    prim_built = [c for cs in built_by_doc.values() for c in cs if not c.get('is_decoy')]
    prim_built.sort(key=lambda c: (c['doc_id'], c['subject'], c['slot']))
    keys = build_keys(prim_built, rng)

    # 不可重建性
    by_chain = {(c['doc'], c['subject'], c['slot']): c for c in prim_built}
    for q in keys:
        c = by_chain.get((q['doc'], q['subject'], q['slot']))
        if c is None:
            continue
        aliases = [q['subject'], former_of.get((q['doc'], q['subject']), '')]
        q['reconstructible'] = reconstructible(q, c['events'], aliases, corpus, q['doc'])

    # ---- 日志（答案键的真源） ----
    log = dict(
        seed=SEED,
        n_docs=len(built_by_doc),
        docs=[dict(doc=doc, kind=cs[0]['kind'], n_seq=N_SEQ[cs[0]['kind']],
                   n_chains=len(cs)) for doc, cs in built_by_doc.items()],
        chains=[dict(doc=c['doc'], doc_id=c['doc_id'], subject=c['subject'], slot=c['slot'],
                     kind=c['kind'], interference=c['interference'],
                     is_decoy=bool(c.get('is_decoy')), target=c['target'],
                     seqs=c['seqs'], events=c['events']) for cs in built_by_doc.values()
                for c in cs],
    )

    # ---- 一致性自检：从日志复算每题答案，与 keys 逐字段比对 ----
    log_chains = {(c['doc'], c['subject'], c['slot']): c for c in log['chains']}
    bad = 0
    bad_chg = 0
    for q in keys:
        c = log_chains.get((q['doc'], q['subject'], q['slot']))
        if c is None:
            if q['answer']['state'] != 'absent':
                bad += 1
            continue
        if q['answer'].get('change_chain') != change_view(c['events']):
            bad_chg += 1
        st = state_at(c['events'], q['sample_at_seq'])
        exp = dict(value=st['value'], state=st['state'], at_seq=st['at_seq'])
        if q['type'] == '缘由':
            ev = [e for e in c['events'] if e['seq'] == q['answer']['at_seq']]
            exp = dict(value=ev[0]['reason'] if ev else None,
                       state=state_at(c['events'], q['answer']['at_seq'])['state'],
                       at_seq=q['answer']['at_seq'])
        got = {k: q['answer'][k] for k in ('value', 'state', 'at_seq')}
        if got != exp:
            bad += 1

    # ---- 不可重建性探测器的自检 ----
    # ① 正控（合成片段）：提示句命中、无关句不命中；
    demo_corpus = [dict(doc='X', seq=1, text='值班同学把有效期回退到 3600。'),
                   dict(doc='X', seq=2, text='猎户项目的有效期秒数由 300 改为 600。')]
    demo_hit = reconstructible(dict(type='现值', answer=dict(value='3600')),
                               [dict(seq=9)], ['猎户项目'], demo_corpus, 'X')
    demo_neg = reconstructible(dict(type='现值', answer=dict(value='9999')),
                               [dict(seq=9)], ['猎户项目'], demo_corpus, 'X')
    # ② 正控（真实语料 + 人工注入泄漏）：把某题答案值连同主体名塞进一条无关 seq，
    #    探测器必须从 False 翻到 True——证明标记是算出来的，不是恒 false。
    probe_q = next(q for q in keys
                   if q['type'] == '历史' and len(norm(q['answer']['value'])) >= 2
                   and q['answer']['value'])
    pc = by_chain[(probe_q['doc'], probe_q['subject'], probe_q['slot'])]
    pc_ev = {(probe_q['doc'], e['seq']) for e in pc['events']}
    free = next(c for c in corpus if c['doc'] == probe_q['doc']
                and (c['doc'], c['seq']) not in pc_ev)
    injected = dict(free, text=free['text'] + f'{probe_q["subject"]} 的'
                                            f'{probe_q["slot"]}早先一度为 {probe_q["answer"]["value"]}。')
    perturbed = [injected if c is free else c for c in corpus]
    pc_before = reconstructible(probe_q, pc['events'], [probe_q['subject']],
                                corpus, probe_q['doc'])
    pc_after = reconstructible(probe_q, pc['events'], [probe_q['subject']],
                               perturbed, probe_q['doc'])
    n_rec = sum(1 for q in keys if q['reconstructible'])
    n_hint = 0
    for q in keys:
        c = by_chain.get((q['doc'], q['subject'], q['slot']))
        if c is not None:
            n_hint += 1 if reconstructible_hint_only(q, c['events'], corpus, q['doc']) else 0

    # ---- 写盘 ----
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'corpus.json').write_text(
        json.dumps(corpus, ensure_ascii=False, indent=1), encoding='utf-8')
    (OUT / 'keys.json').write_text(
        json.dumps(keys, ensure_ascii=False, indent=1), encoding='utf-8')
    (OUT / 'synth_log.json').write_text(
        json.dumps(log, ensure_ascii=False, indent=1), encoding='utf-8')

    n_chars = sum(len(c['text']) for c in corpus)
    n_prim = len(prim_built)
    n_dec = len(log['chains']) - n_prim
    print(f'[synth] 一致性自检：keys ↔ synth_log 复算不符 {bad} 题（应为 0）；'
          f'change_chain ↔ 日志复算不符 {bad_chg} 题（应为 0）')
    print(f'[synth] 不可重建性探测器自检：提示句正控={demo_hit}（应 True）'
          f'／无关句负控={demo_neg}（应 False）；'
          f'真实语料注入泄漏前={pc_before} → 注入后={pc_after}（应 False → True）')
    print(f'[synth] 语料内判为可重建（应剔除）的题 {n_rec}/{len(keys)}；'
          f'其中仅由提示词护栏（_HINT）命中的 {n_hint} 题'
          f'（生产语料若为 0，说明该护栏只在正控上生效）；'
          f'故意注入的泄漏句 {len(leak_plan)} 处')
    n_leak, leak_samples = leak_scan(corpus)
    print(f'[synth] 泄漏扫描：把前值/当前值摆在句面的段落 {len(n_leak)}/{len(corpus)}'
          f'（目标 0——变更句只写新值，前值须靠链式追踪）')
    for s in leak_samples:
        print(f'       ⚠ {s}')
    print(f'规模摘要：链数 {n_prim}（A 类 15 / B 类 48，另含干扰链 {n_dec}）｜'
          f'题数 {len(keys)}｜字符数 {n_chars}')


if __name__ == '__main__':
    main()
