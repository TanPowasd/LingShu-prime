"""Generic structured discriminative memory; no language/domain-specific rules.

Assertions and dependencies are caller-confirmed inputs. Raw text remains
uninterpreted until such inputs are supplied. Evidence, not truth probability,
is selected by a budgeted coverage planner.
"""
from __future__ import annotations
from collections import Counter, defaultdict, OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
from types import MappingProxyType

if __package__:
    from .temporal_facts import TemporalFacts, UNSET
else:
    from temporal_facts import TemporalFacts, UNSET


def encoded(value):
    def check(obj):
        if isinstance(obj,dict):
            if any(not isinstance(k,str) for k in obj): raise ValueError('JSON object keys must be strings')
            for v in obj.values(): check(v)
        elif isinstance(obj,(list,tuple)):
            for v in obj: check(v)
        elif obj is not None and not isinstance(obj,(str,int,float,bool)):
            raise ValueError('Values must be JSON-compatible')
    check(value)
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def finite(value):
    value=float(value)
    if not math.isfinite(value): raise ValueError('An explicit finite clock is required')
    return value


@dataclass(frozen=True)
class Slot:
    entity: str
    facet: str
    role: str='primary'
    conditions_json: str='{}'

    def __post_init__(self):
        if any(not isinstance(s,str) or not s.strip() for s in (self.entity,self.facet,self.role)):
            raise ValueError('Entity, facet and role must be nonempty strings')
        conditions=json.loads(self.conditions_json)
        if not isinstance(conditions,dict):raise ValueError('Conditions must be a JSON object')
        object.__setattr__(self,'conditions_json',encoded(conditions))

    @classmethod
    def of(cls,entity,facet,role='primary',conditions=None):
        if conditions is not None and not isinstance(conditions,dict):raise ValueError('Conditions must be a JSON object')
        return cls(entity,facet,role,encoded({} if conditions is None else conditions))

    @property
    def key(self): return encoded([self.entity,self.facet,self.role,json.loads(self.conditions_json)])

    @classmethod
    def from_key(cls,key):
        entity,facet,role,conditions=json.loads(key)
        return cls.of(entity,facet,role,conditions)


@dataclass(frozen=True)
class Dependency:
    slot: Slot
    value_json: str
    episode: str|None=None

    def __post_init__(self):
        if not isinstance(self.slot,Slot):raise ValueError('Dependency needs an explicit Slot')
        object.__setattr__(self,'value_json',encoded(json.loads(self.value_json)))
        if self.episode is not None and (not isinstance(self.episode,str) or not self.episode):
            raise ValueError('Episode reference must be a source ID')

    @classmethod
    def of(cls,slot,value,episode=None): return cls(slot,encoded(value),episode)

    def data(self): return {'slot':self.slot.key,'value':json.loads(self.value_json),'episode':self.episode}


@dataclass(frozen=True)
class Need:
    name: str
    slot: Slot
    mode: str='state'
    weight: float=1.

    def __post_init__(self):
        if not self.name or self.mode not in ('state','history','plans') or not math.isfinite(self.weight) or self.weight<=0:
            raise ValueError('Invalid requirement')


@dataclass(frozen=True)
class Query:
    requirements: tuple[Need,...]
    at: float
    known_at: float=math.inf
    scope: str='default'
    text: str=''

    def __post_init__(self):
        object.__setattr__(self,'requirements',tuple(self.requirements))
        object.__setattr__(self,'at',finite(self.at))
        object.__setattr__(self,'known_at',float(self.known_at))
        if math.isnan(float(self.known_at)) or not self.scope: raise ValueError('Invalid query clocks/scope')
        if len({n.name for n in self.requirements})!=len(self.requirements): raise ValueError('Requirement names must be unique')


@dataclass(frozen=True)
class Source:
    id: str
    text: str
    scope: str
    recorded_at: float
    effective_at: float|None
    kind: str
    group: str
    annotations_json: str='{}'

    def render(self):
        data={'id':self.id,'scope':self.scope,'kind':self.kind,
              'effective_at':self.effective_at,'recorded_at':self.recorded_at}
        if self.annotations_json!='{}':data['annotations']=json.loads(self.annotations_json)
        header=encoded(data)
        return header+'\n'+self.text+'\n'

    @property
    def cost(self):return len(self.render())


@dataclass(frozen=True)
class Certificate:
    refs: frozenset[str]
    covers: frozenset[str]


@dataclass(frozen=True)
class Answer:
    name: str
    status: str
    payload_json: str


@dataclass(frozen=True)
class Problem:
    query: Query
    sources: object
    certificates: tuple[Certificate,...]
    answers: tuple[Answer,...]
    mandatory: frozenset[str]
    dependencies: tuple[tuple[str,int],...]
    unresolved: tuple[str,...]


class _DB:
    def __init__(self,path):
        self.conn=sqlite3.connect(path,isolation_level=None)
        self.conn.row_factory=sqlite3.Row; self.depth=0; self.counter=0

    def all(self,sql,args=()):return self.conn.execute(sql,args).fetchall()
    def scalar(self,sql,args=()):
        row=self.conn.execute(sql,args).fetchone()
        return row[0] if row else None

    @contextmanager
    def tx(self):
        self.counter+=1; name='dm_'+str(self.counter); outer=self.depth==0
        self.conn.execute('BEGIN IMMEDIATE' if outer else 'SAVEPOINT '+name); self.depth+=1
        try:
            yield self.conn
            self.conn.execute('COMMIT' if outer else 'RELEASE SAVEPOINT '+name)
        except BaseException:
            if outer:self.conn.execute('ROLLBACK')
            else:
                self.conn.execute('ROLLBACK TO SAVEPOINT '+name); self.conn.execute('RELEASE SAVEPOINT '+name)
            raise
        finally:self.depth-=1


class Memory:
    def __init__(self,path=':memory:',max_proofs=256,cache_size=256):
        if not isinstance(max_proofs,int) or max_proofs<=0:raise ValueError('Invalid proof expansion limit')
        if not isinstance(cache_size,int) or cache_size<0:raise ValueError('Invalid cache capacity')
        self.db=_DB(path); self.max_proofs=max_proofs; self.cache_size=cache_size;self._cache=OrderedDict(); self.cache_hits=0
        self.facts=TemporalFacts(self.db)
        self.db.conn.executescript('''
        CREATE TABLE IF NOT EXISTS dm_sources (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
          text TEXT NOT NULL, scope TEXT NOT NULL, recorded REAL NOT NULL, effective REAL,
          kind TEXT NOT NULL, searchable INTEGER NOT NULL, canonical_id TEXT NOT NULL,
          group_id TEXT NOT NULL, signature TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS dm_source_group ON dm_sources(scope,searchable,group_id);
        CREATE INDEX IF NOT EXISTS dm_source_scope ON dm_sources(scope,recorded);
        CREATE TABLE IF NOT EXISTS dm_claims (
          id TEXT PRIMARY KEY, source_id TEXT NOT NULL, scope TEXT NOT NULL, slot TEXT NOT NULL,
          kind TEXT NOT NULL, value_json TEXT NOT NULL, effective REAL, end_at REAL,
          root_id TEXT NOT NULL, deps_json TEXT NOT NULL, extra_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS dm_claim_slot ON dm_claims(scope,slot);
        CREATE TABLE IF NOT EXISTS dm_controls (
          source_id TEXT NOT NULL, root_id TEXT NOT NULL, scope TEXT NOT NULL, enabled INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS dm_epochs (name TEXT PRIMARY KEY, epoch INTEGER NOT NULL);
        ''')
        for table in ('dm_sources','dm_claims','dm_controls'):
            for action in ('UPDATE','DELETE'):
                self.db.conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable memory record'); END")

    def _epoch_name(self,scope,slot):return encoded([scope,slot])
    def _source_epoch_name(self,scope,sid):return encoded(['source',scope,sid])
    def _epoch(self,name):return self.db.scalar('SELECT epoch FROM dm_epochs WHERE name=?',(name,)) or 0
    def _touch(self,scope,slot):
        self.db.conn.execute('INSERT INTO dm_epochs(name,epoch) VALUES (?,1) ON CONFLICT(name) DO UPDATE SET epoch=epoch+1',
                             (self._epoch_name(scope,slot),))

    def _source_row(self,sid):
        rows=self.db.all('SELECT * FROM dm_sources WHERE id=?',(sid,))
        if not rows:raise ValueError('Unknown source: '+sid)
        return rows[0]

    def _source(self,sid,query):
        row=self._source_row(sid)
        if row['scope']!=query.scope or not row['searchable'] or row['recorded']>query.known_at:
            raise ValueError('Source is not authorized in this snapshot')
        return self._renderable_source(row)

    def _renderable_source(self,row):
        annotations={}
        if row['id']!=row['canonical_id']:annotations['same_event_as']=row['canonical_id']
        for claim in self.db.all('SELECT * FROM dm_claims WHERE source_id=? ORDER BY slot',(row['id'],)):
            data={}
            if claim['end_at'] is not None:data['valid_to']=claim['end_at']
            deps=json.loads(claim['deps_json']);extra=json.loads(claim['extra_json'])
            if deps:data['requires']=deps
            if extra:data['support_refs']=extra
            if claim['root_id']!=claim['id']:data['revises']=self._claim(claim['root_id'])['source_id']
            if data:annotations[claim['slot']]=data
        controls=[{'target':self._claim(r['root_id'])['source_id'],'enabled':bool(r['enabled'])}
                  for r in self.db.all('SELECT * FROM dm_controls WHERE source_id=?',(row['id'],))]
        if controls:annotations['controls']=controls
        return Source(row['id'],row['text'],row['scope'],row['recorded'],row['effective'],row['kind'],row['group_id'],encoded(annotations))

    def _insert_source(self,sid,text,scope,recorded,effective,kind,searchable,group,signature):
        if not isinstance(sid,str) or not sid or not isinstance(text,str) or not text.strip() or not scope:
            raise ValueError('Source identity, scope and original text are required')
        recorded=finite(recorded); effective=None if effective is None else finite(effective)
        last=self.db.scalar('SELECT MAX(recorded) FROM dm_sources')
        if last is not None and recorded<last:raise ValueError('Receipt clock must not go backwards')
        prior=self.db.all('SELECT * FROM dm_sources WHERE scope=? AND searchable=? AND group_id=? ORDER BY seq',
                          (scope,int(searchable),group))
        canonical=prior[0]['canonical_id'] if prior else sid
        if prior and prior[0]['signature']!=signature:raise ValueError('A provenance group cannot merge different events/interpretations')
        self.db.conn.execute('INSERT INTO dm_sources(id,text,scope,recorded,effective,kind,searchable,canonical_id,group_id,signature) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (sid,text,scope,recorded,effective,kind,int(searchable),canonical,group,signature))
        self.db.conn.execute('INSERT INTO dm_epochs(name,epoch) VALUES (?,1)',(self._source_epoch_name(scope,sid),))
        return canonical

    def append(self,sid,text,*,assertions=None,effective_at=None,recorded_at,kind='state',scope='default',
               searchable=True,provenance_group=None,valid_to=None,dependencies=None,support_refs=()):
        assertions=assertions or {}; dependencies=dependencies or {}
        if not isinstance(searchable,bool):raise ValueError('Visibility must be an explicit boolean')
        if kind not in ('state','plan','pending'):raise ValueError('Unknown assertion kind')
        if kind=='pending' and assertions:raise ValueError('Uninterpreted text cannot carry confirmed assertions')
        if kind!='pending' and not assertions:raise ValueError('Confirmed input needs assertions')
        if kind=='state' or effective_at is not None:effective_at=finite(effective_at)
        if valid_to is not None:
            valid_to=finite(valid_to)
            if effective_at is None or valid_to<=effective_at:raise ValueError('Invalid validity interval')
        entries=[]
        for slot,value in assertions.items():
            if not isinstance(slot,Slot):raise ValueError('Assertions require generic Slot keys')
            deps=tuple(dependencies.get(slot,()))
            if any(not isinstance(d,Dependency) for d in deps):raise ValueError('Dependencies must be explicit typed bindings')
            unique={encoded(d.data()) for d in deps}
            entries.append((slot.key,encoded(value),encoded([json.loads(d) for d in sorted(unique)])))
        if any(slot not in assertions for slot in dependencies):raise ValueError('Dependency assigned to an absent claim')
        signature=encoded([kind,effective_at,valid_to,sorted(entries),sorted(set(support_refs))])
        with self.db.tx():
            for ref in support_refs:
                row=self._source_row(ref)
                if row['scope']!=scope or bool(row['searchable'])!=bool(searchable):raise ValueError('Cross-scope/visibility support reference')
            canonical=self._insert_source(sid,text,scope,recorded_at,effective_at,kind,searchable,provenance_group or sid,signature)
            if canonical!=sid:return canonical
            for slot,value_json,deps_json in sorted(entries):
                fid=sid+'#'+hashlib.sha256(slot.encode()).hexdigest()[:16]
                if kind=='state':
                    value=None if value_json=='null' else value_json
                    self.facts.assert_state(fid,slot,value,effective_at=effective_at,recorded_at=recorded_at,
                        scope=scope,source=text,source_ref=sid,valid_to=valid_to)
                self.db.conn.execute('INSERT INTO dm_claims VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (fid,sid,scope,slot,kind,value_json,effective_at,valid_to,fid,deps_json,encoded(sorted(set(support_refs)))))
                self._touch(scope,slot)
        return sid

    def append_raw(self,sid,text,*,recorded_at,scope='default',searchable=True,provenance_group=None):
        return self.append(sid,text,recorded_at=recorded_at,kind='pending',scope=scope,
                           searchable=searchable,provenance_group=provenance_group)

    def _claims_for_source(self,sid):
        canonical=self._source_row(sid)['canonical_id']
        return self.db.all('SELECT * FROM dm_claims WHERE source_id=? ORDER BY slot',(canonical,))

    def correct(self,sid,target,text,*,replacements,recorded_at,effective_at=UNSET,valid_to=UNSET):
        targets={r['slot']:r for r in self._claims_for_source(target)}
        if not replacements or any(slot.key not in targets for slot in replacements):raise ValueError('Correction must bind existing claims explicitly')
        original=self._source_row(target); scope=original['scope']; searchable=bool(original['searchable'])
        entries=[]
        for slot,value in replacements.items():
            old=targets[slot.key]
            latest=self.db.all('SELECT c.id FROM dm_claims c JOIN dm_sources s ON s.id=c.source_id WHERE c.root_id=? ORDER BY s.seq DESC',(old['root_id'],))[0]['id']
            if latest!=old['id']:raise ValueError('Correct the latest revision explicitly')
            at=old['effective'] if effective_at is UNSET else None if effective_at is None else finite(effective_at)
            if old['kind']=='state' and at is None:raise ValueError('Actual facts require an effective clock')
            end=old['end_at'] if valid_to is UNSET else None if valid_to is None else finite(valid_to)
            if end is not None and (at is None or end<=at):raise ValueError('Invalid corrected interval')
            entries.append((old,encoded(value),at,end))
        effective=entries[0][2] if len({r[2] for r in entries})==1 else None
        signature=encoded(['correction',target,[(r['slot'],v,a,e) for r,v,a,e in entries]])
        with self.db.tx():
            self._insert_source(sid,text,scope,recorded_at,effective,'correction',searchable,sid,signature)
            for old,value_json,at,end in entries:
                fid=sid+'#'+hashlib.sha256(old['slot'].encode()).hexdigest()[:16]
                if old['kind']=='state':
                    self.facts.correct(fid,old['id'],recorded_at=recorded_at,source=text,source_ref=sid,
                        value=None if value_json=='null' else value_json,effective_at=at,valid_to=end)
                self.db.conn.execute('INSERT INTO dm_claims VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (fid,sid,scope,old['slot'],old['kind'],value_json,at,end,old['root_id'],old['deps_json'],old['extra_json']))
                self._touch(scope,old['slot'])
        return sid

    def set_enabled(self,sid,target,text,*,enabled,recorded_at):
        if not isinstance(enabled,bool):raise ValueError('Control must be an explicit boolean')
        rows=self._claims_for_source(target)
        if not rows:raise ValueError('Control must target confirmed claims')
        original=self._source_row(target); scope=original['scope']
        kind='restore' if enabled else 'retract'; signature=encoded([kind,target])
        with self.db.tx():
            self._insert_source(sid,text,scope,recorded_at,None,kind,bool(original['searchable']),sid,signature)
            for old in rows:
                root=old['root_id']
                self.db.conn.execute('INSERT INTO dm_controls VALUES (?,?,?,?)',(sid,root,scope,int(enabled)))
                if old['kind']=='state':
                    eid=sid+'#'+hashlib.sha256(old['slot'].encode()).hexdigest()[:16]
                    self.facts.set_enabled(eid,old['id'],enabled=enabled,recorded_at=recorded_at,source=text,source_ref=sid)
                self._touch(scope,old['slot'])

    def reclassify(self,sid,target,text,*,assertions,effective_at,recorded_at,kind='state',dependencies=None):
        """Explicit caller feedback replaces an interpretation across slots.

        It does not train or infer a language rule. The original raw record,
        disabling event and new interpretation are one atomic transaction.
        """
        original=self._source_row(target)
        with self.db.tx():
            self.set_enabled(sid+'/disable',target,text,enabled=False,recorded_at=recorded_at)
            self.append(sid,text,assertions=assertions,effective_at=effective_at,recorded_at=recorded_at,
                kind=kind,scope=original['scope'],searchable=bool(original['searchable']),
                dependencies=dependencies,support_refs=(original['canonical_id'],sid+'/disable'))

    def _state_views(self,slot,query,visited):
        visited.add(self._epoch_name(query.scope,slot))
        views=self.facts._views(slot,query.scope,query.known_at)
        out=[]
        for v in views:
            meta=self.db.all('SELECT c.*,s.searchable FROM dm_claims c JOIN dm_sources s ON s.id=c.source_id WHERE c.id=?',(v['tip']['id'],))
            if meta and meta[0]['searchable']:out.append(v)
        return out

    def _resolve(self,slot,query,at,visited):
        return self.facts._resolve(self._state_views(slot,query,visited),at)

    def _qualifiers(self,views,query,at):
        """Keep revisions/withdrawals that change this snapshot's conclusion.

        An excluded newer claim can make an older one current again. Its
        decisive withdrawal cannot disappear merely because its endpoint is
        absent from the winning state view.
        """
        def meaning(state):return (state['status'],state['value'],tuple(state['alternatives']))
        actual=meaning(self.facts._resolve(views,at));refs=set()
        for i,view in enumerate(views):
            decisive=False
            if view['controls']:
                altered=dict(view);altered['enabled']=not view['enabled']
                alternate=list(views);alternate[i]=altered
                decisive=meaning(self.facts._resolve(alternate,at))!=actual
            for version in view['versions'][:-1]:
                altered=dict(view);altered['tip']=version
                alternate=list(views);alternate[i]=altered
                decisive|=meaning(self.facts._resolve(alternate,at))!=actual
            if decisive:
                refs.update(r['source_ref'] for r in view['versions'])
                refs.update(r['source_ref'] for r in view['controls'])
        for ref in refs:self._source(ref,query)
        return frozenset(refs)

    def _claim(self,fid):
        rows=self.db.all('SELECT * FROM dm_claims WHERE id=?',(fid,))
        if not rows:raise ValueError('Unknown claim')
        return rows[0]

    def _root_proofs(self,fid,query,at,visited,stack):
        marker=(fid,at)
        if marker in stack:return []
        row=self._claim(fid); self._source(row['source_id'],query)
        refs={row['source_id'],*json.loads(row['extra_json'])}
        versions=self.db.all('''SELECT c.source_id FROM dm_claims c JOIN dm_sources s ON s.id=c.source_id
            WHERE c.root_id=? AND s.recorded<=? AND s.searchable=1 ORDER BY s.seq''',(row['root_id'],query.known_at))
        # A correction certificate keeps the chain that establishes its target.
        refs.update(r[0] for r in versions)
        controls=self.db.all('''SELECT x.source_id FROM dm_controls x JOIN dm_sources s ON s.id=x.source_id
            WHERE x.root_id=? AND x.scope=? AND s.recorded<=? AND s.searchable=1 ORDER BY s.seq''',
            (row['root_id'],query.scope,query.known_at))
        refs.update(r[0] for r in controls)
        if row['kind']=='state':
            refs.update(self._qualifiers(self._state_views(row['slot'],query,visited),query,at))
        for ref in refs:self._source(ref,query)
        choices=[frozenset(refs)]
        for dep in json.loads(row['deps_json']):
            resolved=self._resolve(dep['slot'],query,at,visited)
            actual=resolved['value'] if resolved['status']=='known' else None
            wanted=None if dep['value'] is None else encoded(dep['value'])
            if actual!=wanted or (resolved['status']!='known' and not (resolved['status']=='unknown' and resolved['tip_ids'] and dep['value'] is None)):
                return []
            supporting=[]
            for candidate in resolved['tip_ids']:
                other=self._claim(candidate)
                pinned=frozenset()
                if dep.get('episode') is not None:
                    visited.add(self._source_epoch_name(query.scope,dep['episode']))
                    try:self._source(dep['episode'],query)
                    except ValueError:continue
                    lineages={r['root_id'] for r in self._claims_for_source(dep['episode']) if r['slot']==dep['slot']}
                    if other['root_id'] not in lineages:continue
                    pinned=frozenset({dep['episode']})
                supporting.extend(p|pinned for p in self._root_proofs(candidate,query,at,visited,stack|{marker}))
            if not supporting:return []
            choices=self._minimal_sets(a|b for a in choices for b in supporting)
        return choices

    def _minimal_sets(self,sets):
        unique=sorted(set(sets),key=lambda s:(len(s),tuple(sorted(s))))
        if len(unique)>self.max_proofs:raise ValueError('Proof expansion limit reached; no certainty is returned')
        result=[]
        for refs in unique:
            if not any(old<=refs for old in result):result.append(refs)
        return result

    def _need(self,need,query,visited):
        slot=need.slot.key
        if need.mode=='plans':
            visited.add(self._epoch_name(query.scope,slot))
            rows=self.db.all('''SELECT c.* FROM dm_claims c JOIN dm_sources s ON s.id=c.source_id
                WHERE c.slot=? AND c.scope=? AND c.kind='plan' AND s.recorded<=? AND s.searchable=1 ORDER BY s.seq''',
                (slot,query.scope,query.known_at))
            tips={r['root_id']:r for r in rows}; proofs=[]; values=[]
            for root,row in tips.items():
                controls=self.db.all('''SELECT x.enabled FROM dm_controls x JOIN dm_sources s ON s.id=x.source_id
                    WHERE x.root_id=? AND s.recorded<=? ORDER BY s.seq''',(root,query.known_at))
                if controls and not controls[-1][0]:continue
                if row['end_at'] is not None and row['end_at']<=query.at:continue
                p=self._root_proofs(row['id'],query,query.at,visited,set())
                if p:proofs.append(p); values.append(json.loads(row['value_json']))
            merged=[frozenset()]
            for p in proofs:merged=self._minimal_sets(a|b for a in merged for b in p)
            return Answer(need.name,'planned' if values else 'unknown',encoded(values if values else None)), merged if values else []
        views=self._state_views(slot,query,visited)
        if need.mode=='history':
            boundaries=sorted({v['tip']['effective_at'] for v in views if v['enabled'] and v['base_kind']=='state' and v['tip']['effective_at']<=query.at} |
                {v['tip']['valid_to'] for v in views if v['enabled'] and v['base_kind']=='state' and v['tip']['valid_to'] is not None and v['tip']['valid_to']<=query.at})
            entries=[]; all_proofs=[frozenset()]
            for at in boundaries:
                state=self.facts._resolve(views,at)
                if state['valid_from']!=at:continue
                entry={'at':at,'status':state['status'],'value':json.loads(state['value']) if state['status']=='known' else None,
                       'alternatives':[None if value is None else json.loads(value) for value in state['alternatives']],
                       'episodes':[self._claim(fid)['root_id'] for fid in state['tip_ids']]}
                entries.append(entry)
                qualifier=self._qualifiers(views,query,at)
                all_proofs=[p|qualifier for p in all_proofs]
                for fid in state['tip_ids']:
                    proofs=self._root_proofs(fid,query,at,visited,set())
                    if not proofs:return Answer(need.name,'defer',encoded(None)),[]
                    all_proofs=self._minimal_sets(a|b for a in all_proofs for b in proofs)
            return Answer(need.name,'history' if entries else 'unknown',encoded(entries if entries else None)), all_proofs if entries else []
        state=self.facts._resolve(views,query.at)
        value=json.loads(state['value']) if state['status']=='known' else (
            [None if v is None else json.loads(v) for v in state['alternatives']] if state['status']=='conflict' else None)
        proofs=[]
        if state['status']=='conflict':
            per_value=defaultdict(list)
            for fid in state['tip_ids']:
                meta=self._claim(fid)
                per_value[meta['value_json']].extend(self._root_proofs(fid,query,query.at,visited,set()))
            proofs=[frozenset()]
            for alternatives in per_value.values():
                if not alternatives:proofs=[];break
                proofs=self._minimal_sets(a|b for a in proofs for b in alternatives)
        else:
            for fid in state['tip_ids']:proofs.extend(self._root_proofs(fid,query,query.at,visited,set()))
            proofs=self._minimal_sets(proofs)
        status=state['status']
        if state['tip_ids'] and not proofs:status='defer';value=None
        qualifier=self._qualifiers(views,query,query.at)
        if proofs:proofs=[p|qualifier for p in proofs]
        elif status=='unknown' and qualifier:
            # A withdrawal explicitly establishes loss of support; the
            # qualifier itself is evidence, unlike an ungrounded "unknown".
            proofs=[qualifier]
        return Answer(need.name,status,encoded(value)),proofs

    def prepare(self,query):
        cached=self._cache.get(query)
        if cached and all(self._epoch(name)==epoch for name,epoch in cached.dependencies):
            self._cache.move_to_end(query)
            self.cache_hits+=1;return cached
        with self.db.tx():
            visited=set(); merged=defaultdict(set); answers=[]; mandatory=set(); unresolved=[]
            for need in query.requirements:
                answer,proofs=self._need(need,query,visited); answers.append(answer)
                if answer.status=='conflict':mandatory.add(need.name)
                if not proofs:unresolved.append(need.name)
                for refs in proofs:merged[refs].add(need.name)
            certificates=tuple(Certificate(refs,frozenset(names)) for refs,names in sorted(merged.items(),key=lambda z:tuple(sorted(z[0]))))
            refs=set().union(*(c.refs for c in certificates)) if certificates else set()
            sources=MappingProxyType({ref:self._source(ref,query) for ref in sorted(refs)})
            problem=Problem(query,sources,certificates,tuple(answers),frozenset(mandatory),
                tuple((name,self._epoch(name)) for name in sorted(visited)),tuple(unresolved))
        if self.cache_size:
            self._cache[query]=problem;self._cache.move_to_end(query)
            while len(self._cache)>self.cache_size:self._cache.popitem(last=False)
        return problem

    def query(self,query,budget,*,strategy='discriminative',improve=True):
        return solve(self.prepare(query),budget,strategy=strategy,improve=improve)

    def statistics(self):
        return {'raw_sources':self.db.scalar('SELECT COUNT(*) FROM dm_sources'),
                'canonical_sources':self.db.scalar('SELECT COUNT(*) FROM dm_sources WHERE id=canonical_id'),
                'interpreted_claims':self.db.scalar('SELECT COUNT(*) FROM dm_claims'),
                'cache_entries':len(self._cache),'cache_hits':self.cache_hits}

    def search_raw(self,text,*,scope='default',known_at=math.inf,budget=4000,limit=60):
        if budget<0 or limit<=0:raise ValueError('Invalid raw search budget')
        rows=self.db.all('SELECT * FROM dm_sources WHERE scope=? AND recorded<=? AND searchable=1 AND id=canonical_id ORDER BY seq',(scope,known_at))
        sources=[self._renderable_source(r) for r in rows]
        scores=bm25_scores([s.text for s in sources],text)
        selected=[];used=0
        for i in sorted(range(len(sources)),key=lambda i:(-scores[i],i))[:limit]:
            if scores[i]<=0:continue
            if used+sources[i].cost<=budget:selected.append(sources[i]);used+=sources[i].cost
        return {'status':'evidence_only','hits':[{'id':s.id,'text':s.text,'rendered':s.render()} for s in selected],
                'context':''.join(s.render() for s in selected),'budget_used':used}

    def close(self):self.db.conn.close()


def coverage(problem,refs):
    return frozenset().union(*(c.covers for c in problem.certificates if c.refs<=refs))


def cost(problem,refs):return sum(problem.sources[r].cost for r in refs)


def utility(problem,refs):
    covered=coverage(problem,refs)
    return sum(n.weight for n in problem.query.requirements if n.name in covered)


def bm25_scores(texts,query):
    def grams(text):
        s=re.sub(r'[^\w]','',text,flags=re.UNICODE)
        return [s[i:i+2] for i in range(len(s)-1)]
    tfs=[Counter(grams(t)) for t in texts]; lengths=[sum(tf.values()) for tf in tfs]
    df=Counter(g for tf in tfs for g in tf); n=len(texts); avg=sum(lengths)/max(1,n) or 1
    out=[]
    for tf,length in zip(tfs,lengths):
        value=0.
        for g in set(grams(query)):
            f=tf.get(g,0)
            if f:value+=math.log(1+(n-df[g]+.5)/(df[g]+.5))*f*2.5/(f+1.5*(.25+.75*length/avg))
        out.append(value)
    return out


def mandatory_plan(problem,budget,max_nodes=20000):
    if not problem.mandatory:return frozenset(),False
    best=None;nodes=0;truncated=False
    def visit(refs):
        nonlocal best,nodes,truncated
        nodes+=1
        if nodes>max_nodes:truncated=True;return
        amount=cost(problem,refs)
        if amount>budget or (best is not None and amount>=cost(problem,best)):return
        missing=problem.mandatory-coverage(problem,refs)
        if not missing:best=refs;return
        name=min(missing)
        options=[c for c in problem.certificates if name in c.covers]
        for c in sorted(options,key=lambda c:(cost(problem,c.refs-refs),tuple(sorted(c.refs)))):visit(refs|c.refs)
    visit(frozenset())
    return best,truncated


def solve(problem,budget,*,strategy='discriminative',improve=True):
    if not isinstance(budget,int) or budget<0:raise ValueError('Budget must be a nonnegative integer')
    if strategy not in ('discriminative','sql','shortest','bm25','agm','rrf','exact'):raise ValueError('Unknown evidence planner')
    selected,truncated=mandatory_plan(problem,budget)
    if selected is None:
        return _deliver(problem,frozenset(),budget,'insufficient_budget',truncated)
    if strategy=='exact':
        ids=sorted(problem.sources)
        if len(ids)>18:raise ValueError('Exact diagnostic restricted to 18 sources')
        best=selected;best_key=(utility(problem,best),-cost(problem,best))
        for mask in range(1<<len(ids)):
            refs=frozenset(ids[j] for j in range(len(ids)) if mask & (1<<j))
            amount=cost(problem,refs)
            if amount>budget or not problem.mandatory<=coverage(problem,refs):continue
            key=(utility(problem,refs),-amount)
            if key>best_key:best,best_key=refs,key
        selected=best
    else:
        order=None
        if strategy in ('bm25','agm','rrf'):
            ids=sorted(problem.sources); texts=[problem.sources[i].text for i in ids]
            raw=bm25_scores(texts,problem.query.text); lexical=sorted(range(len(ids)),key=lambda i:(-raw[i],i))
            if strategy in ('agm','rrf'):
                # This reference ranker uses the repository static AGM; it
                # receives the identical sources/certificates/query frame.
                bench=Path(__file__).resolve().parent.parent/'agm/bench'
                sys.path.insert(0,str(bench))
                from hive_retrieval import AGM,BM25
                chunks=[{'i':i,'cid':problem.sources[sid].scope,'text':text} for i,(sid,text) in enumerate(zip(ids,texts))]
                graph_order=AGM(chunks,BM25(chunks)).rank(problem.query.text) if chunks else []
                if strategy=='agm':lexical=graph_order
                else:
                    recent=sorted(range(len(ids)),key=lambda i:(-problem.sources[ids[i]].recorded_at,i))
                    rrf=defaultdict(float)
                    for ranking in (recent,lexical,graph_order):
                        for rank,i in enumerate(ranking,1):rrf[i]+=1/(60+rank)
                    lexical=sorted(rrf,key=lambda i:(-rrf[i],i))
            ranks={ids[i]:r for r,i in enumerate(lexical)}
            order=sorted(problem.certificates,key=lambda c:(min(ranks[r] for r in c.refs),sum(ranks[r] for r in c.refs),tuple(sorted(c.refs))))
        elif strategy=='sql':
            # Straight exact-frame lookup: consume certificates in requested
            # field order, preferring latest received supporting records.
            priorities={n.name:i for i,n in enumerate(problem.query.requirements)}
            order=sorted(problem.certificates,key=lambda c:(min(priorities[n] for n in c.covers),
                -max(problem.sources[r].recorded_at for r in c.refs),tuple(sorted(c.refs))))
        if order is not None:
            for certificate in order:
                if utility(problem,selected|certificate.refs)<=utility(problem,selected):continue
                if cost(problem,selected|certificate.refs)<=budget:selected=selected|certificate.refs
        else:
            while True:
                candidates=[]
                current=utility(problem,selected)
                for c in problem.certificates:
                    refs=selected|c.refs;added=cost(problem,c.refs-selected);gain=utility(problem,refs)-current
                    if added>0 and gain>0 and cost(problem,refs)<=budget:
                        key=(gain/added,gain,-added) if strategy=='discriminative' else (-added,gain,0)
                        candidates.append((key,tuple(sorted(c.refs)),refs))
                if not candidates:break
                candidates.sort(key=lambda x:tuple(-v for v in x[0])+x[1])
                selected=candidates[0][2]
        if strategy=='discriminative' and improve:
            # Removing one completed bundle and inserting one alternative can
            # escape some expensive early choices. No optimum is promised.
            for _ in range(3):
                base_key=(utility(problem,selected),-cost(problem,selected));best=selected
                removable=[c.refs for c in problem.certificates if c.refs<=selected]
                for old in [frozenset(),*removable]:
                    remaining=selected-old
                    for c in problem.certificates:
                        refs=remaining|c.refs
                        if cost(problem,refs)>budget or not problem.mandatory<=coverage(problem,refs):continue
                        key=(utility(problem,refs),-cost(problem,refs))
                        if key>base_key:best=refs;base_key=key
                if best==selected:break
                selected=best
    # Remove sources that add cost without changing certified answers. Raw
    # provenance is retained in storage even when excluded from this context.
    covered=coverage(problem,selected)
    for ref in sorted(selected,key=lambda r:(-problem.sources[r].cost,r)):
        if coverage(problem,selected-{ref})==covered:selected=selected-{ref}
    return _deliver(problem,selected,budget,None,truncated)


def _deliver(problem,selected,budget,override,truncated):
    covered=coverage(problem,selected);answers={}
    for answer in problem.answers:
        if answer.name in covered:answers[answer.name]={'status':answer.status,'value':json.loads(answer.payload_json)}
        else:answers[answer.name]={'status':answer.status if answer.name in problem.unresolved else 'insufficient_evidence','value':None}
    complete=len(covered)==len(problem.query.requirements)
    statuses={a['status'] for a in answers.values()}
    if override:status=override
    elif not covered and all(n.name in problem.unresolved for n in problem.query.requirements):status='unknown' if 'defer' not in statuses else 'defer'
    elif not complete:status='partial' if covered else 'insufficient_budget'
    elif 'conflict' in statuses:status='conflict'
    elif 'unknown' in statuses:status='unknown'
    else:status='complete'
    ordered=sorted(selected,key=lambda r:(problem.sources[r].recorded_at,r))
    context=''.join(problem.sources[r].render() for r in ordered)
    assert len(context)==cost(problem,selected)<=budget
    return {'status':status,'answers':answers,'covered':sorted(covered),
        'missing':[n.name for n in problem.query.requirements if n.name not in covered],
        'weighted_coverage':utility(problem,selected)/sum(n.weight for n in problem.query.requirements) if problem.query.requirements else 1.,
        'selected':ordered,'context':context,'budget_used':len(context),'budget_limit':budget,
        'mandatory_search_truncated':truncated,'evidence':[{'id':r,'text':problem.sources[r].text} for r in ordered]}
