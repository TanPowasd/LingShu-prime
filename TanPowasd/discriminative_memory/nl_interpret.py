"""Zero-model natural-language interpreter for the discriminative memory.

Turns Chinese/English utterances into *candidate* structured operations
(state, plan, correction, retraction, negation, uncertain) and binds
questions to slots.  Everything is generic surface syntax: copulas
("X的Y是Z", "the Y of X is Z", "X's Y is Z"), imperative setters
("把X的Y改成Z", "set the Y of X to Z"), discourse markers (plan, hedge,
negation, correction, retraction), pronoun carry-over and explicit clocks.
There are no entity, attribute or domain word lists.

What it does not do (measured, not hidden): free paraphrase without a
copula ("她更喜欢英文"), possessive pronouns inside the predicate
("move its standup"), implicit subjects without a topic, nested clauses.
Such text is still stored verbatim and reachable through ``search_raw``.

The interpreter never writes anything by itself; ``NLMemory`` applies its
operations through the public ``Memory`` API, so every derived claim keeps
the raw sentence as its source.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import re
from dataclasses import dataclass, field

from discriminative_memory import Memory, Need, Query, Slot

# ---------------------------------------------------------------- markers
# Discourse markers are grammar, not domain vocabulary.
PLAN = re.compile(r'(计划|打算|准备|将要|将会|拟|预计|下周|明天起|以后会|\bwill\b|\bplans? to\b|\bplanned to\b|\bgoing to\b|\bintends? to\b|\bscheduled to\b)', re.I)
HEDGE = re.compile(r'(可能|也许|大概|好像|似乎|不确定|估计|\bmaybe\b|\bperhaps\b|\bprobably\b|\bmight\b|\bpossibly\b|\bnot sure\b)', re.I)
CORRECT = re.compile(r'^\s*(更正|纠正|订正|修正|其实|实际上|说错了|我说错了|应该是|correction|actually|i meant|to correct)\s*[:：,，]?\s*', re.I)
CORRECT_ANY = re.compile(r'(更正|纠正|订正|说错了|应该是|\bcorrection\b|\bactually\b|\bi meant\b)', re.I)
RETRACT = re.compile(r'(撤回|作废|不算数|忽略(刚才|上一条|那条)|删掉(刚才|上一条|那条)|取消刚才|\bretract\b|\bdisregard\b|\bignore (that|the previous|my last)\b|\bscratch that\b|\bnever mind\b)', re.I)
PAST = re.compile(r'(以前|曾经|过去|原来|\bused to\b|\bpreviously\b|\bformerly\b)', re.I)
PRONOUN_ZH = re.compile(r'^(它|他|她|其|该对象|这个|那个|它们|他们|她们)(?=的)')
PRONOUN_EN = re.compile(r'^(its|their|his|her)\s+', re.I)
FILLER_ZH = re.compile(r'^(我们|我|你|大家|请|麻烦|现在|目前|当前|已经|另外|还有|然后|那么|所以|好的|嗯|啊)+')
FILLER_EN = re.compile(r'^(please|so|and|also|ok(ay)?|well|now|then|note that|fyi)[, ]+', re.I)

COPULA_ZH = r'(?:现在|目前|当前|已经|已|仍然|仍|还|则|也|一直)?(?:应该|应当|应)?(?:是|为|变成了?|变为|改成了?|改为|换成了?|调整为|调整成|设为|设置为|设成|定为|等于|升到|降到|达到)'
SET_VERB_ZH = r'(?:改成|改为|换成|调整为|调整成|设为|设置为|设成|定为|调到|升到|降到)'
COPULA_EN = r'(?:is now|are now|is still|has been set to|has been changed to|was changed to|is set to|changed to|became|becomes|is|are|was|were|equals)'
SPLIT = re.compile(r'(?<=[。！？!?；;\n])|(?<=\.)\s+')
VALUE_END = re.compile(r'[，,。；;！!？?\n]|\s(?:and|but|because|which|so)\s|(?<=\S)\.(?:\s|$)')
DATE_ISO = re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})')
DATE_ZH = re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})[日号]')
CLOCK = re.compile(r'(?:\bat\s+)?(?:在\s*)?(?<![A-Za-z0-9_])[tT]\s*=\s*(-?\d+(?:\.\d+)?)\s*(?:时)?|(?:在)?时刻\s*(-?\d+(?:\.\d+)?)\s*(?:时)?')
REL_DAY = {'前天': -2, '昨天': -1, '今天': 0, '明天': 1, '后天': 2,
           'yesterday': -1, 'today': 0, 'tomorrow': 1}
COND_ZH = re.compile(r'在(?P<c>[^，,。的在]{1,16}?)(?:模式|环境|条件|配置|情况|场景)?下')
COND_EN = re.compile(r'\b(?:in|under) (?P<c>[\w\- ]{1,24}?) (?:mode|environment|condition|profile|configuration)\b', re.I)


def _norm(s):
    return re.sub(r'\s+', ' ', s or '').strip(' \t"\'“”‘’「」『』`')


def parse_value(raw):
    """Generic literal normalisation: JSON, numbers, booleans, else text."""
    v = _norm(raw)
    v = re.sub(r'(了|啦|呢|吧|哦|呀)$', '', v).strip()
    v = _norm(v.rstrip('.。'))
    if not v:
        return None
    try:
        parsed = json.loads(v)
        if isinstance(parsed, (int, float, bool, list, dict)) and not (isinstance(parsed, float) and not math.isfinite(parsed)):
            return parsed
    except Exception:
        pass
    if re.fullmatch(r'-?\d+', v):
        return int(v)
    if re.fullmatch(r'-?\d+\.\d+', v):
        return float(v)
    low = v.lower()
    if low in ('true', 'yes', 'on', 'enabled'):
        return True
    if low in ('false', 'no', 'off', 'disabled'):
        return False
    return v


def _clean_entity(e):
    e = _norm(e)
    e = FILLER_ZH.sub('', e)
    e = FILLER_EN.sub('', e)
    e = re.sub(r'^(the|a|an)\s+', '', e, flags=re.I)
    e = re.sub(r'^(这个|那个|该|此)', '', e)
    return e.strip(' ，,')


def _clean_facet(f):
    f = _norm(f)
    f = re.sub(r'^(the|a|an)\s+', '', f, flags=re.I)
    return f.strip(' ，,')


def find_time(text, recorded_at, day=1.0, clock=None):
    """Explicit clock in the text, else None.  Dates map to ordinal days."""
    clock = clock or (lambda d: float(d.toordinal()))
    m = CLOCK.search(text)
    if m:
        return float(m.group(1) or m.group(2)), m.group(0)
    for rx in (DATE_ISO, DATE_ZH):
        m = rx.search(text)
        if m:
            try:
                return clock(_dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))), m.group(0)
            except ValueError:
                pass
    for word, k in REL_DAY.items():
        if re.search((r'\b%s\b' % word) if word.isascii() else word, text, re.I):
            return float(recorded_at) + k * day, word
    return None, None


@dataclass
class Candidate:
    op: str                     # state / plan / correct / retract / negate / uncertain
    entity: str | None
    facet: str | None
    value: object = None
    conditions: dict = field(default_factory=dict)
    effective_at: float | None = None
    time_source: str = 'none'   # explicit / recorded / none
    implicit_entity: bool = False
    span: str = ''

    def slot(self):
        return Slot.of(self.entity, self.facet, conditions=self.conditions or None)

    def data(self):
        return {'op': self.op, 'entity': self.entity, 'facet': self.facet, 'value': self.value,
                'conditions': self.conditions, 'effective_at': self.effective_at,
                'time_source': self.time_source, 'implicit_entity': self.implicit_entity, 'span': self.span}


def _conditions(text):
    conds = {}
    for rx in (COND_ZH, COND_EN):
        for m in rx.finditer(text):
            conds['context'] = _norm(m.group(0))
    stripped = COND_ZH.sub('', text)
    stripped = COND_EN.sub('', stripped)
    return conds, stripped


def _cut_value(v):
    m = VALUE_END.search(v)
    return v[:m.start()] if m else v


def _match_clause(clause, topic):
    """Return (entity, facet, raw_value, implicit) or None for one clause."""
    c = clause.strip()
    c = re.sub(r'^[，,、\s]+', '', c)
    # imperative setter (Chinese): 把/将 X的Y 改成 Z
    m = re.search(r'(?:把|将)(?P<e>[^，,。]{1,30}?)的(?P<f>[^，,。]{1,20}?)' + SET_VERB_ZH + r'(?P<v>.+)', c)
    if m:
        return m.group('e'), m.group('f'), m.group('v'), False
    # imperative setter (English)
    m = re.search(r'\b(?:set|change|update|move|switch)\s+(?:the\s+)?(?P<f>[\w\- ]{1,30}?) of (?:the\s+)?(?P<e>[\w\-\. ]{1,40}?) to (?P<v>.+)', c, re.I)
    if m:
        return m.group('e'), m.group('f'), m.group('v'), False
    m = re.search(r"\b(?:set|change|update|move|switch)\s+(?P<e>[\w\-\. ]{1,40}?)'s (?P<f>[\w\- ]{1,30}?) to (?P<v>.+)", c, re.I)
    if m:
        return m.group('e'), m.group('f'), m.group('v'), False
    # pronoun subject (Chinese 它的Y是Z / English its Y is Z)
    if topic:
        m = re.search(r'(?:^|[，,]\s*)(?:它|他|她|其|它们|他们|她们)的(?P<f>[^，,。]{1,20}?)' + COPULA_ZH + r'(?P<v>.+)', c)
        if m:
            return topic, m.group('f'), m.group('v'), True
        m = re.search(r'\b(?:its|their|his|her)\s+(?P<f>[\w\- ]{1,30}?)\s+' + COPULA_EN + r'\s+(?P<v>.+)', c, re.I)
        if m:
            return topic, m.group('f'), m.group('v'), True
    # Chinese copula: X的Y是Z
    m = re.search(r'(?P<e>[^，,。：:]{1,30}?)的(?P<f>[^，,。：:]{1,20}?)' + COPULA_ZH + r'(?P<v>.+)', c)
    if m and not PRONOUN_ZH.match(m.group('e')):
        return m.group('e'), m.group('f'), m.group('v'), False
    # English: the Y of X is Z
    m = re.search(r'\b(?:the\s+)?(?P<f>[\w\- ]{1,30}?) of (?:the\s+)?(?P<e>[\w\-\. ]{1,40}?)\s+' + COPULA_EN + r'\s+(?P<v>.+)', c, re.I)
    if m:
        return m.group('e'), m.group('f'), m.group('v'), False
    # English: X's Y is Z
    m = re.search(r"(?P<e>[\w\-\.]+(?: [\w\-\.]+){0,2})'s (?P<f>[\w\- ]{1,30}?)\s+" + COPULA_EN + r'\s+(?P<v>.+)', c, re.I)
    if m:
        return m.group('e'), m.group('f'), m.group('v'), False
    return None


def _structured(text):
    """JSON objects / key=value lines.  Keys that are canonical Slot keys
    (the library's own encoding) bind fully; other keys need an entity."""
    out = []
    dec = json.JSONDecoder()
    i = 0
    while True:
        j = text.find('{', i)
        if j < 0:
            break
        try:
            obj, end = dec.raw_decode(text, j)
        except ValueError:
            i = j + 1
            continue
        i = end
        stack = [obj]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                for k, v in o.items():
                    slot = _slot_key(k)
                    if slot:
                        out.append((slot, v))
                    else:
                        stack.append(v)
    for line in text.splitlines():
        m = re.match(r'^\s*(\[.*\])\s*=\s*(.+)$', line)
        if m and _slot_key(m.group(1)):
            try:
                out.append((_slot_key(m.group(1)), json.loads(m.group(2))))
            except ValueError:
                pass
    seen = {}
    for s, v in out:
        seen[s] = v
    return list(seen.items())


def _slot_key(k):
    try:
        e, f, r, c = json.loads(k)
        if all(isinstance(x, str) and x for x in (e, f, r)) and isinstance(c, dict):
            return Slot.of(e, f, r, c)
    except Exception:
        return None
    return None


def interpret(text, *, recorded_at, topic=None, day=1.0, clock=None, last_slots=()):
    """Interpret one utterance.  Returns (candidates, new_topic, notes)."""
    notes = []
    structured = _structured(text)
    if structured:
        cands = []
        for slot, v in structured:
            c = Candidate('state', slot.entity, slot.facet, v, json.loads(slot.conditions_json), None, 'none', False, '')
            c._slot = slot
            cands.append(c)
        notes.append('structured')
        return cands, topic, notes
    cands = []
    sentences = [s for s in SPLIT.split(text) if s and s.strip()]
    retract_all = bool(RETRACT.search(text))
    for sent in sentences:
        is_correction = bool(CORRECT.match(sent) or CORRECT_ANY.search(sent))
        body = CORRECT.sub('', sent)
        t, tspan = find_time(body, recorded_at, day, clock)
        if tspan:
            probe = _match_clause(re.sub(r'(可能|也许|大概|不是|并非)', '', body), topic)
            if probe and tspan in probe[2]:
                t, tspan = None, None      # the date is the value, not the event clock
            else:
                body = body.replace(tspan, ' ')
                body = re.sub(r'^[\s，,]+', '', body)
        conds, body = _conditions(body)
        plan = bool(PLAN.search(body))
        hedge = bool(HEDGE.search(body))
        past = bool(PAST.search(body))
        neg = False
        b2 = PLAN.sub(' ', body) if plan else body
        b2 = HEDGE.sub('', b2)
        b2 = re.sub(r'\s+', ' ', b2)
        if re.search(r'(不是|并非|不再是|不为|\bis not\b|\bisn\'t\b|\bis no longer\b|\bare not\b|\bwas not\b)', b2, re.I):
            neg = True
            b2 = re.sub(r'不再是|不是|并非|不为', '是', b2)
            b2 = re.sub(r"\bis no longer\b|\bis not\b|\bisn't\b", 'is', b2, flags=re.I)
            b2 = re.sub(r'\bare not\b', 'are', b2, flags=re.I)
            b2 = re.sub(r'\bwas not\b', 'was', b2, flags=re.I)
        hit = None
        for clause in re.split(r'(?<=[。！？!?；;])', b2):
            hit = _match_clause(clause, topic)
            if hit:
                break
        if not hit:
            continue
        e, f, v, implicit = hit
        e, f = _clean_entity(e), _clean_facet(f)
        v = parse_value(_cut_value(v))
        if not e or not f or v is None or len(f) > 24:
            notes.append('unbound:' + sent.strip()[:40])
            continue
        if neg:
            op = 'negate'
        elif hedge:
            op = 'uncertain'
        elif plan:
            op = 'plan'
        elif is_correction:
            op = 'correct'
        else:
            op = 'state'
        if t is not None:
            ts = 'explicit'
        elif past and op == 'state':
            ts = 'none'          # past without a clock stays uninterpreted in time
        else:
            t, ts = float(recorded_at), 'recorded'
        cands.append(Candidate(op, e, f, v, conds, t, ts, implicit, sent.strip()))
        topic = e
    if retract_all and not cands:
        cands.append(Candidate('retract', None, None, None, {}, None, 'none', True, text.strip()))
    return cands, topic, notes


# ---------------------------------------------------------------- questions
Q_HISTORY = re.compile(r'(历史|变过|改过|变化|哪些值|所有值|曾经是|\bhistory\b|\bchanges?\b|\bever\b|\ball values\b|\bover time\b)', re.I)
Q_PLAN = re.compile(r'(计划|打算|将要|预计|\bplan(ned|s)?\b|\bwill\b|\bscheduled\b|\bintended\b)', re.I)
Q_TAIL_ZH = re.compile(r'(现在|目前|当前|当时|那时)?(是|为)?(什么|多少|谁|哪|几|怎样|如何|啥)?.*$')


def _bigrams(s):
    s = s.lower()
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def _best(name, options):
    if not options:
        return None, 0.
    low = name.lower()
    for o in options:
        if o.lower() == low:
            return o, 1.
    scored = sorted(((len(_bigrams(name) & _bigrams(o)) / len(_bigrams(name) | _bigrams(o)), o) for o in options), reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None, scored[0][0]
    return scored[0][1], scored[0][0]


def bind_question(text, *, now, known, topic=None, day=1.0, clock=None):
    """Bind a question to (slot, mode, at).  ``known`` maps entity -> {facet -> [Slot]}.
    Returns dict with status bound / ambiguous / unbound."""
    t, tspan = find_time(text, now, day, clock)
    body = text.replace(tspan, ' ') if tspan else text
    conds, body = _conditions(body)
    mode = 'history' if Q_HISTORY.search(body) else 'plans' if Q_PLAN.search(body) else 'state'
    b = re.sub(r'[？?。!！]+\s*$', '', body.strip())
    b = re.sub(r'^\s*(请问|问一下|那么|那)\s*', '', b)
    b = re.sub(r'\bat\s*$', '', b).strip()
    e = f = None
    m = re.search(r'(?P<e>[^，,。]{1,30}?)的(?P<f>.+)', b)
    if m:
        e, f = m.group('e'), m.group('f')
        f = re.sub(r'(现在|目前|当前|当时|那时)?(的值)?(是|为)?(什么|多少|谁|哪[里个些]?|几|怎样|如何|啥)?(值)?$', '', f)
        f = re.sub(r'(变过哪些值|有什么计划|有哪些计划|的历史|历史|变过|改过|计划)$', '', f)
        f = re.sub(r'(有什么|有哪些|是否)$', '', f)
    else:
        m = re.search(r'(?:what|which|who)(?:\'s| is| was| are| were)?\s+(?:planned for\s+|the history of\s+)?(?:the\s+)?(?P<f>[\w\- ]{1,30}?) of (?:the\s+)?(?P<e>[\w\-\. ]{1,40})', b, re.I)
        if m:
            e, f = m.group('e'), m.group('f')
            rest = re.match(r"'s (?P<f2>[\w\- ]{1,30})", b[m.end('e'):])
            if rest:
                f = rest.group('f2')
        else:
            m = re.search(r"(?:what|which|who)(?:'s| is| was)?\s+(?:the\s+)?(?:history of|planned for|plan for|changes to)?\s*(?P<e>[\w\-\.]+(?: [\w\-\.]+){0,2})'s (?P<f>[\w\- ]{1,30})", b, re.I)
            if m:
                e, f = m.group('e'), m.group('f')
    if e is not None and "'s " in e:
        e, f = e.split("'s ", 1)
    if e is None:
        return {'status': 'unbound', 'mode': mode, 'at': now if t is None else t}
    e = _clean_entity(e)
    if PRONOUN_ZH.match(e + '的') or e.lower() in ('it', 'its', 'they', 'them') and topic:
        e = topic or e
    f = _clean_facet(f)
    f = re.sub(r'\s+(now|currently|then)$', '', f, flags=re.I)
    ent, es = _best(e, list(known))
    if ent is None or es < .34:
        return {'status': 'unbound', 'mode': mode, 'at': now if t is None else t, 'entity': e, 'facet': f}
    fac, fs = _best(f, list(known[ent]))
    if fac is None or fs < .34:
        return {'status': 'unbound', 'mode': mode, 'at': now if t is None else t, 'entity': ent, 'facet': f}
    slots = known[ent][fac]
    if conds:
        match = [s for s in slots if json.loads(s.conditions_json) == conds]
        slots = match or slots
    elif len(slots) > 1:
        plain = [s for s in slots if s.conditions_json == '{}']
        slots = plain or slots
    status = 'bound' if len(slots) == 1 else 'ambiguous'
    return {'status': status, 'mode': mode, 'at': float(now if t is None else t), 'slots': slots,
            'entity': ent, 'facet': fac, 'scores': [es, fs]}


# ---------------------------------------------------------------- memory
class NLMemory:
    """Applies interpreted operations to a ``Memory``.  Raw text is always kept."""

    def __init__(self, memory=None, *, day=1.0, clock=None):
        self.m = memory or Memory()
        self.day, self.clock = day, clock
        self.topic = None
        self.known = {}            # entity -> facet -> [Slot]
        self.tip = {}              # slot.key -> latest revision source id
        self.last_sources = []     # (sid, [slot keys]) in arrival order
        self.log = []

    def _register(self, slot):
        lst = self.known.setdefault(slot.entity, {}).setdefault(slot.facet, [])
        if slot not in lst:
            lst.append(slot)

    def _current(self, slot, at):
        r = self.m.query(Query((Need('v', slot),), at), 10 ** 9)
        a = r['answers']['v']
        return a['value'] if a['status'] == 'known' or r['status'] == 'complete' else None

    def ingest(self, sid, text, *, recorded_at):
        cands, self.topic, notes = interpret(text, recorded_at=recorded_at, topic=self.topic, day=self.day, clock=self.clock)
        reported = [x.data() for x in cands]
        applied = []
        groups = {}
        for c in cands:
            slot = getattr(c, '_slot', None) or (c.slot() if c.entity else None)
            if c.op == 'retract':
                target = None
                if self.last_sources:
                    target = self.last_sources[-1]
                if target:
                    self.m.append_raw(sid, text, recorded_at=recorded_at)
                    self.m.set_enabled(sid + '/retract', target[0], text, enabled=False, recorded_at=recorded_at)
                    for k in target[1]:
                        self.tip.pop(k, None)
                    applied.append({'op': 'retract', 'target': target[0]})
                    self.log.append({'sid': sid, 'applied': applied, 'notes': notes})
                    return {'sid': sid, 'candidates': reported, 'applied': applied, 'notes': notes}
                continue
            if c.op == 'correct' and slot.key not in self.tip:
                c.op = 'state'
            if c.op == 'negate':
                cur = self._current(slot, recorded_at) if slot.key in self.tip else None
                if cur is not None and cur == c.value:
                    c.op, c.value, c.effective_at = 'state', None, c.effective_at if c.effective_at is not None else float(recorded_at)
                else:
                    applied.append({'op': 'negate_unapplied', 'slot': slot.key})
                    continue
            if c.op == 'uncertain':
                applied.append({'op': 'uncertain_unapplied', 'slot': slot.key})
                self._register(slot)
                continue
            if c.op in ('state',) and c.effective_at is None:
                if c.time_source == 'none' and not getattr(c, '_slot', None):
                    applied.append({'op': 'untimed_unapplied', 'slot': slot.key})
                    continue
                c.effective_at = float(recorded_at)
            groups.setdefault((c.op, c.effective_at), []).append((slot, c))
        used = False
        touched = []
        for n, ((op, at), items) in enumerate(sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0))):
            gid = sid if not used else f'{sid}/{n}'
            if op == 'correct':
                by_target = {}
                for slot, c in items:
                    by_target.setdefault(self.tip[slot.key], {})[slot] = c.value
                for k, (target, repl) in enumerate(by_target.items()):
                    cid = gid if k == 0 else f'{gid}/{k}'
                    if not used:
                        self.m.append_raw(sid, text, recorded_at=recorded_at)
                        used = True
                        cid = sid + '/correct' + ('' if k == 0 else str(k))
                    self.m.correct(cid, target, text, replacements=repl, recorded_at=recorded_at)
                    for slot in repl:
                        self.tip[slot.key] = cid
                        touched.append(slot.key)
                    applied.append({'op': 'correct', 'sid': cid, 'target': target, 'slots': [s.key for s in repl]})
                continue
            assertions = {slot: c.value for slot, c in items}
            kind = 'plan' if op == 'plan' else 'state'
            self.m.append(gid, text, assertions=assertions, effective_at=at, recorded_at=recorded_at, kind=kind)
            used = True
            for slot in assertions:
                self._register(slot)
                if kind == 'state':
                    self.tip[slot.key] = gid
                touched.append(slot.key)
            applied.append({'op': kind, 'sid': gid, 'slots': [s.key for s in assertions], 'effective_at': at})
        if not used:
            self.m.append_raw(sid, text, recorded_at=recorded_at)
            applied.append({'op': 'raw', 'sid': sid})
        if touched:
            last = [a for a in applied if a.get('sid')][-1]['sid']
            self.last_sources.append((last, touched))
        self.log.append({'sid': sid, 'applied': applied, 'notes': notes})
        return {'sid': sid, 'candidates': reported, 'applied': applied, 'notes': notes}

    def ask(self, text, *, now, budget=4000, known_at=math.inf):
        b = bind_question(text, now=now, known=self.known, topic=self.topic, day=self.day, clock=self.clock)
        if b['status'] != 'bound':
            raw = self.m.search_raw(text, known_at=known_at, budget=budget)
            return {'binding': {k: v for k, v in b.items() if k != 'slots'}, 'status': 'evidence_only', 'raw': raw}
        slot = b['slots'][0]
        r = self.m.query(Query((Need('answer', slot, b['mode']),), b['at'], known_at, text=text), budget)
        return {'binding': {'status': 'bound', 'mode': b['mode'], 'at': b['at'], 'slot': slot.key}, 'status': r['status'],
                'answer': r['answers']['answer'], 'result': r}
