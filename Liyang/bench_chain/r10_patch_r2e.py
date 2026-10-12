# chain-r10 第 2 轮 dev 补丁 e（一次性脚本，应用后保留作记录）
p = '/workspace/work/ls/wt-chain/lingshu_ng/chain/shorthand.py'
s = open(p).read()


def R(a, b):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, 1)


R('''_ZH_VERB = (r"尘埃落定|定下了|定下|''', '''_ZH_VERB = (r"尘埃落定|裁定为|裁定|已定|定稿|初定|定下了|定下|''')
R('''_TRAIL = re.compile(r"(?:\\s+(?:now|again|done|ok|already|for\\s+now|asap|✅|✔)|''', '''_TRAIL = re.compile(r"(?:\\s+(?:now|again|done|ok|already|for\\s+now|asap|init|initial|new|✅|✔)|''')
R('''    t = re.sub(r"\\(\\s*(?:=|≈|~|i\\.e\\.?|aka)\\s*[^()]{1,16}\\)", " ", t)                 # 「7200（=2h）」等值注释''',
  '''    t = re.sub(r"\\(\\s*(?:=|≈|~|i\\.e\\.?|aka)\\s*[^()]{1,16}\\)", " ", t)                 # 「7200（=2h）」等值注释
    t = re.sub(r"(?<=[\\dsmhd])\\s*\\(\\s*\\d+(?:\\.\\d+)?\\s*(?:ms|s|sec|secs|seconds?|min|mins|minutes?|h|hr|hrs|hours?|d|days?|秒|分钟|小时|天)\\s*\\)", "", t)   # 「10800（3h）」''')
R('''        TAGS[0] += " " + inner''', '''        TAGS[0] += " " + inner
        if re.fullmatch(r"(?i)mv|move[ds]?|moving|relocated?|搬迁|迁移|移动|搬家|调动", inner or ""):
            MOVETAG[0] = True''')
R('''    TAGS[0] = ""
    for _ in range(3):''', '''    TAGS[0] = ""
    MOVETAG[0] = False
    for _ in range(3):''')
R('''TAGGED = [False]''', '''TAGGED = [False]
MOVETAG = [False]''')
R('''    s, a = _split_head(head)
    loc_explicit = bool(a and _LOC_ATTR.match(a))''', '''    s, a = _split_head(head)
    loc_explicit = bool(a and _LOC_ATTR.match(a)) or (a is None and MOVETAG[0])
    if verb == ":" and not (s and a and _HAS_CJK.search(s) and (_HAS_CJK.search(a) or _LOC_ATTR.match(a))):
        return None''')
R('''    if a is None and re.fullmatch(_ARROW, verb.strip()):''', '''    if a is None and not loc_explicit and re.fullmatch(_ARROW, verb.strip()):''')
open(p, 'w').write(s)
print("patched")
