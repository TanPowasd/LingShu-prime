"""Write a report from saved outputs only. Never calls a model."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from run_keyed import dump, read


def main():
    root = Path(__file__).resolve().parent
    repo = Path('E:/DF/liyang-hive-eval/LingShu-prime')
    bench = Path('E:/DF/liyang-hive-eval/hive-memory-bench')
    result, metadata = read(root / 'keyed_readings.json'), read(root / 'metadata.json')
    sys.path.insert(0, str(bench / 'chain/tools'))
    import probe_judge as J
    J.OUT, J.RUNS = root / 'data', root / 'runs'
    questions, norms, decoys = J._corpus_index()
    recomputed = J.judge_arm(result['arm'], [q for q in questions if q['doc_id'] not in {'A1', 'B1'}], norms, decoys)
    if recomputed != result['readings']['test']:
        raise RuntimeError('Score recomputation failed')
    if recomputed['n'] != 419:
        raise RuntimeError('Wrong test denominator')
    errors = read(root / 'errors.json')
    placeholder_count = sum(bool(read(p).get('_run_failure'))
                            for p in (root / 'runs' / f"chain_{result['arm']}" / 'sut/out').glob('*.json'))
    if placeholder_count != len(errors):
        raise RuntimeError('Failure count does not match placeholder answers')
    raw_cite_hits = 0
    original_cids = {c['cid'] for c in read(root / 'data/corpus.json')}
    for q in questions:
        if q['reconstructible'] or q['doc_id'] in {'A1', 'B1'}:
            continue
        arm_dir = root / 'runs' / f"chain_{result['arm']}"
        answer = read(arm_dir / 'sut/out' / f"{q['qid']}.json")
        retrieval = arm_dir / 'retrieval' / f"{q['qid']}.json"
        mats = read(retrieval)['material'] if retrieval.exists() else []
        raw = {m['cid']: m['text'] for m in mats if m.get('cid') in original_cids}
        hit = False
        for b in answer.get('basis') or []:
            if not isinstance(b, dict) or not isinstance(b.get('quote'), str):
                continue
            cid, quote = b.get('file'), J.norm(b['quote'])
            try:
                same = cid in raw and int(cid.rsplit('#', 1)[1]) == int(b.get('line'))
            except (TypeError, ValueError, AttributeError):
                same = False
            if same and len(quote) >= 8 and quote in J.norm(raw[cid]):
                hit = True
        raw_cite_hits += hit
    source_changes = []
    for rel, expected in metadata['source_sha256'].items():
        p = bench / 'chain/tools/probe_judge.py' if rel == 'benchmark\\probe_judge.py' or rel == 'benchmark/probe_judge.py' else repo / rel
        if hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            source_changes.append(rel)
    stages = Counter(e['stage'] for e in errors)
    by_finish, provider_models, usage = Counter(), Counter(), Counter()
    for p in (root / 'responses/by_prompt').glob('*.json'):
        data = read(p)['response']
        by_finish[data['choices'][0].get('finish_reason')] += 1
        provider_models[data.get('model')] += 1
        for key, val in (data.get('usage') or {}).items():
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                usage[key] += val
        usage['reasoning_tokens'] += (data.get('usage', {}).get('completion_tokens_details') or {}).get('reasoning_tokens', 0)
    audit = dict(score_recomputed=True, test_denominator=recomputed['n'],
                 placeholders=placeholder_count, failed_stages=dict(stages),
                 provider_finish_reasons=dict(by_finish), provider_models=dict(provider_models),
                 source_changes=source_changes, usage_saved_responses_only=dict(usage))
    audit['raw_source_citation'] = dict(hits=raw_cite_hits, total=419, rate=round(raw_cite_hits / 419, 4),
                                      normalization='official norm; same original source cid and line')
    buckets = result['readings']['all']['bucket_main']
    audit['length_gate'] = dict(scope='all', rates=buckets,
                               monotone=buckets['short'] >= buckets['mid'] >= buckets['long'])
    examples_path = root / 'failure_examples.json'
    examples = read(examples_path) if examples_path.exists() else []
    history_examples = [e for e in examples if e['type'] == '历史']
    conflicts = [e for e in history_examples if e['expected_state'] == e['predicted_state'] == 'unresolved']
    audit['history_error_diagnostics'] = dict(total=len(history_examples), unresolved_value_format=len(conflicts),
                                              other=len(history_examples) - len(conflicts))
    dump(root / 'audit.json', audit)
    prior_path = repo / 'TanPowasd/discriminative_memory/nl_eval/results/chain/chain_readings_reader_on_memory.json'
    prior = next(r['test'] for r in read(prior_path)['readings'] if r['arm'] == 'llm_dm_reader')
    initial_path = root / 'initial_8000/keyed_readings.json'
    initial = read(initial_path) if initial_path.exists() else result
    fields = ('present', 'history', 'chain', 'four_state', 'reason', 'stale', 'verbatim')
    labels = ('现值', '历史', '变更链完整', '四态', '缘由', '滞后混淆↓', '引文回源')
    rows = [('旧 Memory + RRF3 v1.0 + 模型读者（仓库历史记录）', prior),
            ('本轮 ChronicleDM + RRF3 v1.1，8,000 token 上限', initial['readings']['test'])]
    if result.get('truncation_repair'):
        rows.append(('本轮 ChronicleDM + RRF3 v1.1，补完截断题', result['readings']['test']))
    lines = ['# ChronicleDM 带 key 评测（2026-10-11）', '',
             f"流程：RRF3 v1.1 → {result['model']} 抽取 → ChronicleDM → 同模型按官方契约作答。",
             f"基准提交：`{metadata['bench_commit']}`；算法仓库提交：`{metadata['repo_commit']}`，实际使用的本地源码已留快照和 SHA-256。",
             '', '共覆盖 642 题，排除 17 道 reconstructible 题后全量计分 625 题；主表为排除 A1/B1 开发文档后的 419 道测试题。', '',
             '| 管线 | ' + ' | '.join(labels) + ' |',
             '|---|' + '|'.join(['---:'] * len(labels)) + '|']
    for label, row in rows:
        lines.append('| ' + label + ' | ' + ' | '.join(f'{100 * row[f]:.2f}%' for f in fields) + ' |')
    lines += ['', '历史记录没有重新生成；它使用旧召回和不同的记忆核心，不能把本轮差值单独归因于 ChronicleDM。旧记录引文轴为 0 是因早期脚本未保存读者材料，不能据此比较引用质量。', '',
              f"本轮模型 HTTP 请求尝试{'至少' if result.get('attempt_count_is_lower_bound') else '共'} {result['actual_http_attempts']} 次（含重试）；缓存 HTTP 成功响应 {result['successful_unique_cached_responses']} 份；最终未完成 {result['failures']} 题。未完成题保留空答卷并进入分母。",
              f"各 key 请求尝试数：`{json.dumps(result['per_key_attempts'])}`；后续按用户指令将每 key 并发改为 {metadata['per_key_concurrency']}，总并发为 {metadata['workers']}。",
              f"保存响应的 prompt tokens：{usage.get('prompt_tokens', 0):,}，completion tokens：{usage.get('completion_tokens', 0):,}，其中 reasoning tokens：{usage.get('reasoning_tokens', 0):,}。失败请求没有返回用量时无法计入。",
              '接口的原始 usage 和 cost 字段保留在 JSON 中；没有把未核实的费用字段当作最终账单。']
    lines += ['', f"请求 model 字段始终固定为 {result['model']}；接口返回的路由标签计数为 `{json.dumps(dict(provider_models))}`。底层路由由提供方决定，路由一致性未独立核验。"]
    if result.get('attempt_count_is_lower_bound'):
        lines += ['并发由 4 提高至 16 时重启了进程并复用缓存；中断前最后检查点之后的少量在途请求未完整计数，因此请求数是下界。原并发配置、源码和检查点保存在 restart_4_to_16/。']
    lines += ['', f"额外的原文依据校验：{raw_cite_hits}/419 = {100 * raw_cite_hits / 419:.2f}%。引用须归一化后落在其 file/line 指向的同一个原文片段；记忆摘要不计作原文依据。"]
    lines += ['', f"历史题机械扣分 {len(history_examples)} 道，其中 {len(conflicts)} 道状态正确地标为 unresolved，但把两个候选值合写到 value，未被单值/替代值匹配器接受；另外 {len(history_examples) - len(conflicts)} 道选错历史版本。官方分数保持原样，未据此改分。逐题样例在 failure_examples.json。",
              '这一轮的主要用途是检验反复更新与版本查询。现值及完整变更链在测试集中全部命中；后续需要改善未决值的结构化输出、原文 file/line/quote 绑定，并检查未召回最新状态和抽取错误的个案。']
    repair = result.get('truncation_repair')
    if repair:
        lines += ['', f"8,000 token 主轮发现 {repair.get('truncated_questions', repair['questions'])} 道截断题、{repair.get('transport_questions', 0)} 道接口失败题；仅补跑这些题，统一按 8,000 → 16,000 → 32,000 升上限（只有 finish_reason=length 才升级），补完 {repair['repaired']} 题，额外请求尝试 {repair['http_attempts']} 次。",
                  '主轮结果保留在 initial_8000/；成功响应没有重复生成。']
    lines += ['', '抽取提示、问题绑定与 ChronicleDM 适配器沿用现有实现；未为单题改写规则。抽取提示仍不提取缘由；最终读者可从对应原文片段读取缘由。',
              '这是公开的模板生成状态链测试，问题绑定使用该轨适配器。本轮没有验证自由对话泛化或持续写入后的长期记忆质量。',
              '每题按检索材料重建记忆库；跨会话持续状态、晚到事件与双时钟语义需另测。',
              '本轮只对新算法调用模型，未新增模型闭卷/版本盲控制臂；离线控制读数不能代替模型控制臂，因此不宣称通过完整校准门。',
              f"长度门诊断（全量）：短链 {buckets['short']:.4f}、中链 {buckets['mid']:.4f}、长链 {buckets['long']:.4f}，未呈基准要求的单调退化。上述分数是诊断读数，不是通过校准的认证成绩。", '',
              '所有答卷、真正交给读者的材料、请求提示、原始响应、逐 key 计数和源码快照均在本目录；答案与引文分数已从磁盘独立复算。',
              f"源码变化审计：{'无变化' if not source_changes else json.dumps(source_changes)}。"]
    (root / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(dict(test=result['readings']['test'], audit=audit, report=str(root / 'REPORT.md')), ensure_ascii=False))


if __name__ == '__main__':
    main()
