# chain-r10 第 3 轮 dev 补丁 c：消息前缀算语境；「S A <英文记号>」无动词写法；动词后取值落在下一分句
p = '/workspace/work/ls/wt-chain/lingshu_ng/chain/shorthand.py'
s = open(p).read()


def R(a, b):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, 1)


R('''    for _ in range(3):
        t2 = _MSG_PREFIX.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    t = re.sub(r"(?<=[" + _CJK + r"A-Za-z0-9_)\\]])\\s*(?:这边''', '''    for _ in range(3):
        t2 = _MSG_PREFIX.sub("", t).strip()
        if t2 == t:
            break
        t = t2
        TAGGED[0] = True                                     # FYI/update/@oncall 等消息前缀：状态同步语境，等同标签
    t = re.sub(r"(?<=[" + _CJK + r"A-Za-z0-9_)\\]])\\s*(?:这边''')
R('''_ZH_VERB = (r"尘埃落定|裁定为|裁定|已定|定稿|初定|''', '''_ZH_VERB = (r"尘埃落定|裁定为|裁定|已定|定稿|初定|先定|拍板为|''')
R('''        mm = list(re.finditer(r":", main)) or list(re.finditer(r"(?<![A-Za-z0-9_])=", main))
        if not mm:
            return None''', '''        mm = list(re.finditer(r":", main)) or list(re.finditer(r"(?<![A-Za-z0-9_])=", main))
        if not mm:
            m3 = re.match(r"^(?P<h>.+?)\\s+(?P<v>[A-Za-z_][A-Za-z0-9_]*=\\d+|[A-Za-z_][A-Za-z0-9_]*\\([^()]*\\)|[A-Za-z_][A-Za-z0-9_]*|\\d+(?:\\s*[A-Za-z]+)?)$", main)
            if not (m3 and TAGGED[0] and len(clauses) <= 2):
                return None                                  # 「FYI S A <英文记号>」：消息/标签语境下，属性后直接跟取值记号
            return _finish(op, m3.group("h"), m3.group("v"), ":", reason, first, src, whole)''')
R('''    head, tail = main[:vm.start()], main[vm.end():]
    if op == "resolve":''', '''    head, tail = main[:vm.start()], main[vm.end():]
    if not _CONN.sub("", tail, count=1).strip(" :=") and len(clauses) > 1:   # 「A 改了，= V」「A 改了，现在 = V」：取值落在下一分句
        nxt = re.sub(r"^(?:现在|目前|如今|now)?\\s*[:=]?\\s*", "", clauses[1], flags=re.I)
        if nxt and not _CAUSE_HEAD.match(clauses[1]):
            tail = " " + nxt
    if op == "resolve":''')
open(p, 'w').write(s)
print("patched")
