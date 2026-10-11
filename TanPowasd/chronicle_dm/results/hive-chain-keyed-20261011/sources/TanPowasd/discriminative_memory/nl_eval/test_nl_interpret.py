"""Behaviour tests for the zero-model NL interpreter.
Run from discriminative_memory/:  python -B -X utf8 nl_eval/test_nl_interpret.py
Kept outside the package test discovery so the published 48-test verification stays unchanged."""
import socket, sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nl_interpret import NLMemory, interpret, bind_question, parse_value




def ops(text, topic=None):
    c, _, _ = interpret(text, recorded_at=1, topic=topic)
    return [(x.op, x.entity, x.facet, x.value) for x in c]


def test_copula_zh_en():
    assert ops('甲板A的温度是20。') == [('state', '甲板A', '温度', 20)]
    assert ops('The mode of unit-2 is eco.') == [('state', 'unit-2', 'mode', 'eco')]
    assert ops("unit-2's mode is now turbo and loud.") == [('state', 'unit-2', 'mode', 'turbo')]


def test_markers():
    assert ops('我们打算把甲板A的温度改成25。')[0][0] == 'plan'
    assert ops('甲板A的温度可能是30。')[0][0] == 'uncertain'
    assert ops('甲板A的温度不是30。')[0][0] == 'negate'
    assert ops('更正：甲板A的温度应该是21。') == [('correct', '甲板A', '温度', 21)]
    assert ops('撤回刚才那条。')[0][0] == 'retract'
    assert ops('谢谢，聊点别的吧。') == [] and ops('Sounds good to me.') == []


def test_pronoun_and_date_value():
    c, topic, _ = interpret('项目K的负责人是周。它的截止日期是2027-01-02。', recorded_at=1)
    assert [(x.entity, x.facet, x.value, x.time_source) for x in c] == [
        ('项目K', '负责人', '周', 'recorded'), ('项目K', '截止日期', '2027-01-02', 'recorded')]
    assert topic == '项目K'


def test_explicit_clock_and_conditions():
    c, _, _ = interpret('2026年3月1日，表B在夜间模式下的亮度是3。', recorded_at=9)
    x = c[0]
    assert x.time_source == 'explicit' and x.entity == '表B' and x.conditions == {'context': '在夜间模式下'}


def test_values():
    assert parse_value('1.5') == 1.5 and parse_value('true') is True and parse_value('[1, 2]') == [1, 2]
    assert parse_value('“蓝色”了') == '蓝色'


def test_memory_end_to_end():
    nm = NLMemory()
    nm.ingest('1', '泵P的转速是100。', recorded_at=1)
    nm.ingest('2', '泵P的转速改为120。', recorded_at=3)
    nm.ingest('3', '更正：泵P的转速应该是125。', recorded_at=4)
    assert nm.ask('泵P的转速是多少？', now=5)['answer']['value'] == 125
    assert nm.ask('泵P的转速在t=2时是多少？', now=5)['answer']['value'] == 100
    hist = nm.ask('泵P的转速变过哪些值？', now=5)['answer']['value']
    assert [h['value'] for h in hist] == [100, 125]


def test_retract_negate_uncertain_do_not_confirm():
    nm = NLMemory()
    nm.ingest('1', 'The owner of box-1 is Ann.', recorded_at=1)
    nm.ingest('2', 'Please disregard that.', recorded_at=2)
    assert nm.ask('Who is the owner of box-1?', now=3)['answer']['value'] is None
    nm.ingest('3', '箱子Z的颜色可能是红。', recorded_at=4)
    nm.ingest('4', '箱子Y的颜色是蓝。', recorded_at=5)
    nm.ingest('5', '箱子Y的颜色不是蓝。', recorded_at=6)
    assert nm.ask('箱子Y的颜色是什么？', now=7)['answer']['value'] is None
    r = nm.ask('箱子Z的颜色是什么？', now=7)
    assert r.get('answer', {}).get('value') is None


def test_plans_separate_from_state():
    nm = NLMemory()
    nm.ingest('1', '会议室M的容量是10。', recorded_at=1)
    nm.ingest('2', '我们计划把会议室M的容量改成20。', recorded_at=2)
    assert nm.ask('会议室M的容量是多少？', now=3)['answer']['value'] == 10
    assert nm.ask('会议室M的容量有什么计划？', now=3)['answer']['value'] == [20]


def test_unbound_question_falls_back_to_raw_text():
    nm = NLMemory()
    nm.ingest('1', '她后来说更喜欢英文。', recorded_at=1)
    r = nm.ask('她喜欢什么语言？', now=2)
    assert r['status'] == 'evidence_only'


def test_raw_text_is_always_kept_and_fuzzy_binding():
    nm = NLMemory()
    nm.ingest('1', 'The status of gateway-9 is ONLINE.', recorded_at=1)
    assert nm.m.statistics()['raw_sources'] == 1
    b = bind_question('what is the status of Gateway-9?', now=2, known=nm.known)
    assert b['status'] == 'bound'


def _deny(*a, **k):
    raise RuntimeError('offline')


class NLTests(unittest.TestCase):
    pass


for _n in ['test_copula_zh_en', 'test_markers', 'test_pronoun_and_date_value', 'test_explicit_clock_and_conditions', 'test_values', 'test_memory_end_to_end', 'test_retract_negate_uncertain_do_not_confirm', 'test_plans_separate_from_state', 'test_unbound_question_falls_back_to_raw_text', 'test_raw_text_is_always_kept_and_fuzzy_binding']:
    setattr(NLTests, _n, (lambda f: lambda self: f())(globals()[_n]))

if __name__ == '__main__':
    with patch.object(socket, 'create_connection', _deny), patch.object(socket.socket, 'connect', _deny):
        unittest.main(verbosity=1)
