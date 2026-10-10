"""Schema-independent evidence planning, revision, isolation and provenance."""
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest
from discriminative_memory import (Memory,Slot,Dependency,Need,Query,Certificate,Answer,Problem,Source,
                                   cost,coverage,solve,encoded)
from types import MappingProxyType


class MemoryBehavior(unittest.TestCase):
    def setUp(self):self.m=Memory();self.slot=Slot.of('subject-A','attribute-X')
    def tearDown(self):self.m.close()
    def add(self,sid,value,at,received=None,slot=None,**kw):
        self.m.append(sid,f'{sid}: {encoded(value)}',assertions={slot or self.slot:value},effective_at=at,
                      recorded_at=at if received is None else received,**kw)
    def ask(self,at,known_at=float('inf'),slot=None,mode='state',budget=10000,scope='default'):
        return self.m.query(Query((Need('n',slot or self.slot,mode),),at,known_at,scope),budget)

    def test_repeated_value_is_a_distinct_episode(self):
        self.add('a','v1',10);self.add('b','v2',20);self.add('c','v1',30)
        self.assertEqual(self.ask(35)['answers']['n']['value'],'v1')
        history=self.ask(35,mode='history')['answers']['n']['value']
        self.assertEqual([e['value'] for e in history],['v1','v2','v1'])
        self.assertNotEqual(history[0]['episodes'],history[2]['episodes'])

    def test_correction_changes_past_not_more_recent_state(self):
        self.add('a','v1',10);self.add('b','v2',20);self.add('c','v3',30)
        self.m.correct('fix','b','Revision: v4 at 20',replacements={self.slot:'v4'},recorded_at=40)
        self.assertEqual(self.ask(25,35)['answers']['n']['value'],'v2')
        self.assertEqual(self.ask(25,45)['answers']['n']['value'],'v4')
        self.assertEqual(self.ask(35,45)['answers']['n']['value'],'v3')
        self.assertEqual(set(self.ask(25,45)['selected']),{'b','fix'})

    def test_correction_can_move_effective_time(self):
        self.add('a','v1',10);self.add('b','v2',20)
        self.m.correct('fix','b','Revision at 22',replacements={self.slot:'v4'},recorded_at=30,effective_at=22)
        self.assertEqual(self.ask(21,35)['answers']['n']['value'],'v1')
        self.assertEqual(self.ask(23,35)['answers']['n']['value'],'v4')

    def test_late_old_record_does_not_replace_newer_effective_state(self):
        self.add('a','v1',10);self.add('c','v3',30);self.add('late','v2',20,40)
        self.assertEqual(self.ask(35,50)['answers']['n']['value'],'v3')
        self.assertEqual(self.ask(25,35)['answers']['n']['value'],'v1')
        self.assertEqual(self.ask(25,50)['answers']['n']['value'],'v2')

    def test_plans_never_become_actual_states(self):
        self.add('a','v1',10)
        self.m.append('p','Pending proposed value v2',assertions={self.slot:'v2'},kind='plan',recorded_at=20)
        self.assertEqual(self.ask(100)['answers']['n']['value'],'v1')
        result=self.ask(100,mode='plans')
        self.assertEqual(result['answers']['n'],{'status':'planned','value':['v2']})

    def test_plan_correction_retraction_and_restore(self):
        self.m.append('p','v1 proposal',assertions={self.slot:'v1'},kind='plan',recorded_at=10)
        self.m.correct('pc','p','v2 proposal correction',replacements={self.slot:'v2'},recorded_at=20)
        self.m.set_enabled('off','pc','Plan disabled',enabled=False,recorded_at=30)
        self.assertEqual(self.ask(100,35,mode='plans')['status'],'unknown')
        self.m.set_enabled('on','pc','Plan restored',enabled=True,recorded_at=40)
        self.assertEqual(self.ask(100,45,mode='plans')['answers']['n']['value'],['v2'])

    def test_conflict_requires_both_values_even_when_other_fields_are_cheap(self):
        self.add('a','v1',10);self.add('b','v2',10,20)
        query=Query((Need('n',self.slot),),30)
        problem=self.m.prepare(query);total=cost(problem,frozenset({'a','b'}))
        for strategy in ('discriminative','sql','shortest','bm25','agm','rrf','exact'):
            both=solve(problem,total,strategy=strategy)
            self.assertEqual(set(both['selected']),{'a','b'},strategy)
            self.assertEqual(both['status'],'conflict')
            partial=solve(problem,total-1,strategy=strategy)
            self.assertEqual(partial['selected'],[],strategy)
            self.assertEqual(partial['answers']['n']['value'],None)

    def test_expiry_gap_does_not_resurrect_previous_value(self):
        self.add('a','v1',10);self.add('b','v2',20,valid_to=25)
        self.assertEqual(self.ask(22)['answers']['n']['value'],'v2')
        self.assertEqual(self.ask(26)['answers']['n']['value'],None)
        self.assertEqual(self.ask(26)['status'],'unknown')

    def test_explicit_unknown_has_evidence(self):
        self.add('a','v1',10);self.add('lost',None,20)
        answer=self.ask(25)
        self.assertEqual(answer['status'],'unknown');self.assertEqual(answer['covered'],['n'])
        self.assertEqual(answer['selected'],['lost'])

    def test_scope_visibility_roles_and_conditions_are_distinct(self):
        self.add('public','ok',10)
        self.add('private','hidden',20,searchable=False)
        self.add('scope2','other',20,scope='other')
        role=Slot.of('subject-A','attribute-X','secondary')
        condition=Slot.of('subject-A','attribute-X',conditions={'region':'r'})
        self.add('role','role-value',20,slot=role);self.add('condition','condition-value',20,slot=condition)
        self.assertEqual(self.ask(30)['answers']['n']['value'],'ok')
        self.assertEqual(self.ask(30,scope='other')['answers']['n']['value'],'other')
        self.assertEqual(self.ask(30,slot=role)['answers']['n']['value'],'role-value')
        self.assertEqual(self.ask(30,slot=condition)['answers']['n']['value'],'condition-value')

    def test_future_and_hidden_sources_cannot_change_old_problem(self):
        self.add('a','v1',10)
        q=Query((Need('n',self.slot),),15,15)
        a=self.m.query(q,1000)
        self.add('future','v2',40);self.add('hidden','v3',40,searchable=False)
        b=self.m.query(q,1000)
        self.assertEqual(a,b)

    def test_duplicate_event_group_changes_neither_certificates_nor_results(self):
        self.add('a','v1',10,provenance_group='observation-1')
        query=Query((Need('n',self.slot),),20)
        before=self.m.query(query,1000)
        for i in range(30):
            self.m.append('copy'+str(i),'Copied observation v1',assertions={self.slot:'v1'},effective_at=10,
                          recorded_at=20,provenance_group='observation-1')
        self.assertEqual(self.m.query(query,1000),before)
        self.assertEqual(self.m.statistics()['interpreted_claims'],1)
        self.assertEqual(self.m.statistics()['raw_sources'],31)

    def test_same_text_is_not_automatic_event_equivalence(self):
        for i,t in enumerate((10,20,30)):
            self.m.append(str(i),'Identical original text',assertions={self.slot:'v'},effective_at=t,recorded_at=t)
        self.assertEqual(len(self.ask(40,mode='history')['answers']['n']['value']),3)

    def test_group_collision_is_rejected_atomically(self):
        self.add('a','v1',10,provenance_group='g')
        before=self.m.statistics()
        with self.assertRaises(ValueError):self.add('bad','v2',20,provenance_group='g')
        self.assertEqual(self.m.statistics(),before)

    def test_incomplete_dependency_packet_does_not_expose_value(self):
        parent=Slot.of('node-A','flag')
        self.add('a',True,10,slot=parent)
        self.m.append('b','A explicitly supports payload P',assertions={self.slot:'P'},effective_at=10,recorded_at=20,
                      dependencies={self.slot:[Dependency.of(parent,True)]})
        problem=self.m.prepare(Query((Need('n',self.slot),),30))
        amount=cost(problem,frozenset({'a','b'}))
        full=solve(problem,amount)
        self.assertEqual(full['answers']['n']['value'],'P');self.assertEqual(set(full['selected']),{'a','b'})
        small=solve(problem,amount-1)
        self.assertEqual(small['answers']['n']['value'],None)
        self.assertEqual(small['selected'],[])

    def test_episode_pinned_dependency_does_not_attach_to_later_same_value(self):
        parent=Slot.of('node-A','flag')
        self.add('a',True,10,slot=parent)
        self.m.append('reason','Reason for a',assertions={self.slot:'r'},effective_at=10,recorded_at=20,
                      dependencies={self.slot:[Dependency.of(parent,True,episode='a')]})
        self.assertEqual(self.ask(25)['answers']['n']['value'],'r')
        self.add('new',True,30,slot=parent)
        self.assertEqual(self.ask(35)['status'],'defer')

    def test_future_alias_cannot_supply_past_episode_identity(self):
        parent=Slot.of('parent','field')
        self.add('a',True,10,slot=parent,provenance_group='event-A')
        self.m.append('derived','Conditional interpretation',assertions={self.slot:'r'},effective_at=10,recorded_at=12,
                      dependencies={self.slot:[Dependency.of(parent,True,episode='future-copy')]})
        old=Query((Need('n',self.slot),),15,15)
        current=Query((Need('n',self.slot),),15)
        self.assertEqual(self.m.query(old,1000)['status'],'defer')
        self.assertEqual(self.m.query(current,1000)['status'],'defer')
        self.m.append('future-copy','Copied event A',assertions={parent:True},effective_at=10,recorded_at=20,
                      provenance_group='event-A')
        self.assertEqual(self.m.query(old,1000)['status'],'defer')
        latest=self.m.query(current,1000)
        self.assertEqual(latest['status'],'complete')
        self.assertIn('future-copy',latest['selected'])
        self.assertIn('same_event_as',latest['context'])

    def test_episode_can_reference_a_known_corrected_claim_lineage(self):
        parent=Slot.of('parent','field')
        self.add('a',False,10,slot=parent)
        self.m.correct('fix','a','True correction',replacements={parent:True},recorded_at=20)
        self.m.append('derived','Conditional interpretation',assertions={self.slot:'r'},effective_at=10,recorded_at=30,
                      dependencies={self.slot:[Dependency.of(parent,True,episode='fix')]})
        result=self.ask(15,35)
        self.assertEqual(result['answers']['n']['value'],'r')
        self.assertTrue({'a','fix','derived'}<=set(result['selected']))

    def test_private_episode_identity_is_not_usable_as_public_support(self):
        parent=Slot.of('parent','field')
        self.add('a',True,10,slot=parent)
        self.add('secret',True,10,slot=parent,searchable=False)
        self.m.append('derived','Conditional interpretation',assertions={self.slot:'r'},effective_at=10,recorded_at=12,
                      dependencies={self.slot:[Dependency.of(parent,True,episode='secret')]})
        self.assertEqual(self.ask(20)['status'],'defer')

    def test_correcting_dependency_invalidates_derived_certificate(self):
        parent=Slot.of('node-A','flag')
        self.add('a',True,10,slot=parent)
        self.m.append('b','Conditional payload',assertions={self.slot:'r'},effective_at=10,recorded_at=20,
                      dependencies={self.slot:[Dependency.of(parent,True)]})
        q=Query((Need('n',self.slot),),15)
        self.assertEqual(self.m.query(q,1000)['answers']['n']['value'],'r')
        self.m.correct('fix','a','Flag corrected to false',replacements={parent:False},recorded_at=30)
        self.assertEqual(self.m.query(q,1000)['status'],'defer')

    def test_missing_dependency_is_in_cache_invalidation_set(self):
        parent=Slot.of('node-B','flag')
        self.m.append('b','Conditional payload',assertions={self.slot:'r'},effective_at=10,recorded_at=10,
                      dependencies={self.slot:[Dependency.of(parent,True)]})
        q=Query((Need('n',self.slot),),30)
        self.assertEqual(self.m.query(q,1000)['status'],'defer')
        self.add('a',True,20,slot=parent)
        self.assertEqual(self.m.query(q,1000)['status'],'complete')

    def test_decisive_controls_in_dependencies_are_in_the_certificate(self):
        parent=Slot.of('P','x')
        self.add('old',1,10,slot=parent);self.add('new',2,20,slot=parent)
        self.m.set_enabled('off','new','Disable new',enabled=False,recorded_at=30)
        self.m.append('derived','Explicit conditional result',assertions={self.slot:'result'},effective_at=10,recorded_at=40,
                      dependencies={self.slot:[Dependency.of(parent,1)]})
        answer=self.ask(25,45)
        self.assertEqual(set(answer['selected']),{'old','new','off','derived'})
        self.assertIn('annotations',answer['context'])

    def test_cycles_cannot_prove_each_other(self):
        a=Slot.of('A','x');b=Slot.of('B','x')
        self.m.append('a','A needs B',assertions={a:1},effective_at=10,recorded_at=10,dependencies={a:[Dependency.of(b,1)]})
        self.m.append('b','B needs A',assertions={b:1},effective_at=10,recorded_at=10,dependencies={b:[Dependency.of(a,1)]})
        self.assertEqual(self.ask(20,slot=a)['status'],'defer')

    def test_typed_boolean_and_integer_bindings_are_not_equal(self):
        parent=Slot.of('parent','typed')
        self.add('a',1,10,slot=parent)
        self.m.append('b','Boolean requirement',assertions={self.slot:'r'},effective_at=10,recorded_at=20,
                      dependencies={self.slot:[Dependency.of(parent,True)]})
        self.assertEqual(self.ask(30)['status'],'defer')

    def test_generic_JSON_values_and_caller_mutation_are_safe(self):
        value={'nested':['a',2,False],'other':{'x':None}}
        self.add('a',value,10);value['nested'].append('later')
        result=self.ask(20)['answers']['n']['value']
        self.assertEqual(result,{'nested':['a',2,False],'other':{'x':None}})
        result['nested'].append('modified result')
        self.assertNotIn('modified result',self.ask(20)['answers']['n']['value']['nested'])

    def test_selecting_unrelated_sources_never_proves_missing_reason(self):
        self.add('a','event',10)
        missing=Slot.of('subject-A','unprovided_relation')
        result=self.ask(20,slot=missing)
        self.assertEqual(result['status'],'unknown');self.assertEqual(result['covered'],[])

    def test_uninterpreted_text_remains_evidence_only(self):
        self.m.append_raw('raw','Arbitrary alpha beta gamma statement.',recorded_at=10)
        self.assertEqual(self.ask(20)['status'],'unknown')
        raw=self.m.search_raw('alpha beta',budget=1000)
        self.assertEqual(raw['status'],'evidence_only');self.assertEqual(raw['hits'][0]['id'],'raw')
        self.assertEqual(raw['hits'][0]['text'],'Arbitrary alpha beta gamma statement.')

    def test_raw_search_respects_scope_visibility_known_clock_and_full_cost(self):
        self.m.append_raw('ok','alpha beta',recorded_at=10)
        self.m.append_raw('other','alpha beta',recorded_at=10,scope='other')
        self.m.append_raw('hidden','alpha beta',recorded_at=10,searchable=False)
        self.m.append_raw('future','alpha beta',recorded_at=40)
        raw=self.m.search_raw('alpha',known_at=20,budget=1000)
        self.assertEqual([r['id'] for r in raw['hits']],['ok'])
        self.assertEqual(raw['budget_used'],len(raw['context']))
        self.assertEqual(self.m.search_raw('alpha',budget=1)['hits'],[])

    def test_query_is_read_only_and_unrelated_write_keeps_cached_problem(self):
        self.add('a','v1',10);q=Query((Need('n',self.slot),),20)
        problem=self.m.prepare(q);before=self.m.db.conn.total_changes
        self.m.query(q,1000)
        self.assertEqual(before,self.m.db.conn.total_changes)
        self.add('other','v2',20,slot=Slot.of('another','x'))
        self.assertIs(self.m.prepare(q),problem)

    def test_retraction_restore_and_receipt_time(self):
        self.add('a','v1',10)
        self.m.set_enabled('off','a','Withdraw a',enabled=False,recorded_at=20)
        self.assertEqual(self.ask(15,15)['answers']['n']['value'],'v1')
        self.assertEqual(self.ask(15,25)['status'],'unknown')
        self.m.set_enabled('on','a','Restore a',enabled=True,recorded_at=30)
        restored=self.ask(15,35)
        self.assertEqual(restored['answers']['n']['value'],'v1')
        self.assertEqual(set(restored['selected']),{'a','off','on'})

    def test_stale_correction_and_invalid_write_have_no_partial_effect(self):
        self.add('a','v1',10)
        self.m.correct('fix','a','v2 corrected',replacements={self.slot:'v2'},recorded_at=20)
        count=self.m.statistics()['raw_sources']
        with self.assertRaises(ValueError):self.m.correct('stale','a','v3',replacements={self.slot:'v3'},recorded_at=30)
        with self.assertRaises(ValueError):self.add('nan',float('nan'),30)
        with self.assertRaises(ValueError):self.add('bad','x',30,29,valid_to=20)
        self.assertEqual(self.m.statistics()['raw_sources'],count)

    def test_withdrawing_newer_claim_keeps_the_decisive_control_in_packet(self):
        self.add('old','v1',10);self.add('new','v2',20)
        self.m.set_enabled('off','new','Withdraw newer claim',enabled=False,recorded_at=30)
        result=self.ask(25,35)
        self.assertEqual(result['answers']['n']['value'],'v1')
        self.assertEqual(set(result['selected']),{'old','new','off'})

    def test_moving_correction_requires_qualifier_for_previous_state(self):
        self.add('old','v1',10);self.add('new','v2',20)
        self.m.correct('fix','new','Effective time is 22',replacements={self.slot:'v2'},recorded_at=30,effective_at=22)
        result=self.ask(21,35)
        self.assertEqual(result['answers']['n']['value'],'v1')
        self.assertEqual(set(result['selected']),{'old','new','fix'})

    def test_generic_reclassification_preserves_old_known_view(self):
        self.add('base','v1',10);self.add('misbound','v2',20)
        other=Slot.of('subject-A','attribute-X','different-role')
        self.m.reclassify('feedback','misbound','The event belongs to the other role',
                          assertions={other:'v2'},effective_at=20,recorded_at=30)
        self.assertEqual(self.ask(25,25)['answers']['n']['value'],'v2')
        self.assertEqual(self.ask(25,35)['answers']['n']['value'],'v1')
        changed=self.ask(25,35,slot=other)
        self.assertEqual(changed['answers']['n']['value'],'v2')
        self.assertTrue({'misbound','feedback','feedback/disable'}<=set(changed['selected']))

    def test_failed_reclassification_rolls_back_disabling_the_old_claim(self):
        self.add('a','v1',10)
        before=self.m.statistics()['raw_sources']
        with self.assertRaises(ValueError):
            self.m.reclassify('feedback','a','Invalid new interpretation',assertions={Slot.of('A','new'):float('nan')},
                              effective_at=10,recorded_at=20)
        self.assertEqual(self.m.statistics()['raw_sources'],before)
        self.assertEqual(self.ask(25)['answers']['n']['value'],'v1')

    def test_cross_visibility_support_references_are_rejected(self):
        self.m.append_raw('private','secret',recorded_at=10,searchable=False)
        with self.assertRaises(ValueError):self.add('public','x',20,support_refs=['private'])
        self.assertEqual(self.m.statistics()['raw_sources'],1)

    def test_append_only_database_records(self):
        self.add('a','v1',10)
        for table in ('dm_sources','dm_claims','temporal_facts'):
            with self.assertRaises(sqlite3.IntegrityError):self.m.db.conn.execute('DELETE FROM '+table)
        self.assertEqual(self.ask(20)['answers']['n']['value'],'v1')

    def test_reopen_database_preserves_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'memory.sqlite')
            a=Memory(path)
            a.append('a','value A',assertions={self.slot:'A'},effective_at=10,recorded_at=10)
            a.correct('fix','a','value B',replacements={self.slot:'B'},recorded_at=20);a.close()
            b=Memory(path)
            try:
                q=Query((Need('n',self.slot),),15,15)
                self.assertEqual(b.query(q,1000)['answers']['n']['value'],'A')
                self.assertEqual(b.query(Query((Need('n',self.slot),),15,25),1000)['answers']['n']['value'],'B')
            finally:b.close()

    def test_cache_is_bounded_and_eviction_does_not_lose_memory(self):
        self.m.close();self.m=Memory(cache_size=2)
        self.add('a','v1',10)
        for t in (11,12,13):self.ask(t)
        self.assertEqual(self.m.statistics()['cache_entries'],2)
        self.assertEqual(self.ask(11)['answers']['n']['value'],'v1')

    def test_schema_and_control_types_are_validated(self):
        with self.assertRaises(ValueError):Slot('e','f',conditions_json='[]')
        with self.assertRaises(ValueError):self.add('bad','v',10,searchable='false')
        self.add('a','v1',10)
        with self.assertRaises(ValueError):self.m.set_enabled('bad','a','invalid control',enabled='false',recorded_at=20)
        self.assertEqual(self.m.statistics()['raw_sources'],1)

    def test_numeric_clock_normalization_does_not_change_answers(self):
        self.add('a','v1',10)
        q=Query((Need('n',self.slot),),'15','20')
        self.assertEqual(self.m.query(q,1000),self.ask(15,20,budget=1000))

    def test_random_updates_match_independent_time_oracle(self):
        rng=random.Random(314159);events=[]
        for i in range(100):
            at=rng.randrange(300);received=500+i;value={'code':rng.randrange(15),'active':bool(rng.randrange(2))}
            self.add('e'+str(i),value,at,received);events.append((at,received,encoded(value)))
        for _ in range(100):
            at=rng.randrange(320);known=rng.randrange(480,620)
            visible=[e for e in events if e[0]<=at and e[1]<=known]
            expected=sorted({e[2] for e in visible if e[0]==max(v[0] for v in visible)}) if visible else []
            answer=self.ask(at,known)['answers']['n']
            self.assertEqual(answer['status'],'unknown' if not expected else 'known' if len(expected)==1 else 'conflict')
            if len(expected)==1:self.assertEqual(encoded(answer['value']),expected[0])
            elif len(expected)>1:self.assertEqual({encoded(v) for v in answer['value']},set(expected))


class PlannerBehavior(unittest.TestCase):
    def problem(self):
        slots=[Slot.of('opaque','f'+str(i)) for i in range(3)]
        query=Query(tuple(Need(str(i),s) for i,s in enumerate(slots)),10)
        sources={k:Source(k,text,'default',i,1,'state',k) for i,(k,text) in enumerate(
            [('a','a'*180),('b','b'*20),('c','c'*20),('shared','all three '+'.'*60)])}
        certs=(Certificate(frozenset({'a'}),frozenset({'0'})),Certificate(frozenset({'b'}),frozenset({'1'})),
               Certificate(frozenset({'c'}),frozenset({'2'})),Certificate(frozenset({'shared'}),frozenset({'0','1','2'})))
        return Problem(query,MappingProxyType(sources),certs,tuple(Answer(str(i),'known',encoded(i)) for i in range(3)),frozenset(),(),())

    def test_shared_source_counts_once_and_completes_multiple_requirements(self):
        p=self.problem();budget=p.sources['shared'].cost
        result=solve(p,budget)
        self.assertEqual(result['selected'],['shared']);self.assertEqual(result['covered'],['0','1','2'])
        self.assertEqual(result['budget_used'],budget)

    def test_certificate_and_detector_replication_changes_nothing(self):
        p=self.problem()
        duplicate=Problem(p.query,p.sources,p.certificates*4,p.answers,p.mandatory,p.dependencies,p.unresolved)
        self.assertEqual(solve(p,500),solve(duplicate,500))

    def test_local_swaps_can_remove_an_expensive_early_choice(self):
        p=self.problem()
        improved=solve(p,1000);plain=solve(p,1000,improve=False)
        self.assertGreaterEqual(improved['weighted_coverage'],plain['weighted_coverage'])
        self.assertLessEqual(improved['budget_used'],plain['budget_used'])

    def test_exact_oracle_bounds_heuristic_and_budget(self):
        rng=random.Random(2718)
        for _ in range(30):
            p=self.problem();budget=rng.randrange(0,600)
            candidate=solve(p,budget);exact=solve(p,budget,strategy='exact')
            self.assertLessEqual(candidate['weighted_coverage'],exact['weighted_coverage'])
            self.assertLessEqual(candidate['budget_used'],budget)

    def test_unknown_without_evidence_has_no_free_coverage(self):
        p=self.problem()
        p=Problem(p.query,MappingProxyType({}),(),tuple(Answer(str(i),'unknown','null') for i in range(3)),frozenset(),(),('0','1','2'))
        result=solve(p,100)
        self.assertEqual(result['weighted_coverage'],0);self.assertEqual(result['status'],'unknown')

    def test_budget_cost_includes_source_metadata(self):
        p=self.problem();budget=len(p.sources['shared'].text)
        result=solve(p,budget)
        self.assertEqual(result['selected'],[])
        self.assertEqual(result['answers']['0']['value'],None)


if __name__=='__main__':unittest.main(verbosity=2)
