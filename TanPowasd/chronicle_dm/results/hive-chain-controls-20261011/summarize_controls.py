"""Recompute control scores and calibration from disk, without any network."""
from collections import Counter
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import socket

ROOT = Path(__file__).resolve().parent
NETWORK_ATTEMPTS = 0


def deny_network(*args, **kwargs):
    global NETWORK_ATTEMPTS
    NETWORK_ATTEMPTS += 1
    raise RuntimeError('Network forbidden for control report verification')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    socket.socket = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    output = read(ROOT / 'control_readings.json')
    metadata = read(ROOT / 'metadata.json')
    spec = importlib.util.spec_from_file_location('frozen_judge', ROOT / 'sources/benchmark/probe_judge.py')
    J = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(J)
    J.OUT, J.RUNS = ROOT / 'data', ROOT / 'runs'
    questions, norms, decoys = J._corpus_index()
    for rel, expected in metadata['source_sha256'].items():
        if hashlib.sha256((ROOT / 'sources' / rel).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Frozen source fingerprint mismatch')
    arms = ('llm_closed', 'llm_versionblind', read(ROOT / 'sut_readings.json')['arm'])
    for arm in arms:
        for split, qs in (('all', questions), ('test', [q for q in questions if q['doc_id'] not in {'A1','B1'}]),
                          ('dev', [q for q in questions if q['doc_id'] in {'A1','B1'}])):
            if J.judge_arm(arm, qs, norms, decoys) != output['readings'][arm][split]:
                raise RuntimeError('Control score recomputation mismatch')
        if output['readings'][arm]['all']['n'] != 625 or output['readings'][arm]['test']['n'] != 419:
            raise RuntimeError('Control scoring denominator mismatch')
        if read(ROOT / 'runs' / f'chain_{arm}' / 'manifest.json')['keys_fp'] != J.keys_fp(questions):
            raise RuntimeError('Control answer-key fingerprint mismatch')
    gate = J.calibration([output['readings'][a]['all'] for a in arms], sut_arm=arms[-1],
                         control_arms=('llm_versionblind','llm_closed'))
    if gate != output['calibration']:
        raise RuntimeError('Calibration recomputation mismatch')
    length_tolerance = inspect.signature(J._nonincreasing).parameters['tol'].default
    placeholders = sum(bool(read(p).get('_run_failure')) for arm in arms[:2]
                       for p in (ROOT / 'runs' / f'chain_{arm}' / 'sut/out').glob('*.json'))
    if placeholders != output['failures']:
        raise RuntimeError('Control missing-answer audit mismatch')
    if NETWORK_ATTEMPTS:
        raise RuntimeError('Offline verifier attempted network')
    audit = dict(verified=True, arms=len(arms), questions_per_arm=642, scored_test=419,
                 control_placeholders=placeholders, network_attempts=NETWORK_ATTEMPTS, model_calls=0,
                 criteria=gate['criteria'], passed=gate['passed'], length_gate_tolerance=length_tolerance)
    (ROOT / 'verification.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    names = {arms[0]:'闭卷（官方提示，无材料）', arms[1]:'版本盲（官方最新快照）', arms[2]:'ChronicleDM + RRF3 v1.1（既有答卷）'}
    fields = ('present','history','chain','four_state','stale','future','subject_confusion')
    lines = ['# ChronicleDM：闭卷与版本盲控制（2026-10-11）', '',
             '主算法：RRF3 v1.1 → LLM 抽取 → ChronicleDM → 官方模型读者。主臂复用已发布答卷，本轮新增两条官方控制臂。',
             f"请求模型固定为 `{output['model']}`；每 key 最多 4 个并发请求，共 4 个 key、总并发 16。",
             '基准 chain v0.2：642 题/臂，排除可重建题后全量 625 题；主表为排除 A1/B1 开发文档后的 419 题。', '',
             '| 臂 | 现值 | 历史 | 完整变更链 | 四态 | 滞后↓ | 超前↓ | 主体混淆↓ |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for arm in (arms[2],arms[1],arms[0]):
        row = output['readings'][arm]['test']
        lines.append('| '+names[arm]+' | '+' | '.join(f'{100*row[f]:.2f}%' for f in fields)+' |')
    lines += ['', '## 校准门（按全量 625 题，冻结的官方判分器）', '',
              '| 判据 | 结果 |', '|---|---|',
              *[f"| {name} | {'通过' if gate['criteria'][key] else '未通过'} |" for key,name in (
                  ('c1','版本盲指纹'),('c2','闭卷低分'),('c3','主算法链长单调退化'),('c4','答卷完整、同源、读数可复算'))],
              '', f"完整校准门：{'通过' if gate['passed'] else '未通过'}。", '', gate['details'], '',
              f"长度门更正：官方 `_nonincreasing` 允许相邻桶 {100*length_tolerance:g} 个百分点容差。短/中/长桶 0.9463/0.9412/0.9655 在此规则下通过；先前按零容差严格不增判断该门未过，是解释错误。本轮未修改官方判分器或主臂答卷。", '',
              '## 控制口径与边界', '',
              '版本盲语料按官方 versionblind_corpus 逐链只留最后事件的当前值/撤销快照，含主链和影子链；旧版本、修改前值和缘由均不提供。使用既有 BM25 控制适配器及官方读者提示。',
              '闭卷臂只提交问题及官方闭卷提示，没有原文、记忆摘要或抽取事件。官方提示允许凭自身知识作答，但包含 null/absent 的 JSON 示例，会引导弃答；低闭卷分不能单独排除全部预训练污染。',
              '这两条臂是基准规定的模型读者控制，不是对 ChronicleDM 内部两核心的严格结构消融；不能据此单独归因双核心收益。',
              '主臂使用其既有的截断恢复策略；控制臂同样从 8,000 token 开始，仅当 finish_reason=length 时升至 16,000/32,000，不按答案正误选择重试。',
              f"新增模型 HTTP 尝试 {output['model_http_attempts']} 次（含限流/接口重试），最终运行失败 {output['failures']} 题次；失败占位答卷保留在分母。",
              '每臂的答卷、真正交付材料、请求提示、原始响应与源码快照分别保存在本目录。未导入主臂生成缓存。',
              f"接口返回的路由标签计数：`{json.dumps(output['provider_routes'])}`；请求仍固定使用指定模型别名。",
              '这是已公开的模板生成状态链测试；自由对话泛化、持续写入和双时钟语义需另测。', '',
              '用户在本轮执行期间要求后续统一不设置客户端 token 上限。共用客户端及工作区约定已更新；本轮仍按启动时冻结的 8,000/16,000/32,000 恢复协议完成，保持与既有主臂的配置可对照。', '',
              '离线复核：`python -B summarize_controls.py`。不需要 key，禁止网络，复算三个臂的读数及四项校准判据。']
    if not (ROOT / 'README.md').exists():
        (ROOT / 'REPORT.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(dict(audit=audit, test={names[a]:output['readings'][a]['test'] for a in arms}, report=str(ROOT/('README.md' if (ROOT/'README.md').exists() else 'REPORT.md'))),ensure_ascii=False))


if __name__ == '__main__':
    main()
