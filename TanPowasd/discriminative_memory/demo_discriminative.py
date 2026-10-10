"""Executable examples of the generic Python API; no automatic text parsing."""
import json
from pathlib import Path
from discriminative_memory import Memory,Slot,Dependency,Need,Query,encoded

ROOT=Path(__file__).resolve().parent


def main():
    m=Memory()
    attribute=Slot.of('object_1','attribute_1','role_A',{'context':'C'})
    m.append('e1','{"attribute_1":"v1"}',assertions={attribute:'v1'},effective_at=1,recorded_at=1)
    m.append('e2','{"attribute_1":"v2"}',assertions={attribute:'v2'},effective_at=3,recorded_at=3)
    m.append('e3','{"attribute_1":"v1"}',assertions={attribute:'v1'},effective_at=6,recorded_at=6)
    m.append('proposal','{"proposed":"v3"}',assertions={attribute:'v3'},kind='plan',recorded_at=7)
    m.correct('revision','e2','{"corrected_attribute_1":"v4"}',replacements={attribute:'v4'},recorded_at=8)
    queries={'current':Query((Need('value',attribute),),9,9),
             'past_using_current_knowledge':Query((Need('value',attribute),),4,9),
             'past_using_then_known':Query((Need('value',attribute),),4,4),
             'history':Query((Need('value',attribute,'history'),),9,9),
             'plans':Query((Need('value',attribute,'plans'),),9,9),
             'missing_relation':Query((Need('value',Slot.of('object_1','unprovided_relation')),),9,9)}
    first={key:m.query(query,4000) for key,query in queries.items()}
    assert first['current']['answers']['value']['value']=='v1'
    assert first['past_using_current_knowledge']['answers']['value']['value']=='v4'
    assert first['past_using_then_known']['answers']['value']['value']=='v2'
    assert first['missing_relation']['status']=='unknown'
    m.close()
    m=Memory();guard=Slot.of('component_2','flag');derived=Slot.of('component_3','payload')
    m.append('guard','{"flag":true}',assertions={guard:True},effective_at=1,recorded_at=1)
    m.append('payload','{"payload":{"code":7,"options":["a","b"]}}',
        assertions={derived:{'code':7,'options':['a','b']}},effective_at=1,recorded_at=2,
        dependencies={derived:[Dependency.of(guard,True,episode='guard')]})
    q=Query((Need('result',derived),),3,20)
    before=m.query(q,2000);short=m.query(q,80)
    m.correct('guard_fix','guard','{"corrected_flag":false}',replacements={guard:False},recorded_at=10)
    after=m.query(q,2000)
    assert before['status']=='complete' and short['answers']['result']['value'] is None and after['status']=='defer'
    m.close()
    output={'structured_time_example':first,'dependent_evidence_example':{'before':before,'tiny_budget':short,'after_correction':after},
        'note':'All assertions/requirements are supplied through the generic API. This demo does not parse natural-language text.',
        'model_calls':0}
    (ROOT/'outputs').mkdir(exist_ok=True)
    (ROOT/'outputs/demo.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'time_answers':{key:result['answers']['value'] for key,result in first.items()},
                      'dependent_statuses':[before['status'],short['status'],after['status']]},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
