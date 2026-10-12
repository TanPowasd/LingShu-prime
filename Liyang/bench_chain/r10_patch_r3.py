# chain-r10 第 3 轮 dev 补丁（H4/H5/H6 已暴露，作 dev）：IM/交接消息体的通用现象
p = '/workspace/work/ls/wt-chain/lingshu_ng/chain/shorthand.py'
s = open(p).read()


def R(a, b):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, 1)


# 1) 消息前缀：@提及、FYI/update/sync/cc、时间副词开头的寒暄分句
R('''    t = re.sub(r"\\s+", " ", t).strip()
    t = re.sub(r"(首次|初次|''', '''    t = re.sub(r"\\s+", " ", t).strip()
    for _ in range(3):
        t2 = _MSG_PREFIX.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    t = re.sub(r"(?<=[" + _CJK + r"A-Za-z0-9_)\\]])\\s*(?:这边|那边|这里|那里|方面|这头|那头)\\s*(?:的\\s*)?", " 的 ", t)   # 「S 这边 A」→「S 的 A」
    t = re.sub(r"(?<=[" + _CJK + r"])(?=(?:" + _GLUE_VERB + r"))", " ", t)          # 「依赖名改成了」：粘连的多字变更动词前补空格
    t = re.sub(r"(首次|初次|''')
R('''_CAUSE_HEAD = re.compile(''', '''_MSG_PREFIX = re.compile(r"(?i)^(?:@\\S+|(?:fyi|update|upd|sync|cc|ps|note|heads\\s*up|btw)(?![A-Za-z_])|"
                         r"(?:今早|今天|昨天|昨晚|早上|上午|中午|下午|晚上|今晚|刚刚|刚才|方才|会上|会后|补充|备注|提醒|同步)(?:同步|更新|说一下|说下|一下|下)?)"
                         r"\\s*[,:：，]?\\s*")
_GLUE_VERB = r"改成了|改成|改为|改到|换成了|换成|换为|定成了|定成|定为|设为|设成|挪到|迁到|搬到|切到|更新为|变成了|变成|变为|定下了|定下|拍板定成|拍板|不再有值|不再保留"
_CAUSE_HEAD = re.compile(''')
# 2) 句尾使役起因「R 引起的 / 推动的 / 带出来的 / 提的」
R('''_CAUSE_TAIL = re.compile(r"\\s*(?:导致|所致|引起|引发|触发|驱动|带来|促成|之故|而起|使然)\\s*$")''',
  '''_CAUSE_TAIL = re.compile(r"\\s*(?:导致|所致|引起|引发|触发|驱动|带来|带出来|促成|推动|造成|提出|提|拍|定|之故|而起|使然)(?:的)?(?:了)?\\s*$")''')
# 3) 等值括注加「即」
R('''    t = re.sub(r"\\(\\s*(?:=|≈|~|i\\.e\\.?|aka)\\s*[^()]{1,16}\\)", " ", t)''', '''    t = re.sub(r"\\(\\s*(?:=|≈|~|i\\.e\\.?|aka|即|约|也就是)\\s*[^()]{1,16}\\)", " ", t)''')
# 4) 「不再…」类撤销词不要求左边界
R('''    rm = next((m for m in _RETIRE.finditer(main) if not _HAS_CJK.match(m.group(0)) or m.start() == 0''',
  '''    rm = next((m for m in _RETIRE.finditer(main) if not _HAS_CJK.match(m.group(0)) or m.start() == 0 or m.group(0).startswith("不再")''')
open(p, 'w').write(s)
print("patched")
