# -*- coding: utf-8 -*-
"""状态链召回探针 · 判分器（纯机械 · 零 LLM）

读 `out/keys.json` 与各臂答卷（`runs/chain_<arm>/sut/out/<qid>.json`），逐题机械比对
`value` / `state` / `at_seq` / `chain`；`basis` 走「逐字可回源」——去空白与非词字符后
包含，**且必须落在该题真正检索到的材料里**、`file`/`line` 指向返回的片段（口径见
`verbatim_ok`）。

产出 `out/readings.json`：每臂一行，字段＝
  arm, present, history, chain, chain_row_recall, stale, future, subject_confusion,
  four_state, reason, verbatim, n, n_expected, sampled, complete, counts,
  bucket_main, bucket_main_n
（`readings_excluded.json` 收「指纹不符 / --limit 截断 / 答卷缺题」的臂，不当作整臂读数发布。）

指标（全部机械，口径见函数 docstring）：
  现值正确率 / 历史召回率 / 变更链完整率 / 变更链行召回 / 滞后混淆率 / 超前混淆率 /
  主体混淆率 / 状态归属四态正确率 / 缘由随账率 / 依据轴逐字可回源率。
可推题（reconstructible=True）不进主读数；历史叙述豁免须**自报状态与答案键一致**才生效。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'out'
ROOT = HERE.parent.parent
RUNS = ROOT / 'membench' / 'dist' / '记忆系统对比_v1.0' / 'runs'

# 主读数九项（值域自洽与复算一致性都按这一组比）
METRIC_FIELDS = ('present', 'history', 'chain', 'chain_row_recall', 'stale', 'future',
                 'subject_confusion', 'four_state', 'reason', 'verbatim')

# 校准零号的两个**对照臂**（不是被测系统）；③ 只在被测系统臂上评。
CONTROL_ARMS = ('versionblind', 'closed')
SUT_ORDER = ('lingshu', 'mem0', 'memos', 'hindsight', 'openviking', 'bm25')

# 最小样本量守卫：不足即判据不过（防「n=1 也算过」）
MIN_ARM_N = 100          # 对照臂至少要答这么多非可推题
MIN_BUCKET_N = 5         # 链长桶至少这么多题才允许进单调性判据
MIN_PRESENT_N = 20       # 版本盲臂现值问（有取值）的分母下限
# ★ 效度门 ③ 的**绝对水平下界**（2026-10-10 复核整改）：只要求「非增且非全等」会被
#   恒输出全局最高频答案值的**常数猜测器**蒙过——语料结构本身随链长单调（短链取值少、
#   瞎猜命中率高），实测常数猜测器桶率 short 0.0714 > mid 0.0098 > long 0.0 ⇒ 旧判据
#   c3=True。故 ③ 还须要求被测臂**短链桶的绝对正确率**既达有意义的下界，又显著高于
#   结构基线（语料侧瞎猜期望）。
MIN_SUT_SHORT = 0.30     # 被测臂短链桶主指标绝对下界
MIN_SUT_MARGIN = 0.10    # 短链桶须比结构基线（_structural_baseline 的 short）高出的幅度

_WORD = re.compile(r'[\W_]+', re.UNICODE)


def norm(s) -> str:
    return _WORD.sub('', '' if s is None else str(s)).lower()


def eq(a, b) -> bool:
    return norm(a) == norm(b)


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return default


def keys_fp(keys=None) -> str:
    """当前答案键的指纹（qid/问型/答案四字段），写入 manifest 供判分器校验答卷是否同源。"""
    if keys is None:
        keys = _load(OUT / 'keys.json', [])
    h = hashlib.sha256()
    for k in keys:
        h.update(json.dumps([k['qid'], k['type'], k['answer'].get('value'),
                             k['answer'].get('state'), k['answer'].get('at_seq')],
                            ensure_ascii=False, sort_keys=True).encode('utf-8'))
    return h.hexdigest()[:16]


def _ans_of(arm: str, qid: str):
    p = RUNS / f'chain_{arm}' / 'sut' / 'out' / f'{qid}.json'
    if not p.exists():
        return None
    return _load(p, None)


def _manifest(arm: str) -> dict:
    return _load(RUNS / f'chain_{arm}' / 'manifest.json', {}) or {}


def _material_of(arm: str, qid: str):
    """该题实际检索到的材料：返回 (归一化拼接文本, cid 集合, seq 集合)；无检索件返回 None。"""
    o = _load(RUNS / f'chain_{arm}' / 'retrieval' / f'{qid}.json', None)
    if not isinstance(o, dict):
        return None
    mat = o.get('material') or []
    txt = ''.join((m.get('text') or '') for m in mat if isinstance(m, dict))
    cids, seqs = set(), set()
    for m in mat:
        if not isinstance(m, dict) or m.get('cid') is None:
            continue
        cid = str(m['cid'])
        cids.add(cid)
        if '#' in cid:
            tail = cid.rsplit('#', 1)[1]
            if tail.isdigit():
                seqs.add(int(tail))
    return norm(txt), cids, seqs


def _chain_items(a) -> list[dict]:
    out = []
    for it in (a.get('chain') or []):
        if isinstance(it, dict):
            out.append(it)
    return out


def _value_of(a) -> str:
    v = a.get('value')
    return '' if v is None else str(v)


# ---------------- 单题机械判据 ----------------
def value_correct(a: dict, key: dict) -> bool:
    """值判定：命中主答案值**或**任一「可接受替代值」即算对。

    `answer.accept`（可选）承载**语料本身并列**的取值——目前只有「时点」问落在
    unresolved 事件时（语料写「出现两种并存的取值：X 与 Y」，X 记作 to、Y 记作 alt，
    谁当 to 只是句面词序，不是可判定的正确性差异）。见 synth.build_keys 的 accept 注入。
    """
    if eq(a.get('value'), key['answer']['value']):
        return True
    for x in (key['answer'].get('accept') or []):
        if eq(a.get('value'), x):
            return True
    return False


def want_changes(key: dict) -> list[dict]:
    """题面要的「每一次变更前后的值」＝**前后值都有值**的转移。

    粒度预注册（design §5）：一次修改＝一次「值发生变化」的写入事件。
    首次确立（from=null）、退役后重新确立（from=null）都不是「变更」；撤回（to=null）
    的语料句只写「被撤销，此后不再保留取值」、**不携带前值**，要求答卷逐字对上等于
    要求它从别处反推——故一律不进 want。★ 未决/裁定（unresolve/resolve）同样不进：
    语料把它们叙述成「出现两种并存的取值…尚未裁定」与「争议就此裁定为 X」，都不写前值，
    一个忠实读者无从给出 from（见 synth.change_view 的同口径排除）。生成器
    `answer.change_chain` 已按此过滤，本函数只做兜底过滤。
    """
    ch = key['answer'].get('change_chain')
    if ch is None:                                   # 兼容旧键：就地过滤（旧键无 kev，
        ch = [r for r in (key['answer'].get('chain') or [])   # 故只能按 from/to 过滤）
              if r.get('from') is not None and r.get('to') is not None]
    return [r for r in ch if r.get('from') is not None and r.get('to') is not None]


def chain_rows_hit(a: dict, key: dict) -> tuple[int, int]:
    """返回 (答对的变更行数, 应列的变更行数)——供「链条无缺环」之外的**部分召回**诊断。

    `chain` 是全或无（预注册口径），单看它分不清「一行没对」与「只差两行」；
    这条给出连续读数，避免变更链又变成无法区分系统的地板指标。
    """
    want = want_changes(key)
    if not want:
        return 0, 0
    got = _chain_items(a)
    hit = 0
    for w in want:
        for g in got:
            if (str(g.get('seq')) == str(w['seq']) and eq(g.get('from'), w.get('from'))
                    and eq(g.get('to'), w.get('to'))):
                hit += 1
                break
    return hit, len(want)


def chain_complete(a: dict, key: dict) -> bool:
    """变更链完整率：want 的每一次「值→值」变更都能在答卷 chain 里找到同 seq 同前后值。

    答卷多列的行（create / retire / restore）不扣分——多列不是缺环。
    """
    want = want_changes(key)
    if not want:
        return False
    got = _chain_items(a)
    for w in want:
        hit = False
        for g in got:
            if (str(g.get('seq')) == str(w['seq']) and eq(g.get('from'), w.get('from'))
                    and eq(g.get('to'), w.get('to'))):
                hit = True
                break
        if not hit:
            return False
    return True


def _exempt(a: dict, key: dict) -> bool:
    """历史叙述豁免：只有**自报状态与答案键在该时点的状态一致**时才成立。

    旧实现只看答卷自己填的 state 是不是 retired/unresolved，不交叉校验——把每题都填
    unresolved 就能在答错值的同时把滞后/超前混淆清零。现在必须「状态也判对」才豁免。
    """
    st = str(a.get('state') or '')
    return st in ('retired', 'unresolved') and eq(st, key['answer'].get('state'))


def stale_confused(a: dict, key: dict) -> bool:
    """滞后混淆：现值问里把**已退役的旧值**当作现行值（豁免见 `_exempt`）。"""
    v = norm(a.get('value'))
    if not v:
        return False
    cur = norm(key['answer']['value'])
    if v == cur:
        return False
    olds = {norm(e['to']) for e in key['answer']['chain'][:-1] if e.get('to')}
    if v not in olds:
        return False
    return not _exempt(a, key)


def future_confused(a: dict, key: dict) -> bool:
    """超前混淆：历史/时点问里用了**取样点之后才生效**的值（豁免见 `_exempt`）。

    ★ 2026-10-10 复核整改（甲-4）：旧实现只看「某值是否出现在 seq>T 的事件 to 里」，
    **不检查它是否也出现在 seq≤T**。语料「同值异时」档故意让链内某值复现
    （synth.make_values 的 vals[j]=vals[i]），于是「当时确实成立过的」值会被记成超前混淆，
    超前混淆率按构造虚高。现在要求该值**只在 T 之后出现过**（T 之前从未出现）才算超前。
    另外，若该值本就是答案键列出的**可接受替代值**（accept，见 value_correct），也不算。
    """
    v = norm(a.get('value'))
    if not v or v == norm(key['answer']['value']):
        return False
    if v in {norm(x) for x in (key['answer'].get('accept') or [])}:
        return False
    T = key['sample_at_seq']
    chain = key['answer']['chain']
    later = {norm(e['to']) for e in chain if e.get('to') and e['seq'] > T}
    if v not in later:
        return False
    earlier = {norm(e['to']) for e in chain if e.get('to') and e['seq'] <= T}
    if v in earlier:                                  # 该值在取样点前已成立过 ⇒ 非超前
        return False
    return not _exempt(a, key)


def verbatim_ok(a: dict, mat) -> bool:
    """依据轴：quote 必须是**该题检索到的材料**里的逐字原文，且 file/line 指向返回的片段。

    只查「是全文任意位置的子串」会让模型从语料别处抄一句就得分（与检索无关）；
    quote 须落在本题 material 内，**且 file 与 line 须指向同一个返回片段**（2026-10-10
    复核整改·甲-9：旧实现用 `ok_file or ok_line`，于是「引文取自片段 A、却把 line 填成
    片段 B 的 seq」仍算逐字可回源。现要求 file 命中某返回片段、且 line 等于**该片段自身**
    的序号——cid 形如 `doc#seq`，从中解析出 seq 与 line 比对；cid 无 `#` 时退化为
    「line 须在该题返回的 seq 集合里」）。
    """
    if mat is None:
        return False
    mat_norm, cids, seqs = mat
    if not mat_norm:
        return False
    cid_norms = {norm(c): c for c in cids}
    for b in (a.get('basis') or []):
        if not isinstance(b, dict):
            continue
        q = norm(b.get('quote'))
        if len(q) < 8 or q not in mat_norm:
            continue
        fkey = norm(b.get('file'))
        if cid_norms and fkey not in cid_norms:
            continue
        try:
            line = int(b.get('line'))
        except Exception:
            continue
        if fkey in cid_norms:
            raw_cid = cid_norms[fkey]
            tail = raw_cid.rsplit('#', 1)[1] if '#' in raw_cid else ''
            if tail.isdigit():
                if line == int(tail):          # file 与 line 须同指一个片段
                    return True
                continue
        if line in seqs:                        # cid 无 seq 信息时退回 seq 集合判定
            return True
    return False


# ---------------- 主体混淆（同名异体/嵌套主体的影子链取值） ----------------
def decoy_index() -> dict:
    lg = _load(OUT / 'synth_log.json', {'chains': []})
    idx = {}
    for c in lg.get('chains', []):
        if c.get('is_decoy') and c.get('decoy_of'):
            vals = {norm(e['to']) for e in c['events'] if e.get('to')}
            idx[tuple(c['decoy_of'])] = vals
    return idx


def subject_confused(a: dict, key: dict, decoys: dict) -> bool:
    v = norm(a.get('value'))
    if not v or v == norm(key['answer']['value']):
        return False
    return v in decoys.get((key['doc'], key['subject'], key['slot']), set())


# ---------------- 单臂判分 ----------------
def _bucket(chain_len: int) -> str:
    if chain_len <= 8:
        return 'short'
    if chain_len <= 30:
        return 'mid'
    return 'long'


def _main_ok(k: dict, a: dict):
    """主指标（链长压力轴用）：现值/历史看值对不对，变更看链条全不全；其它问型不进。

    与 `judge_arm` 同分母：答案为 null 的现值/历史题、没有「值→值」变更的变更题
    一律**不进分母**（否则空答臂靠 null 平凡匹配拿分——自检里的坏系统就钻这个空子）。
    """
    if k['type'] in ('现值', '历史'):
        if k['answer']['value'] is None:
            return None
        return value_correct(a, k)
    if k['type'] == '变更':
        if not want_changes(k):
            return None
        return chain_complete(a, k)
    return None


def judge_arm(arm: str, keys: list[dict], doc_norms: dict, decoys: dict) -> dict:
    """只统计**确实有答卷文件**的题（小样 --limit 跑时，未跑的题不进分母）。"""
    pairs = []
    for k in keys:
        if k['reconstructible']:
            continue
        a = _ans_of(arm, k['qid'])
        if a is None:
            continue
        pairs.append((k, a))
    n = len(pairs)

    def has_value(k) -> bool:
        """现值/历史问只统计**存在取值**的题：答案为 null（已退役/不存在）的题里，
        答 null 是无内容的平凡匹配，会把闭卷/空答臂的分数虚高（自检实测空答臂会因此
        拿到 0.24 现值分）。故这两类指标的分母剔除 null 答案题。"""
        return k['answer']['value'] is not None

    def rate(xs):
        return round(sum(1 for x in xs if x) / len(xs), 4) if xs else 0.0

    present = [value_correct(a, k) for k, a in pairs
               if k['type'] == '现值' and has_value(k)]
    history = [value_correct(a, k) for k, a in pairs
               if k['type'] == '历史' and has_value(k)]
    chain = [chain_complete(a, k) for k, a in pairs if k['type'] == '变更']
    chain_rows = [chain_rows_hit(a, k) for k, a in pairs if k['type'] == '变更']
    chain_row_recall = (round(sum(h for h, _ in chain_rows) / sum(t for _, t in chain_rows), 4)
                        if chain_rows and sum(t for _, t in chain_rows) else 0.0)
    stale = [stale_confused(a, k) for k, a in pairs
             if k['type'] == '现值' and has_value(k)]
    # ★ 2026-10-10 复核整改·甲-9：future 分母也须用 has_value 过滤——旧实现把答案为
    #   null 的历史/时点问（如退役点）也计入分母，而 null 答案的题在 future_confused 里
    #   恒返回 False（v 为空），只会**稀释**超前混淆率，偏离「用了取样点之后才生效的值
    #   的比例」这一声明口径。现值/历史已用 has_value，这里对齐。
    future = [future_confused(a, k) for k, a in pairs
              if k['type'] in ('历史', '时点') and has_value(k)]
    subj = [subject_confused(a, k, decoys) for k, a in pairs
            if k['interference'] in ('同名异体', '嵌套主体')]
    four = [eq(a.get('state'), k['answer']['state']) for k, a in pairs
            if k['type'] == '状态归属']
    reason = [value_correct(a, k) for k, a in pairs if k['type'] == '缘由']
    verb = [verbatim_ok(a, _material_of(arm, k['qid'])) for k, a in pairs]

    # 链长三桶的主指标（③ 用；与上面同一批 pairs，故与行内读数不可能矛盾）
    bmain, bmain_n = {}, {}
    for k, a in pairs:
        ok = _main_ok(k, a)
        if ok is None:
            continue
        b = _bucket(k['chain_len'])
        bmain[b] = bmain.get(b, 0) + (1 if ok else 0)
        bmain_n[b] = bmain_n.get(b, 0) + 1
    bucket_main = {b: round(bmain[b] / bmain_n[b], 4) for b in bmain_n if bmain_n[b]}
    counts = dict(present=len(present), history=len(history), chain=len(chain),
                  chain_row_recall=len(chain_rows), stale=len(stale), future=len(future),
                  subject_confusion=len(subj), four_state=len(four), reason=len(reason),
                  verbatim=len(verb))
    return dict(arm=arm, present=rate(present), history=rate(history), chain=rate(chain),
                chain_row_recall=chain_row_recall,
                stale=rate(stale), future=rate(future),
                subject_confusion=rate(subj), four_state=rate(four),
                reason=rate(reason), verbatim=rate(verb), n=n,
                counts=counts, bucket_main=bucket_main, bucket_main_n=bmain_n)


def _corpus_index():
    keys = _load(OUT / 'keys.json', [])
    corpus = _load(OUT / 'corpus.json', [])
    doc_text = {}
    for c in corpus:
        doc_text.setdefault(c['doc'], []).append(c['text'])
    doc_norms = {d: norm(''.join(t)) for d, t in doc_text.items()}
    return keys, doc_norms, decoy_index()


def judge_arms(arms: list[str], write: bool = True) -> list[dict]:
    """判分；**只把「同源且非截断」的臂当整臂读数发布**。

    一条臂进 readings.json 的条件：有 manifest、keys 指纹与当前 keys.json 一致、
    且不是 `--limit` 截断的冒烟答卷、答卷题数不缺。否则进 readings_excluded.json。
    """
    keys, doc_norms, decoys = _corpus_index()
    fp = keys_fp(keys)
    n_expected = sum(1 for k in keys if not k['reconstructible'])
    rows, excluded = [], []
    for arm in arms:
        row = judge_arm(arm, keys, doc_norms, decoys)
        m = _manifest(arm)
        row['keys_fp'] = m.get('keys_fp')
        row['n_expected'] = n_expected
        row['sampled'] = bool(m.get('calib_sample'))
        reasons = []
        if not m:
            reasons.append('无 manifest.json（无法核对同源）')
        elif m.get('keys_fp') != fp:
            reasons.append(f"keys 指纹不符（manifest={m.get('keys_fp')} vs 当前={fp}）")
        if (m.get('limit') or 0) > 0:
            reasons.append(f"答卷为 --limit {m.get('limit')} 的截断冒烟，非整臂读数")
        # 缺题：只统计非可推题，故分母也用非可推题数（n_expected）
        if m.get('keys_fp') == fp and row['n'] < n_expected:
            reasons.append(f"答卷缺题（{row['n']}/{n_expected} 非可推题）")
        row['complete'] = not reasons
        if reasons:
            row['exclude_reason'] = '；'.join(reasons)
            excluded.append(row)
        else:
            rows.append(row)
    if write:
        (OUT / 'readings.json').write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
        (OUT / 'readings_excluded.json').write_text(
            json.dumps(excluded, ensure_ascii=False, indent=1), encoding='utf-8')
    return rows


# ---------------- 校准零号 ----------------
def _bucket_rates(arm: str, keys: list[dict], field: str = 'present') -> dict:
    """按链长三桶（short ≤8 / mid 9–30 / long >30）算某指标的桶内正确率。

    只作**诊断**用（③ 现在从 reading 行的 bucket_main 取，见 calibration）。
    """
    qs = [k for k in keys if not k['reconstructible']]
    if field == 'present':
        qs = [k for k in qs if k['type'] == '现值' and k['answer']['value'] is not None]
    buckets = {}
    for k in qs:
        a = _ans_of(arm, k['qid'])
        if a is None:
            continue
        ok = value_correct(a, k)
        buckets.setdefault(_bucket(k['chain_len']), []).append(ok)
    return {b: round(sum(v) / len(v), 4) for b, v in buckets.items() if v}


def _structural_baseline(keys: list[dict]) -> dict:
    """语料结构压力轴：现值问的「只凭值集合瞎猜」期望正确率 = 1/该链不同取值个数。

    ★ 这是**语料侧诊断**，只读 keys.json、与任何臂无关——**不得**作为效度门判据
    （否则一个答不对任何题的坏系统也能靠它过关）。
    """
    qs = [k for k in keys if not k['reconstructible'] and k['type'] == '现值']
    buckets = {}
    for k in qs:
        vals = {norm(e['to']) for e in k['answer']['chain'] if e.get('to')}
        if not vals:
            continue
        buckets.setdefault(_bucket(k['chain_len']), []).append(1.0 / len(vals))
    return {b: round(sum(v) / len(v), 4) for b, v in buckets.items() if v}


def _nonincreasing(seq: list[float], tol: float = 0.05) -> bool:
    return all(seq[i] >= seq[i + 1] - tol for i in range(len(seq) - 1))


def _all_equal(seq: list[float], tol: float = 1e-6) -> bool:
    return (max(seq) - min(seq)) <= tol


def calibration(readings: list[dict], limit: int = 0, sut_arm: str | None = None,
                control_arms: tuple = CONTROL_ARMS) -> dict:
    """校准零号四条判据（全过才 passed）。

    ① 版本盲指纹（现值≈正常、历史/变更→0）＋现值分母 ≥ MIN_PRESENT_N；
    ② 闭卷核心（各 ≤0.2）＋答题量 ≥ MIN_ARM_N；
    ③ **被测系统臂**的主指标随链长单调退化（≥2 个桶、每桶 ≥ MIN_BUCKET_N）
       **且短链桶达绝对水平下界、且显著高于结构基线**（防常数猜测器蒙过，见 MIN_SUT_SHORT）；
       本轮读数里若**没有被测系统臂**（只跑了 versionblind/closed 两个对照臂），
       ③ 记为「未评」（`criteria.c3 is None`、`gate_stage='controls-only'`）——
       这一阶段 `passed` 仍为 false（不在缺 ③ 的情况下宣布过门），待被测臂答卷后
       再跑一次判分（`probe_judge.py --gate`）把 ③ 补上。
    ④ 读数自洽（**独立复核输入与读数**，不是把输出跟自己比）：九项主读数都在 [0,1]、
       每条臂的答卷与当前 keys **同源且完整**（manifest.keys_fp 一致、非可推题答卷数
       达 n_expected）、且能由**磁盘上的答卷**机械复算（防陈旧/伪造读数）。
    """
    keys, doc_norms, decoys = _corpus_index()
    fp = keys_fp(keys)
    n_expected = sum(1 for k in keys if not k['reconstructible'])
    by = {r['arm']: r for r in readings}
    vb = by.get(control_arms[0])
    cb = by.get(control_arms[1])

    vb_present_n = (vb or {}).get('counts', {}).get('present', 0)
    cb_n = (cb or {}).get('n', 0)
    c1 = bool(vb) and vb['present'] >= 0.5 and vb['history'] <= 0.15 \
        and vb['chain'] <= 0.15 and vb_present_n >= MIN_PRESENT_N
    c2 = bool(cb) and cb['present'] <= 0.2 and cb['history'] <= 0.2 \
        and cb['chain'] <= 0.2 and cb_n >= MIN_ARM_N

    # ③ 只认被测系统臂的读数（对照臂与语料结构都不算）
    if sut_arm is not None:
        sut = by.get(sut_arm)
    else:
        suts = [r for r in readings if r['arm'] not in control_arms]
        suts.sort(key=lambda r: (SUT_ORDER.index(r['arm']) if r['arm'] in SUT_ORDER
                                 else len(SUT_ORDER), r['arm']))
        sut = suts[0] if suts else None
    struct = _structural_baseline(keys)          # 语料结构基线（诊断 + ③ 的下界参照）
    if sut is None:
        c3 = None
        c3_reason = '未评：本轮读数只有对照臂（versionblind/closed），链长压力轴无被测对象'
        sut_buckets = {}
    else:
        bm = sut.get('bucket_main') or {}
        bn = sut.get('bucket_main_n') or {}
        order = [b for b in ('short', 'mid', 'long') if b in bm and bn.get(b, 0) >= MIN_BUCKET_N]
        seq = [bm[b] for b in order]
        monotone = bool(len(seq) >= 2 and _nonincreasing(seq) and not _all_equal(seq))
        # ★ 绝对水平下界：单调性**单独**不够——语料结构本身随链长单调（短链取值少），
        #   一个只会瞎猜（恒输出最高频答案值）的坏系统也能「非增且非全等」。故还须
        #   短链桶既达 MIN_SUT_SHORT，又显著高于结构基线（MIN_SUT_MARGIN）。
        short_rate = bm.get('short') if bn.get('short', 0) >= MIN_BUCKET_N else None
        base_short = struct.get('short')
        floor_ok = short_rate is not None and short_rate >= MIN_SUT_SHORT
        margin_ok = (short_rate is not None and base_short is not None
                     and short_rate >= base_short + MIN_SUT_MARGIN)
        c3 = bool(monotone and floor_ok and margin_ok)
        sut_buckets = {b: {'rate': bm.get(b), 'n': bn.get(b)} for b in bm}
        if c3:
            c3_reason = (f'被测臂 {sut["arm"]} 桶 {order}＝{seq}，'
                         f'短链 {short_rate} ≥ 下界 {MIN_SUT_SHORT} 且 ≥ 结构基线 '
                         f'{base_short}+{MIN_SUT_MARGIN}')
        elif not monotone:
            c3_reason = (f'被测臂 {sut["arm"]} 桶不满足单调退化（可用桶 {order}，值 {seq}）')
        elif not floor_ok:
            c3_reason = (f'被测臂 {sut["arm"]} 短链桶 {short_rate} 低于绝对下界 '
                         f'{MIN_SUT_SHORT}（单调但绝对水平不合格，疑为常数猜测/瞎猜系统）')
        else:
            c3_reason = (f'被测臂 {sut["arm"]} 短链桶 {short_rate} 未显著高于结构基线 '
                         f'{base_short}（要求 ≥ +{MIN_SUT_MARGIN}）')

    # ④ 自洽（2026-10-10 复核整改）：
    #   旧实现只把 readings 与 `judge_arm` 现算结果逐字段比对，而 readings 本来就是
    #   `judge_arm` 的输出 ⇒ 对「本管线生成的 calibration.json」**恒真**，唯一能触发它
    #   的是事后手改文件——它不独立验证任何东西，却占着四门之一。
    #   现在 ④ 改为**独立复核输入与读数**，三件事都必须过：
    #     (a) 每条臂的答卷**同源且完整**——manifest.keys_fp == 当前 keys 指纹、且
    #         非可推题答卷数 == n_expected（缺题/换语料重跑会当场失败，这是真会发生的
    #         管线故障，判分器在此之前只是把这类臂**静默剔除**、并不会让门不过）；
    #     (b) 九项主读数都在 [0,1]（防越界/伪造）；
    #     (c) 读数能由**磁盘上的答卷**独立复算（防陈旧 readings.json / 手改）。
    #   三件事各由不同来源（manifest / 值域 / 答卷文件）支撑，不再是把输出跟自己比。
    fresh = {r['arm']: judge_arm(r['arm'], keys, doc_norms, decoys) for r in readings}
    in_range = all(isinstance(r.get(f), (int, float)) and 0.0 <= r[f] <= 1.0
                   for r in readings for f in METRIC_FIELDS)
    same_source = all(_manifest(r['arm']).get('keys_fp') == fp for r in readings)
    complete = all(r.get('n') == n_expected for r in readings)
    repro = all(r.get(f) is not None
                and abs(float(r[f]) - float(fresh[r['arm']][f])) < 1e-9
                for r in readings for f in METRIC_FIELDS) and \
        all(r.get('n') == fresh[r['arm']]['n'] for r in readings)
    c4 = bool(in_range and repro and same_source and complete)
    if c4:
        c4_reason = '值域合法、答卷同源完整、且读数可由答卷独立复算'
    elif not in_range:
        c4_reason = '指标值域越界'
    elif not same_source:
        c4_reason = '答卷与当前 keys 不同源（manifest.keys_fp 不符，或 manifest 缺失）'
    elif not complete:
        c4_reason = f'答卷缺题（存在臂的非可推题答卷数 < {n_expected}）'
    else:
        c4_reason = '读数与答卷复算不一致（陈旧/被改写）'

    passed = bool(c1 and c2 and c4 and c3 is True)
    stage = 'full' if c3 is not None else 'controls-only'
    details = (
        f'① 版本盲指纹：现值 {vb["present"] if vb else None}（要求 ≥0.5）、'
        f'历史 {vb["history"] if vb else None}、变更链 {vb["chain"] if vb else None}'
        f'（要求 ≤0.15）、现值分母 {vb_present_n}（要求 ≥{MIN_PRESENT_N}）'
        f'→ {"过" if c1 else "不过"}；'
        f'② 闭卷核心：现值 {cb["present"] if cb else None} / 历史 {cb["history"] if cb else None}'
        f' / 变更链 {cb["chain"] if cb else None}（各 ≤0.2）、答题量 {cb_n}（≥{MIN_ARM_N}）'
        f'→ {"过" if c2 else "不过"}；'
        f'③ 链长单调（**被测系统臂**）：{c3_reason}；结构基线 {struct}（仅诊断，不作判据）'
        f'→ {("过" if c3 else ("不过" if c3 is False else "未评"))}；'
        f'④ 读数自洽：{c4_reason} → {"过" if c4 else "不过"}。'
        f'（本次 limit={limit or "全量"}；阶段={stage}；'
        f'口径：可推题不进主读数，历史叙述豁免须状态判对。）')
    return dict(version_blind=dict(present=vb['present'] if vb else 0.0,
                                   history=vb['history'] if vb else 0.0,
                                   chain=vb['chain'] if vb else 0.0),
                closed_book=(round((cb['present'] + cb['history'] + cb['chain']) / 3, 4)
                             if cb else 0.0),
                chain_length_monotonic=bool(c3 is True),
                sut_arm=sut['arm'] if sut else None,
                sut_buckets=sut_buckets,
                gate_stage=stage,
                criteria=dict(c1=bool(c1), c2=bool(c2), c3=c3, c4=bool(c4)),
                passed=passed, details=details)


# ---------------- 自检（不调用 LLM：伪造 oracle / 对照臂 / 坏系统，验证判分器与效度门） ----------------
def _check(name: str, cond: bool, extra: str = '') -> None:
    print(f'[selftest] {name}: {"PASS" if cond else "FAIL"} {extra}')
    if not cond:
        raise AssertionError(name)


def selftest() -> None:
    """机械自检：① 判分器认得出 oracle/空答；② 变更链粒度、豁免、依据轴三条判据可被
    正反例区分；③ 效度门 ③④ 可失败（坏系统不过、好系统过、读数被改写不过）。"""
    keys, doc_norms, decoys = _corpus_index()
    corpus = _load(OUT / 'corpus.json', [])
    fp = keys_fp(keys)
    by_seq = {(c['doc'], c['seq']): c['text'] for c in corpus}

    # ---- 单元级正反例 ----
    k_act = dict(answer=dict(value='v9', state='active', at_seq=9,
                             chain=[{'seq': 1, 'from': None, 'to': 'v1'},
                                    {'seq': 5, 'from': 'v1', 'to': 'v9'}],
                             change_chain=[{'seq': 5, 'from': 'v1', 'to': 'v9'}]))
    _check('豁免：自报 unresolved 但键为 active ⇒ 仍计滞后混淆',
           stale_confused(dict(value='v1', state='unresolved'), k_act) is True)
    k_ret = dict(answer=dict(value=None, state='retired', at_seq=5,
                             chain=[{'seq': 1, 'from': None, 'to': 'v1'},
                                    {'seq': 5, 'from': 'v1', 'to': None}],
                             change_chain=[]))
    _check('豁免：自报 retired 且键为 retired ⇒ 历史叙述豁免生效',
           stale_confused(dict(value='v1', state='retired'), k_ret) is False)
    _check('豁免：自报 retired 但键为 unresolved ⇒ 不豁免（状态须判对）',
           stale_confused(dict(value='v1', state='retired'),
                          dict(answer=dict(value='v9', state='unresolved', at_seq=9,
                                           chain=[{'seq': 1, 'from': None, 'to': 'v1'},
                                                  {'seq': 5, 'from': 'v1', 'to': 'v9'}],
                                           change_chain=[{'seq': 5, 'from': 'v1', 'to': 'v9'}]))
                          ) is True)
    _check('变更链：只列「值→值」变更即算完整（不要求 create/retire 行）',
           chain_complete(dict(chain=[{'seq': 5, 'from': 'v1', 'to': 'v9'}]), k_act) is True)
    _check('变更链：缺该次变更 ⇒ 不完整',
           chain_complete(dict(chain=[{'seq': 1, 'from': None, 'to': 'v1'}]), k_act) is False)
    _check('变更行召回：答对 0/1 行、行召回 0.0（链条仍判不完整）',
           chain_rows_hit(dict(chain=[{'seq': 1, 'from': None, 'to': 'v1'}]), k_act) == (0, 1))
    mat = (norm('猎户项目的有效期秒数由 300 改为 600，起因是压测暴露并发缺陷。'), {'A1#5'}, {5})
    _check('依据轴：quote 在材料内且 file 指向返回片段 ⇒ 命中',
           verbatim_ok(dict(basis=[{'file': 'A1#5', 'line': 5,
                                    'quote': '由 300 改为 600'}]), mat) is True)
    _check('依据轴：quote 不在材料内（别处语料）⇒ 不命中',
           verbatim_ok(dict(basis=[{'file': 'A1#5', 'line': 5,
                                    'quote': '井台边有人在打水'}]), mat) is False)
    _check('依据轴：quote 在材料内但 file/line 都不是返回片段 ⇒ 不命中',
           verbatim_ok(dict(basis=[{'file': 'A9#99', 'line': 99,
                                    'quote': '由 300 改为 600'}]), mat) is False)
    # ★ 甲-9：file 与 line 必须指向**同一个**返回片段（旧实现 ok_file or ok_line 会放行）
    mat2 = (norm('甲#1 片段一的正文内容。乙#2 片段二的正文内容。'), {'甲#1', '乙#2'}, {1, 2})
    _check('依据轴：file 命中片段 A、line 命中片段 B ⇒ 不命中（须同片段）',
           verbatim_ok(dict(basis=[{'file': '甲#1', 'line': 2,
                                    'quote': '片段一的正文内容'}]), mat2) is False)
    _check('依据轴：file 与 line 同指片段 A ⇒ 命中',
           verbatim_ok(dict(basis=[{'file': '甲#1', 'line': 1,
                                    'quote': '片段一的正文内容'}]), mat2) is True)
    # ★ 甲-4：同值异时——某值在取样点前已成立过，即便 T 之后又出现，也不算超前混淆
    k_rec = dict(answer=dict(value='vB', state='active', at_seq=3,
                             chain=[{'seq': 1, 'from': None, 'to': 'vA'},
                                    {'seq': 3, 'from': 'vA', 'to': 'vB'},
                                    {'seq': 5, 'from': 'vB', 'to': 'vA'},
                                    {'seq': 9, 'from': 'vA', 'to': 'vB'}],
                             change_chain=[]),
                 sample_at_seq=3)
    _check('超前混淆：候选值在取样点前已出现过（同值异时）⇒ 不算超前（旧实现会误判）',
           future_confused(dict(value='vA'), k_rec) is False)
    k_fut = dict(answer=dict(value='vB', state='active', at_seq=1,
                             chain=[{'seq': 1, 'from': None, 'to': 'vB'},
                                    {'seq': 9, 'from': 'vB', 'to': 'vA'}],
                             change_chain=[]),
                 sample_at_seq=1)
    _check('超前混淆：候选值仅在取样点之后才出现 ⇒ 算超前',
           future_confused(dict(value='vA'), k_fut) is True)
    # ★ 甲-5：时点问落在 unresolved 点，alt 是语料并列的可接受替代值
    k_acc = dict(answer=dict(value='X', state='unresolved', at_seq=5, accept=['Y'],
                             chain=[{'seq': 5, 'from': 'W', 'to': 'X'}], change_chain=[]),
                 sample_at_seq=5)
    _check('时点问 accept：答卷给出并列的另一取值 ⇒ 判对',
           value_correct(dict(value='Y'), k_acc) is True)
    _check('时点问 accept：alt 在后文复现也不算超前混淆',
           future_confused(dict(value='Y'), k_acc) is False)

    # ---- 端到端：伪造答卷（含材料件），跑真判分器 ----
    def oracle(k):
        seg = by_seq.get((k['doc'], k['sample_at_seq']), '')
        return dict(value=k['answer']['value'], state=k['answer']['state'],
                    at_seq=k['answer']['at_seq'], chain=k['answer']['chain'],
                    basis=[{'file': f'{k["doc"]}#{k["sample_at_seq"]}',
                            'line': k['sample_at_seq'], 'quote': seg[:40] or 'x' * 8}])

    def empty(k):
        return dict(value=None, state=None, at_seq=None, chain=[], basis=[])

    def vb_fake(k):
        """版本盲伪记忆：现值答对、历史/变更全空。"""
        if k['type'] == '现值':
            return dict(value=k['answer']['value'], state=k['answer']['state'],
                        at_seq=k['answer']['at_seq'], chain=[], basis=[])
        return empty(k)

    def bad_sut(k):
        """坏系统：答不对任何题。"""
        return empty(k)

    def good_sut(k):
        """好系统（仅用于证 ③ 可被满足）：短链答对、中/长链答错。"""
        b = _bucket(k['chain_len'])
        if b == 'short':
            return oracle(k)
        return empty(k)

    def only_changes(k):
        """只列「值→值」变更的系统（变更链粒度回归用）。"""
        if k['type'] == '变更':
            return dict(value=k['answer']['value'], state=k['answer']['state'],
                        at_seq=k['answer']['at_seq'],
                        chain=want_changes(k), basis=[])
        return empty(k)

    # ★ 甲-1：常数猜测器——恒输出全局最高频答案值，完全没有记忆。旧判据 ③ 只看
    #   「非增且非全等」会被它蒙过（语料结构本身随链长单调）；加绝对水平下界后必须失败。
    from collections import Counter as _C
    _mode = _C(str(k['answer']['value']) for k in keys
               if k['answer']['value'] is not None).most_common(1)[0][0]

    def const_sut(k):
        return dict(value=_mode, state='active', at_seq=None, chain=[], basis=[])

    def fake(name, fn):
        d = RUNS / f'chain_{name}' / 'sut' / 'out'
        d.mkdir(parents=True, exist_ok=True)
        (RUNS / f'chain_{name}' / 'retrieval').mkdir(parents=True, exist_ok=True)
        for k in keys:
            (d / f'{k["qid"]}.json').write_text(
                json.dumps(fn(k), ensure_ascii=False), encoding='utf-8')
            # 材料件：给本题 doc 的全部 seq（让 oracle 的 quote 可回源）
            mat = [{'cid': f'{k["doc"]}#{c["seq"]}', 'text': c['text'], 'score': 1.0}
                   for c in corpus if c['doc'] == k['doc']]
            (RUNS / f'chain_{name}' / 'retrieval' / f'{k["qid"]}.json').write_text(
                json.dumps({'qid': k['qid'], 'material': mat}, ensure_ascii=False),
                encoding='utf-8')
        (RUNS / f'chain_{name}' / 'manifest.json').write_text(
            json.dumps({'arm': name, 'phase': 'ask', 'keys_fp': fp,
                        'n_questions': len(keys), 'limit': 0, 'calib_sample': 0},
                       ensure_ascii=False), encoding='utf-8')

    names = ['selftest_oracle', 'selftest_empty', 'selftest_vb', 'selftest_changes',
             'selftest_bad', 'selftest_good', 'selftest_const']
    fake('selftest_oracle', oracle)
    fake('selftest_empty', empty)
    fake('selftest_vb', vb_fake)
    fake('selftest_changes', only_changes)
    fake('selftest_bad', bad_sut)
    fake('selftest_good', good_sut)
    fake('selftest_const', const_sut)
    try:
        rows = {r['arm']: r for r in judge_arms(names, write=False)}
        o = rows['selftest_oracle']
        _check('oracle：现值/历史/变更链/行召回/四态/缘由/依据轴 全 1.0',
               o['present'] == 1.0 and o['history'] == 1.0 and o['chain'] == 1.0
               and o['chain_row_recall'] == 1.0
               and o['four_state'] == 1.0 and o['reason'] == 1.0 and o['verbatim'] == 1.0,
               f'(present={o["present"]}, history={o["history"]}, chain={o["chain"]}, '
               f'row_recall={o["chain_row_recall"]}, reason={o["reason"]}, '
               f'verbatim={o["verbatim"]})')
        e = rows['selftest_empty']
        _check('空答：九项主读数全 0',
               all(e[f] == 0.0 for f in METRIC_FIELDS))
        v = rows['selftest_vb']
        _check('版本盲指纹：现值 1.0 / 历史 0.0 / 变更链 0.0',
               v['present'] == 1.0 and v['history'] == 0.0 and v['chain'] == 0.0,
               f'(present={v["present"]}, history={v["history"]}, chain={v["chain"]})')
        ch = rows['selftest_changes']
        _check('只列变更（不含 create/retire）的系统：变更链完整率 1.0、行召回 1.0',
               ch['chain'] == 1.0 and ch['chain_row_recall'] == 1.0,
               f'(chain={ch["chain"]}, row_recall={ch["chain_row_recall"]})')

        # ---- 效度门可失败性 ----
        ctl = ('selftest_vb', 'selftest_empty')
        bad = calibration([v, e, rows['selftest_bad']], sut_arm='selftest_bad',
                          control_arms=ctl)
        _check('③ 可失败：坏系统（全 0）→ chain_length_monotonic=False',
               bad['chain_length_monotonic'] is False and bad['passed'] is False,
               f'(sut={bad["sut_arm"]}, buckets={bad["sut_buckets"]})')
        good = calibration([v, e, rows['selftest_good']], sut_arm='selftest_good',
                           control_arms=ctl)
        _check('③ 可满足：好系统（短链对/长链错）→ ③ 过、四条全过',
               good['chain_length_monotonic'] is True and good['passed'] is True,
               f'(sut={good["sut_arm"]}, buckets={good["sut_buckets"]})')
        # 仅对照臂（工作流 calibrate 现状）→ ③ 不可评、明确报「未评」，且不宣布过门
        only_ctl = calibration([v, e], control_arms=ctl)
        _check('③ 不可评：只有对照臂 → c3=None / gate_stage=controls-only / passed=False',
               only_ctl['criteria']['c3'] is None
               and only_ctl['chain_length_monotonic'] is False
               and only_ctl['gate_stage'] == 'controls-only'
               and only_ctl['sut_arm'] is None
               and only_ctl['passed'] is False
               and '未评' in only_ctl['details'])
        # ④ 可失败：读数被改写
        tampered = [dict(v, present=0.99), e, rows['selftest_good']]
        t = calibration(tampered, sut_arm='selftest_good', control_arms=ctl)
        _check('④ 可失败：读数与答卷复算不一致 → 不过',
               t['criteria']['c4'] is False and t['passed'] is False)
        # ★ 甲-1：常数猜测器（单调但绝对水平极低）必须让 ③ 失败
        cs = rows['selftest_const']
        cst = calibration([v, e, cs], sut_arm='selftest_const', control_arms=ctl)
        _check('③ 可失败：常数猜测器（桶率随链长单调但水平极低）→ 不过',
               cst['chain_length_monotonic'] is False and cst['passed'] is False,
               f'(buckets={cst["sut_buckets"]})')
        # ★ 甲-2：④ 独立于 judge_arm 复算——manifest 指纹不符（不同源）须让 ④ 失败
        mf = RUNS / 'chain_selftest_good' / 'manifest.json'
        bak = mf.read_text(encoding='utf-8')
        try:
            mf.write_text(json.dumps({'arm': 'selftest_good', 'keys_fp': 'deadbeef',
                                      'limit': 0}, ensure_ascii=False), encoding='utf-8')
            ns = calibration([v, e, rows['selftest_good']], sut_arm='selftest_good',
                             control_arms=ctl)
            _check('④ 可失败：答卷与当前 keys 不同源（manifest.keys_fp 不符）→ 不过',
                   ns['criteria']['c4'] is False and ns['passed'] is False
                   and '不同源' in ns['details'])
        finally:
            mf.write_text(bak, encoding='utf-8')
    finally:
        # 自检产物不留在 runs/ 里（否则缺省扫描会把它当成真臂）
        import shutil
        for name in names:
            shutil.rmtree(RUNS / f'chain_{name}', ignore_errors=True)
    print('[selftest] 全部通过')


def main() -> None:
    ap = argparse.ArgumentParser(description='状态链召回探针 · 机械判分器（零 LLM）')
    ap.add_argument('--arms', default='',
                    help='逗号分隔的臂名（缺省＝扫描 runs/chain_* 下已存在的臂）')
    ap.add_argument('--selftest', action='store_true',
                    help='用伪造答卷（oracle/对照臂/坏系统）自检判分器与效度门，不调用 LLM')
    ap.add_argument('--gate', action='store_true',
                    help='判分后**在全部现存臂上**评一次校准零号并写 out/calibration.json'
                         '（③ 需要被测系统臂的答卷，故须在被测臂答完之后跑）')
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    if a.arms:
        arms = [x.strip() for x in a.arms.split(',') if x.strip()]
    else:
        arms = sorted(p.name[len('chain_'):] for p in RUNS.glob('chain_*')
                      if (p / 'sut' / 'out').is_dir())
    rows = judge_arms(arms)
    print(json.dumps(rows, ensure_ascii=False, indent=1))
    if a.gate:
        excluded = _load(OUT / 'readings_excluded.json', [])
        if excluded:
            print('[gate] 以下臂被剔出整臂读数（指纹不符/截断/缺题）：'
                  + '；'.join(f"{r['arm']}（{r['exclude_reason']}）" for r in excluded))
        calib = calibration(rows)
        (OUT / 'calibration.json').write_text(
            json.dumps(calib, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f"[gate] calibration.json 已写出：passed={calib['passed']}｜"
              f"判据 {calib['criteria']}｜③ 被测臂={calib['sut_arm']}")
        print('[gate] ' + calib['details'])


if __name__ == '__main__':
    main()
