"""hive-memory-bench 状态链轨（chain/ v0.2）零模型测试：判别记忆版本账本 vs 检索臂。

预注册见 chain_prereg.md。官方判分器 chain/tools/probe_judge.py 原样复用，只改 RUNS/OUT。
Usage: python -B -X utf8 nl_eval/chain_bench.py <hive-memory-bench> [--arms a,b] [--out DIR]
"""
from __future__ import annotations

import argparse, collections, json, re, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAN = HERE.parent.parent
sys.path[:0] = [str(HERE.parent), str(TAN / 'agm' / 'rrf3')]
import nl_interpret as NL                       # noqa: E402

DEV = {'A1', 'B1'}
K, CHAIN_K = 6, 60
CAP, CHAIN_CAP = 14000, 80000
SENT = re.compile(r'(?<=[。！？!?；;])')

# ------------------------------------------------------------------ extraction
# 通用中文版本动词（不含任何实体/属性词表）
V_SET = r'(?:首次确立为|此后确立为|确立为|调整为|调整成|改为|改成|转为|变为|设为|定为|当前为|现为)'
R_UNRES = re.compile(r'^(?P<e>.+?)\s*的(?P<f>[^，,。]{1,20}?)出现两种并存的取值[：:]\s*(?P<v>[^，,。]+?)\s*与\s*(?P<a>[^，,。]+?)[，,]\s*尚未裁定')
R_RESOLVE = re.compile(r'^(?P<e>.+?)\s*的(?P<f>[^，,。]{1,20}?)的?争议(?:就此)?裁定为\s*(?P<v>[^，,。（(]+)')
R_RETIRE = re.compile(r'^(?P<e>.+?)\s*的(?P<f>[^，,。]{1,20}?)(?:被撤销|已撤销|当前已撤销|不再保留取值)')
R_SET = re.compile(r'^(?P<e>.+?)\s*的(?P<f>[^，,。]{1,20}?)' + V_SET + r'\s*(?P<v>[^，,。（(]+)')
R_MOVE = re.compile(r'^(?P<e>[^，,。的]+?)\s*(?:移到了|移到|搬到了|搬到|去了|来到了)\s*(?P<v>[^，,。（(]+)')
R_REASON = re.compile(r'[，,]\s*(?:起因是|原因是|因为)(?P<r>[^，,。]+)')
R_RENAME = re.compile(r'^(?P<a>[^，,。]+?)\s*自第\s*(?P<n>\d+)\s*\S{0,3}?起改名为\s*(?P<b>[^，,。]+)')
R_SEQCLK = re.compile(r'第\s*(?P<n>\d+)\s*(?:次提交|章)\s*生效')
R_PAST = re.compile(r'(早先|曾经|以前|一度)')


def strip_lead(s):
    s = s.strip()
    s = re.sub(r'^(需要说明的是|另外|此外|同时)[，,]?', '', s)
    return s.strip()


def ext_events(sentence, seq):
    """返回 [(kind, entity, facet, value, alt, reason, eff_seq)] 或 [('rename', a, b, n)]。"""
    s = strip_lead(sentence)
    if R_PAST.search(s):
        return []                                   # 回忆性提及不改变状态
    m = R_RENAME.search(s)
    if m:
        return [('rename', m.group('a').strip(), m.group('b').strip(), int(m.group('n')))]
    r = R_REASON.search(s)
    reason = r.group('r').strip() if r else None
    c = R_SEQCLK.search(s)
    eff = int(c.group('n')) if c else seq
    for kind, rx in (('unresolve', R_UNRES), ('resolve', R_RESOLVE), ('retire', R_RETIRE), ('set', R_SET)):
        m = rx.search(s)
        if m:
            d = m.groupdict()
            return [(kind, d['e'].strip(), d['f'].strip(), (d.get('v') or '').strip() or None,
                     (d.get('a') or '').strip() or None, reason, eff)]
    m = R_MOVE.search(s)
    if m:
        return [('set', m.group('e').strip(), '位置', m.group('v').strip(), None, reason, eff)]
    return []


def frozen_events(sentence, seq):
    cands, _, _ = NL.interpret(sentence, recorded_at=seq)
    out = []
    for c in cands:
        if c.op in ('state', 'correct') and c.entity and c.facet and c.value is not None:
            out.append(('set', c.entity, c.facet, str(c.value), None, None, seq))
    return out


class Ledger:
    """槽位 × 生效序号 的版本账本（判别记忆语义：每条事件保留原句与来源）。"""

    def __init__(self, extractor):
        self.ex = extractor
        self.ev = collections.defaultdict(list)     # (doc, entity, facet) -> events
        self.alias = {}                             # (doc, old) -> new

    def ingest(self, doc, cid, seq, text):
        for sent in SENT.split(text):
            if not sent.strip():
                continue
            for e in self.ex(sent, seq):
                if e[0] == 'rename':
                    self.alias[(doc, e[1])] = e[2]
                    continue
                kind, ent, fac, v, alt, reason, eff = e
                self.ev[(doc, ent, fac)].append(dict(kind=kind, seq=eff, value=v, alt=alt,
                                                     reason=reason, cid=cid, quote=sent.strip()))

    def finalize(self):
        # 按别名把旧称下的事件并入新称
        merged = collections.defaultdict(list)
        for (doc, ent, fac), evs in self.ev.items():
            seen = set()
            while (doc, ent) in self.alias and ent not in seen:
                seen.add(ent)
                ent = self.alias[(doc, ent)]
            merged[(doc, ent, fac)].extend(evs)
        self.ev = {k: sorted(v, key=lambda e: e['seq']) for k, v in merged.items()}
        return self

    def finalize_from_raw(self):
        return self.finalize()

    def slot(self, doc, ent, fac):
        if (doc, ent, fac) in self.ev:
            return self.ev[(doc, ent, fac)]
        # 主体须精确（避免同名异体/下属单元混淆）；属性用 bigram 最近匹配
        facs = [k[2] for k in self.ev if k[0] == doc and k[1] == ent]
        best, sc = NL._best(fac, facs) if facs else (None, 0)
        if best is not None and sc >= .5:
            return self.ev[(doc, ent, best)]
        return []


def state_at(evs, T):
    cur = None
    for e in evs:
        if e['seq'] <= T:
            cur = e
    if cur is None:
        return dict(state='absent', value=None, at=None, ev=None)
    k = cur['kind']
    if k == 'retire':
        return dict(state='retired', value=None, at=cur['seq'], ev=cur)
    if k == 'unresolve':
        return dict(state='unresolved', value=cur['value'], at=cur['seq'], ev=cur)
    return dict(state='active', value=cur['value'], at=cur['seq'], ev=cur)


# ------------------------------------------------------------------ questions
R_Q_SEQ = re.compile(r'第\s*(\d+)\s*(?:次提交|章)')
R_Q_SLOT = re.compile(r'(?:^|[，,])\s*(?P<e>[^，,]+?)\s*的(?P<f>[^，,？?]+?)(?:当前是|处于|是什么|的值和|从最初|为什么)')


def parse_q(q, n_seq):
    t = q
    typ = ('缘由' if '为什么' in t else '变更' if ('经历过' in t or '变更' in t) else
           '状态归属' if '处于什么状态' in t else '现值' if '截至' in t and '当前' in t else
           '时点' if '时间点' in t else '历史')
    m = R_Q_SEQ.search(t)
    T = int(m.group(1)) if m else n_seq
    m = R_Q_SLOT.search(t)
    ent, fac = (m.group('e').strip(), m.group('f').strip()) if m else (None, None)
    return typ, T, ent, fac


def answer(ledger, doc, q, n_seq):
    typ, T, ent, fac = parse_q(q['question'], n_seq)
    a = dict(qid=q['qid'], value=None, state='absent', at_seq=None, chain=[], basis=[], confidence='unknown')
    if not ent:
        return a, []
    evs = ledger.slot(doc, ent, fac)
    used = []
    if typ == '变更':
        prev = None
        for e in evs:
            if e['seq'] > T:
                break
            to = None if e['kind'] == 'retire' else e['value']
            a['chain'].append({'seq': e['seq'], 'from': prev, 'to': to})
            used.append(e)
            prev = to
        st = state_at(evs, T)
    elif typ == '缘由':
        hit = [e for e in evs if e['seq'] == T]
        if hit:
            a['value'] = hit[-1]['reason']
            used.append(hit[-1])
        st = state_at(evs, T)
        a['state'], a['at_seq'] = st['state'], T if hit else None
        a['basis'] = [{'file': e['cid'], 'line': int(e['cid'].rsplit('#', 1)[1]) if e['cid'].rsplit('#', 1)[1].isdigit() else 0,
                       'quote': e['quote']} for e in used[-1:]]
        return a, used
    else:
        st = state_at(evs, T)
        if st['ev']:
            used.append(st['ev'])
    if typ != '变更' or True:
        a['value'], a['state'], a['at_seq'] = st['value'], st['state'], st['at']
    a['confidence'] = 'certain' if used else 'unknown'
    a['basis'] = [{'file': e['cid'], 'line': int(e['cid'].rsplit('#', 1)[1]) if e['cid'].rsplit('#', 1)[1].isdigit() else 0,
                   'quote': e['quote']} for e in used[-3:]]
    return a, used


# ------------------------------------------------------------------ 通用判别记忆（用户 Memory）+ 解释器
def dm_build(material):
    """material 按序号写入 NLMemory（nl_interpret.interpret → discriminative_memory.Memory）。"""
    from discriminative_memory import Memory
    nm = NL.NLMemory(Memory())
    sid2cid = {}
    for m in sorted(material, key=lambda m: m['seq']):
        for i, sent in enumerate(x for x in SENT.split(m['text']) if x.strip()):
            sid = f"{m['cid']}/{i}"
            sid2cid[sid] = m
            try:
                nm.ingest(sid, sent.strip(), recorded_at=m['seq'])
            except Exception:
                pass
    return nm, sid2cid


def dm_state(nm, slot, T):
    r = nm.m.query(NL.Query((NL.Need('v', slot),), T), 10 ** 9)
    a = r['answers']['v']
    if a['status'] == 'known':
        return ('active', a['value']) if a['value'] is not None else ('retired', None)
    if a['status'] == 'conflict':
        return 'unresolved', (a['value'] or [None])[0]
    return 'absent', None


def dm_answer(nm, mats, doc, q, n_seq):
    typ, T, ent, fac = parse_q(q['question'], n_seq)
    a = dict(qid=q['qid'], value=None, state='absent', at_seq=None, chain=[], basis=[], confidence='unknown')
    facs = nm.known.get(ent, {}) if ent else {}
    best, sc = NL._best(fac, list(facs)) if facs else (None, 0)
    if best is None or sc < .5:
        return a, []
    slot = facs[best][0]
    seqs = sorted({m['seq'] for m in mats if m['seq'] <= T})
    trans, prev = [], ('absent', None)
    for t in seqs:
        st = dm_state(nm, slot, t)
        if st != prev:
            trans.append((t, prev, st))
            prev = st
    used = [next(m for m in mats if m['seq'] == t) for t, _, _ in trans]
    if typ == '变更':
        a['chain'] = [{'seq': t, 'from': p[1], 'to': n[1]} for t, p, n in trans]
    st = dm_state(nm, slot, T)
    a['state'], a['value'] = st
    a['at_seq'] = trans[-1][0] if trans else None
    if typ == '缘由':
        a['value'] = None                       # Memory 不存缘由
    a['confidence'] = 'certain' if trans else 'unknown'
    a['basis'] = [{'file': m['cid'], 'line': m['seq'], 'quote': m['text'][:200]} for m in used[-3:]]
    return a, used


# ------------------------------------------------------------------ retrieval
def bigr(s):
    s = re.sub(r'\s+', '', s)
    return [s[i:i + 2] for i in range(len(s) - 1)]


class BM25:
    def __init__(self, chunks):
        import math
        self.c = chunks
        self.tf = [collections.Counter(bigr(c['text'])) for c in chunks]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / max(1, len(self.len))
        df = collections.Counter(g for t in self.tf for g in t)
        N = len(chunks)
        self.idf = {g: math.log(1 + (N - n + .5) / (n + .5)) for g, n in df.items()}

    def top(self, q, k):
        qs = set(bigr(q))
        sc = []
        for i, t in enumerate(self.tf):
            s = 0.0
            for g in qs:
                f = t.get(g)
                if f:
                    s += self.idf[g] * f * 2.2 / (f + 1.2 * (.25 + .75 * self.len[i] / self.avg))
            sc.append((s, i))
        sc.sort(key=lambda x: -x[0])
        return [self.c[i] for s, i in sc[:k] if s > 0]


def cap_material(hits, cap):
    out, used = [], 0
    for h in hits:
        t = h['text']
        if used + len(t) > cap:
            t = t[:max(0, cap - used)]
        if not t.strip():
            continue
        out.append({'cid': h['cid'], 'text': t})
        used += len(t)
        if used >= cap:
            break
    return out


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bench')
    ap.add_argument('--arms', default='disc_frozen,disc_ext,bm25,rrf3,lingshu,versionblind,closed')
    ap.add_argument('--dsh', default=str(TAN.parent.parent / 'dsh-memory'))
    ap.add_argument('--out', default=str(HERE / 'results' / 'chain'))
    args = ap.parse_args()
    B = Path(args.bench) / 'chain'
    out = Path(args.out)
    data = out / 'data'
    data.mkdir(parents=True, exist_ok=True)
    for src in ('corpus/corpus.json', 'keys/keys.json', 'keys/synth_log.json'):
        shutil.copy(B / src, data / Path(src).name)
    sys.path.insert(0, str(B / 'tools'))
    import probe_judge as J
    import synth as S
    J.OUT, J.RUNS = data, out / 'runs'
    corpus = json.loads((data / 'corpus.json').read_text(encoding='utf-8'))
    keys = json.loads((data / 'keys.json').read_text(encoding='utf-8'))
    n_seq = {}
    for c in corpus:
        n_seq[c['doc']] = max(n_seq.get(c['doc'], 0), c['seq'])
    fp = J.keys_fp(keys)

    # 官方版本盲语料（照抄 probe_runner.versionblind_corpus）
    lg = json.loads((data / 'synth_log.json').read_text(encoding='utf-8'))
    vb = collections.defaultdict(list)
    for ch in lg['chains']:
        last = ch['events'][-1]
        unit = S.UNIT[ch['kind']]
        vb[ch['doc']].append(f"{ch['subject']} 的{ch['slot']}当前已撤销，不再保留取值。" if last['to'] is None else
                             f"{ch['subject']} 的{ch['slot']}当前为 {last['to']}（第 {last['seq']} {unit}生效）。")
    vb_corpus = [dict(cid=f'{d}#latest', doc=d, seq=0, text=''.join(v)) for d, v in vb.items()]

    def full_ledger(ex):
        L = Ledger(ex)
        for c in corpus:
            L.ingest(c['doc'], c['cid'], c['seq'], c['text'])
        return L.finalize()

    def mat_ledger(material):
        L = Ledger(ext_events)
        for m in material:
            seq = int(m['cid'].rsplit('#', 1)[1]) if m['cid'].rsplit('#', 1)[1].isdigit() else 0
            L.ingest(m['cid'].split('#')[0], m['cid'], seq, m['text'])
        return L.finalize()

    by_cid = {c['cid']: c for c in corpus}
    readings = []
    for arm in args.arms.split(','):
        d = out / 'runs' / f'chain_{arm}'
        shutil.rmtree(d, ignore_errors=True)
        (d / 'sut' / 'out').mkdir(parents=True)
        (d / 'retrieval').mkdir(parents=True)
        led = full_ledger(frozen_events if arm == 'disc_frozen' else ext_events) if arm.startswith('disc') else None
        bm = BM25(corpus) if arm == 'bm25' else BM25(vb_corpus) if arm == 'versionblind' else None
        rm = lm = None
        if arm == 'lingshu':                      # 官方 lingshu 臂＝dsh-memory md_cg（MdCG.add/search）
            import tempfile
            sys.path.insert(0, str(Path(args.dsh)))
            from md_cg.mdcg import MdCG
            lm = MdCG(tempfile.mkdtemp(prefix='mdcg_chain_'))
            nid = {}
            for c in corpus:
                i = lm.add(c['cid'].replace('#', '@'), f"# {c['cid']}\n{c['text']}")
                nid[i] = c['cid']
        if arm == 'lingshu_ng':                   # Liyang/lingshu_ng MemoryEngine.perceive/search（默认 M5 去重）
            sys.path.insert(0, str(TAN.parent / 'Liyang'))
            from lingshu_ng.engine import MemoryEngine
            ng = MemoryEngine(); nid = {}
            for c in corpus:
                nid[ng.perceive(c['text']).node_id] = c['cid']
            class _NG:
                def search(self, q, k):
                    return ([({'id': n.id}, sc) for n, sc in ng.search(q, limit=k)], None)
            lm = _NG()
        dm_cache = {}
        if arm in ('rrf3', 'rrf3_dm'):
            import rrf3 as R
            rm = R.RRF3Memory()
            owner = []
            for c in corpus:
                for i in rm.add_turn('doc', c['text']):
                    while len(owner) <= i:
                        owner.append(c['cid'])
        for q in keys:
            chq = q['type'] == '变更'
            if arm == 'closed':
                a, mat = dict(qid=q['qid'], value=None, state='absent', at_seq=None, chain=[], basis=[],
                              confidence='unknown'), []
            elif arm in ('rrf3_dm', 'dm_full'):
                if arm == 'dm_full':
                    mats = [c for c in corpus if c['cid'].split('#')[0] == q['doc']]
                else:
                    mats, seen = [], set()
                    for h in rm.retrieve(q['question'], budget=CHAIN_CAP if chq else CAP):
                        cid = owner[h.id]
                        if cid not in seen:
                            seen.add(cid); mats.append(by_cid[cid])
                key = (q['doc'],) if arm == 'dm_full' else None
                if key and key in dm_cache:
                    nm = dm_cache[key]
                else:
                    nm, _ = dm_build(mats)
                    if key: dm_cache[key] = nm
                a, used = dm_answer(nm, mats, q['doc'], q, n_seq[q['doc']])
                mat = [{'cid': m['cid'], 'text': m['text']} for m in sorted(used, key=lambda m: m['seq'])]
            elif led is not None:
                a, used = answer(led, q['doc'], q, n_seq[q['doc']])
                cids = sorted({e['cid'] for e in used}, key=lambda c: by_cid[c]['seq'])
                mat = [{'cid': c, 'text': by_cid[c]['text']} for c in cids]
            else:
                if lm is not None:
                    res, _ = lm.search(q['question'], k=CHAIN_K if chq else K)
                    hits = [by_cid[nid[r[0]['id']]] for r in res if r[0].get('id') in nid]
                elif rm is not None:
                    hits, seen = [], set()
                    for h in rm.retrieve(q['question'], budget=CHAIN_CAP if chq else CAP):
                        cid = owner[h.id]
                        if cid not in seen:
                            seen.add(cid)
                            hits.append(by_cid[cid])
                else:
                    hits = bm.top(q['question'], CHAIN_K if chq else K)
                mat = cap_material(hits, CHAIN_CAP if chq else CAP)
                a, _ = answer(mat_ledger(mat), q['doc'], q, n_seq[q['doc']])
            (d / 'sut' / 'out' / f"{q['qid']}.json").write_text(json.dumps(a, ensure_ascii=False), encoding='utf-8')
            (d / 'retrieval' / f"{q['qid']}.json").write_text(
                json.dumps({'qid': q['qid'], 'material': mat}, ensure_ascii=False), encoding='utf-8')
        (d / 'manifest.json').write_text(json.dumps(dict(arm=arm, keys_fp=fp, limit=0, llm_calls=0),
                                                   ensure_ascii=False), encoding='utf-8')
        _, doc_norms, decoys = J._corpus_index()
        row = {'arm': arm}
        for split, ks in (('all', keys), ('test', [k for k in keys if k['doc_id'] not in DEV]),
                          ('dev', [k for k in keys if k['doc_id'] in DEV])):
            row[split] = J.judge_arm(arm, ks, doc_norms, decoys)
        readings.append(row)
        t = row['test']
        print(f"{arm:13s} test 现值{t['present']:.3f} 历史{t['history']:.3f} 变更{t['chain']:.3f} "
              f"行召回{t['chain_row_recall']:.3f} 四态{t['four_state']:.3f} 缘由{t['reason']:.3f} "
              f"滞后{t['stale']:.3f} 超前{t['future']:.3f} 主体{t['subject_confusion']:.3f} 回源{t['verbatim']:.3f} n={t['n']}",
              flush=True)
    try:
        cal = J.calibration([r['all'] for r in readings], sut_arm='disc_ext' if any(r['arm'] == 'disc_ext' for r in readings) else None)
    except Exception as e:                       # noqa: BLE001
        cal = {'error': f'{type(e).__name__}: {e}'}
    res = dict(bench_commit='426a86a', prereg='chain_prereg.md', dev_docs=sorted(DEV),
               readings=readings, calibration=cal)
    (out / 'chain_readings.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in cal.items() if k in ('passed', 'criteria', 'gate_stage')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
