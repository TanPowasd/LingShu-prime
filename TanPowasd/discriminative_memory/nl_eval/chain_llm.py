"""hive-memory-bench chain/ v0.2 —— 带 key 的 LLM 读者臂（需用户逐次许可才可真跑）。

前置：先跑 chain_bench.py（零模型）生成各检索臂的 runs/chain_<arm>/retrieval/<qid>.json 材料。
本脚本复用这些材料（与零模型臂完全同一召回），只把「读者」换掉：

  llm_<arm>   官方读者：probe_runner.CHAIN_SYS + build_prompt 原文提示，LLM 直接作答 JSON
              （arm ∈ bm25, rrf3, lingshu_ng, versionblind；llm_closed 用官方闭卷提示）
  llm_dm      RRF3 召回 → LLM 代替 nl_interpret 抽取所问槽位的版本事件 → 写入用户
              discriminative_memory.Memory → 按 Memory.query 逐序号求状态作答（LLM 不作答）

判分：官方 probe_judge.judge_arm（机械、零 LLM）。

用法：
  python chain_llm.py <bench> --arms llm_rrf3,llm_bm25,... --dry        # 只数调用、打印样例提示，不发请求
  python chain_llm.py <bench> --arms ... [--limit N] [--workers 8]       # 真跑（消耗 key）
原始回复缓存在 results/chain/llm_raw/<arm>/<qid>.txt，可断点续跑。
"""
from __future__ import annotations

import argparse, ast, json, re, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import chain_bench as CB                          # noqa: E402
from discriminative_memory import Memory, Need, Query, Slot   # noqa: E402

API = 'https://api.cline.bot/api/v1/chat/completions'
MODEL = 'cline-pass/deepseek-v4.1-flash'
RES = HERE / 'results' / 'chain'


def load_official(bench):
    """从 probe_runner.py 源码里取 CHAIN_SYS 与闭卷提示原文（不 import：它依赖仓外 harness）。"""
    src = (Path(bench) / 'chain' / 'tools' / 'probe_runner.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    sysmsg = next(ast.literal_eval(n.value) for n in tree.body
                  if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'CHAIN_SYS')
    return sysmsg


def build_prompt(sysmsg, qid, question, material):
    blocks = [f'【片段{i} · {m.get("cid") or "未知"}】\n{m.get("text", "")}' for i, m in enumerate(material, 1)]
    user = ('## 检索到的材料\n\n' + ('\n\n'.join(blocks) if blocks else '（无材料）') +
            f'\n\n## 问题（{qid}）\n\n{question}\n\n请按契约输出 JSON（qid 填 {qid}）。')
    return [{'role': 'system', 'content': sysmsg}, {'role': 'user', 'content': user}]


def build_closed_prompt(qid, question):
    sys_ = ('你是被评测的记忆理解系统。本题**不提供任何材料**——请凭你自己的知识作答。\n'
            '只输出一个 JSON（不要任何其他内容）：{"qid":"...", "value":null, '
            '"state":"absent", "at_seq":null, "chain":[], "basis":[], '
            '"confidence":"unknown"}')
    user = (f'## 问题（{qid}）\n\n{question}\n\n'
            f'（注意：本题不提供任何材料。）\n请按契约输出 JSON（qid 填 {qid}）。')
    return [{'role': 'system', 'content': sys_}, {'role': 'user', 'content': user}]


EXTRACT_SYS = (
    '你是记忆系统的写入解释器，只做抽取、不作答。给你若干材料片段（片段头是 doc#序号）和一个目标槽位'
    '「主体 · 属性」。请从材料中找出**改变该槽位状态**的每一条事件，按 JSON 数组输出，每项：\n'
    '{"seq":<生效序号，整数；句中写明「第 n 次/章生效」则用 n，否则用片段头序号>,'
    ' "op":"set|retire|unresolve", "value":"<set 的取值；unresolve 时为并存的取值之一>",'
    ' "alt":"<unresolve 时另一个并存取值，否则 null>", "cid":"<片段头 doc#序号>"}\n'
    '规则：主体可能改过名，改名前后视为同一主体；只回忆旧值、不改变状态的句子不要输出；'
    '「裁定为 X」记为 set X；撤销记为 retire。只依据材料，不要编。只输出 JSON 数组。')


def build_extract_prompt(ent, fac, material):
    blocks = [f'【{m.get("cid")}】\n{m.get("text", "")}' for m in material]
    user = (f'## 目标槽位\n\n主体：{ent}\n属性：{fac}\n\n## 材料\n\n' +
            ('\n\n'.join(blocks) if blocks else '（无材料）') + '\n\n只输出 JSON 数组。')
    return [{'role': 'system', 'content': EXTRACT_SYS}, {'role': 'user', 'content': user}]


class LLM:
    def __init__(self, model):
        self.model, self.calls, self.lock = model, 0, threading.Lock()

    def chat(self, messages, max_tokens=8000, tries=4):
        body = json.dumps({'model': self.model, 'messages': messages,
                           'max_tokens': max_tokens, 'temperature': 0}).encode()
        err = None
        for k in range(tries):
            try:
                with self.lock:
                    self.calls += 1
                req = urllib.request.Request(API, data=body, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=300) as r:
                    d = json.loads(r.read())
                d = d.get('data', d)
                txt = d['choices'][0]['message']['content']
                if txt and txt.strip():
                    return txt
            except Exception as e:   # noqa: BLE001
                err = e
            time.sleep(3 * (k + 1))
        raise RuntimeError(f'chat failed: {err}')


def parse_answer(raw, qid):
    m = re.search(r'\{.*\}', raw or '', re.S)
    o = None
    if m:
        try:
            o = json.loads(m.group(0))
        except Exception:   # noqa: BLE001
            o = None
    o = o if isinstance(o, dict) else {}
    o['qid'] = qid
    for k, v in (('value', None), ('state', None), ('at_seq', None), ('confidence', 'unknown')):
        o.setdefault(k, v)
    for k in ('chain', 'basis'):
        if not isinstance(o.get(k), list):
            o[k] = []
    o['_json_ok'] = bool(m)
    return o


def parse_events(raw):
    m = re.search(r'\[.*\]', raw or '', re.S)
    try:
        ev = json.loads(m.group(0)) if m else []
    except Exception:   # noqa: BLE001
        ev = []
    out = []
    for e in ev if isinstance(ev, list) else []:
        try:
            out.append(dict(seq=int(e['seq']), op=str(e.get('op')), value=e.get('value'),
                            alt=e.get('alt'), cid=e.get('cid')))
        except Exception:   # noqa: BLE001
            continue
    return out


def dm_from_events(events, q, n_seq, by_cid):
    """把 LLM 抽到的事件写进用户的 Memory，再按 Memory.query 作答。"""
    typ, T, ent, fac = CB.parse_q(q['question'], n_seq)
    a = dict(qid=q['qid'], value=None, state='absent', at_seq=None, chain=[], basis=[], confidence='unknown')
    if not ent:
        return a
    m, slot = Memory(), Slot.of(ent, fac)
    seen_any = []
    for i, e in enumerate(sorted(events, key=lambda e: e['seq'])):
        t = float(e['seq'])
        try:
            if e['op'] == 'unresolve' and e['alt'] is not None:
                m.append(f's{i}a', 'x', assertions={slot: str(e['value'])}, effective_at=t, recorded_at=t)
                m.append(f's{i}b', 'x', assertions={slot: str(e['alt'])}, effective_at=t, recorded_at=t)
            elif e['op'] == 'retire':
                m.append(f's{i}', 'x', assertions={slot: None}, effective_at=t, recorded_at=t)
            elif e['value'] is not None:
                m.append(f's{i}', 'x', assertions={slot: str(e['value'])}, effective_at=t, recorded_at=t)
            else:
                continue
            seen_any.append(e)
        except Exception:   # noqa: BLE001
            continue

    def state(t):
        r = m.query(Query((Need('v', slot),), float(t)), 10 ** 9)['answers']['v']
        if r['status'] == 'known' and r['value'] is not None:
            return 'active', r['value']
        if r['status'] == 'conflict':
            return 'unresolved', (r['value'] or [None])[0]
        # Memory 对 null 断言回 unknown；之前有过事件 → 已撤销，否则不存在
        return ('retired', None) if any(e['seq'] <= t for e in seen_any) else ('absent', None)

    trans, prev = [], ('absent', None)
    for t in sorted({e['seq'] for e in seen_any if e['seq'] <= T}):
        st = state(t)
        if st != prev:
            trans.append((t, prev, st))
            prev = st
    if typ == '变更':
        a['chain'] = [{'seq': t, 'from': p[1], 'to': n[1]} for t, p, n in trans]
    a['state'], a['value'] = state(T)
    a['at_seq'] = trans[-1][0] if trans else None
    if typ == '缘由':
        a['value'] = None                          # Memory 不存缘由
    a['confidence'] = 'certain' if trans else 'unknown'
    ev_by_seq = {e['seq']: e for e in seen_any}
    for t, _, _ in trans[-3:]:
        cid = ev_by_seq[t].get('cid')
        if cid in by_cid:
            a['basis'].append({'file': cid, 'line': by_cid[cid]['seq'], 'quote': by_cid[cid]['text'][:200]})
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bench')
    ap.add_argument('--arms', default='llm_rrf3,llm_bm25,llm_lingshu_ng,llm_versionblind,llm_closed,llm_dm')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--model', default=MODEL)
    ap.add_argument('--dry', action='store_true', help='不发请求：只数调用并打印一条样例提示')
    args = ap.parse_args()
    sysmsg = load_official(args.bench)
    data = RES / 'data'
    corpus = json.loads((data / 'corpus.json').read_text(encoding='utf-8'))
    keys = json.loads((data / 'keys.json').read_text(encoding='utf-8'))
    if args.limit:
        keys = keys[:args.limit]
    by_cid = {c['cid']: c for c in corpus}
    n_seq = {}
    for c in corpus:
        n_seq[c['doc']] = max(n_seq.get(c['doc'], 0), c['seq'])
    sys.path.insert(0, str(Path(args.bench) / 'chain' / 'tools'))
    import probe_judge as J
    J.OUT, J.RUNS = data, RES / 'runs'
    llm = None if args.dry else LLM(args.model)
    total = 0
    readings = []
    for arm in args.arms.split(','):
        src = 'rrf3' if arm == 'llm_dm' else arm[4:]
        d = RES / 'runs' / f'chain_{arm}'
        raw_dir = RES / 'llm_raw' / arm
        (d / 'sut' / 'out').mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)

        def material(q):
            if src == 'closed':
                return []
            return json.loads((RES / 'runs' / f'chain_{src}' / 'retrieval' / f"{q['qid']}.json")
                              .read_text(encoding='utf-8'))['material']

        def prompt(q):
            if arm == 'llm_closed':
                return build_closed_prompt(q['qid'], q['question'])
            if arm == 'llm_dm':
                _, _, ent, fac = CB.parse_q(q['question'], n_seq[q['doc']])
                return build_extract_prompt(ent, fac, material(q))
            return build_prompt(sysmsg, q['qid'], q['question'], material(q))

        todo = [q for q in keys if not (raw_dir / f"{q['qid']}.txt").exists()]
        total += len(todo)
        if args.dry:
            print(f'{arm:16s} 待调用 {len(todo)} / {len(keys)}')
            if todo and arm in ('llm_rrf3', 'llm_dm'):
                p = prompt(todo[0])
                print('  样例 user 提示前 300 字：', p[-1]['content'][:300].replace('\n', ' '))
            continue

        def one(q):
            raw = llm.chat(prompt(q))
            (raw_dir / f"{q['qid']}.txt").write_text(raw, encoding='utf-8')

        with ThreadPoolExecutor(args.workers) as ex:
            for f in [ex.submit(one, q) for q in todo]:
                try:
                    f.result()
                except Exception as e:   # noqa: BLE001
                    print('  失败', type(e).__name__, str(e)[:120], flush=True)
        for q in keys:
            p = raw_dir / f"{q['qid']}.txt"
            raw = p.read_text(encoding='utf-8') if p.exists() else ''
            a = (dm_from_events(parse_events(raw), q, n_seq[q['doc']], by_cid) if arm == 'llm_dm'
                 else parse_answer(raw, q['qid']))
            (d / 'sut' / 'out' / f"{q['qid']}.json").write_text(json.dumps(a, ensure_ascii=False), encoding='utf-8')
        (d / 'manifest.json').write_text(json.dumps(dict(arm=arm, model=args.model, limit=args.limit,
                                                         llm_calls=llm.calls), ensure_ascii=False), encoding='utf-8')
        _, doc_norms, decoys = J._corpus_index()
        row = {'arm': arm}
        for split, ks in (('all', keys), ('test', [k for k in keys if k['doc_id'] not in CB.DEV])):
            row[split] = J.judge_arm(arm, ks, doc_norms, decoys)
        readings.append(row)
        t = row['test']
        print(f"{arm:16s} test 现值{t['present']:.3f} 历史{t['history']:.3f} 变更{t['chain']:.3f} "
              f"四态{t['four_state']:.3f} 缘由{t['reason']:.3f} 滞后{t['stale']:.3f} 回源{t['verbatim']:.3f} "
              f"n={t['n']} 调用累计{llm.calls}", flush=True)
    if args.dry:
        print('合计待调用', total)
        return
    try:
        cal = J.calibration([r['all'] for r in readings], sut_arm='llm_rrf3')
    except Exception as e:   # noqa: BLE001
        cal = {'error': f'{type(e).__name__}: {e}'}
    (RES / 'chain_readings_llm.json').write_text(json.dumps(dict(model=args.model, readings=readings,
                                                                 calibration=cal), ensure_ascii=False, indent=1),
                                                encoding='utf-8')
    print(json.dumps(cal, ensure_ascii=False)[:400])


if __name__ == '__main__':
    main()
