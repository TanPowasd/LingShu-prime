# chain-r10 第 3 轮 dev 补丁 b：消息体前置规范化对严格/宽松/锚定三条路径都生效；非严格事件的取值统一过数值/键值归一
p = '/workspace/work/ls/wt-chain/lingshu_ng/chain/shorthand.py'
s = open(p).read()
s += '''

def pre_normalize(sent: str) -> str:
    """消息体前置规范化（供严格/宽松/锚定三条路径共用）：去句首 @提及、FYI/update、时间寒暄前缀；「S 这边 A」→「S 的 A」。
    只在句子带速记信号或消息前缀时改写，其余原样返回（中文散文不受影响）。"""
    t = (sent or "").strip()
    if not t or not (_PRE.search(t) and (_STRONG.search(t) or _MSG_PREFIX.match(t))):
        return t
    for _ in range(3):
        t2 = _MSG_PREFIX.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    t = re.sub(r"(?<=[" + _CJK + r"A-Za-z0-9_)\\]」』])\\s*(?:这边|那边|这里|那里|方面|这头|那头)\\s*(?:的\\s*)?", " 的 ", t)
    return t


def norm_event_value(v, attr):
    """非严格事件的取值归一：只做数值格式（千分位/单位按属性换算/键值对齐/等值括注），不认的写法原样返回。"""
    if not v:
        return v
    x = re.sub(r"(?<=\\d),(?=\\d{3}(?!\\d))", "", v.translate(_QUOTES)).strip()
    x = re.sub(r"\\s*\\(\\s*(?:=|≈|~|i\\.e\\.?|aka|即|约|也就是)\\s*[^()]{1,16}\\)", "", x).strip()
    y = norm_value(x, attr)
    return y if y != x else (v if x == v.strip() else x if _NUM_UNIT.match(x) or _KV.match(x) else v)
'''
open(p, 'w').write(s)

p = '/workspace/work/ls/wt-chain/lingshu_ng/chain/extract.py'
s = open(p).read()
old = '''    for i, sent in enumerate(split_sentences(text)):
        s = sent.strip()
        sm = s.translate(_QUOTES) if use_loose else s      # 匹配用去引号的句子；quote 仍存原句'''
new = '''    for i, sent in enumerate(split_sentences(text)):
        s = sent.strip()
        sn = _sh.pre_normalize(s) if (use_loose and _sh.SHORT) else s   # v11（chain-r10）：消息体前置规范化，quote 仍存原句
        sm = sn.translate(_QUOTES) if use_loose else s      # 匹配用去引号的句子；quote 仍存原句'''
assert old in s
s = s.replace(old, new, 1)
old = '''                lz = _sh.extract_shorthand(s) if strong else None      # 强速记信号：速记规范化优先
                if lz is None and not strong:
                    lz = extract_loose(s)'''
new = '''                lz = _sh.extract_shorthand(s) if strong else None      # 强速记信号：速记规范化优先
                if lz is None and not strong:
                    lz = extract_loose(sn)'''
assert old in s
s = s.replace(old, new, 1)
old = '''                if lz is None and strong:
                    lz = extract_loose(s)'''
new = '''                if lz is None and strong:
                    lz = extract_loose(sn)
                    if lz is not None and _sh.SHORT:
                        lz["value"] = _sh.norm_event_value(lz["value"], lz["attr"])
                        lz["alt"] = _sh.norm_event_value(lz["alt"], lz["attr"])'''
assert old in s
s = s.replace(old, new, 1)
open(p, 'w').write(s)

p = '/workspace/work/ls/wt-chain/lingshu_ng/chain/ledger.py'
s = open(p).read()
old = '''                a = _anc.extract_anchored(sent, ns, self.lex, self.group)
                if a is None:
                    continue'''
new = '''                a = _anc.extract_anchored(_sh.pre_normalize(sent) if _sh.SHORT else sent, ns, self.lex, self.group)
                if a is None:
                    continue'''
assert old in s
s = s.replace(old, new, 1)
old = '''                    continue                                   # v10：速记信号句上的锚定结果先自检（残缺记号、标签词、起因当值、点分名前缀）'''
new = '''                    continue                                   # v10：速记信号句上的锚定结果先自检（残缺记号、标签词、起因当值、点分名前缀）
                if _sh.SHORT and _sh.strong_cue(sent):
                    a["value"] = _sh.norm_event_value(a["value"], a["attr"]); a["alt"] = _sh.norm_event_value(a["alt"], a["attr"])'''
assert old in s
s = s.replace(old, new, 1)
open(p, 'w').write(s)

p = '/workspace/work/ls/wt-chain/lingshu_ng/chain/shorthand.py'
s = open(p).read()
old = '''        if _TAG_WORDS.match(x) or _UCUE.fullmatch(x)'''
new = '''        if _TAG_WORDS.match(x) or _MSG_PREFIX.fullmatch(x) or _UCUE.fullmatch(x)'''
assert old in s
s = s.replace(old, new, 1)
open(p, 'w').write(s)
print("patched")
